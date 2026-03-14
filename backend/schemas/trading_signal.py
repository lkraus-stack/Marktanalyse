from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import SignalType


class TradingSignalCreate(BaseModel):
    """Payload to create a generated trading signal."""

    asset_id: int
    signal_type: SignalType
    strength: float = Field(ge=0.0, le=100.0)
    composite_score: float
    price_at_signal: Decimal = Field(max_digits=20, decimal_places=8)
    sentiment_component: float
    technical_component: float
    volume_component: float
    momentum_component: float = 0.0
    reasoning: str = Field(min_length=1)
    execution_id: Optional[str] = Field(default=None, max_length=100)
    strategy_id: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = True
    expires_at: Optional[datetime] = None


class TradingSignalUpdate(BaseModel):
    """Payload to partially update a trading signal."""

    signal_type: Optional[SignalType] = None
    strength: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    composite_score: Optional[float] = None
    price_at_signal: Optional[Decimal] = Field(default=None, max_digits=20, decimal_places=8)
    sentiment_component: Optional[float] = None
    technical_component: Optional[float] = None
    volume_component: Optional[float] = None
    momentum_component: Optional[float] = None
    reasoning: Optional[str] = Field(default=None, min_length=1)
    execution_id: Optional[str] = Field(default=None, max_length=100)
    strategy_id: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


class TradingSignalRead(BaseModel):
    """Serialized trading signal response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: int
    signal_type: SignalType
    strength: float
    composite_score: float
    price_at_signal: Decimal
    sentiment_component: float
    technical_component: float
    volume_component: float
    momentum_component: float
    reasoning: str
    execution_id: Optional[str]
    strategy_id: Optional[str]
    is_active: bool
    created_at: datetime
    expires_at: Optional[datetime]
