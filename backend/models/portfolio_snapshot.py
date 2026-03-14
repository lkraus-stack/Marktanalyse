from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum as SqlEnum, Integer, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.enums import BrokerName


class PortfolioSnapshot(Base):
    """Periodic snapshot of broker portfolio state."""

    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    broker: Mapped[BrokerName] = mapped_column(
        SqlEnum(BrokerName, native_enum=False),
        nullable=False,
        index=True,
    )
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    positions_value: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    daily_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )
