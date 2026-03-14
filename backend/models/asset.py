from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import AssetType, WatchStatus

if TYPE_CHECKING:
    from models.aggregated_sentiment import AggregatedSentiment
    from models.alert import Alert
    from models.price_data import PriceData
    from models.sentiment_record import SentimentRecord
    from models.trade import Trade
    from models.trading_signal import TradingSignal


class Asset(Base):
    """Tracked stock or crypto asset."""

    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        SqlEnum(AssetType, native_enum=False),
        index=True,
        nullable=False,
    )
    exchange: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    watch_status: Mapped[WatchStatus] = mapped_column(
        SqlEnum(WatchStatus, native_enum=False, values_callable=lambda enum: [item.value for item in enum]),
        nullable=False,
        default=WatchStatus.NONE,
        server_default=WatchStatus.NONE.value,
        index=True,
    )
    watch_notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    price_data: Mapped[List["PriceData"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    sentiment_records: Mapped[List["SentimentRecord"]] = relationship(back_populates="asset")
    aggregated_sentiments: Mapped[List["AggregatedSentiment"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )
    trading_signals: Mapped[List["TradingSignal"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    alerts: Mapped[List["Alert"]] = relationship(back_populates="asset")
    trades: Mapped[List["Trade"]] = relationship(back_populates="asset")
