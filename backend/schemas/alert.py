from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.enums import AlertType, DeliveryMethod


class AlertCreate(BaseModel):
    """Payload to create an alert rule."""

    asset_id: Optional[int] = None
    alert_type: AlertType
    condition_json: Dict[str, Any]
    delivery_method: DeliveryMethod
    is_enabled: bool = True


class AlertUpdate(BaseModel):
    """Payload to partially update an alert rule."""

    asset_id: Optional[int] = None
    alert_type: Optional[AlertType] = None
    condition_json: Optional[Dict[str, Any]] = None
    delivery_method: Optional[DeliveryMethod] = None
    is_enabled: Optional[bool] = None
    last_triggered: Optional[datetime] = None


class AlertRead(BaseModel):
    """Serialized alert rule response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_id: Optional[int]
    alert_type: AlertType
    condition_json: Dict[str, Any]
    delivery_method: DeliveryMethod
    is_enabled: bool
    last_triggered: Optional[datetime]
    created_at: datetime
