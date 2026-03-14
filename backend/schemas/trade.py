from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import BrokerName, TradeSide, TradeStatus


class TradeCreate(BaseModel):
    """Payload to create one paper trade record."""

    asset_id: Optional[int] = None
    broker: BrokerName = BrokerName.ALPACA_PAPER
    order_id: Optional[str] = Field(default=None, max_length=120)
    side: TradeSide
    quantity: Decimal = Field(max_digits=20, decimal_places=8)
    price: Decimal = Field(max_digits=20, decimal_places=8)
    total_value: Decimal = Field(max_digits=20, decimal_places=8)
    status: TradeStatus
    signal_id: Optional[int] = None
    is_paper: bool = True
    is_live: bool = False
    filled_at: Optional[datetime] = None
    notes: Optional[str] = None


class TradeUpdate(BaseModel):
    """Payload to partially update one trade."""

    order_id: Optional[str] = Field(default=None, max_length=120)
    status: Optional[TradeStatus] = None
    filled_at: Optional[datetime] = None
    notes: Optional[str] = None


class TradeRead(BaseModel):
    """Serialized trade response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: Optional[int]
    broker: BrokerName
    order_id: Optional[str]
    side: TradeSide
    quantity: Decimal
    price: Decimal
    total_value: Decimal
    status: TradeStatus
    signal_id: Optional[int]
    is_paper: bool
    is_live: bool
    created_at: datetime
    filled_at: Optional[datetime]
    notes: Optional[str]
