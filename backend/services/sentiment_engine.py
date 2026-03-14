from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Dict, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import get_settings
from database import AsyncSessionLocal
from models import (
    AggregatedSentiment,
    AggregationSource,
    AggregationTimeframe,
    Asset,
    SentimentLabel,
    SentimentModel,
    SentimentRecord,
    SentimentSource,
)
from services.finbert_analyzer import FinBERTAnalyzer
from services.finvader_analyzer import FinVADERAnalyzer

logger = logging.getLogger("market_intelligence.services.sentiment_engine")


class SentimentEngine:
    """Orchestrates scoring and aggregation of sentiment records."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
        finvader_analyzer: Optional[FinVADERAnalyzer] = None,
        finbert_analyzer: Optional[FinBERTAnalyzer] = None,
    ) -> None:
        settings = get_settings()
        self._session_factory = session_factory
        self._batch_size = settings.sentiment_batch_size
        self._default_limit = settings.sentiment_process_limit
        self._finvader = finvader_analyzer or FinVADERAnalyzer()
        self._finbert = finbert_analyzer or FinBERTAnalyzer()

    async def process_unscored_records(self, limit: int = 100, use_finbert: bool = True) -> Dict[str, int]:
        """Score records without sentiment values."""
        records = await self._fetch_unscored_records(limit=max(1, limit))
        if not records:
            return {"processed": 0, "finbert_used": 0, "finvader_used": 0}
        texts = [record.text_snippet for record in records]
        finvader_results = self._finvader.analyze_batch(texts)
        finbert_results = await self._run_finbert_batch(texts, use_finbert=use_finbert)
        finbert_used = 0
        for idx, record in enumerate(records):
            primary = finbert_results[idx] if finbert_results else finvader_results[idx]
            if primary.get("model") == "finbert":
                finbert_used += 1
            self._apply_result(record, primary)
        await self._commit_records(records)
        return {"processed": len(records), "finbert_used": finbert_used, "finvader_used": len(records) - finbert_used}

    async def upgrade_records_with_finbert(self, limit: int = 200) -> int:
        """Upgrade previously finvader-scored records with FinBERT when available."""
        if not self._finbert.is_available():
            return 0
        records = await self._fetch_finbert_upgrade_candidates(limit=max(1, limit))
        if not records:
            return 0
        texts = [record.text_snippet for record in records]
        finbert_results = await self._run_finbert_batch(texts, use_finbert=True)
        if not finbert_results:
            return 0
        for idx, record in enumerate(records):
            self._apply_result(record, finbert_results[idx])
        await self._commit_records(records)
        return len(records)

    async def aggregate_sentiment(self, asset_id: int, timeframe: str = "1h") -> AggregatedSentiment:
        """Aggregate sentiment scores for one asset and timeframe."""
        timeframe_enum = self._parse_timeframe(timeframe)
        period_end = datetime.now(timezone.utc)
        period_start = self._period_start(period_end, timeframe_enum)
        records = await self._fetch_records_in_window(asset_id=asset_id, period_start=period_start, period_end=period_end)
        payload = self._compute_aggregation(records)
        aggregate = await self._upsert_aggregate(asset_id, timeframe_enum, period_start, period_end, payload)
        return aggregate

    async def aggregate_all_assets(self, timeframe: str) -> int:
        """Aggregate sentiment windows for all active assets."""
        timeframe_enum = self._parse_timeframe(timeframe)
        asset_ids = await self._fetch_active_asset_ids()
        aggregated_count = 0
        for asset_id in asset_ids:
            try:
                await self.aggregate_sentiment(asset_id=asset_id, timeframe=timeframe_enum.value)
                aggregated_count += 1
            except Exception:
                logger.exception("Sentiment aggregation failed.", extra={"event": "aggregate_asset_failed", "asset_id": str(asset_id)})
        return aggregated_count

    async def _fetch_unscored_records(self, limit: int) -> List[SentimentRecord]:
        async with self._session_factory() as session:
            query = (
                select(SentimentRecord)
                .where(or_(SentimentRecord.sentiment_score.is_(None), SentimentRecord.model_used.is_(None)))
                .order_by(SentimentRecord.created_at.asc())
                .limit(limit)
            )
            return list((await session.execute(query)).scalars().all())

    async def _fetch_finbert_upgrade_candidates(self, limit: int) -> List[SentimentRecord]:
        async with self._session_factory() as session:
            query = (
                select(SentimentRecord)
                .where(
                    SentimentRecord.source.in_(
                        [SentimentSource.REDDIT, SentimentSource.NEWS, SentimentSource.PERPLEXITY, SentimentSource.TWITTER]
                    ),
                    SentimentRecord.model_used.in_([None, SentimentModel.FINVADER]),
                )
                .order_by(SentimentRecord.created_at.desc())
                .limit(limit)
            )
            return list((await session.execute(query)).scalars().all())

    async def _run_finbert_batch(self, texts: Sequence[str], use_finbert: bool) -> Optional[List[Dict[str, object]]]:
        if not use_finbert:
            return None
        try:
            return await self._finbert.analyze_batch(texts, batch_size=self._batch_size)
        except Exception:
            logger.warning("FinBERT unavailable during scoring, fallback to FinVADER.", extra={"event": "finbert_fallback"})
            return None

    def _apply_result(self, record: SentimentRecord, result: Dict[str, object]) -> None:
        score = float(result.get("score", 0.0))
        confidence = float(result.get("confidence", 0.0))
        label_text = str(result.get("label", "neutral"))
        model_text = str(result.get("model", "finvader"))
        record.sentiment_score = max(-1.0, min(1.0, score))
        record.confidence = max(0.0, min(1.0, confidence))
        record.sentiment_label = self._label_from_text(label_text)
        record.model_used = self._model_from_text(model_text)

    async def _commit_records(self, records: Sequence[SentimentRecord]) -> None:
        if not records:
            return
        async with self._session_factory() as session:
            for record in records:
                await session.merge(record)
            await session.commit()

    async def _fetch_records_in_window(self, asset_id: int, period_start: datetime, period_end: datetime) -> List[SentimentRecord]:
        async with self._session_factory() as session:
            query = (
                select(SentimentRecord)
                .where(
                    SentimentRecord.asset_id == asset_id,
                    SentimentRecord.created_at >= period_start,
                    SentimentRecord.created_at < period_end,
                    SentimentRecord.sentiment_score.is_not(None),
                )
                .order_by(SentimentRecord.created_at.asc())
            )
            return list((await session.execute(query)).scalars().all())

    def _compute_aggregation(self, records: Sequence[SentimentRecord]) -> Dict[str, float | int]:
        if not records:
            return {"avg_score": 0.0, "weighted_score": 0.0, "positive_count": 0, "negative_count": 0, "neutral_count": 0, "total_mentions": 0}
        score_sum = 0.0
        weighted_sum = 0.0
        weight_total = 0.0
        positive = 0
        negative = 0
        neutral = 0
        for item in records:
            score = float(item.sentiment_score or 0.0)
            weight = self._source_weight(item.source)
            score_sum += score
            weighted_sum += score * weight
            weight_total += weight
            label = item.sentiment_label or self._label_from_score(score)
            if label == SentimentLabel.POSITIVE:
                positive += 1
            elif label == SentimentLabel.NEGATIVE:
                negative += 1
            else:
                neutral += 1
        total = len(records)
        return {
            "avg_score": score_sum / total,
            "weighted_score": weighted_sum / weight_total if weight_total else 0.0,
            "positive_count": positive,
            "negative_count": negative,
            "neutral_count": neutral,
            "total_mentions": total,
        }

    async def _upsert_aggregate(
        self,
        asset_id: int,
        timeframe: AggregationTimeframe,
        period_start: datetime,
        period_end: datetime,
        payload: Dict[str, float | int],
    ) -> AggregatedSentiment:
        async with self._session_factory() as session:
            query = select(AggregatedSentiment).where(
                AggregatedSentiment.asset_id == asset_id,
                AggregatedSentiment.timeframe == timeframe,
                AggregatedSentiment.source == AggregationSource.ALL,
                AggregatedSentiment.period_start == period_start,
            )
            record = (await session.execute(query)).scalar_one_or_none()
            if record is None:
                record = AggregatedSentiment(asset_id=asset_id, timeframe=timeframe, source=AggregationSource.ALL, period_start=period_start, period_end=period_end, avg_score=0.0, weighted_score=0.0, positive_count=0, negative_count=0, neutral_count=0, total_mentions=0)
                session.add(record)
            record.period_end = period_end
            record.avg_score = float(payload["avg_score"])
            record.weighted_score = float(payload["weighted_score"])
            record.positive_count = int(payload["positive_count"])
            record.negative_count = int(payload["negative_count"])
            record.neutral_count = int(payload["neutral_count"])
            record.total_mentions = int(payload["total_mentions"])
            await session.commit()
            await session.refresh(record)
            return record

    async def _fetch_active_asset_ids(self) -> List[int]:
        async with self._session_factory() as session:
            query = select(Asset.id).where(Asset.is_active.is_(True)).order_by(Asset.symbol.asc())
            return [asset_id for asset_id in (await session.execute(query)).scalars().all()]

    def _parse_timeframe(self, timeframe: str) -> AggregationTimeframe:
        try:
            return AggregationTimeframe(timeframe)
        except ValueError as exc:
            raise ValueError("Unsupported timeframe: {0}".format(timeframe)) from exc

    def _period_start(self, period_end: datetime, timeframe: AggregationTimeframe) -> datetime:
        if timeframe == AggregationTimeframe.H1:
            return period_end - timedelta(hours=1)
        if timeframe == AggregationTimeframe.H4:
            return period_end - timedelta(hours=4)
        return period_end - timedelta(days=1)

    def _source_weight(self, source: SentimentSource) -> float:
        if source == SentimentSource.NEWS:
            return 2.0
        return 1.0

    def _label_from_text(self, value: str) -> SentimentLabel:
        normalized = value.strip().lower()
        if normalized == "positive":
            return SentimentLabel.POSITIVE
        if normalized == "negative":
            return SentimentLabel.NEGATIVE
        return SentimentLabel.NEUTRAL

    def _model_from_text(self, value: str) -> SentimentModel:
        normalized = value.strip().lower()
        if normalized == "finbert":
            return SentimentModel.FINBERT
        if normalized == "pre_labeled":
            return SentimentModel.PRE_LABELED
        return SentimentModel.FINVADER

    def _label_from_score(self, score: float) -> SentimentLabel:
        if score > 0.05:
            return SentimentLabel.POSITIVE
        if score < -0.05:
            return SentimentLabel.NEGATIVE
        return SentimentLabel.NEUTRAL
