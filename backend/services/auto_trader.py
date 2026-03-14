from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
import logging
from typing import Any, Dict, List, Mapping, Optional

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import get_settings
from database import AsyncSessionLocal
from models import (
    Asset,
    AssetType,
    AutoTradeMode,
    BrokerName,
    PortfolioSnapshot,
    PriceData,
    PriceTimeframe,
    SignalType,
    Trade,
    TradeSide,
    TradeStatus,
    TradingSignal,
)
from services.alpaca_service import AlpacaService
from services.exceptions import ExternalAPIError, SafetyConstraintError
from services.kraken_service import KrakenService
from services.signal_engine import SignalEngine

logger = logging.getLogger("market_intelligence.services.auto_trader")


CONFIRMATION_PHRASES = {"BESTAETIGEN", "BESTÄTIGEN"}


@dataclass
class AutoTraderSettings:
    """Runtime settings for autotrader execution logic."""

    mode: AutoTradeMode
    is_live: bool
    max_position_size_usd: float
    max_positions: int
    min_signal_strength: float
    stop_loss_pct: float
    take_profit_pct: float
    double_confirm_threshold_eur: float
    daily_loss_limit_eur: float
    max_trades_per_day: int


@dataclass
class BrokerOrderResult:
    """Normalized broker response for local trade storage."""

    order_id: Optional[str]
    status: TradeStatus
    filled_at: Optional[datetime]
    raw: Mapping[str, Any]


class AutoTrader:
    """Multi-broker autotrader with paper and live safety controls."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        alpaca_service: Optional[AlpacaService] = None,
        kraken_service: Optional[KrakenService] = None,
        signal_engine: Optional[SignalEngine] = None,
    ) -> None:
        settings = get_settings()
        self._session_factory = session_factory
        self._alpaca = alpaca_service or AlpacaService()
        self._kraken = kraken_service or KrakenService()
        self._signal_engine = signal_engine or SignalEngine()
        self._lock = asyncio.Lock()
        self._live_stop_reason: Optional[str] = None
        self._settings = AutoTraderSettings(
            mode=self._parse_mode(settings.auto_trader_mode),
            is_live=bool(settings.auto_is_live),
            max_position_size_usd=max(10.0, settings.auto_max_position_size_usd),
            max_positions=max(1, settings.auto_max_positions),
            min_signal_strength=max(0.0, min(100.0, settings.auto_min_signal_strength)),
            stop_loss_pct=max(0.1, settings.auto_stop_loss_pct),
            take_profit_pct=max(0.1, settings.auto_take_profit_pct),
            double_confirm_threshold_eur=max(1.0, settings.auto_double_confirm_threshold_eur),
            daily_loss_limit_eur=max(1.0, settings.auto_daily_loss_limit_eur),
            max_trades_per_day=max(1, settings.auto_max_trades_per_day),
        )

    async def shutdown(self) -> None:
        """Release broker client resources."""
        await self._alpaca.close()
        await self._kraken.close()

    async def get_settings(self) -> Dict[str, Any]:
        """Return active autotrader settings."""
        async with self._lock:
            cfg = self._settings
            return {
                "mode": cfg.mode.value,
                "is_live": cfg.is_live,
                "max_position_size_usd": cfg.max_position_size_usd,
                "max_positions": cfg.max_positions,
                "min_signal_strength": cfg.min_signal_strength,
                "stop_loss_pct": cfg.stop_loss_pct,
                "take_profit_pct": cfg.take_profit_pct,
                "double_confirm_threshold_eur": cfg.double_confirm_threshold_eur,
                "daily_loss_limit_eur": cfg.daily_loss_limit_eur,
                "max_trades_per_day": cfg.max_trades_per_day,
                "live_stop_reason": self._live_stop_reason,
            }

    async def update_settings(self, patch: Mapping[str, Any]) -> Dict[str, Any]:
        """Update runtime settings for autotrader."""
        async with self._lock:
            current = self._settings
            mode = current.mode
            if "mode" in patch and patch["mode"] is not None:
                mode = self._parse_mode(str(patch["mode"]))
            is_live = current.is_live
            if "is_live" in patch and patch["is_live"] is not None:
                requested_live = bool(patch["is_live"])
                if requested_live and not current.is_live:
                    phrase = str(patch.get("activation_phrase", "")).strip().upper()
                    if phrase not in CONFIRMATION_PHRASES:
                        raise SafetyConstraintError("Live Trading Aktivierung erfordert das Wort BESTAETIGEN.")
                is_live = requested_live
                if not is_live:
                    self._live_stop_reason = None

            self._settings = AutoTraderSettings(
                mode=mode,
                is_live=is_live,
                max_position_size_usd=max(10.0, self._to_float(patch.get("max_position_size_usd"), current.max_position_size_usd)),
                max_positions=max(1, int(self._to_float(patch.get("max_positions"), float(current.max_positions)))),
                min_signal_strength=max(0.0, min(100.0, self._to_float(patch.get("min_signal_strength"), current.min_signal_strength))),
                stop_loss_pct=max(0.1, self._to_float(patch.get("stop_loss_pct"), current.stop_loss_pct)),
                take_profit_pct=max(0.1, self._to_float(patch.get("take_profit_pct"), current.take_profit_pct)),
                double_confirm_threshold_eur=max(
                    1.0,
                    self._to_float(patch.get("double_confirm_threshold_eur"), current.double_confirm_threshold_eur),
                ),
                daily_loss_limit_eur=max(1.0, self._to_float(patch.get("daily_loss_limit_eur"), current.daily_loss_limit_eur)),
                max_trades_per_day=max(1, int(self._to_float(patch.get("max_trades_per_day"), float(current.max_trades_per_day)))),
            )
            cfg = self._settings
            return {
                "mode": cfg.mode.value,
                "is_live": cfg.is_live,
                "max_position_size_usd": cfg.max_position_size_usd,
                "max_positions": cfg.max_positions,
                "min_signal_strength": cfg.min_signal_strength,
                "stop_loss_pct": cfg.stop_loss_pct,
                "take_profit_pct": cfg.take_profit_pct,
                "double_confirm_threshold_eur": cfg.double_confirm_threshold_eur,
                "daily_loss_limit_eur": cfg.daily_loss_limit_eur,
                "max_trades_per_day": cfg.max_trades_per_day,
                "live_stop_reason": self._live_stop_reason,
            }

    async def get_broker_status(self) -> Dict[str, Any]:
        """Return broker connectivity/configuration state."""
        settings_payload = await self.get_settings()
        return {
            "alpaca_configured": self._alpaca.is_configured(),
            "kraken_configured": self._kraken.is_configured(),
            "is_live": settings_payload["is_live"],
            "live_stop_reason": settings_payload.get("live_stop_reason"),
            "mode": settings_payload["mode"],
        }

    async def get_account(self) -> Dict[str, Any]:
        """Return broker account details with safe fallback."""
        async with self._lock:
            cfg = self._settings
        if not self._alpaca.is_configured():
            return {
                "broker": "multi",
                "is_paper": not cfg.is_live,
                "is_live": cfg.is_live,
                "connected": False,
                "equity": 0.0,
                "cash": 0.0,
                "buying_power": 0.0,
                "status": "not_configured",
            }
        payload = await self._alpaca.get_account(live=cfg.is_live)
        kraken_balance: Optional[Dict[str, Any]] = None
        if cfg.is_live and self._kraken.is_configured():
            try:
                kraken_balance = await self._kraken.get_balance()
            except ExternalAPIError:
                logger.exception("Kraken balance fetch failed.", extra={"event": "kraken_balance_fetch_failed"})
        return {
            "broker": "multi",
            "is_paper": not cfg.is_live,
            "is_live": cfg.is_live,
            "connected": True,
            "equity": self._to_float(payload.get("equity"), 0.0),
            "cash": self._to_float(payload.get("cash"), 0.0),
            "buying_power": self._to_float(payload.get("buying_power"), 0.0),
            "status": str(payload.get("status", "unknown")),
            "live_stop_reason": self._live_stop_reason,
            "raw": payload,
            "kraken_balance": kraken_balance,
        }

    async def get_positions(self) -> List[Dict[str, Any]]:
        """Return normalized broker positions."""
        async with self._lock:
            cfg = self._settings
        return await self._get_positions_for_config(cfg)

    async def list_orders(self, limit: int = 100, status: Optional[str] = None) -> List[Trade]:
        """Return locally stored trade records."""
        safe_limit = max(1, min(limit, 500))
        async with self._session_factory() as session:
            query = select(Trade).order_by(Trade.created_at.desc()).limit(safe_limit)
            if status:
                try:
                    query = query.where(Trade.status == TradeStatus(status))
                except ValueError:
                    pass
            return list((await session.execute(query)).scalars().all())

    async def get_trade(self, trade_id: int) -> Optional[Trade]:
        """Return one trade by id."""
        async with self._session_factory() as session:
            return await session.get(Trade, trade_id)

    async def create_manual_order(
        self,
        symbol: str,
        qty: float,
        side: TradeSide,
        order_type: str = "market",
        time_in_force: str = "day",
        notes: Optional[str] = None,
        confirmation_text: Optional[str] = None,
    ) -> Trade:
        """Submit one explicit order and persist it as Trade."""
        async with self._lock:
            cfg = self._settings
            async with self._session_factory() as session:
                asset = await self._get_asset_by_symbol(session, symbol)
                if asset is None:
                    raise ValueError("Asset nicht gefunden: {0}".format(symbol))
                latest_price = await self._latest_price_for_asset(session, asset.id)
                broker = self._broker_for_asset(asset=asset, is_live=cfg.is_live)
                reason = await self._live_block_reason(session=session, cfg=cfg, broker=broker)
                if reason is not None:
                    self._live_stop_reason = reason
                    raise SafetyConstraintError(reason)

                total_value = qty * latest_price
                detail_notes = notes or "manual_order"
                if cfg.is_live and total_value >= cfg.double_confirm_threshold_eur and not self._is_confirmed(confirmation_text):
                    detail_notes = "{0}; double_confirmation_required".format(detail_notes)
                    trade = await self._create_pending_trade(
                        session=session,
                        asset=asset,
                        signal=None,
                        side=side,
                        quantity=qty,
                        price=latest_price,
                        notes=detail_notes,
                        broker=broker,
                        is_live=cfg.is_live,
                    )
                    await session.commit()
                    await session.refresh(trade)
                    self._log_decision("manual_pending_confirmation", asset.symbol, {"broker": broker.value, "total_value": total_value})
                    return trade

                trade = await self._create_executed_or_failed_trade(
                    session=session,
                    asset=asset,
                    signal=None,
                    side=side,
                    quantity=qty,
                    price=latest_price,
                    notes=detail_notes,
                    broker=broker,
                    is_live=cfg.is_live,
                    order_type=order_type,
                    time_in_force=time_in_force,
                )
                await session.commit()
                await session.refresh(trade)
                return trade

    async def confirm_pending_trade(self, trade_id: int, confirmation_text: Optional[str] = None) -> Trade:
        """Submit pending semi-auto/live trade after confirmation."""
        async with self._lock:
            async with self._session_factory() as session:
                trade = await session.get(Trade, trade_id)
                if trade is None:
                    raise ValueError("Trade nicht gefunden.")
                if trade.status != TradeStatus.PENDING_CONFIRMATION:
                    raise ValueError("Trade ist nicht zur Bestaetigung offen.")
                if trade.asset_id is None:
                    raise ValueError("Trade hat kein Asset.")
                asset = await session.get(Asset, trade.asset_id)
                if asset is None:
                    raise ValueError("Asset nicht gefunden.")
                if trade.is_live and float(trade.total_value) >= self._settings.double_confirm_threshold_eur:
                    if not self._is_confirmed(confirmation_text):
                        raise SafetyConstraintError("Bitte BESTAETIGEN eingeben, um den Live-Trade auszufuehren.")

                result = await self._submit_broker_order(
                    broker=trade.broker,
                    symbol=asset.symbol,
                    side=trade.side,
                    quantity=float(trade.quantity),
                    order_type="market",
                    time_in_force="day",
                    is_live=trade.is_live,
                    signal_id=trade.signal_id,
                )
                trade.order_id = result.order_id
                trade.status = result.status
                trade.filled_at = result.filled_at
                await session.commit()
                await session.refresh(trade)
                self._log_decision("confirmed_trade", asset.symbol, {"trade_id": trade.id, "status": trade.status.value})
                return trade

    async def cancel_trade(self, trade_id: int) -> Trade:
        """Cancel trade on broker side where possible."""
        async with self._lock:
            async with self._session_factory() as session:
                trade = await session.get(Trade, trade_id)
                if trade is None:
                    raise ValueError("Trade nicht gefunden.")
                if trade.order_id:
                    try:
                        await self._cancel_broker_order(
                            broker=trade.broker,
                            order_id=trade.order_id,
                            is_live=trade.is_live,
                        )
                    except ExternalAPIError:
                        logger.exception("Cancel order failed.", extra={"event": "cancel_order_failed", "trade_id": str(trade_id)})
                trade.status = TradeStatus.CANCELED
                await session.commit()
                await session.refresh(trade)
                return trade

    async def evaluate_and_trade(self) -> Dict[str, Any]:
        """Process BUY signals and execute according to mode/settings."""
        async with self._lock:
            cfg = self._settings
            positions = await self._get_positions_for_config(cfg)
            open_symbols = {str(item["symbol"]).upper() for item in positions}
            available_slots = max(0, cfg.max_positions - len(open_symbols))
            outcome: Dict[str, Any] = {
                "mode": cfg.mode.value,
                "is_live": cfg.is_live,
                "evaluated": 0,
                "executed": 0,
                "pending_confirmation": 0,
                "recommendations": [],
                "stopped": False,
                "stop_reason": self._live_stop_reason,
            }
            async with self._session_factory() as session:
                signals = await self._fetch_buy_signals(session, cfg.min_signal_strength)
                for signal, asset in signals:
                    outcome["evaluated"] += 1
                    if available_slots <= 0:
                        break
                    symbol = asset.symbol.upper()
                    broker = self._broker_for_asset(asset=asset, is_live=cfg.is_live)
                    if symbol in open_symbols:
                        self._log_decision("skip_existing_position", symbol, {"broker": broker.value})
                        continue
                    if await self._has_recent_trade(
                        session=session,
                        asset_id=asset.id,
                        side=TradeSide.BUY,
                        signal_id=signal.id,
                    ):
                        self._log_decision("skip_recent_trade", symbol, {"signal_id": signal.id})
                        continue
                    reason = await self._live_block_reason(session=session, cfg=cfg, broker=broker)
                    if reason is not None:
                        self._live_stop_reason = reason
                        outcome["stopped"] = True
                        outcome["stop_reason"] = reason
                        self._log_decision("blocked_by_safety", symbol, {"reason": reason})
                        break
                    price = float(signal.price_at_signal)
                    quantity = self._calculate_position_quantity(
                        price=price,
                        signal_strength=float(signal.strength),
                        max_position_size_usd=cfg.max_position_size_usd,
                    )
                    if quantity <= 0:
                        self._log_decision("skip_invalid_quantity", symbol, {"price": price})
                        continue
                    total_value = quantity * price
                    recommendation = {
                        "symbol": symbol,
                        "broker": broker.value,
                        "signal_id": signal.id,
                        "strength": float(signal.strength),
                        "quantity": quantity,
                        "estimated_value": round(total_value, 2),
                    }
                    if cfg.mode == AutoTradeMode.MANUAL:
                        outcome["recommendations"].append(recommendation)
                        self._log_decision("manual_recommendation", symbol, recommendation)
                        continue
                    if cfg.mode == AutoTradeMode.SEMI_AUTO or (
                        cfg.is_live and total_value >= cfg.double_confirm_threshold_eur
                    ):
                        note = "pending_confirmation: buy signal"
                        if cfg.is_live and total_value >= cfg.double_confirm_threshold_eur:
                            note = "{0}; double_confirmation_required".format(note)
                        trade = await self._create_pending_trade(
                            session=session,
                            asset=asset,
                            signal=signal,
                            side=TradeSide.BUY,
                            quantity=quantity,
                            price=price,
                            notes=note,
                            broker=broker,
                            is_live=cfg.is_live,
                        )
                        outcome["pending_confirmation"] += 1
                        outcome["recommendations"].append({"trade_id": trade.id, **recommendation})
                        available_slots -= 1
                        self._log_decision("created_pending_trade", symbol, {"trade_id": trade.id, "broker": broker.value})
                        continue

                    trade = await self._create_executed_or_failed_trade(
                        session=session,
                        asset=asset,
                        signal=signal,
                        side=TradeSide.BUY,
                        quantity=quantity,
                        price=price,
                        notes="auto_buy",
                        broker=broker,
                        is_live=cfg.is_live,
                        order_type="market",
                        time_in_force="day",
                    )
                    if trade.status in {TradeStatus.SUBMITTED, TradeStatus.FILLED}:
                        outcome["executed"] += 1
                        available_slots -= 1
                        open_symbols.add(symbol)
                        self._log_decision("auto_trade_executed", symbol, {"trade_id": trade.id, "broker": broker.value})
                await session.commit()
            return outcome

    async def check_exit_conditions(self) -> Dict[str, Any]:
        """Check sell signals, stop-loss and take-profit exits."""
        async with self._lock:
            cfg = self._settings
            positions = await self._get_positions_for_config(cfg)
            outcome: Dict[str, Any] = {
                "mode": cfg.mode.value,
                "is_live": cfg.is_live,
                "checked": 0,
                "executed": 0,
                "pending_confirmation": 0,
                "recommendations": [],
                "stopped": False,
                "stop_reason": self._live_stop_reason,
            }
            if not positions:
                return outcome

            async with self._session_factory() as session:
                for position in positions:
                    symbol = str(position.get("symbol", "")).upper()
                    if not symbol:
                        continue
                    outcome["checked"] += 1
                    asset = await self._get_asset_by_symbol(session, symbol)
                    if asset is None:
                        continue
                    broker = self._broker_for_asset(asset=asset, is_live=cfg.is_live)
                    quantity = max(0.0, self._to_float(position.get("qty"), 0.0))
                    avg_entry = self._to_float(position.get("avg_entry_price"), 0.0)
                    current_price = self._to_float(position.get("current_price"), 0.0)
                    if quantity <= 0 or avg_entry <= 0 or current_price <= 0:
                        continue
                    reason = await self._live_block_reason(session=session, cfg=cfg, broker=broker)
                    if reason is not None:
                        self._live_stop_reason = reason
                        outcome["stopped"] = True
                        outcome["stop_reason"] = reason
                        self._log_decision("blocked_by_safety", symbol, {"reason": reason})
                        break

                    pnl_pct = ((current_price - avg_entry) / avg_entry) * 100.0
                    sell_signal = await self._latest_sell_signal(session, asset.id, cfg.min_signal_strength)
                    trigger = None
                    signal_id = None
                    if pnl_pct <= (-cfg.stop_loss_pct):
                        trigger = "stop_loss"
                    elif pnl_pct >= cfg.take_profit_pct:
                        trigger = "take_profit"
                    elif sell_signal is not None:
                        trigger = "sell_signal"
                        signal_id = sell_signal.id
                    if trigger is None:
                        continue
                    if await self._has_recent_trade(
                        session=session,
                        asset_id=asset.id,
                        side=TradeSide.SELL,
                        signal_id=signal_id,
                    ):
                        continue

                    recommendation = {
                        "symbol": symbol,
                        "broker": broker.value,
                        "reason": trigger,
                        "quantity": quantity,
                        "pnl_pct": round(pnl_pct, 2),
                    }
                    total_value = quantity * current_price
                    if cfg.mode == AutoTradeMode.MANUAL:
                        outcome["recommendations"].append(recommendation)
                        self._log_decision("manual_exit_recommendation", symbol, recommendation)
                        continue
                    if cfg.mode == AutoTradeMode.SEMI_AUTO or (
                        cfg.is_live and total_value >= cfg.double_confirm_threshold_eur
                    ):
                        note = "pending_confirmation: {0}".format(trigger)
                        if cfg.is_live and total_value >= cfg.double_confirm_threshold_eur:
                            note = "{0}; double_confirmation_required".format(note)
                        trade = await self._create_pending_trade(
                            session=session,
                            asset=asset,
                            signal=sell_signal,
                            side=TradeSide.SELL,
                            quantity=quantity,
                            price=current_price,
                            notes=note,
                            broker=broker,
                            is_live=cfg.is_live,
                        )
                        outcome["pending_confirmation"] += 1
                        outcome["recommendations"].append({"trade_id": trade.id, **recommendation})
                        continue

                    trade = await self._create_executed_or_failed_trade(
                        session=session,
                        asset=asset,
                        signal=sell_signal,
                        side=TradeSide.SELL,
                        quantity=quantity,
                        price=current_price,
                        notes="auto_exit:{0}".format(trigger),
                        broker=broker,
                        is_live=cfg.is_live,
                        order_type="market",
                        time_in_force="day",
                    )
                    if trade.status in {TradeStatus.SUBMITTED, TradeStatus.FILLED}:
                        outcome["executed"] += 1
                        self._log_decision("auto_exit_executed", symbol, {"trade_id": trade.id, "broker": broker.value})
                await session.commit()
            return outcome

    async def take_portfolio_snapshot(self) -> Optional[PortfolioSnapshot]:
        """Store one portfolio state snapshot from available brokers."""
        async with self._lock:
            cfg = self._settings
            snapshots: List[PortfolioSnapshot] = []
            async with self._session_factory() as session:
                if self._alpaca.is_configured():
                    account = await self._alpaca.get_account(live=cfg.is_live)
                    snapshot = await self._create_snapshot(
                        session=session,
                        broker=BrokerName.ALPACA_PAPER,
                        total_value=self._to_float(account.get("equity"), 0.0),
                        cash=self._to_float(account.get("cash"), 0.0),
                        positions_value=self._to_float(account.get("long_market_value"), 0.0),
                        daily_pnl=self._to_float(account.get("equity"), 0.0) - self._to_float(account.get("last_equity"), 0.0),
                    )
                    snapshots.append(snapshot)
                if cfg.is_live and self._kraken.is_configured():
                    balance = await self._kraken.get_balance()
                    cash_eur = self._to_float(balance.get("ZEUR"), 0.0) + self._to_float(balance.get("EUR"), 0.0)
                    snapshot = await self._create_snapshot(
                        session=session,
                        broker=BrokerName.KRAKEN,
                        total_value=cash_eur,
                        cash=cash_eur,
                        positions_value=0.0,
                        daily_pnl=0.0,
                    )
                    snapshots.append(snapshot)
                if not snapshots:
                    return None
                await session.commit()
                for item in snapshots:
                    await session.refresh(item)
                preferred = BrokerName.KRAKEN if cfg.is_live else BrokerName.ALPACA_PAPER
                for item in snapshots:
                    if item.broker == preferred:
                        return item
                return snapshots[-1]

    async def get_portfolio_history(self, limit: int = 200) -> List[PortfolioSnapshot]:
        """Return stored portfolio snapshots for current mode broker."""
        safe_limit = max(1, min(limit, 1000))
        async with self._lock:
            cfg = self._settings
        broker = BrokerName.KRAKEN if cfg.is_live and self._kraken.is_configured() else BrokerName.ALPACA_PAPER
        async with self._session_factory() as session:
            query = (
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.broker == broker)
                .order_by(PortfolioSnapshot.snapshot_at.desc())
                .limit(safe_limit)
            )
            rows = list((await session.execute(query)).scalars().all())
            rows.reverse()
            return rows

    async def get_performance_metrics(self) -> Dict[str, Any]:
        """Compute aggregated trading metrics for current mode broker."""
        async with self._lock:
            cfg = self._settings
        broker = BrokerName.KRAKEN if cfg.is_live and self._kraken.is_configured() else BrokerName.ALPACA_PAPER
        async with self._session_factory() as session:
            latest_snapshot = (
                await session.execute(
                    select(PortfolioSnapshot)
                    .where(PortfolioSnapshot.broker == broker)
                    .order_by(PortfolioSnapshot.snapshot_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            trade_totals = (
                await session.execute(
                    select(
                        func.count(Trade.id),
                        func.sum(case((Trade.status == TradeStatus.FILLED, 1), else_=0)),
                        func.sum(case((Trade.status == TradeStatus.FAILED, 1), else_=0)),
                    ).where(Trade.broker == broker, Trade.is_live.is_(cfg.is_live))
                )
            ).first()
            total = int(trade_totals[0] or 0) if trade_totals else 0
            filled = int(trade_totals[1] or 0) if trade_totals else 0
            failed = int(trade_totals[2] or 0) if trade_totals else 0
            return {
                "total_trades": total,
                "filled_trades": filled,
                "failed_trades": failed,
                "fill_rate": (filled / total) if total > 0 else 0.0,
                "latest_total_value": self._to_float(getattr(latest_snapshot, "total_value", 0.0), 0.0),
                "daily_pnl": self._to_float(getattr(latest_snapshot, "daily_pnl", 0.0), 0.0),
                "total_pnl": self._to_float(getattr(latest_snapshot, "total_pnl", 0.0), 0.0),
                "latest_snapshot_at": getattr(latest_snapshot, "snapshot_at", None),
                "live_stop_reason": self._live_stop_reason,
                "broker": broker.value,
            }

    async def _get_positions_for_config(self, cfg: AutoTraderSettings) -> List[Dict[str, Any]]:
        positions: List[Dict[str, Any]] = []
        if self._alpaca.is_configured():
            rows = await self._alpaca.get_positions(live=cfg.is_live)
            positions.extend(
                [
                    {
                        "symbol": str(item.get("symbol", "")),
                        "qty": self._to_float(item.get("qty"), 0.0),
                        "avg_entry_price": self._to_float(item.get("avg_entry_price"), 0.0),
                        "current_price": self._to_float(item.get("current_price"), 0.0),
                        "market_value": self._to_float(item.get("market_value"), 0.0),
                        "unrealized_pl": self._to_float(item.get("unrealized_pl"), 0.0),
                        "unrealized_plpc": self._to_float(item.get("unrealized_plpc"), 0.0),
                        "side": str(item.get("side", "long")),
                        "broker": BrokerName.ALPACA_PAPER.value,
                    }
                    for item in rows
                ]
            )
        if cfg.is_live and self._kraken.is_configured():
            try:
                balance = await self._kraken.get_balance()
                for symbol in ("BTC", "ETH", "SOL"):
                    qty = self._extract_kraken_balance(balance=balance, symbol=symbol)
                    if qty <= 0:
                        continue
                    positions.append(
                        {
                            "symbol": symbol,
                            "qty": qty,
                            "avg_entry_price": 0.0,
                            "current_price": 0.0,
                            "market_value": 0.0,
                            "unrealized_pl": 0.0,
                            "unrealized_plpc": 0.0,
                            "side": "long",
                            "broker": BrokerName.KRAKEN.value,
                        }
                    )
            except ExternalAPIError:
                logger.exception("Kraken positions fetch failed.", extra={"event": "kraken_positions_failed"})
        return positions

    async def _create_executed_or_failed_trade(
        self,
        session: AsyncSession,
        asset: Asset,
        signal: Optional[TradingSignal],
        side: TradeSide,
        quantity: float,
        price: float,
        notes: str,
        broker: BrokerName,
        is_live: bool,
        order_type: str,
        time_in_force: str,
    ) -> Trade:
        order_id: Optional[str] = None
        status = TradeStatus.FAILED
        filled_at: Optional[datetime] = None
        detail_notes = notes
        try:
            result = await self._submit_broker_order(
                broker=broker,
                symbol=asset.symbol,
                side=side,
                quantity=quantity,
                order_type=order_type,
                time_in_force=time_in_force,
                is_live=is_live,
                signal_id=signal.id if signal else None,
            )
            order_id = result.order_id
            status = result.status
            filled_at = result.filled_at
        except ExternalAPIError as exc:
            detail_notes = "{0}; error={1}".format(detail_notes, str(exc))
        trade = Trade(
            asset_id=asset.id,
            broker=broker,
            order_id=order_id,
            side=side,
            quantity=Decimal(str(quantity)),
            price=Decimal(str(price)),
            total_value=Decimal(str(quantity * price)),
            status=status,
            signal_id=signal.id if signal else None,
            is_paper=not is_live,
            is_live=is_live,
            filled_at=filled_at,
            notes=detail_notes,
        )
        session.add(trade)
        await session.flush()
        return trade

    async def _submit_broker_order(
        self,
        broker: BrokerName,
        symbol: str,
        side: TradeSide,
        quantity: float,
        order_type: str,
        time_in_force: str,
        is_live: bool,
        signal_id: Optional[int],
    ) -> BrokerOrderResult:
        if broker == BrokerName.KRAKEN:
            pair = self._kraken.map_symbol_to_pair(symbol)
            payload = await self._kraken.submit_order(
                pair=pair,
                side=side.value,
                order_type=order_type,
                volume=quantity,
            )
            txids = payload.get("txid", [])
            order_id = None
            if isinstance(txids, list) and txids:
                order_id = str(txids[0])
            return BrokerOrderResult(order_id=order_id, status=TradeStatus.SUBMITTED, filled_at=None, raw=payload)

        client_order_id = "ord-{0}-{1}-{2}".format(
            side.value,
            symbol.lower(),
            signal_id or int(datetime.now(timezone.utc).timestamp()),
        )
        payload = await self._alpaca.submit_order(
            symbol=symbol,
            qty=quantity,
            side=side.value,
            order_type=order_type,
            time_in_force=time_in_force,
            client_order_id=client_order_id,
            live=is_live,
        )
        return BrokerOrderResult(
            order_id=self._string_or_none(payload.get("id")),
            status=self._map_order_status(self._string_or_none(payload.get("status"))),
            filled_at=self._parse_datetime(payload.get("filled_at")),
            raw=payload,
        )

    async def _cancel_broker_order(self, broker: BrokerName, order_id: str, is_live: bool) -> None:
        if broker == BrokerName.KRAKEN:
            await self._kraken.cancel_order(order_id)
            return
        await self._alpaca.cancel_order(order_id, live=is_live)

    async def _fetch_buy_signals(self, session: AsyncSession, min_strength: float) -> List[tuple[TradingSignal, Asset]]:
        now = datetime.now(timezone.utc)
        query = (
            select(TradingSignal, Asset)
            .join(Asset, TradingSignal.asset_id == Asset.id)
            .where(
                TradingSignal.signal_type == SignalType.BUY,
                TradingSignal.is_active.is_(True),
                TradingSignal.strength >= min_strength,
                or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
                Asset.is_active.is_(True),
            )
            .order_by(TradingSignal.strength.desc(), TradingSignal.created_at.desc())
            .limit(100)
        )
        return list((await session.execute(query)).all())

    async def _latest_sell_signal(self, session: AsyncSession, asset_id: int, min_strength: float) -> Optional[TradingSignal]:
        now = datetime.now(timezone.utc)
        query = (
            select(TradingSignal)
            .where(
                TradingSignal.asset_id == asset_id,
                TradingSignal.signal_type == SignalType.SELL,
                TradingSignal.strength >= min_strength,
                TradingSignal.is_active.is_(True),
                or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
            )
            .order_by(TradingSignal.created_at.desc())
            .limit(1)
        )
        return (await session.execute(query)).scalar_one_or_none()

    async def _create_pending_trade(
        self,
        session: AsyncSession,
        asset: Asset,
        signal: Optional[TradingSignal],
        side: TradeSide,
        quantity: float,
        price: float,
        notes: str,
        broker: BrokerName,
        is_live: bool,
    ) -> Trade:
        trade = Trade(
            asset_id=asset.id,
            broker=broker,
            order_id=None,
            side=side,
            quantity=Decimal(str(quantity)),
            price=Decimal(str(price)),
            total_value=Decimal(str(quantity * price)),
            status=TradeStatus.PENDING_CONFIRMATION,
            signal_id=signal.id if signal else None,
            is_paper=not is_live,
            is_live=is_live,
            filled_at=None,
            notes=notes,
        )
        session.add(trade)
        await session.flush()
        return trade

    async def _create_snapshot(
        self,
        session: AsyncSession,
        broker: BrokerName,
        total_value: float,
        cash: float,
        positions_value: float,
        daily_pnl: float,
    ) -> PortfolioSnapshot:
        first_query = (
            select(PortfolioSnapshot.total_value)
            .where(PortfolioSnapshot.broker == broker)
            .order_by(PortfolioSnapshot.snapshot_at.asc())
            .limit(1)
        )
        first_total = (await session.execute(first_query)).scalar_one_or_none()
        baseline = self._to_float(first_total, total_value)
        total_pnl = total_value - baseline
        snapshot = PortfolioSnapshot(
            broker=broker,
            total_value=Decimal(str(total_value)),
            cash=Decimal(str(cash)),
            positions_value=Decimal(str(positions_value)),
            daily_pnl=Decimal(str(daily_pnl)),
            total_pnl=Decimal(str(total_pnl)),
            snapshot_at=datetime.now(timezone.utc),
        )
        session.add(snapshot)
        await session.flush()
        return snapshot

    async def _live_block_reason(
        self,
        session: AsyncSession,
        cfg: AutoTraderSettings,
        broker: BrokerName,
    ) -> Optional[str]:
        if not cfg.is_live:
            return None
        if broker == BrokerName.KRAKEN and not self._kraken.is_configured():
            return "Kraken nicht konfiguriert."
        if broker == BrokerName.ALPACA_PAPER and not self._alpaca.is_configured():
            return "Alpaca nicht konfiguriert."
        trade_count = await self._daily_trade_count(session=session, broker=broker)
        if trade_count >= cfg.max_trades_per_day:
            return "Maximale Anzahl Trades pro Tag erreicht."
        daily_pnl = await self._daily_pnl_for_broker(session=session, broker=broker)
        if daily_pnl <= (-cfg.daily_loss_limit_eur):
            return "Tagesverlustlimit erreicht ({0:.2f} EUR).".format(cfg.daily_loss_limit_eur)
        return None

    async def _daily_trade_count(self, session: AsyncSession, broker: BrokerName) -> int:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = (
            select(func.count(Trade.id))
            .where(
                Trade.is_live.is_(True),
                Trade.broker == broker,
                Trade.created_at >= day_start,
                Trade.status.in_([TradeStatus.SUBMITTED, TradeStatus.FILLED]),
            )
        )
        value = (await session.execute(query)).scalar_one_or_none()
        return int(value or 0)

    async def _daily_pnl_for_broker(self, session: AsyncSession, broker: BrokerName) -> float:
        day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        query = (
            select(PortfolioSnapshot.daily_pnl)
            .where(PortfolioSnapshot.broker == broker, PortfolioSnapshot.snapshot_at >= day_start)
            .order_by(PortfolioSnapshot.snapshot_at.desc())
            .limit(1)
        )
        value = (await session.execute(query)).scalar_one_or_none()
        return self._to_float(value, 0.0)

    async def _has_recent_trade(
        self,
        session: AsyncSession,
        asset_id: int,
        side: TradeSide,
        signal_id: Optional[int],
    ) -> bool:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=1)
        query = (
            select(Trade.id)
            .where(
                Trade.asset_id == asset_id,
                Trade.side == side,
                Trade.created_at >= cutoff,
                Trade.status.in_(
                    [
                        TradeStatus.PENDING_CONFIRMATION,
                        TradeStatus.SUBMITTED,
                        TradeStatus.FILLED,
                    ]
                ),
            )
            .limit(1)
        )
        if signal_id is not None:
            query = query.where(Trade.signal_id == signal_id)
        return (await session.execute(query)).scalar_one_or_none() is not None

    async def _get_asset_by_symbol(self, session: AsyncSession, symbol: str) -> Optional[Asset]:
        query = select(Asset).where(Asset.symbol == symbol.upper().strip())
        return (await session.execute(query)).scalar_one_or_none()

    async def _latest_price_for_asset(self, session: AsyncSession, asset_id: int) -> float:
        query = (
            select(PriceData.close)
            .where(PriceData.asset_id == asset_id, PriceData.timeframe == PriceTimeframe.M1)
            .order_by(PriceData.timestamp.desc())
            .limit(1)
        )
        latest = (await session.execute(query)).scalar_one_or_none()
        return self._to_float(latest, 0.0)

    def _broker_for_asset(self, asset: Asset, is_live: bool) -> BrokerName:
        if asset.asset_type == AssetType.CRYPTO and is_live:
            return BrokerName.KRAKEN
        return BrokerName.ALPACA_PAPER

    def _calculate_position_quantity(self, price: float, signal_strength: float, max_position_size_usd: float) -> float:
        if price <= 0:
            return 0.0
        factor = max(0.25, min(1.0, signal_strength / 100.0))
        usd_value = max_position_size_usd * factor
        qty = usd_value / price
        return round(max(0.0, qty), 6)

    def _map_order_status(self, status: Optional[str]) -> TradeStatus:
        normalized = (status or "").strip().lower()
        if normalized == "filled":
            return TradeStatus.FILLED
        if normalized in {"new", "accepted", "partially_filled", "pending_new", "accepted_for_bidding"}:
            return TradeStatus.SUBMITTED
        if normalized in {"canceled", "cancelled", "expired", "done_for_day"}:
            return TradeStatus.CANCELED
        if normalized in {"rejected", "suspended", "stopped"}:
            return TradeStatus.REJECTED
        return TradeStatus.FAILED

    def _parse_mode(self, value: str) -> AutoTradeMode:
        normalized = (value or "").strip().lower()
        if normalized == AutoTradeMode.AUTO.value:
            return AutoTradeMode.AUTO
        if normalized == AutoTradeMode.SEMI_AUTO.value:
            return AutoTradeMode.SEMI_AUTO
        return AutoTradeMode.MANUAL

    def _is_confirmed(self, value: Optional[str]) -> bool:
        return bool(value and value.strip().upper() in CONFIRMATION_PHRASES)

    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if isinstance(value, str):
            candidate = value.strip()
            if not candidate:
                return None
            if candidate.endswith("Z"):
                candidate = candidate[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(candidate)
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
            except ValueError:
                return None
        return None

    def _extract_kraken_balance(self, balance: Mapping[str, Any], symbol: str) -> float:
        if symbol == "BTC":
            return self._to_float(balance.get("XXBT"), 0.0) + self._to_float(balance.get("XBT"), 0.0)
        if symbol == "ETH":
            return self._to_float(balance.get("XETH"), 0.0) + self._to_float(balance.get("ETH"), 0.0)
        if symbol == "SOL":
            return self._to_float(balance.get("SOL"), 0.0)
        return 0.0

    def _log_decision(self, decision: str, symbol: str, details: Mapping[str, Any]) -> None:
        logger.info(
            "Autotrader decision: {0} for {1}".format(decision, symbol),
            extra={
                "event": "autotrader_decision",
                "decision": decision,
                "symbol": symbol,
                "details": str(dict(details)),
            },
        )

    def _string_or_none(self, value: Any) -> Optional[str]:
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _to_float(self, value: Any, fallback: float) -> float:
        if isinstance(value, Decimal):
            return float(value)
        try:
            parsed = float(value)
            if parsed != parsed:
                return fallback
            return parsed
        except (TypeError, ValueError):
            return fallback


@lru_cache
def get_auto_trader() -> AutoTrader:
    """Return singleton autotrader instance for API/scheduler."""
    return AutoTrader()
