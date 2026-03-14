from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import AggregationSource, AggregationTimeframe

if TYPE_CHECKING:
    from models.asset import Asset


class AggregatedSentiment(Base):
    """Hourly/daily aggregated sentiment metrics per asset."""

    __tablename__ = "aggregated_sentiments"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "period_start",
            "timeframe",
            "source",
            name="uq_aggregated_sentiment_window",
        ),
        CheckConstraint("avg_score >= -1.0 AND avg_score <= 1.0", name="ck_agg_avg_score_range"),
        CheckConstraint("weighted_score >= -1.0 AND weighted_score <= 1.0", name="ck_agg_weighted_score_range"),
        CheckConstraint("positive_count >= 0", name="ck_agg_positive_count_nonnegative"),
        CheckConstraint("negative_count >= 0", name="ck_agg_negative_count_nonnegative"),
        CheckConstraint("neutral_count >= 0", name="ck_agg_neutral_count_nonnegative"),
        CheckConstraint("total_mentions >= 0", name="ck_agg_total_mentions_nonnegative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timeframe: Mapped[AggregationTimeframe] = mapped_column(
        SqlEnum(AggregationTimeframe, native_enum=False),
        index=True,
        nullable=False,
    )
    avg_score: Mapped[float] = mapped_column(Float, nullable=False)
    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    neutral_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_mentions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    source: Mapped[AggregationSource] = mapped_column(
        SqlEnum(AggregationSource, native_enum=False),
        index=True,
        nullable=False,
    )
    weighted_score: Mapped[float] = mapped_column(Float, nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="aggregated_sentiments")
