from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SqlEnum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import SignalType

if TYPE_CHECKING:
    from models.alert_history import AlertHistory
    from models.asset import Asset
    from models.trade import Trade


class TradingSignal(Base):
    """Generated buy/sell/hold signal."""

    __tablename__ = "trading_signals"
    __table_args__ = (
        CheckConstraint("strength >= 0.0 AND strength <= 100.0", name="ck_signal_strength_range"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"), index=True, nullable=False)
    signal_type: Mapped[SignalType] = mapped_column(
        SqlEnum(SignalType, native_enum=False),
        index=True,
        nullable=False,
    )
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    composite_score: Mapped[float] = mapped_column(Float, nullable=False)
    price_at_signal: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    sentiment_component: Mapped[float] = mapped_column(Float, nullable=False)
    technical_component: Mapped[float] = mapped_column(Float, nullable=False)
    volume_component: Mapped[float] = mapped_column(Float, nullable=False)
    momentum_component: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    execution_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    strategy_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
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
        index=True,
        server_default=func.now(),
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    asset: Mapped["Asset"] = relationship(back_populates="trading_signals")
    alert_history: Mapped[List["AlertHistory"]] = relationship(back_populates="signal")
    trades: Mapped[List["Trade"]] = relationship(back_populates="signal")
