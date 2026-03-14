from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Asset, PriceData, PriceTimeframe, WatchStatus
from schemas.asset import AssetCreate, AssetRead

router = APIRouter(prefix="/api", tags=["market-data"])


class LatestPriceResponse(BaseModel):
    """Response model for latest price endpoints."""

    symbol: str
    timeframe: PriceTimeframe
    source: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: float


class AssetWithLatestPrice(BaseModel):
    """Response model combining asset metadata and latest close."""

    id: int
    symbol: str
    name: str
    asset_type: str
    exchange: Optional[str]
    watch_status: WatchStatus
    watch_notes: Optional[str]
    is_tool_suggested: bool
    is_active: bool
    latest_close: Optional[Decimal]
    latest_timestamp: Optional[datetime]
    latest_source: Optional[str]


class WatchStatusUpdateRequest(BaseModel):
    """Update payload for user watchlist/holding state."""

    watch_status: WatchStatus
    watch_notes: Optional[str] = None


@router.get("/prices/{symbol}", response_model=LatestPriceResponse)
async def get_latest_price(symbol: str, db: AsyncSession = Depends(get_db)) -> LatestPriceResponse:
    """Return latest stored 1m price snapshot for a symbol."""
    asset = await _get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")

    query = (
        select(PriceData)
        .where(PriceData.asset_id == asset.id, PriceData.timeframe == PriceTimeframe.M1)
        .order_by(PriceData.timestamp.desc())
        .limit(1)
    )
    latest = (await db.execute(query)).scalar_one_or_none()
    if latest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Keine Preisdaten vorhanden.")

    return LatestPriceResponse(
        symbol=asset.symbol,
        timeframe=latest.timeframe,
        source=latest.source,
        timestamp=latest.timestamp,
        open=latest.open,
        high=latest.high,
        low=latest.low,
        close=latest.close,
        volume=latest.volume,
    )


@router.get("/prices/{symbol}/history", response_model=List[LatestPriceResponse])
async def get_price_history(
    symbol: str,
    timeframe: PriceTimeframe = Query(default=PriceTimeframe.D1),
    limit: int = Query(default=100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
) -> List[LatestPriceResponse]:
    """Return historical price records for one symbol/timeframe."""
    asset = await _get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")

    query = (
        select(PriceData)
        .where(PriceData.asset_id == asset.id, PriceData.timeframe == timeframe)
        .order_by(PriceData.timestamp.desc())
        .limit(limit)
    )
    rows = list((await db.execute(query)).scalars().all())
    rows.reverse()
    return [
        LatestPriceResponse(
            symbol=asset.symbol,
            timeframe=item.timeframe,
            source=item.source,
            timestamp=item.timestamp,
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=item.volume,
        )
        for item in rows
    ]


@router.get("/assets", response_model=List[AssetWithLatestPrice])
async def get_assets_with_prices(
    scope: Literal["all", "watchlist", "holding"] = Query(default="all"),
    db: AsyncSession = Depends(get_db),
) -> List[AssetWithLatestPrice]:
    """Return all assets plus their most recent 1m close."""
    latest_subquery = (
        select(PriceData.asset_id, func.max(PriceData.timestamp).label("latest_timestamp"))
        .where(PriceData.timeframe == PriceTimeframe.M1)
        .group_by(PriceData.asset_id)
        .subquery()
    )
    query = (
        select(Asset, PriceData)
        .outerjoin(latest_subquery, Asset.id == latest_subquery.c.asset_id)
        .outerjoin(
            PriceData,
            and_(
                PriceData.asset_id == latest_subquery.c.asset_id,
                PriceData.timestamp == latest_subquery.c.latest_timestamp,
                PriceData.timeframe == PriceTimeframe.M1,
            ),
        )
        .order_by(Asset.symbol.asc())
    )
    if scope == "watchlist":
        query = query.where(Asset.watch_status == WatchStatus.WATCHLIST)
    elif scope == "holding":
        query = query.where(Asset.watch_status == WatchStatus.HOLDING)
    rows = (await db.execute(query)).all()
    suggested_symbols = await _suggested_symbols(db)
    return [
        AssetWithLatestPrice(
            id=asset.id,
            symbol=asset.symbol,
            name=asset.name,
            asset_type=asset.asset_type.value,
            exchange=asset.exchange,
            watch_status=asset.watch_status,
            watch_notes=asset.watch_notes,
            is_tool_suggested=asset.symbol in suggested_symbols,
            is_active=asset.is_active,
            latest_close=price_row.close if price_row else None,
            latest_timestamp=price_row.timestamp if price_row else None,
            latest_source=price_row.source if price_row else None,
        )
        for asset, price_row in rows
    ]


@router.post("/assets", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
async def create_asset(payload: AssetCreate, db: AsyncSession = Depends(get_db)) -> AssetRead:
    """Create one new tracked asset."""
    normalized_symbol = payload.symbol.upper().strip()
    existing = await _get_asset_by_symbol(db, normalized_symbol)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset existiert bereits.")

    asset = Asset(
        symbol=normalized_symbol,
        name=payload.name,
        asset_type=payload.asset_type,
        exchange=payload.exchange,
        watch_status=payload.watch_status,
        watch_notes=payload.watch_notes,
        is_active=payload.is_active,
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return AssetRead.model_validate(asset)


@router.patch("/assets/{symbol}/watch", response_model=AssetRead)
async def update_watch_status(
    symbol: str,
    payload: WatchStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> AssetRead:
    """Set one asset as watchlist/holding/none with optional note."""
    asset = await _get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")
    asset.watch_status = payload.watch_status
    asset.watch_notes = payload.watch_notes
    await db.commit()
    await db.refresh(asset)
    return AssetRead.model_validate(asset)


async def _get_asset_by_symbol(db: AsyncSession, symbol: str) -> Optional[Asset]:
    query = select(Asset).where(Asset.symbol == symbol.upper().strip())
    return (await db.execute(query)).scalar_one_or_none()


async def _suggested_symbols(db: AsyncSession) -> set[str]:
    from models import SignalType, TradingSignal

    now = datetime.now(timezone.utc)
    query = (
        select(Asset.symbol)
        .join(TradingSignal, TradingSignal.asset_id == Asset.id)
        .where(
            TradingSignal.is_active.is_(True),
            TradingSignal.signal_type == SignalType.BUY,
            TradingSignal.strength >= 45.0,
            or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
        )
    )
    return set((await db.execute(query)).scalars().all())
