from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.alert import Alert
    from models.trading_signal import TradingSignal


class AlertHistory(Base):
    """Delivery log for triggered alerts."""

    __tablename__ = "alert_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True, nullable=False)
    signal_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("trading_signals.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    message: Mapped[str] = mapped_column(String(1000), nullable=False)
    delivered: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.now(),
    )

    alert: Mapped["Alert"] = relationship(back_populates="history")
    signal: Mapped[Optional["TradingSignal"]] = relationship(back_populates="alert_history")
