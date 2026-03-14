from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import PriceTimeframe


class PriceDataCreate(BaseModel):
    """Payload to store a new OHLCV entry."""

    asset_id: int
    open: Decimal = Field(max_digits=20, decimal_places=8)
    high: Decimal = Field(max_digits=20, decimal_places=8)
    low: Decimal = Field(max_digits=20, decimal_places=8)
    close: Decimal = Field(max_digits=20, decimal_places=8)
    volume: float
    timestamp: datetime
    timeframe: PriceTimeframe
    source: str = Field(min_length=1, max_length=50)


class PriceDataUpdate(BaseModel):
    """Payload to partially update OHLCV data."""

    open: Optional[Decimal] = Field(default=None, max_digits=20, decimal_places=8)
    high: Optional[Decimal] = Field(default=None, max_digits=20, decimal_places=8)
    low: Optional[Decimal] = Field(default=None, max_digits=20, decimal_places=8)
    close: Optional[Decimal] = Field(default=None, max_digits=20, decimal_places=8)
    volume: Optional[float] = None
    timestamp: Optional[datetime] = None
    timeframe: Optional[PriceTimeframe] = None
    source: Optional[str] = Field(default=None, min_length=1, max_length=50)


class PriceDataRead(BaseModel):
    """Serialized OHLCV response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: float
    timestamp: datetime
    timeframe: PriceTimeframe
    source: str
