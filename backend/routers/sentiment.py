from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import AggregatedSentiment, AggregationSource, AggregationTimeframe, Asset, SentimentRecord

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])


class SentimentSnapshotResponse(BaseModel):
    """Latest sentiment snapshot for one symbol."""

    symbol: str
    score: Optional[float]
    label: str
    mentions_1h: int
    mentions_1d: int
    updated_at: Optional[datetime]


class SentimentHistoryItem(BaseModel):
    """Historical aggregate item for charting."""

    period_start: datetime
    period_end: datetime
    score: float
    avg_score: float
    total_mentions: int


class SentimentOverviewItem(BaseModel):
    """Overview row for all tracked assets."""

    symbol: str
    score: Optional[float]
    label: str
    mentions_1h: int
    updated_at: Optional[datetime]


@router.get("/overview", response_model=List[SentimentOverviewItem])
async def get_sentiment_overview(db: AsyncSession = Depends(get_db)) -> List[SentimentOverviewItem]:
    """Return latest sentiment overview for all active assets."""
    latest_subquery = (
        select(AggregatedSentiment.asset_id, func.max(AggregatedSentiment.period_end).label("latest_end"))
        .where(
            AggregatedSentiment.timeframe == AggregationTimeframe.H1,
            AggregatedSentiment.source == AggregationSource.ALL,
        )
        .group_by(AggregatedSentiment.asset_id)
        .subquery()
    )
    query = (
        select(Asset, AggregatedSentiment)
        .outerjoin(latest_subquery, Asset.id == latest_subquery.c.asset_id)
        .outerjoin(
            AggregatedSentiment,
            and_(
                AggregatedSentiment.asset_id == latest_subquery.c.asset_id,
                AggregatedSentiment.period_end == latest_subquery.c.latest_end,
                AggregatedSentiment.timeframe == AggregationTimeframe.H1,
                AggregatedSentiment.source == AggregationSource.ALL,
            ),
        )
        .where(Asset.is_active.is_(True))
        .order_by(Asset.symbol.asc())
    )
    rows = (await db.execute(query)).all()
    overview = [
        SentimentOverviewItem(
            symbol=asset.symbol,
            score=aggregate.weighted_score if aggregate else None,
            label=_label_from_score(aggregate.weighted_score if aggregate else None),
            mentions_1h=aggregate.total_mentions if aggregate else 0,
            updated_at=aggregate.period_end if aggregate else None,
        )
        for asset, aggregate in rows
    ]
    overview.sort(key=lambda item: abs(item.score) if item.score is not None else -1.0, reverse=True)
    return overview


@router.get("/{symbol}/history", response_model=List[SentimentHistoryItem])
async def get_sentiment_history(
    symbol: str,
    timeframe: AggregationTimeframe = Query(default=AggregationTimeframe.H1),
    limit: int = Query(default=48, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> List[SentimentHistoryItem]:
    """Return historical aggregated sentiment for one symbol."""
    asset = await _get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")
    query = (
        select(AggregatedSentiment)
        .where(
            AggregatedSentiment.asset_id == asset.id,
            AggregatedSentiment.timeframe == timeframe,
            AggregatedSentiment.source == AggregationSource.ALL,
        )
        .order_by(AggregatedSentiment.period_start.desc())
        .limit(limit)
    )
    rows = list((await db.execute(query)).scalars().all())
    rows.reverse()
    return [
        SentimentHistoryItem(
            period_start=row.period_start,
            period_end=row.period_end,
            score=row.weighted_score,
            avg_score=row.avg_score,
            total_mentions=row.total_mentions,
        )
        for row in rows
    ]


@router.get("/{symbol}", response_model=SentimentSnapshotResponse)
async def get_sentiment_snapshot(symbol: str, db: AsyncSession = Depends(get_db)) -> SentimentSnapshotResponse:
    """Return current sentiment snapshot for one symbol."""
    asset = await _get_asset_by_symbol(db, symbol)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")
    one_hour = await _latest_aggregate(db, asset.id, AggregationTimeframe.H1)
    one_day = await _latest_aggregate(db, asset.id, AggregationTimeframe.D1)
    score = one_hour.weighted_score if one_hour else None
    return SentimentSnapshotResponse(
        symbol=asset.symbol,
        score=score,
        label=_label_from_score(score),
        mentions_1h=one_hour.total_mentions if one_hour else 0,
        mentions_1d=one_day.total_mentions if one_day else 0,
        updated_at=one_hour.period_end if one_hour else None,
    )


async def _get_asset_by_symbol(db: AsyncSession, symbol: str) -> Optional[Asset]:
    query = select(Asset).where(Asset.symbol == symbol.upper().strip())
    return (await db.execute(query)).scalar_one_or_none()


async def _latest_aggregate(
    db: AsyncSession,
    asset_id: int,
    timeframe: AggregationTimeframe,
) -> Optional[AggregatedSentiment]:
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
    return (await db.execute(query)).scalar_one_or_none()


def _label_from_score(score: Optional[float]) -> str:
    if score is None:
        return "neutral"
    if score > 0.05:
        return "positive"
    if score < -0.05:
        return "negative"
    return "neutral"
