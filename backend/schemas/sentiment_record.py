from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import SentimentLabel, SentimentModel, SentimentSource


class SentimentRecordCreate(BaseModel):
    """Payload to store one sentiment analysis record."""

    asset_id: Optional[int] = None
    source: SentimentSource
    text_snippet: str = Field(min_length=1, max_length=500)
    sentiment_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    sentiment_label: Optional[SentimentLabel] = None
    model_used: Optional[SentimentModel] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source_url: Optional[str] = Field(default=None, max_length=2048)
    author: Optional[str] = Field(default=None, max_length=120)
    created_at: Optional[datetime] = None


class SentimentRecordUpdate(BaseModel):
    """Payload to partially update a sentiment record."""

    asset_id: Optional[int] = None
    source: Optional[SentimentSource] = None
    text_snippet: Optional[str] = Field(default=None, min_length=1, max_length=500)
    sentiment_score: Optional[float] = Field(default=None, ge=-1.0, le=1.0)
    sentiment_label: Optional[SentimentLabel] = None
    model_used: Optional[SentimentModel] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source_url: Optional[str] = Field(default=None, max_length=2048)
    author: Optional[str] = Field(default=None, max_length=120)


class SentimentRecordRead(BaseModel):
    """Serialized sentiment record response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: Optional[int]
    source: SentimentSource
    text_snippet: str
    sentiment_score: Optional[float]
    sentiment_label: Optional[SentimentLabel]
    model_used: Optional[SentimentModel]
    confidence: Optional[float]
    source_url: Optional[str]
    author: Optional[str]
    created_at: datetime
