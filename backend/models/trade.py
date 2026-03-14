from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import BrokerName, TradeSide, TradeStatus

if TYPE_CHECKING:
    from models.asset import Asset
    from models.trading_signal import TradingSignal


class Trade(Base):
    """Executed or pending paper-trading order."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    broker: Mapped[BrokerName] = mapped_column(
        SqlEnum(BrokerName, native_enum=False),
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    side: Mapped[TradeSide] = mapped_column(SqlEnum(TradeSide, native_enum=False), nullable=False, index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    status: Mapped[TradeStatus] = mapped_column(SqlEnum(TradeStatus, native_enum=False), nullable=False, index=True)
    signal_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("trading_signals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_paper: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        index=True,
    )
    is_live: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
    filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    asset: Mapped[Optional["Asset"]] = relationship(back_populates="trades")
    signal: Mapped[Optional["TradingSignal"]] = relationship(back_populates="trades")
