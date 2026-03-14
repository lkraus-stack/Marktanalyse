from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import AssetType, WatchStatus


class AssetCreate(BaseModel):
    """Payload to create a tracked asset."""

    symbol: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=120)
    asset_type: AssetType
    exchange: Optional[str] = Field(default=None, max_length=80)
    watch_status: WatchStatus = WatchStatus.WATCHLIST
    watch_notes: Optional[str] = Field(default=None, max_length=255)
    is_active: bool = True


class AssetUpdate(BaseModel):
    """Payload to partially update an asset."""

    symbol: Optional[str] = Field(default=None, min_length=1, max_length=20)
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    asset_type: Optional[AssetType] = None
    exchange: Optional[str] = Field(default=None, max_length=80)
    watch_status: Optional[WatchStatus] = None
    watch_notes: Optional[str] = Field(default=None, max_length=255)
    is_active: Optional[bool] = None


class AssetRead(BaseModel):
    """Serialized asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    symbol: str
    name: str
    asset_type: AssetType
    exchange: Optional[str]
    watch_status: WatchStatus
    watch_notes: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime
