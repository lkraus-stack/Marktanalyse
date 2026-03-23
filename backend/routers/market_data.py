from __future__ import annotations

import csv
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from typing import Any, Dict, Literal, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Asset, AssetType, PriceData, PriceTimeframe, WatchStatus
from schemas.asset import AssetCreate, AssetRead
from services.default_assets import seed_default_assets as seed_default_assets_in_db

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


class AssetCsvImportRequest(BaseModel):
    """CSV import payload for watchlist/holding bulk updates."""

    csv_content: str = Field(min_length=1)
    dry_run: bool = False
    create_missing: bool = True


class AssetCsvImportResponse(BaseModel):
    """Import summary with row-level validation errors."""

    rows_total: int
    rows_valid: int
    created: int
    updated: int
    skipped: int
    errors: List[str]


class DefaultAssetSeedResponse(BaseModel):
    """Summary for inserting the built-in starter asset universe."""

    seeded_count: int
    existing_count: int
    total_defaults: int
    active_assets_total: int
    symbols_added: List[str]


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


@router.post("/assets/seed-defaults", response_model=DefaultAssetSeedResponse)
async def seed_default_assets(db: AsyncSession = Depends(get_db)) -> DefaultAssetSeedResponse:
    """Insert the default stock/crypto starter universe once."""
    summary = await seed_default_assets_in_db(db)
    return DefaultAssetSeedResponse(**summary)


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


@router.post("/assets/import", response_model=AssetCsvImportResponse)
async def import_assets_from_csv(
    payload: AssetCsvImportRequest,
    db: AsyncSession = Depends(get_db),
) -> AssetCsvImportResponse:
    """Bulk import assets from CSV to set watchlist/holding quickly.

    Expected headers:
    symbol,name,asset_type,exchange,watch_status,watch_notes,is_active
    """
    parsed_rows = _parse_csv_rows(payload.csv_content)
    errors: List[str] = []
    rows_valid = 0
    created = 0
    updated = 0
    skipped = 0

    for idx, row in enumerate(parsed_rows, start=2):
        try:
            normalized = _normalize_import_row(row)
        except ValueError as exc:
            errors.append("Zeile {0}: {1}".format(idx, str(exc)))
            continue
        rows_valid += 1
        symbol = str(normalized["symbol"])
        asset = await _get_asset_by_symbol(db, symbol)
        if asset is None and not payload.create_missing:
            skipped += 1
            continue
        if asset is None:
            asset = Asset(
                symbol=symbol,
                name=str(normalized["name"]),
                asset_type=AssetType(str(normalized["asset_type"])),
                exchange=_nullable_str(normalized.get("exchange")),
                watch_status=WatchStatus(str(normalized["watch_status"])),
                watch_notes=_nullable_str(normalized.get("watch_notes")),
                is_active=bool(normalized["is_active"]),
            )
            db.add(asset)
            created += 1
        else:
            asset.name = str(normalized["name"])
            asset.asset_type = AssetType(str(normalized["asset_type"]))
            asset.exchange = _nullable_str(normalized.get("exchange"))
            asset.watch_status = WatchStatus(str(normalized["watch_status"]))
            asset.watch_notes = _nullable_str(normalized.get("watch_notes"))
            asset.is_active = bool(normalized["is_active"])
            updated += 1

    if not payload.dry_run:
        await db.commit()
    else:
        await db.rollback()
        created = 0
        updated = 0

    return AssetCsvImportResponse(
        rows_total=len(parsed_rows),
        rows_valid=rows_valid,
        created=created,
        updated=updated,
        skipped=skipped,
        errors=errors,
    )


@router.get("/assets/import-template")
async def get_asset_import_template() -> Dict[str, Any]:
    """Return CSV header + example row for frontend import helpers."""
    return {
        "header": "symbol,name,asset_type,exchange,watch_status,watch_notes,is_active",
        "example": "AAPL,Apple Inc.,stock,NASDAQ,holding,Langfristig halten,true",
    }


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


def _parse_csv_rows(csv_content: str) -> List[Dict[str, str]]:
    stream = StringIO(csv_content.strip())
    reader = csv.DictReader(stream)
    if not reader.fieldnames:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSV Header fehlt.")
    required = {"symbol", "name", "asset_type", "exchange", "watch_status", "watch_notes", "is_active"}
    provided = {item.strip() for item in reader.fieldnames if item}
    missing = sorted(required - provided)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fehlende CSV-Spalten: {0}".format(", ".join(missing)),
        )
    return [dict(row) for row in reader]


def _normalize_import_row(row: Dict[str, str]) -> Dict[str, Any]:
    symbol = (row.get("symbol") or "").upper().strip()
    name = (row.get("name") or "").strip()
    asset_type_text = (row.get("asset_type") or "").strip().lower()
    watch_status_text = (row.get("watch_status") or "").strip().lower()
    is_active_text = (row.get("is_active") or "").strip().lower()
    if not symbol:
        raise ValueError("symbol ist leer.")
    if not name:
        raise ValueError("name ist leer.")
    if asset_type_text not in {AssetType.STOCK.value, AssetType.CRYPTO.value}:
        raise ValueError("asset_type ungueltig: {0}".format(asset_type_text))
    if watch_status_text not in {WatchStatus.NONE.value, WatchStatus.WATCHLIST.value, WatchStatus.HOLDING.value}:
        raise ValueError("watch_status ungueltig: {0}".format(watch_status_text))
    if is_active_text not in {"true", "false", "1", "0", "yes", "no"}:
        raise ValueError("is_active ungueltig: {0}".format(is_active_text))
    return {
        "symbol": symbol,
        "name": name,
        "asset_type": asset_type_text,
        "exchange": row.get("exchange"),
        "watch_status": watch_status_text,
        "watch_notes": row.get("watch_notes"),
        "is_active": is_active_text in {"true", "1", "yes"},
    }


def _nullable_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
