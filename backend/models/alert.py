from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, ForeignKey, Integer, JSON, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base
from models.enums import AlertType, DeliveryMethod

if TYPE_CHECKING:
    from models.alert_history import AlertHistory
    from models.asset import Asset


class Alert(Base):
    """Configurable alert definition."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    alert_type: Mapped[AlertType] = mapped_column(
        SqlEnum(AlertType, native_enum=False),
        index=True,
        nullable=False,
    )
    condition_json: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    delivery_method: Mapped[DeliveryMethod] = mapped_column(
        SqlEnum(DeliveryMethod, native_enum=False),
        index=True,
        nullable=False,
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        index=True,
    )
    last_triggered: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
        server_default=func.now(),
    )

    asset: Mapped[Optional["Asset"]] = relationship(back_populates="alerts")
    history: Mapped[List["AlertHistory"]] = relationship(back_populates="alert", cascade="all, delete-orphan")
