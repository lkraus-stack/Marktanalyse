from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SqlEnum, Float, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import PriceTimeframe

if TYPE_CHECKING:
    from models.asset import Asset


class PriceData(Base):
    """OHLCV market price data."""

    __tablename__ = "price_data"
    __table_args__ = (
        UniqueConstraint("asset_id", "timestamp", "timeframe", name="uq_price_data_asset_timestamp_timeframe"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[float] = mapped_column(Float, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    timeframe: Mapped[PriceTimeframe] = mapped_column(
        SqlEnum(PriceTimeframe, native_enum=False),
        index=True,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(50), index=True, nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="price_data")
