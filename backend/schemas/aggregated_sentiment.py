from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import AggregationSource, AggregationTimeframe


class AggregatedSentimentCreate(BaseModel):
    """Payload for aggregated sentiment windows."""

    asset_id: int
    period_start: datetime
    period_end: datetime
    timeframe: AggregationTimeframe
    avg_score: float = Field(ge=-1.0, le=1.0)
    positive_count: int = Field(ge=0)
    negative_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    total_mentions: int = Field(ge=0)
    source: AggregationSource
    weighted_score: float = Field(ge=-1.0, le=1.0)


class AggregatedSentimentUpdate(BaseModel):
    """Payload to partially update an aggregated sentiment window."""

    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    timeframe: Optional[AggregationTimeframe] = None
    avg_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    positive_count: Optional[int] = Field(default=None, ge=0)
    negative_count: Optional[int] = Field(default=None, ge=0)
    neutral_count: Optional[int] = Field(default=None, ge=0)
    total_mentions: Optional[int] = Field(default=None, ge=0)
    source: Optional[AggregationSource] = None
    weighted_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)


class AggregatedSentimentRead(BaseModel):
    """Serialized aggregated sentiment response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    period_start: datetime
    period_end: datetime
    timeframe: AggregationTimeframe
    avg_score: float
    positive_count: int
    negative_count: int
    neutral_count: int
    total_mentions: int
    source: AggregationSource
    weighted_score: float
