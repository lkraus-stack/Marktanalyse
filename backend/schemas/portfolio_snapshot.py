from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from models.enums import BrokerName


class PortfolioSnapshotCreate(BaseModel):
    """Payload to create one portfolio snapshot."""

    broker: BrokerName = BrokerName.ALPACA_PAPER
    total_value: Decimal = Field(max_digits=20, decimal_places=8)
    cash: Decimal = Field(max_digits=20, decimal_places=8)
    positions_value: Decimal = Field(max_digits=20, decimal_places=8)
    daily_pnl: Decimal = Field(max_digits=20, decimal_places=8)
    total_pnl: Decimal = Field(max_digits=20, decimal_places=8)
    snapshot_at: datetime


class PortfolioSnapshotRead(BaseModel):
    """Serialized portfolio snapshot."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    broker: BrokerName
    total_value: Decimal
    cash: Decimal
    positions_value: Decimal
    daily_pnl: Decimal
    total_pnl: Decimal
    snapshot_at: datetime
