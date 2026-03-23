from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import AsyncSessionLocal, get_db
from models import (
    AggregatedSentiment,
    AggregationTimeframe,
    Asset,
    PriceData,
    PriceTimeframe,
    SentimentRecord,
    SignalType,
    TradingSignal,
    WatchStatus,
)
from services.data_collector import DataCollector
from services.sentiment_engine import SentimentEngine
from services.signal_engine import SignalEngine
from services.signal_lab_service import SignalLabService

router = APIRouter(prefix="/api/signals", tags=["signals"])


class SignalResponse(BaseModel):
    """Public signal payload for dashboard consumption."""

    symbol: str
    signal_type: SignalType
    strength: float
    composite_score: float
    price_at_signal: Decimal
    sentiment_component: float
    technical_component: float
    volume_component: float
    momentum_component: float
    reasoning: str
    execution_id: Optional[str]
    strategy_id: Optional[str]
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]


class SignalLeaderboardResponse(BaseModel):
    """Top buy/sell signals for quick ranking views."""

    top_buy: List[SignalResponse]
    top_sell: List[SignalResponse]


class SignalRecommendationResponse(BaseModel):
    """Tool-generated buy suggestions for discovery list."""

    symbol: str
    asset_type: str
    watch_status: WatchStatus
    signal_type: SignalType
    strength: float
    composite_score: float
    reasoning: str
    created_at: datetime
    expires_at: Optional[datetime]


class SignalPipelineStatusResponse(BaseModel):
    """Readiness and blockers for signal generation."""

    assets_total: int
    price_points_1m: int
    price_points_h1: int
    scored_sentiment_records: int
    aggregated_1h: int
    active_signals: int
    blockers: List[str]


class SignalBootstrapResponse(BaseModel):
    """Result of manual bootstrap cycle."""

    backfilled_h1: Dict[str, int]
    backfilled_m1: Dict[str, int]
    collected_prices: Dict[str, int]
    collected_social: Dict[str, int]
    sentiment_processed: Dict[str, int]
    aggregated_assets_1h: int
    generated_signals: int
    active_signals_after_run: int
    notes: List[str]


class SignalScorecardRowResponse(BaseModel):
    """One evaluated historical signal for the test bot."""

    signal_id: int
    symbol: str
    signal_type: SignalType
    strength: float
    created_at: datetime
    entry_price: float
    evaluation_price: float
    raw_return_pct: float
    strategy_return_pct: float
    success: bool
    horizon: str
    reasoning: str


class SignalScorecardSymbolResponse(BaseModel):
    """Aggregated signal quality metrics for one symbol."""

    symbol: str
    evaluated_signals: int
    hit_rate_pct: float
    avg_strategy_return_pct: float


class SignalScorecardResponse(BaseModel):
    """Aggregated signal quality summary over recent history."""

    horizon: Literal["24h", "72h", "7d"]
    total_signals: int
    evaluated_signals: int
    buy_signals: int
    sell_signals: int
    hold_signals: int
    hit_rate_pct: float
    avg_strategy_return_pct: float
    avg_buy_return_pct: Optional[float]
    avg_sell_return_pct: Optional[float]
    positive_return_share_pct: float
    top_symbols: List[SignalScorecardSymbolResponse]
    weak_symbols: List[SignalScorecardSymbolResponse]
    recent: List[SignalScorecardRowResponse]


@router.get("", response_model=List[SignalResponse])
async def get_active_signals(
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> List[SignalResponse]:
    """Return active signals sorted by strength descending."""
    now = datetime.now(timezone.utc)
    query = (
        select(TradingSignal, Asset.symbol)
        .join(Asset, TradingSignal.asset_id == Asset.id)
        .where(
            TradingSignal.is_active.is_(True),
            or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
        )
        .order_by(TradingSignal.strength.desc(), TradingSignal.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(query)).all()
    return [_to_signal_response(signal=signal, symbol=symbol) for signal, symbol in rows]


@router.get("/leaderboard", response_model=SignalLeaderboardResponse)
async def get_signals_leaderboard(db: AsyncSession = Depends(get_db)) -> SignalLeaderboardResponse:
    """Return top 10 buy and top 10 sell signals."""
    now = datetime.now(timezone.utc)
    base_query = (
        select(TradingSignal, Asset.symbol)
        .join(Asset, TradingSignal.asset_id == Asset.id)
        .where(
            TradingSignal.is_active.is_(True),
            or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
        )
    )
    buy_rows = (
        await db.execute(
            base_query.where(TradingSignal.signal_type == SignalType.BUY)
            .order_by(TradingSignal.strength.desc(), TradingSignal.created_at.desc())
            .limit(10)
        )
    ).all()
    sell_rows = (
        await db.execute(
            base_query.where(TradingSignal.signal_type == SignalType.SELL)
            .order_by(TradingSignal.strength.desc(), TradingSignal.created_at.desc())
            .limit(10)
        )
    ).all()
    return SignalLeaderboardResponse(
        top_buy=[_to_signal_response(signal=item, symbol=symbol) for item, symbol in buy_rows],
        top_sell=[_to_signal_response(signal=item, symbol=symbol) for item, symbol in sell_rows],
    )


@router.get("/recommendations", response_model=List[SignalRecommendationResponse])
async def get_signal_recommendations(
    direction: Literal["all", "buy", "sell"] = Query(default="all"),
    include_hold: bool = Query(default=False),
    min_strength: float = Query(default=45.0, ge=0.0, le=100.0),
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> List[SignalRecommendationResponse]:
    """Return signal-driven tool suggestions (buy/sell/optional hold)."""
    now = datetime.now(timezone.utc)
    priority = case(
        (TradingSignal.signal_type == SignalType.BUY, 0),
        (TradingSignal.signal_type == SignalType.SELL, 1),
        else_=2,
    )
    query = (
        select(TradingSignal, Asset)
        .join(Asset, TradingSignal.asset_id == Asset.id)
        .where(
            TradingSignal.is_active.is_(True),
            TradingSignal.strength >= float(min_strength),
            or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
            Asset.is_active.is_(True),
        )
        .order_by(priority.asc(), TradingSignal.strength.desc(), TradingSignal.created_at.desc())
        .limit(limit)
    )
    if direction == "buy":
        query = query.where(TradingSignal.signal_type == SignalType.BUY)
    elif direction == "sell":
        query = query.where(TradingSignal.signal_type == SignalType.SELL)
    else:
        if include_hold:
            query = query.where(TradingSignal.signal_type.in_([SignalType.BUY, SignalType.SELL, SignalType.HOLD]))
        else:
            query = query.where(TradingSignal.signal_type.in_([SignalType.BUY, SignalType.SELL]))
    rows = (await db.execute(query)).all()
    return [
        SignalRecommendationResponse(
            symbol=asset.symbol,
            asset_type=asset.asset_type.value,
            watch_status=asset.watch_status,
            signal_type=signal.signal_type,
            strength=signal.strength,
            composite_score=signal.composite_score,
            reasoning=signal.reasoning,
            created_at=signal.created_at,
            expires_at=signal.expires_at,
        )
        for signal, asset in rows
    ]


@router.get("/scorecard", response_model=SignalScorecardResponse)
async def get_signal_scorecard(
    horizon: Literal["24h", "72h", "7d"] = Query(default="72h"),
    limit: int = Query(default=300, ge=25, le=500),
    asset_type: Literal["all", "stock", "crypto"] = Query(default="all"),
) -> SignalScorecardResponse:
    """Return historical test-bot metrics for recent signals."""
    service = SignalLabService()
    try:
        report = await service.get_scorecard(horizon=horizon, limit=limit, asset_type=asset_type)
    finally:
        await service.close()
    return SignalScorecardResponse(**report)


@router.get("/pipeline-status", response_model=SignalPipelineStatusResponse)
async def get_signal_pipeline_status(db: AsyncSession = Depends(get_db)) -> SignalPipelineStatusResponse:
    """Return data readiness for signal generation."""
    now = datetime.now(timezone.utc)
    assets_total = int((await db.execute(select(func.count(Asset.id)).where(Asset.is_active.is_(True)))).scalar_one() or 0)
    price_points_1m = int(
        (await db.execute(select(func.count(PriceData.id)).where(PriceData.timeframe == PriceTimeframe.M1))).scalar_one() or 0
    )
    price_points_h1 = int(
        (await db.execute(select(func.count(PriceData.id)).where(PriceData.timeframe == PriceTimeframe.H1))).scalar_one() or 0
    )
    scored_sentiment_records = int(
        (
            await db.execute(
                select(func.count(SentimentRecord.id)).where(SentimentRecord.sentiment_score.is_not(None))
            )
        ).scalar_one()
        or 0
    )
    aggregated_1h = int(
        (
            await db.execute(
                select(func.count(AggregatedSentiment.id)).where(AggregatedSentiment.timeframe == AggregationTimeframe.H1)
            )
        ).scalar_one()
        or 0
    )
    active_signals = int(
        (
            await db.execute(
                select(func.count(TradingSignal.id)).where(
                    TradingSignal.is_active.is_(True),
                    or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
                )
            )
        ).scalar_one()
        or 0
    )
    blockers: List[str] = []
    if assets_total == 0:
        blockers.append("Keine aktiven Assets vorhanden.")
    if price_points_1m == 0:
        blockers.append("Keine Preisdaten in timeframe=1m vorhanden.")
    if price_points_h1 == 0:
        blockers.append("Keine Preisdaten in timeframe=1h vorhanden.")
    if aggregated_1h == 0:
        blockers.append("Keine 1h-Sentiment-Aggregationen vorhanden.")
    if active_signals == 0 and not blockers:
        blockers.append("Pipeline bereit, aber noch keine Signal-Schwelle erreicht.")
    return SignalPipelineStatusResponse(
        assets_total=assets_total,
        price_points_1m=price_points_1m,
        price_points_h1=price_points_h1,
        scored_sentiment_records=scored_sentiment_records,
        aggregated_1h=aggregated_1h,
        active_signals=active_signals,
        blockers=blockers,
    )


@router.post("/bootstrap", response_model=SignalBootstrapResponse)
async def bootstrap_signal_pipeline() -> SignalBootstrapResponse:
    """Run one full manual pipeline cycle to get first signals quickly."""
    collector = DataCollector()
    sentiment_engine = SentimentEngine()
    signal_engine = SignalEngine()
    notes: List[str] = []
    try:
        backfilled_h1 = await collector.backfill_analysis_candles(h1_limit=120)
        backfilled_m1 = await collector.backfill_m1_history(days=7)
        collected_prices = await collector.collect_all()
        collected_social = await collector.collect_social_data()
        sentiment_processed = await sentiment_engine.process_unscored_records(limit=500, use_finbert=False)
        aggregated_assets_1h = await sentiment_engine.aggregate_all_assets(timeframe="1h")
        generated_signals = await signal_engine.generate_all_signals(timeframe="1h")
    finally:
        await collector.shutdown()

    async with AsyncSessionLocal() as session:
        now = datetime.now(timezone.utc)
        total_m1 = int(
            (await session.execute(select(func.count(PriceData.id)).where(PriceData.timeframe == PriceTimeframe.M1))).scalar_one()
            or 0
        )
        total_h1 = int(
            (await session.execute(select(func.count(PriceData.id)).where(PriceData.timeframe == PriceTimeframe.H1))).scalar_one()
            or 0
        )
        active_signals_after_run = int(
            (
                await session.execute(
                    select(func.count(TradingSignal.id)).where(
                        TradingSignal.is_active.is_(True),
                        or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
                    )
                )
            ).scalar_one()
            or 0
        )

    if total_h1 == 0:
        notes.append("Kein H1-Datenbestand: Ohne Historie bleiben technische Signale oft neutral.")
    if total_m1 == 0:
        notes.append("Kein M1-Datenbestand: Volume/Momentum-Komponenten koennen neutral bleiben.")
    if collected_prices.get("stocks", 0) == 0 and collected_prices.get("crypto", 0) == 0:
        notes.append("Keine Preise gesammelt: API-Keys/Rate-Limits pruefen (Finnhub/Binance/CoinGecko).")
    if aggregated_assets_1h == 0:
        notes.append("Keine Aggregation erzeugt: Rohdaten/Sentiment-Scoring pruefen.")
    if generated_signals == 0:
        notes.append("Keine Signale erzeugt: wahrscheinlich fehlen Candle-Daten (>=20 fuer Technik, ideal 50).")

    return SignalBootstrapResponse(
        backfilled_h1=backfilled_h1,
        backfilled_m1=backfilled_m1,
        collected_prices=collected_prices,
        collected_social=collected_social,
        sentiment_processed=sentiment_processed,
        aggregated_assets_1h=aggregated_assets_1h,
        generated_signals=generated_signals,
        active_signals_after_run=active_signals_after_run,
        notes=notes,
    )


@router.get("/{symbol}/history", response_model=List[SignalResponse])
async def get_signal_history(
    symbol: str,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> List[SignalResponse]:
    """Return signal history for one symbol."""
    asset = await _get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")

    query = (
        select(TradingSignal)
        .where(TradingSignal.asset_id == asset.id)
        .order_by(TradingSignal.created_at.desc())
        .limit(limit)
    )
    signals = list((await db.execute(query)).scalars().all())
    return [_to_signal_response(signal=item, symbol=asset.symbol) for item in signals]


@router.get("/{symbol}", response_model=SignalResponse)
async def get_signal_detail(symbol: str, db: AsyncSession = Depends(get_db)) -> SignalResponse:
    """Return latest active signal detail for one symbol."""
    asset = await _get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")

    now = datetime.now(timezone.utc)
    active_query = (
        select(TradingSignal)
        .where(
            TradingSignal.asset_id == asset.id,
            TradingSignal.is_active.is_(True),
            or_(TradingSignal.expires_at.is_(None), TradingSignal.expires_at > now),
        )
        .order_by(TradingSignal.created_at.desc())
        .limit(1)
    )
    signal = (await db.execute(active_query)).scalar_one_or_none()
    if signal is None:
        fallback_query = (
            select(TradingSignal)
            .where(TradingSignal.asset_id == asset.id)
            .order_by(TradingSignal.created_at.desc())
            .limit(1)
        )
        signal = (await db.execute(fallback_query)).scalar_one_or_none()
    if signal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein Signal vorhanden.")
    return _to_signal_response(signal=signal, symbol=asset.symbol)


async def _get_asset_by_symbol(db: AsyncSession, symbol: str) -> Optional[Asset]:
    query = select(Asset).where(Asset.symbol == symbol.upper().strip())
    return (await db.execute(query)).scalar_one_or_none()


def _to_signal_response(signal: TradingSignal, symbol: str) -> SignalResponse:
    return SignalResponse(
        symbol=symbol,
        signal_type=signal.signal_type,
        strength=signal.strength,
        composite_score=signal.composite_score,
        price_at_signal=signal.price_at_signal,
        sentiment_component=signal.sentiment_component,
        technical_component=signal.technical_component,
        volume_component=signal.volume_component,
        momentum_component=signal.momentum_component,
        reasoning=signal.reasoning,
        execution_id=signal.execution_id,
        strategy_id=signal.strategy_id,
        is_active=signal.is_active,
        created_at=signal.created_at,
        expires_at=signal.expires_at,
    )
