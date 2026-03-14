from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AlertHistoryCreate(BaseModel):
    """Payload to store one triggered alert event."""

    alert_id: int
    signal_id: Optional[int] = None
    message: str = Field(min_length=1, max_length=1000)
    delivered: bool = False


class AlertHistoryUpdate(BaseModel):
    """Payload to partially update a trigger record."""

    signal_id: Optional[int] = None
    message: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    delivered: Optional[bool] = None


class AlertHistoryRead(BaseModel):
    """Serialized alert history response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_id: int
    signal_id: Optional[int]
    message: str
    delivered: bool
    created_at: datetime
