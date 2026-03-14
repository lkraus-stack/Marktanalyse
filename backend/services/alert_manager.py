from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, Mapping, Optional, Sequence

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import get_settings
from database import AsyncSessionLocal
from models import (
    AggregatedSentiment,
    AggregationSource,
    AggregationTimeframe,
    Alert,
    AlertHistory,
    AlertType,
    DeliveryMethod,
    Asset,
    PriceData,
    PriceTimeframe,
    TradingSignal,
)
from services.email_service import EmailService
from services.price_stream import price_pubsub
from services.telegram_service import TelegramService

logger = logging.getLogger("market_intelligence.services.alert_manager")


@dataclass
class AlertDecision:
    """Intermediate evaluation result for one alert."""

    triggered: bool
    message: str
    signal_id: Optional[int] = None
    symbol: Optional[str] = None


class AlertManager:
    """Evaluates active alerts and dispatches alert deliveries."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        email_service: Optional[EmailService] = None,
        telegram_service: Optional[TelegramService] = None,
    ) -> None:
        settings = get_settings()
        self._session_factory = session_factory
        self._cooldown = timedelta(minutes=max(1, settings.alert_cooldown_minutes))
        self._email_service = email_service or EmailService()
        self._telegram_service = telegram_service or TelegramService()
        self._custom_evaluator = CustomExpressionEvaluator()

    async def evaluate_alerts(self) -> Dict[str, int]:
        """Evaluate all enabled alerts and write history entries."""
        now = datetime.now(timezone.utc)
        result = {"evaluated": 0, "triggered": 0, "delivered": 0}
        async with self._session_factory() as session:
            alerts = await self._fetch_enabled_alerts(session)
            signal_cache: Dict[int, Optional[TradingSignal]] = {}
            price_cache: Dict[int, Optional[PriceData]] = {}
            sentiment_cache: Dict[int, Optional[AggregatedSentiment]] = {}
            shift_cache: Dict[tuple[int, int], Optional[float]] = {}
            symbol_cache: Dict[int, Optional[str]] = {}

            for alert in alerts:
                result["evaluated"] += 1
                if not self._cooldown_elapsed(alert, now):
                    continue
                decision = await self._evaluate_one(
                    session=session,
                    alert=alert,
                    signal_cache=signal_cache,
                    price_cache=price_cache,
                    sentiment_cache=sentiment_cache,
                    shift_cache=shift_cache,
                    symbol_cache=symbol_cache,
                )
                if not decision.triggered:
                    continue

                delivered = await self._deliver_alert(alert=alert, message=decision.message)
                await self._broadcast_alert(
                    alert=alert,
                    message=decision.message,
                    signal_id=decision.signal_id,
                    delivered=delivered,
                    symbol=decision.symbol,
                )

                session.add(
                    AlertHistory(
                        alert_id=alert.id,
                        signal_id=decision.signal_id,
                        message=decision.message,
                        delivered=delivered,
                    )
                )
                alert.last_triggered = now
                result["triggered"] += 1
                if delivered:
                    result["delivered"] += 1
            await session.commit()
        return result

    async def shutdown(self) -> None:
        """Release managed resources."""
        await self._telegram_service.close()

    async def _fetch_enabled_alerts(self, session: AsyncSession) -> Sequence[Alert]:
        query = select(Alert).where(Alert.is_enabled.is_(True)).order_by(Alert.created_at.asc())
        return list((await session.execute(query)).scalars().all())

    def _cooldown_elapsed(self, alert: Alert, now: datetime) -> bool:
        if alert.last_triggered is None:
            return True
        return now - alert.last_triggered >= self._cooldown

    async def _evaluate_one(
        self,
        session: AsyncSession,
        alert: Alert,
        signal_cache: Dict[int, Optional[TradingSignal]],
        price_cache: Dict[int, Optional[PriceData]],
        sentiment_cache: Dict[int, Optional[AggregatedSentiment]],
        shift_cache: Dict[tuple[int, int], Optional[float]],
        symbol_cache: Dict[int, Optional[str]],
    ) -> AlertDecision:
        if alert.alert_type == AlertType.SIGNAL_THRESHOLD:
            return await self._evaluate_signal_threshold(session, alert, signal_cache, symbol_cache)
        if alert.alert_type == AlertType.PRICE_TARGET:
            return await self._evaluate_price_target(session, alert, price_cache, symbol_cache)
        if alert.alert_type == AlertType.SENTIMENT_SHIFT:
            return await self._evaluate_sentiment_shift(session, alert, sentiment_cache, shift_cache, symbol_cache)
        if alert.alert_type == AlertType.CUSTOM:
            return await self._evaluate_custom(
                session,
                alert,
                signal_cache,
                price_cache,
                sentiment_cache,
                shift_cache,
                symbol_cache,
            )
        return AlertDecision(triggered=False, message="Unbekannter Alert-Typ.")

    async def _evaluate_signal_threshold(
        self,
        session: AsyncSession,
        alert: Alert,
        signal_cache: Dict[int, Optional[TradingSignal]],
        symbol_cache: Dict[int, Optional[str]],
    ) -> AlertDecision:
        if alert.asset_id is None:
            return AlertDecision(False, "Signal-Alert ohne Asset.")
        signal = await self._get_latest_signal(session, alert.asset_id, signal_cache)
        if signal is None:
            return AlertDecision(False, "Kein Signal verfuegbar.")

        condition = alert.condition_json or {}
        threshold = float(condition.get("threshold", 70.0))
        direction = str(condition.get("direction", "above")).strip().lower()
        strength = float(signal.strength)
        triggered = strength >= threshold if direction != "below" else strength <= threshold
        if not triggered:
            return AlertDecision(False, "Signal-Schwelle nicht erreicht.")

        symbol = await self._get_asset_symbol(session, alert.asset_id, symbol_cache)
        msg = "Signal {0} ({1}) bei Staerke {2:.1f} hat Schwelle {3:.1f} ({4}) erreicht.".format(
            symbol or "N/A",
            signal.signal_type.value.upper(),
            strength,
            threshold,
            direction,
        )
        return AlertDecision(True, msg, signal_id=signal.id, symbol=symbol)

    async def _evaluate_price_target(
        self,
        session: AsyncSession,
        alert: Alert,
        price_cache: Dict[int, Optional[PriceData]],
        symbol_cache: Dict[int, Optional[str]],
    ) -> AlertDecision:
        if alert.asset_id is None:
            return AlertDecision(False, "Price-Alert ohne Asset.")
        point = await self._get_latest_price(session, alert.asset_id, price_cache)
        if point is None:
            return AlertDecision(False, "Kein Preis verfuegbar.")

        condition = alert.condition_json or {}
        target = self._to_float(condition.get("target_price"))
        if target is None:
            return AlertDecision(False, "target_price fehlt.")
        direction = str(condition.get("direction", "above")).strip().lower()
        current = float(point.close)
        triggered = current >= target if direction != "below" else current <= target
        if not triggered:
            return AlertDecision(False, "Preisziel nicht erreicht.")

        symbol = await self._get_asset_symbol(session, alert.asset_id, symbol_cache)
        msg = "Preisziel fuer Asset {0} erreicht: {1:.4f} ({2} {3:.4f}).".format(
            symbol or str(alert.asset_id),
            current,
            direction,
            target,
        )
        return AlertDecision(True, msg, symbol=symbol)

    async def _evaluate_sentiment_shift(
        self,
        session: AsyncSession,
        alert: Alert,
        sentiment_cache: Dict[int, Optional[AggregatedSentiment]],
        shift_cache: Dict[tuple[int, int], Optional[float]],
        symbol_cache: Dict[int, Optional[str]],
    ) -> AlertDecision:
        if alert.asset_id is None:
            return AlertDecision(False, "Sentiment-Alert ohne Asset.")

        condition = alert.condition_json or {}
        min_shift = abs(float(condition.get("shift", 0.2)))
        hours = max(1, min(72, int(condition.get("hours", 4))))
        mode = str(condition.get("direction", "abs")).strip().lower()
        shift = await self._get_sentiment_shift(session, alert.asset_id, hours, sentiment_cache, shift_cache)
        if shift is None:
            return AlertDecision(False, "Nicht genug Sentiment-Historie.")

        if mode == "up":
            triggered = shift >= min_shift
        elif mode == "down":
            triggered = shift <= -min_shift
        else:
            triggered = abs(shift) >= min_shift
        if not triggered:
            return AlertDecision(False, "Sentiment-Verschiebung zu klein.")

        symbol = await self._get_asset_symbol(session, alert.asset_id, symbol_cache)
        msg = "Sentiment-Shift fuer Asset {0}: {1:+.3f} in {2}h (Schwelle {3:.3f}, Modus {4}).".format(
            symbol or str(alert.asset_id),
            shift,
            hours,
            min_shift,
            mode,
        )
        return AlertDecision(True, msg, symbol=symbol)

    async def _evaluate_custom(
        self,
        session: AsyncSession,
        alert: Alert,
        signal_cache: Dict[int, Optional[TradingSignal]],
        price_cache: Dict[int, Optional[PriceData]],
        sentiment_cache: Dict[int, Optional[AggregatedSentiment]],
        shift_cache: Dict[tuple[int, int], Optional[float]],
        symbol_cache: Dict[int, Optional[str]],
    ) -> AlertDecision:
        context = await self._build_custom_context(
            session=session,
            alert=alert,
            signal_cache=signal_cache,
            price_cache=price_cache,
            sentiment_cache=sentiment_cache,
            shift_cache=shift_cache,
        )
        expression = alert.condition_json.get("expression", alert.condition_json)
        if not isinstance(expression, Mapping):
            return AlertDecision(False, "custom expression ist ungueltig.")
        triggered = self._custom_evaluator.evaluate(expression, context)
        if not triggered:
            return AlertDecision(False, "Custom expression nicht erfuellt.")

        symbol = await self._get_asset_symbol(session, alert.asset_id, symbol_cache) if alert.asset_id else None
        msg = "Custom Alert ausgelöst fuer Asset {0}. Kontext: signal_strength={1}, price={2}, sentiment={3}.".format(
            symbol or str(alert.asset_id),
            self._safe_str(context.get("signal_strength")),
            self._safe_str(context.get("price")),
            self._safe_str(context.get("sentiment_score")),
        )
        signal_id = context.get("signal_id")
        return AlertDecision(
            True,
            msg,
            signal_id=signal_id if isinstance(signal_id, int) else None,
            symbol=symbol,
        )

    async def _build_custom_context(
        self,
        session: AsyncSession,
        alert: Alert,
        signal_cache: Dict[int, Optional[TradingSignal]],
        price_cache: Dict[int, Optional[PriceData]],
        sentiment_cache: Dict[int, Optional[AggregatedSentiment]],
        shift_cache: Dict[tuple[int, int], Optional[float]],
    ) -> Dict[str, Any]:
        context: Dict[str, Any] = {}
        if alert.asset_id is None:
            return context

        signal = await self._get_latest_signal(session, alert.asset_id, signal_cache)
        price = await self._get_latest_price(session, alert.asset_id, price_cache)
        sentiment = await self._get_latest_sentiment(session, alert.asset_id, sentiment_cache)
        shift_4h = await self._get_sentiment_shift(session, alert.asset_id, 4, sentiment_cache, shift_cache)

        context["signal_id"] = signal.id if signal else None
        context["signal_strength"] = float(signal.strength) if signal else None
        context["signal_type"] = signal.signal_type.value if signal else None
        context["signal_composite"] = float(signal.composite_score) if signal else None
        context["price"] = float(price.close) if price else None
        context["sentiment_score"] = float(sentiment.weighted_score) if sentiment else None
        context["sentiment_mentions_1h"] = int(sentiment.total_mentions) if sentiment else None
        context["sentiment_shift_4h"] = shift_4h
        return context

    async def _deliver_alert(self, alert: Alert, message: str) -> bool:
        subject = "Alert: {0}".format(alert.alert_type.value)
        title = "Alert {0}".format(alert.alert_type.value.upper())
        to_email = self._string_or_none(alert.condition_json.get("email_to"))
        telegram_chat = self._string_or_none(alert.condition_json.get("telegram_chat_id"))

        if alert.delivery_method == DeliveryMethod.WEBSOCKET:
            return True
        if alert.delivery_method == DeliveryMethod.EMAIL:
            return await self._email_service.send_alert_email(
                subject=subject,
                alert_title=title,
                message=message,
                to_email=to_email,
            )
        if alert.delivery_method == DeliveryMethod.TELEGRAM:
            telegram_message = "*{0}*\n{1}".format(title, self._escape_markdown(message))
            return await self._telegram_service.send_alert_message(
                message=telegram_message,
                chat_id=telegram_chat,
            )
        return False

    async def _broadcast_alert(
        self,
        alert: Alert,
        message: str,
        signal_id: Optional[int],
        delivered: bool,
        symbol: Optional[str],
    ) -> None:
        await price_pubsub.publish(
            {
                "type": "alert_triggered",
                "channel": "alerts",
                "alert_id": alert.id,
                "alert_type": alert.alert_type.value,
                "delivery_method": alert.delivery_method.value,
                "asset_id": alert.asset_id,
                "symbol": symbol,
                "signal_id": signal_id,
                "message": message,
                "delivered": delivered,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    async def _get_asset_symbol(
        self,
        session: AsyncSession,
        asset_id: int,
        cache: Dict[int, Optional[str]],
    ) -> Optional[str]:
        if asset_id in cache:
            return cache[asset_id]
        query = select(Asset.symbol).where(Asset.id == asset_id)
        symbol = (await session.execute(query)).scalar_one_or_none()
        cache[asset_id] = symbol
        return symbol

    async def _get_latest_signal(
        self,
        session: AsyncSession,
        asset_id: int,
        cache: Dict[int, Optional[TradingSignal]],
    ) -> Optional[TradingSignal]:
        if asset_id in cache:
            return cache[asset_id]
        now = datetime.now(timezone.utc)
        query = (
            select(TradingSignal)
            .where(
                TradingSignal.asset_id == asset_id,
                TradingSignal.is_active.is_(True),
                or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
            )
            .order_by(TradingSignal.created_at.desc())
            .limit(1)
        )
        signal = (await session.execute(query)).scalar_one_or_none()
        cache[asset_id] = signal
        return signal

    async def _get_latest_price(
        self,
        session: AsyncSession,
        asset_id: int,
        cache: Dict[int, Optional[PriceData]],
    ) -> Optional[PriceData]:
        if asset_id in cache:
            return cache[asset_id]
        query = (
            select(PriceData)
            .where(PriceData.asset_id == asset_id, PriceData.timeframe == PriceTimeframe.M1)
            .order_by(PriceData.timestamp.desc())
            .limit(1)
        )
        point = (await session.execute(query)).scalar_one_or_none()
        cache[asset_id] = point
        return point

    async def _get_latest_sentiment(
        self,
        session: AsyncSession,
        asset_id: int,
        cache: Dict[int, Optional[AggregatedSentiment]],
    ) -> Optional[AggregatedSentiment]:
        if asset_id in cache:
            return cache[asset_id]
        query = (
            select(AggregatedSentiment)
            .where(
                AggregatedSentiment.asset_id == asset_id,
                AggregatedSentiment.timeframe == AggregationTimeframe.H1,
                AggregatedSentiment.source == AggregationSource.ALL,
            )
            .order_by(AggregatedSentiment.period_end.desc())
            .limit(1)
        )
        sentiment = (await session.execute(query)).scalar_one_or_none()
        cache[asset_id] = sentiment
        return sentiment

    async def _get_sentiment_shift(
        self,
        session: AsyncSession,
        asset_id: int,
        hours: int,
        sentiment_cache: Dict[int, Optional[AggregatedSentiment]],
        shift_cache: Dict[tuple[int, int], Optional[float]],
    ) -> Optional[float]:
        key = (asset_id, hours)
        if key in shift_cache:
            return shift_cache[key]

        latest = await self._get_latest_sentiment(session, asset_id, sentiment_cache)
        if latest is None:
            shift_cache[key] = None
            return None

        pivot = latest.period_end - timedelta(hours=hours)
        query = (
            select(AggregatedSentiment)
            .where(
                AggregatedSentiment.asset_id == asset_id,
                AggregatedSentiment.timeframe == AggregationTimeframe.H1,
                AggregatedSentiment.source == AggregationSource.ALL,
                AggregatedSentiment.period_end <= pivot,
            )
            .order_by(AggregatedSentiment.period_end.desc())
            .limit(1)
        )
        baseline = (await session.execute(query)).scalar_one_or_none()
        if baseline is None:
            shift_cache[key] = None
            return None

        shift = float(latest.weighted_score) - float(baseline.weighted_score)
        shift_cache[key] = shift
        return shift

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, Decimal):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _string_or_none(self, value: Any) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _safe_str(self, value: Any) -> str:
        if value is None:
            return "null"
        return str(value)

    def _escape_markdown(self, value: str) -> str:
        escaped = value.replace("\\", "\\\\")
        for token in ("_", "*", "[", "]", "(", ")", "~", "`", ">", "#", "+", "-", "=", "|", "{", "}", ".", "!"):
            escaped = escaped.replace(token, "\\" + token)
        return escaped


class CustomExpressionEvaluator:
    """Safe evaluator for custom alert expressions."""

    _OPERATOR_MAP = {
        ">": lambda left, right: left > right,
        ">=": lambda left, right: left >= right,
        "<": lambda left, right: left < right,
        "<=": lambda left, right: left <= right,
        "==": lambda left, right: left == right,
        "!=": lambda left, right: left != right,
        "in": lambda left, right: left in right if isinstance(right, Sequence) else False,
        "not_in": lambda left, right: left not in right if isinstance(right, Sequence) else False,
    }

    _ALLOWED_FIELDS = {
        "signal_strength",
        "signal_type",
        "signal_composite",
        "price",
        "sentiment_score",
        "sentiment_mentions_1h",
        "sentiment_shift_4h",
    }

    def evaluate(self, expression: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
        """Evaluate expression tree against a constrained context."""
        try:
            return self._evaluate_node(expression, context)
        except Exception:
            return False

    def _evaluate_node(self, node: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
        op = str(node.get("op", "")).strip().lower()
        if op in {"and", "or"}:
            conditions = node.get("conditions", [])
            if not isinstance(conditions, list) or not conditions:
                return False
            results = [self._evaluate_node(item, context) for item in conditions if isinstance(item, Mapping)]
            if not results:
                return False
            return all(results) if op == "and" else any(results)

        if op == "not":
            condition = node.get("condition")
            if not isinstance(condition, Mapping):
                return False
            return not self._evaluate_node(condition, context)

        field = str(node.get("field", "")).strip()
        if field not in self._ALLOWED_FIELDS:
            return False

        operator = str(node.get("operator", "==")).strip().lower()
        value = node.get("value")
        left = context.get(field)
        if left is None:
            return False

        if operator == "between":
            if not isinstance(value, Sequence) or len(value) != 2:
                return False
            return self._compare_between(left, value[0], value[1])

        func = self._OPERATOR_MAP.get(operator)
        if func is None:
            return False
        return bool(func(left, value))

    def _compare_between(self, left: Any, lower: Any, upper: Any) -> bool:
        try:
            left_value = float(left)
            return float(lower) <= left_value <= float(upper)
        except (TypeError, ValueError):
            return False
