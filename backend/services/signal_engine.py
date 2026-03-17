from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional

import pandas as pd
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import get_settings
from database import AsyncSessionLocal
from models import (
    AggregatedSentiment,
    AggregationSource,
    AggregationTimeframe,
    Asset,
    PriceData,
    PriceTimeframe,
    SignalType,
    TradingSignal,
)
from services.technical_indicators import TechnicalAnalyzer

logger = logging.getLogger("market_intelligence.services.signal_engine")

REQUIRED_CANDLES = 50


class SignalEngine:
    """Generates trade signals from sentiment, price and momentum features."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        technical_analyzer: Optional[TechnicalAnalyzer] = None,
        weights: Optional[Mapping[str, float]] = None,
    ) -> None:
        self._session_factory = session_factory
        self._technical = technical_analyzer or TechnicalAnalyzer()
        if weights is None:
            settings = get_settings()
            weights = {
                "sentiment": settings.signal_weight_sentiment,
                "technical": settings.signal_weight_technical,
                "volume": settings.signal_weight_volume,
                "momentum": settings.signal_weight_momentum,
            }
        self._weights = self._validate_weights(weights)

    async def calculate_signal(
        self,
        asset_id: int,
        timeframe: str = "1h",
        execution_id: Optional[str] = None,
    ) -> Optional[TradingSignal]:
        """Calculate and persist one signal for a given asset."""
        timeframe_enum = self._parse_signal_timeframe(timeframe)
        async with self._session_factory() as session:
            asset = await session.get(Asset, asset_id)
            if asset is None or not asset.is_active:
                return None

            analysis_frame = await self._load_analysis_frame(session, asset_id, timeframe_enum, REQUIRED_CANDLES)
            if analysis_frame.empty:
                logger.warning(
                    "Skipping signal generation: no price data.",
                    extra={"event": "signal_skip_no_price", "asset_id": str(asset_id)},
                )
                return None

            market_frame = await self._load_market_frame(session, asset_id, days=8)
            sentiment_score, sentiment_meta = await self._sentiment_component(session, asset_id, timeframe_enum)
            technical_score, technical_meta = self._technical_component(analysis_frame)
            volume_score, volume_meta = self._volume_component(market_frame)
            momentum_score, momentum_meta = self._momentum_component(market_frame)

            coverage = min(1.0, len(analysis_frame) / float(REQUIRED_CANDLES))
            if coverage < 1.0:
                technical_score *= coverage
                volume_score *= coverage
                momentum_score *= coverage

            availability = {
                "sentiment": sentiment_meta["available"],
                "technical": technical_meta["available"],
                "volume": volume_meta["available"],
                "momentum": momentum_meta["available"],
            }
            effective_weights = self._normalize_weights(availability)
            composite = self._compute_composite(
                sentiment=sentiment_score,
                technical=technical_score,
                volume=volume_score,
                momentum=momentum_score,
                weights=effective_weights,
            )
            buy_threshold, sell_threshold, threshold_meta = self._adaptive_thresholds(market_frame)
            signal_type = self._signal_type_from_score(
                composite=composite,
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
            )
            strength = min(100.0, abs(composite))
            expires_at = self._expires_at(timeframe_enum)
            price_at_signal = Decimal(str(float(analysis_frame["close"].iloc[-1])))
            reasoning = self._build_reasoning(
                composite=composite,
                signal_type=signal_type,
                buy_threshold=buy_threshold,
                sell_threshold=sell_threshold,
                sentiment_score=sentiment_score,
                technical_score=technical_score,
                volume_score=volume_score,
                momentum_score=momentum_score,
                sentiment_meta=sentiment_meta,
                technical_meta=technical_meta,
                volume_meta=volume_meta,
                momentum_meta=momentum_meta,
                threshold_meta=threshold_meta,
                weights=effective_weights,
                coverage=coverage,
            )

            strategy_id = "composite_signal_{0}".format(timeframe_enum.value)
            await self._deactivate_previous_active_signals(session, asset_id=asset_id, strategy_id=strategy_id)

            signal = TradingSignal(
                asset_id=asset_id,
                signal_type=signal_type,
                strength=float(strength),
                composite_score=float(composite),
                price_at_signal=price_at_signal,
                sentiment_component=float(sentiment_score),
                technical_component=float(technical_score),
                volume_component=float(volume_score),
                momentum_component=float(momentum_score),
                reasoning=reasoning,
                execution_id=execution_id,
                strategy_id=strategy_id,
                is_active=True,
                expires_at=expires_at,
            )
            session.add(signal)
            await session.commit()
            await session.refresh(signal)
            return signal

    async def generate_all_signals(self, timeframe: str = "1h") -> int:
        """Generate fresh signals for all active assets."""
        execution_id = datetime.now(timezone.utc).strftime("sig-%Y%m%d%H%M%S")
        async with self._session_factory() as session:
            query = select(Asset.id).where(Asset.is_active.is_(True)).order_by(Asset.symbol.asc())
            asset_ids = [item for item in (await session.execute(query)).scalars().all()]

        generated = 0
        for asset_id in asset_ids:
            try:
                signal = await self.calculate_signal(asset_id=asset_id, timeframe=timeframe, execution_id=execution_id)
                if signal is not None:
                    generated += 1
            except Exception:
                logger.exception(
                    "Signal generation failed for asset.",
                    extra={"event": "signal_asset_failed", "asset_id": str(asset_id)},
                )
        return generated

    async def get_ranked_signals(self, limit: int = 20) -> List[TradingSignal]:
        """Return active signals sorted by absolute strength."""
        safe_limit = max(1, min(limit, 200))
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            query = (
                select(TradingSignal)
                .where(
                    TradingSignal.is_active.is_(True),
                    or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
                )
                .order_by(TradingSignal.strength.desc(), TradingSignal.created_at.desc())
                .limit(safe_limit)
            )
            return list((await session.execute(query)).scalars().all())

    async def expire_signals(self) -> int:
        """Deactivate expired signals."""
        now = datetime.now(timezone.utc)
        async with self._session_factory() as session:
            result = await session.execute(
                update(TradingSignal)
                .where(
                    TradingSignal.is_active.is_(True),
                    TradingSignal.expires_at.is_not(None),
                    TradingSignal.expires_at <= now,
                )
                .values(is_active=False)
            )
            await session.commit()
            return max(0, int(result.rowcount or 0))

    async def _load_analysis_frame(
        self,
        session: AsyncSession,
        asset_id: int,
        timeframe: AggregationTimeframe,
        candles: int,
    ) -> pd.DataFrame:
        native_timeframe = PriceTimeframe.H1 if timeframe == AggregationTimeframe.H1 else PriceTimeframe.D1
        query = (
            select(PriceData)
            .where(PriceData.asset_id == asset_id, PriceData.timeframe == native_timeframe)
            .order_by(PriceData.timestamp.desc())
            .limit(candles * 2)
        )
        native_rows = list((await session.execute(query)).scalars().all())
        native_frame = self._rows_to_frame(reversed(native_rows))
        if len(native_frame) >= candles:
            return native_frame.tail(candles)

        fallback_limit = 4000 if timeframe == AggregationTimeframe.H1 else 20000
        fallback_query = (
            select(PriceData)
            .where(PriceData.asset_id == asset_id, PriceData.timeframe == PriceTimeframe.M1)
            .order_by(PriceData.timestamp.desc())
            .limit(fallback_limit)
        )
        fallback_rows = list((await session.execute(fallback_query)).scalars().all())
        fallback_frame = self._rows_to_frame(reversed(fallback_rows))
        if fallback_frame.empty:
            return native_frame

        rule = "1h" if timeframe == AggregationTimeframe.H1 else "1d"
        return self._resample_ohlcv(fallback_frame, rule=rule).tail(candles)

    async def _load_market_frame(self, session: AsyncSession, asset_id: int, days: int) -> pd.DataFrame:
        limit = max(1440 * days, 500)
        query = (
            select(PriceData)
            .where(PriceData.asset_id == asset_id, PriceData.timeframe == PriceTimeframe.M1)
            .order_by(PriceData.timestamp.desc())
            .limit(limit)
        )
        rows = list((await session.execute(query)).scalars().all())
        return self._rows_to_frame(reversed(rows))

    async def _sentiment_component(
        self,
        session: AsyncSession,
        asset_id: int,
        timeframe: AggregationTimeframe,
    ) -> tuple[float, Dict[str, Any]]:
        query = (
            select(AggregatedSentiment)
            .where(
                AggregatedSentiment.asset_id == asset_id,
                AggregatedSentiment.timeframe == timeframe,
                AggregatedSentiment.source == AggregationSource.ALL,
            )
            .order_by(AggregatedSentiment.period_end.desc())
            .limit(1)
        )
        aggregate = (await session.execute(query)).scalar_one_or_none()
        if aggregate is None:
            return 0.0, {"available": False, "mentions": 0}
        score = max(-100.0, min(100.0, float(aggregate.weighted_score) * 100.0))
        return score, {"available": True, "mentions": int(aggregate.total_mentions)}

    def _technical_component(self, frame: pd.DataFrame) -> tuple[float, Dict[str, Any]]:
        if len(frame) < 20:
            return 0.0, {"available": False, "indicators": {}}
        indicators = self._technical.calculate_indicators(frame)
        score = self._technical.get_technical_score(indicators)
        return float(score), {"available": True, "indicators": indicators}

    def _volume_component(self, frame: pd.DataFrame) -> tuple[float, Dict[str, Any]]:
        if frame.empty or len(frame) < 200:
            return 0.0, {"available": False}
        latest_ts = frame.index.max()
        cutoff_24h = latest_ts - pd.Timedelta(hours=24)
        recent = frame[frame.index > cutoff_24h]
        if recent.empty:
            return 0.0, {"available": False}

        daily_volume = frame["volume"].resample("1d").sum().dropna()
        if len(daily_volume) < 3:
            return 0.0, {"available": False}

        volume_24h = float(recent["volume"].sum())
        avg_7d = float(daily_volume.tail(7).mean())
        if avg_7d <= 0:
            return 0.0, {"available": False}

        prev_prices = frame[frame.index <= cutoff_24h]["close"]
        if prev_prices.empty:
            return 0.0, {"available": False}
        latest_close = float(frame["close"].iloc[-1])
        previous_close = float(prev_prices.iloc[-1])
        price_change_24h = self._percent_change(previous_close, latest_close)

        relative = (volume_24h - avg_7d) / avg_7d
        magnitude = min(100.0, abs(relative) * 100.0)
        if relative >= 0:
            score = magnitude if price_change_24h >= 0 else -magnitude
        else:
            score = -0.5 * magnitude if price_change_24h >= 0 else 0.5 * magnitude
        meta = {
            "available": True,
            "volume_24h": volume_24h,
            "avg_7d": avg_7d,
            "ratio": (volume_24h / avg_7d),
            "price_change_24h": price_change_24h,
        }
        return max(-100.0, min(100.0, score)), meta

    def _momentum_component(self, frame: pd.DataFrame) -> tuple[float, Dict[str, Any]]:
        if frame.empty or len(frame) < 200:
            return 0.0, {"available": False}
        close = frame["close"]
        latest_ts = close.index.max()
        latest_price = float(close.iloc[-1])
        changes = {
            "4h": self._change_for_hours(close, latest_ts, latest_price, 4),
            "24h": self._change_for_hours(close, latest_ts, latest_price, 24),
            "7d": self._change_for_hours(close, latest_ts, latest_price, 24 * 7),
        }
        weights = {"4h": 0.5, "24h": 0.3, "7d": 0.2}
        available = {key: value for key, value in changes.items() if value is not None}
        if not available:
            return 0.0, {"available": False}

        total_weight = sum(weights[key] for key in available.keys())
        weighted_change = sum((weights[key] / total_weight) * float(value) for key, value in available.items())
        score = math.tanh(weighted_change / 8.0) * 100.0
        meta = {
            "available": True,
            "changes": {key: float(value) for key, value in available.items()},
            "weighted_change": float(weighted_change),
        }
        return max(-100.0, min(100.0, score)), meta

    async def _deactivate_previous_active_signals(
        self,
        session: AsyncSession,
        asset_id: int,
        strategy_id: str,
    ) -> None:
        query = (
            update(TradingSignal)
            .where(
                TradingSignal.asset_id == asset_id,
                TradingSignal.strategy_id == strategy_id,
                TradingSignal.is_active.is_(True),
            )
            .values(is_active=False)
        )
        await session.execute(query)

    def _compute_composite(
        self,
        sentiment: float,
        technical: float,
        volume: float,
        momentum: float,
        weights: Mapping[str, float],
    ) -> float:
        raw = (
            sentiment * float(weights["sentiment"])
            + technical * float(weights["technical"])
            + volume * float(weights["volume"])
            + momentum * float(weights["momentum"])
        )
        return max(-100.0, min(100.0, raw))

    def _normalize_weights(self, availability: Mapping[str, bool]) -> Dict[str, float]:
        active = {
            name: self._weights[name]
            for name in self._weights.keys()
            if availability.get(name, False)
        }
        total = sum(active.values())
        if total <= 0:
            return {name: 0.0 for name in self._weights.keys()}
        return {name: (active.get(name, 0.0) / total) for name in self._weights.keys()}

    def _signal_type_from_score(
        self,
        composite: float,
        buy_threshold: float,
        sell_threshold: float,
    ) -> SignalType:
        if composite >= buy_threshold:
            return SignalType.BUY
        if composite <= sell_threshold:
            return SignalType.SELL
        return SignalType.HOLD

    def _expires_at(self, timeframe: AggregationTimeframe) -> datetime:
        now = datetime.now(timezone.utc)
        if timeframe == AggregationTimeframe.H1:
            return now + timedelta(hours=4)
        if timeframe == AggregationTimeframe.D1:
            return now + timedelta(hours=48)
        return now + timedelta(hours=12)

    def _build_reasoning(
        self,
        composite: float,
        signal_type: SignalType,
        buy_threshold: float,
        sell_threshold: float,
        sentiment_score: float,
        technical_score: float,
        volume_score: float,
        momentum_score: float,
        sentiment_meta: Mapping[str, Any],
        technical_meta: Mapping[str, Any],
        volume_meta: Mapping[str, Any],
        momentum_meta: Mapping[str, Any],
        threshold_meta: Mapping[str, Any],
        weights: Mapping[str, float],
        coverage: float,
    ) -> str:
        parts: List[str] = []
        parts.append(
            "Signal {0} bei Composite {1:.2f}.".format(signal_type.value.upper(), composite)
        )
        parts.append(
            "Komponenten S:{0:.1f} T:{1:.1f} V:{2:.1f} M:{3:.1f}.".format(
                sentiment_score, technical_score, volume_score, momentum_score
            )
        )

        if sentiment_meta.get("available"):
            parts.append("Sentiment basiert auf {0} Mentions.".format(sentiment_meta.get("mentions", 0)))
        else:
            parts.append("Sentiment-Daten fehlen, Komponente neutral.")

        if technical_meta.get("available"):
            indicators = technical_meta.get("indicators", {})
            rsi_zone = indicators.get("rsi", {}).get("zone", "unknown")
            macd_state = indicators.get("macd", {}).get("state", "none")
            bollinger_pos = indicators.get("bollinger", {}).get("position", "unknown")
            sma_cross = indicators.get("sma", {}).get("cross", "none")
            parts.append(
                "Technik: RSI {0}, MACD {1}, Bollinger {2}, SMA {3}.".format(
                    rsi_zone, macd_state, bollinger_pos, sma_cross
                )
            )
        else:
            parts.append("Technische Daten unzureichend, Komponente neutral.")

        if volume_meta.get("available"):
            parts.append(
                "Volumen 24h/7d: {0:.2f}x, Preis 24h {1:+.2f}%.".format(
                    float(volume_meta.get("ratio", 1.0)),
                    float(volume_meta.get("price_change_24h", 0.0)),
                )
            )
        if momentum_meta.get("available"):
            changes = momentum_meta.get("changes", {})
            parts.append(
                "Momentum 4h {0:+.2f}%, 24h {1:+.2f}%, 7d {2:+.2f}%.".format(
                    float(changes.get("4h", 0.0)),
                    float(changes.get("24h", 0.0)),
                    float(changes.get("7d", 0.0)),
                )
            )

        if coverage < 1.0:
            parts.append(
                "Datenabdeckung nur {0:.0f}% ({1}/{2} Kerzen), technische Komponenten skaliert.".format(
                    coverage * 100.0,
                    int(round(coverage * REQUIRED_CANDLES)),
                    REQUIRED_CANDLES,
                )
            )

        parts.append(
            "Effektive Gewichte S:{0:.2f} T:{1:.2f} V:{2:.2f} M:{3:.2f}.".format(
                float(weights["sentiment"]),
                float(weights["technical"]),
                float(weights["volume"]),
                float(weights["momentum"]),
            )
        )
        if threshold_meta.get("adaptive"):
            parts.append(
                "Adaptive Schwellen BUY>={0:.1f}, SELL<={1:.1f}, Volatilitaet {2:.2f}%.".format(
                    buy_threshold,
                    sell_threshold,
                    float(threshold_meta.get("volatility_pct", 0.0)),
                )
            )
        else:
            parts.append(
                "Standard-Schwellen BUY>={0:.1f}, SELL<={1:.1f}.".format(
                    buy_threshold,
                    sell_threshold,
                )
            )
        return " ".join(parts)

    def _adaptive_thresholds(self, market_frame: pd.DataFrame) -> tuple[float, float, Dict[str, Any]]:
        if market_frame.empty or len(market_frame) < 500:
            return 30.0, -30.0, {"adaptive": False, "volatility_pct": None}
        returns = market_frame["close"].pct_change().dropna() * 100.0
        if returns.empty:
            return 30.0, -30.0, {"adaptive": False, "volatility_pct": None}
        sample = returns.tail(1440)
        volatility_pct = float(sample.std(ddof=0))
        if not math.isfinite(volatility_pct):
            return 30.0, -30.0, {"adaptive": False, "volatility_pct": None}
        buy_threshold = max(18.0, min(40.0, 24.0 + (1.2 * volatility_pct)))
        sell_threshold = -buy_threshold
        return buy_threshold, sell_threshold, {"adaptive": True, "volatility_pct": volatility_pct}

    def _rows_to_frame(self, rows: Iterable[PriceData]) -> pd.DataFrame:
        entries = [
            {
                "timestamp": row.timestamp,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for row in rows
        ]
        if not entries:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        frame = pd.DataFrame(entries)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = frame.set_index("timestamp").sort_index()
        return frame

    def _resample_ohlcv(self, frame: pd.DataFrame, rule: str) -> pd.DataFrame:
        if frame.empty:
            return frame
        resampled = frame.resample(rule).agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        return resampled.dropna(subset=["open", "high", "low", "close"])

    def _change_for_hours(
        self,
        close_series: pd.Series,
        latest_ts: pd.Timestamp,
        latest_price: float,
        hours: int,
    ) -> Optional[float]:
        cutoff = latest_ts - pd.Timedelta(hours=hours)
        historical = close_series[close_series.index <= cutoff]
        if historical.empty:
            return None
        base = float(historical.iloc[-1])
        if base == 0:
            return None
        return self._percent_change(base, latest_price)

    def _percent_change(self, previous: float, current: float) -> float:
        if previous == 0:
            return 0.0
        return ((current - previous) / previous) * 100.0

    def _parse_signal_timeframe(self, timeframe: str) -> AggregationTimeframe:
        if timeframe == AggregationTimeframe.H1.value:
            return AggregationTimeframe.H1
        if timeframe == AggregationTimeframe.D1.value:
            return AggregationTimeframe.D1
        raise ValueError("Unsupported signal timeframe: {0}".format(timeframe))

    def _validate_weights(self, weights: Mapping[str, float]) -> Dict[str, float]:
        required = ("sentiment", "technical", "volume", "momentum")
        missing = [name for name in required if name not in weights]
        if missing:
            raise ValueError("Missing signal weights: {0}".format(", ".join(missing)))
        cleaned = {name: max(0.0, float(weights[name])) for name in required}
        total = sum(cleaned.values())
        if total <= 0:
            raise ValueError("Signal weights must sum to a positive value.")
        return {name: cleaned[name] / total for name in required}
