from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models import Alert, AlertHistory, AlertType, Asset
from schemas.alert import AlertCreate, AlertRead, AlertUpdate
from schemas.alert_history import AlertHistoryRead

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


class AlertWithAsset(AlertRead):
    """Alert payload enriched with asset symbol."""

    asset_symbol: Optional[str] = None


class AlertHistoryWithContext(AlertHistoryRead):
    """History item enriched with alert metadata."""

    alert_type: str
    asset_symbol: Optional[str] = None


@router.get("/history", response_model=List[AlertHistoryWithContext])
async def get_alert_history(
    limit: int = Query(default=100, ge=1, le=500),
    alert_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> List[AlertHistoryWithContext]:
    """Return global alert history feed."""
    query = (
        select(AlertHistory, Alert.alert_type, Asset.symbol)
        .join(Alert, AlertHistory.alert_id == Alert.id)
        .outerjoin(Asset, Alert.asset_id == Asset.id)
        .order_by(AlertHistory.created_at.desc())
        .limit(limit)
    )
    if alert_id is not None:
        query = query.where(AlertHistory.alert_id == alert_id)
    rows = (await db.execute(query)).all()
    return [
        AlertHistoryWithContext(
            id=item.id,
            alert_id=item.alert_id,
            signal_id=item.signal_id,
            message=item.message,
            delivered=item.delivered,
            created_at=item.created_at,
            alert_type=alert_type.value,
            asset_symbol=symbol,
        )
        for item, alert_type, symbol in rows
    ]


@router.get("", response_model=List[AlertWithAsset])
async def list_alerts(
    is_enabled: Optional[bool] = Query(default=None),
    asset_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> List[AlertWithAsset]:
    """List alert rules with optional filtering."""
    query = select(Alert, Asset.symbol).outerjoin(Asset, Alert.asset_id == Asset.id).order_by(Alert.created_at.desc())
    if is_enabled is not None:
        query = query.where(Alert.is_enabled.is_(is_enabled))
    if asset_id is not None:
        query = query.where(Alert.asset_id == asset_id)
    rows = (await db.execute(query)).all()
    return [
        AlertWithAsset(
            id=alert.id,
            asset_id=alert.asset_id,
            alert_type=alert.alert_type,
            condition_json=alert.condition_json,
            delivery_method=alert.delivery_method,
            is_enabled=alert.is_enabled,
            last_triggered=alert.last_triggered,
            created_at=alert.created_at,
            asset_symbol=symbol,
        )
        for alert, symbol in rows
    ]


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(payload: AlertCreate, db: AsyncSession = Depends(get_db)) -> AlertRead:
    """Create one alert rule."""
    if _requires_asset(payload.alert_type) and payload.asset_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dieser Alert-Typ benoetigt ein Asset.",
        )
    if payload.asset_id is not None:
        await _assert_asset_exists(db, payload.asset_id)
    alert = Alert(
        asset_id=payload.asset_id,
        alert_type=payload.alert_type,
        condition_json=payload.condition_json,
        delivery_method=payload.delivery_method,
        is_enabled=payload.is_enabled,
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return AlertRead.model_validate(alert)


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> AlertRead:
    """Get one alert rule by id."""
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert nicht gefunden.")
    return AlertRead.model_validate(alert)


@router.get("/{alert_id}/history", response_model=List[AlertHistoryRead])
async def get_alert_history_by_id(
    alert_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> List[AlertHistoryRead]:
    """Get history entries for one alert."""
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert nicht gefunden.")
    query = (
        select(AlertHistory)
        .where(AlertHistory.alert_id == alert_id)
        .order_by(AlertHistory.created_at.desc())
        .limit(limit)
    )
    rows = list((await db.execute(query)).scalars().all())
    return [AlertHistoryRead.model_validate(item) for item in rows]


@router.patch("/{alert_id}", response_model=AlertRead)
async def update_alert(alert_id: int, payload: AlertUpdate, db: AsyncSession = Depends(get_db)) -> AlertRead:
    """Partially update an alert rule."""
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert nicht gefunden.")
    patch = payload.model_dump(exclude_unset=True)
    target_type = patch.get("alert_type", alert.alert_type)
    target_asset_id = patch.get("asset_id", alert.asset_id)
    if _requires_asset(target_type) and target_asset_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Dieser Alert-Typ benoetigt ein Asset.",
        )
    if "asset_id" in patch and patch["asset_id"] is not None:
        await _assert_asset_exists(db, int(patch["asset_id"]))
    for key, value in patch.items():
        setattr(alert, key, value)
    await db.commit()
    await db.refresh(alert)
    return AlertRead.model_validate(alert)


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(alert_id: int, db: AsyncSession = Depends(get_db)) -> None:
    """Delete one alert and its history."""
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert nicht gefunden.")
    await db.delete(alert)
    await db.commit()


async def _assert_asset_exists(db: AsyncSession, asset_id: int) -> None:
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset nicht gefunden.")


def _requires_asset(alert_type: AlertType) -> bool:
    return alert_type in {
        AlertType.SIGNAL_THRESHOLD,
        AlertType.PRICE_TARGET,
        AlertType.SENTIMENT_SHIFT,
    }
