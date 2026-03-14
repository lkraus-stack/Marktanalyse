from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Asset, TradeSide, TradeStatus
from rate_limit import limiter
from services.auto_trader import get_auto_trader
from services.exceptions import SafetyConstraintError

router = APIRouter(prefix="/api/trading", tags=["trading"])


class TradingOrderCreateRequest(BaseModel):
    """Payload for manual quick-trade order placement."""

    symbol: str = Field(min_length=1, max_length=20)
    qty: float = Field(gt=0, le=1000000)
    side: TradeSide
    order_type: str = "market"
    time_in_force: str = "day"
    notes: Optional[str] = None
    confirmation_text: Optional[str] = Field(default=None, max_length=20)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("Symbol darf nicht leer sein.")
        if len(symbol) > 20:
            raise ValueError("Symbol zu lang.")
        for char in symbol:
            if not (char.isalnum() or char in {"-", ".", "/"}):
                raise ValueError("Symbol enthaelt ungueltige Zeichen.")
        return symbol

    @field_validator("order_type")
    @classmethod
    def validate_order_type(cls, value: str) -> str:
        order_type = value.strip().lower()
        if order_type != "market":
            raise ValueError("order_type muss 'market' sein.")
        return order_type

    @field_validator("time_in_force")
    @classmethod
    def validate_time_in_force(cls, value: str) -> str:
        tif = value.strip().lower()
        if tif not in {"day", "gtc", "ioc"}:
            raise ValueError("time_in_force muss day/gtc/ioc sein.")
        return tif


class TradingOrderResponse(BaseModel):
    """Serialized local trade order record."""

    id: int
    asset_id: Optional[int]
    symbol: Optional[str]
    broker: str
    order_id: Optional[str]
    side: TradeSide
    quantity: Decimal
    price: Decimal
    total_value: Decimal
    status: TradeStatus
    signal_id: Optional[int]
    is_paper: bool
    is_live: bool
    created_at: datetime
    filled_at: Optional[datetime]
    notes: Optional[str]


class TradingSettingsResponse(BaseModel):
    """Autotrader settings response payload."""

    mode: str
    is_live: bool
    max_position_size_usd: float
    max_positions: int
    min_signal_strength: float
    stop_loss_pct: float
    take_profit_pct: float
    double_confirm_threshold_eur: float
    daily_loss_limit_eur: float
    max_trades_per_day: int
    live_stop_reason: Optional[str] = None


class TradingSettingsUpdateRequest(BaseModel):
    """Partial settings update payload."""

    mode: Optional[str] = None
    is_live: Optional[bool] = None
    activation_phrase: Optional[str] = Field(default=None, max_length=20)
    max_position_size_usd: Optional[float] = Field(default=None, gt=0)
    max_positions: Optional[int] = Field(default=None, ge=1)
    min_signal_strength: Optional[float] = Field(default=None, ge=0, le=100)
    stop_loss_pct: Optional[float] = Field(default=None, gt=0)
    take_profit_pct: Optional[float] = Field(default=None, gt=0)
    double_confirm_threshold_eur: Optional[float] = Field(default=None, gt=0)
    daily_loss_limit_eur: Optional[float] = Field(default=None, gt=0)
    max_trades_per_day: Optional[int] = Field(default=None, ge=1)


class ConfirmOrderRequest(BaseModel):
    """Confirmation payload for pending live orders."""

    confirmation_text: Optional[str] = Field(default=None, max_length=20)


@router.get("/account")
@limiter.limit("10/minute")
async def get_account(request: Request) -> Dict[str, Any]:
    """Return paper broker account overview."""
    trader = get_auto_trader()
    try:
        return await trader.get_account()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/positions")
@limiter.limit("10/minute")
async def get_positions(request: Request) -> List[Dict[str, Any]]:
    """Return open paper positions."""
    trader = get_auto_trader()
    try:
        return await trader.get_positions()
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/portfolio/history")
@limiter.limit("10/minute")
async def get_portfolio_history(request: Request, limit: int = Query(default=200, ge=1, le=1000)) -> List[Dict[str, Any]]:
    """Return portfolio snapshots for equity curve."""
    trader = get_auto_trader()
    snapshots = await trader.get_portfolio_history(limit=limit)
    return [
        {
            "id": item.id,
            "broker": item.broker.value,
            "total_value": float(item.total_value),
            "cash": float(item.cash),
            "positions_value": float(item.positions_value),
            "daily_pnl": float(item.daily_pnl),
            "total_pnl": float(item.total_pnl),
            "snapshot_at": item.snapshot_at,
        }
        for item in snapshots
    ]


@router.get("/performance")
@limiter.limit("10/minute")
async def get_performance(request: Request) -> Dict[str, Any]:
    """Return aggregate paper-trading performance metrics."""
    trader = get_auto_trader()
    return await trader.get_performance_metrics()


@router.get("/status")
@limiter.limit("10/minute")
async def get_trading_status(request: Request) -> Dict[str, Any]:
    """Return broker and live-trading safety status."""
    trader = get_auto_trader()
    return await trader.get_broker_status()


@router.get("/settings", response_model=TradingSettingsResponse)
@limiter.limit("10/minute")
async def get_settings(request: Request) -> TradingSettingsResponse:
    """Return autotrader runtime settings."""
    trader = get_auto_trader()
    settings_payload = await trader.get_settings()
    return TradingSettingsResponse(**settings_payload)


@router.patch("/settings", response_model=TradingSettingsResponse)
@limiter.limit("10/minute")
async def update_settings(request: Request, payload: TradingSettingsUpdateRequest) -> TradingSettingsResponse:
    """Update autotrader runtime settings."""
    trader = get_auto_trader()
    try:
        updated = await trader.update_settings(payload.model_dump(exclude_unset=True))
    except SafetyConstraintError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return TradingSettingsResponse(**updated)


@router.post("/run/evaluate")
@limiter.limit("10/minute")
async def run_trade_evaluation(request: Request) -> Dict[str, Any]:
    """Trigger one buy-signal evaluation cycle manually."""
    trader = get_auto_trader()
    return await trader.evaluate_and_trade()


@router.post("/run/exits")
@limiter.limit("10/minute")
async def run_exit_check(request: Request) -> Dict[str, Any]:
    """Trigger one exit-condition check manually."""
    trader = get_auto_trader()
    return await trader.check_exit_conditions()


@router.post("/run/snapshot")
@limiter.limit("10/minute")
async def run_snapshot(request: Request) -> Dict[str, Any]:
    """Trigger immediate portfolio snapshot."""
    trader = get_auto_trader()
    snapshot = await trader.take_portfolio_snapshot()
    if snapshot is None:
        return {"created": False}
    return {"created": True, "snapshot_id": snapshot.id, "snapshot_at": snapshot.snapshot_at}


@router.get("/orders", response_model=List[TradingOrderResponse])
@limiter.limit("10/minute")
async def list_orders(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    db: AsyncSession = Depends(get_db),
) -> List[TradingOrderResponse]:
    """List local trade records."""
    trader = get_auto_trader()
    orders = await trader.list_orders(limit=limit, status=status_filter)
    symbols = await _load_symbols(db, orders)
    return [_to_order_response(item, symbols.get(item.asset_id)) for item in orders]


@router.post("/orders", response_model=TradingOrderResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_order(
    request: Request,
    payload: TradingOrderCreateRequest,
    db: AsyncSession = Depends(get_db),
) -> TradingOrderResponse:
    """Create manual paper order."""
    trader = get_auto_trader()
    try:
        trade = await trader.create_manual_order(
            symbol=payload.symbol,
            qty=payload.qty,
            side=payload.side,
            order_type=payload.order_type,
            time_in_force=payload.time_in_force,
            notes=payload.notes,
            confirmation_text=payload.confirmation_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SafetyConstraintError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    symbol = await _symbol_for_asset_id(db, trade.asset_id)
    return _to_order_response(trade, symbol)


@router.get("/orders/{trade_id}", response_model=TradingOrderResponse)
@limiter.limit("10/minute")
async def get_order(
    request: Request,
    trade_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
) -> TradingOrderResponse:
    """Get one local trade record."""
    trader = get_auto_trader()
    trade = await trader.get_trade(trade_id)
    if trade is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trade nicht gefunden.")
    symbol = await _symbol_for_asset_id(db, trade.asset_id)
    return _to_order_response(trade, symbol)


@router.post("/orders/{trade_id}/confirm", response_model=TradingOrderResponse)
@limiter.limit("10/minute")
async def confirm_order(
    request: Request,
    payload: ConfirmOrderRequest,
    trade_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
) -> TradingOrderResponse:
    """Confirm pending semi-auto order."""
    trader = get_auto_trader()
    try:
        trade = await trader.confirm_pending_trade(trade_id, confirmation_text=payload.confirmation_text)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except SafetyConstraintError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    symbol = await _symbol_for_asset_id(db, trade.asset_id)
    return _to_order_response(trade, symbol)


@router.delete("/orders/{trade_id}", response_model=TradingOrderResponse)
@limiter.limit("10/minute")
async def cancel_order(
    request: Request,
    trade_id: int = Path(..., ge=1),
    db: AsyncSession = Depends(get_db),
) -> TradingOrderResponse:
    """Cancel one local/broker order."""
    trader = get_auto_trader()
    try:
        trade = await trader.cancel_trade(trade_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    symbol = await _symbol_for_asset_id(db, trade.asset_id)
    return _to_order_response(trade, symbol)


async def _load_symbols(db: AsyncSession, trades: List[Any]) -> Dict[Optional[int], Optional[str]]:
    asset_ids = sorted({item.asset_id for item in trades if item.asset_id is not None})
    if not asset_ids:
        return {}
    query = select(Asset.id, Asset.symbol).where(Asset.id.in_(asset_ids))
    rows = (await db.execute(query)).all()
    return {asset_id: symbol for asset_id, symbol in rows}


async def _symbol_for_asset_id(db: AsyncSession, asset_id: Optional[int]) -> Optional[str]:
    if asset_id is None:
        return None
    query = select(Asset.symbol).where(Asset.id == asset_id)
    return (await db.execute(query)).scalar_one_or_none()


def _to_order_response(trade: Any, symbol: Optional[str]) -> TradingOrderResponse:
    return TradingOrderResponse(
        id=trade.id,
        asset_id=trade.asset_id,
        symbol=symbol,
        broker=trade.broker.value,
        order_id=trade.order_id,
        side=trade.side,
        quantity=trade.quantity,
        price=trade.price,
        total_value=trade.total_value,
        status=trade.status,
        signal_id=trade.signal_id,
        is_paper=trade.is_paper,
        is_live=trade.is_live,
        created_at=trade.created_at,
        filled_at=trade.filled_at,
        notes=trade.notes,
    )
