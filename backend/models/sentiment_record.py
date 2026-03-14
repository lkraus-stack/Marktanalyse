from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import SentimentLabel, SentimentModel, SentimentSource

if TYPE_CHECKING:
    from models.asset import Asset


class SentimentRecord(Base):
    """Single sentiment analysis result for a post/news snippet."""

    __tablename__ = "sentiment_records"
    __table_args__ = (
        CheckConstraint("sentiment_score >= -1.0 AND sentiment_score <= 1.0", name="ck_sentiment_score_range"),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_sentiment_confidence_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    source: Mapped[SentimentSource] = mapped_column(
        SqlEnum(SentimentSource, native_enum=False),
        index=True,
        nullable=False,
    )
    text_snippet: Mapped[str] = mapped_column(String(500), nullable=False)
    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sentiment_label: Mapped[Optional[SentimentLabel]] = mapped_column(
        SqlEnum(SentimentLabel, native_enum=False),
        index=True,
        nullable=True,
    )
    model_used: Mapped[Optional[SentimentModel]] = mapped_column(
        SqlEnum(SentimentModel, native_enum=False),
        index=True,
        nullable=True,
    )
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True, index=True)
    author: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.now(),
    )

    asset: Mapped[Optional["Asset"]] = relationship(back_populates="sentiment_records")
