"""Alert management endpoints."""
import time
from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..database import db

router = APIRouter(prefix="/alerts", tags=["alerts"])


class CreateAlertRequest(BaseModel):
    """Request to create an alert."""
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    alert_type: str = Field(..., regex="^(failure_rate|gas_spike|provider_down|custom)$")
    conditions: dict = Field(default_factory=dict)
    threshold: float
    window_minutes: int = Field(5, ge=1, le=1440)
    cooldown_minutes: int = Field(15, ge=1, le=1440)
    severity: str = Field("warning", regex="^(info|warning|critical)$")
    contract_ids: list[int] = Field(default_factory=list)


class UpdateAlertRequest(BaseModel):
    """Request to update an alert."""
    name: Optional[str] = Field(None, min_length=1, max_length=128)
    description: Optional[str] = None
    threshold: Optional[float] = None
    window_minutes: Optional[int] = Field(None, ge=1, le=1440)
    cooldown_minutes: Optional[int] = Field(None, ge=1, le=1440)
    severity: Optional[str] = Field(None, regex="^(info|warning|critical)$")
    is_enabled: Optional[bool] = None
    contract_ids: Optional[list[int]] = None


@router.get("")
async def get_alerts(
    include_events: bool = Query(False),
    events_limit: int = Query(10, ge=1, le=50),
    enabled_only: bool = Query(False),
) -> dict:
    """Get all alert rules and optionally recent events."""
    # Build query
    where_clause = "is_enabled = true" if enabled_only else "1=1"
    
    alerts = await db.fetch_all(
        f"SELECT * FROM alerts WHERE {where_clause} ORDER BY created_at DESC"
    )
    
    # Format response
    result_alerts = []
    
    for alert in alerts:
        alert_data = {
            "id": alert["id"],
            "name": alert["name"],
            "description": alert["description"],
            "alert_type": alert["alert_type"],
            "conditions": alert["conditions"],
            "threshold": float(alert["threshold"]),
            "window_minutes": alert["window_minutes"],
            "cooldown_minutes": alert["cooldown_minutes"],
            "severity": alert["severity"],
            "is_enabled": alert["is_enabled"],
            "contract_ids": alert["contract_ids"] or [],
            "last_triggered_at": alert["last_triggered_at"],
            "created_at": alert["created_at"],
        }
        
        # Optionally include recent events
        if include_events:
            events = await db.fetch_all(
                """
                SELECT * FROM alert_events
                WHERE alert_id = $1
                ORDER BY triggered_at DESC
                LIMIT $2
                """,
                alert["id"],
                events_limit,
            )
            
            alert_data["events"] = [
                {
                    "id": evt["id"],
                    "triggered_at": evt["triggered_at"],
                    "severity": evt["severity"],
                    "value_observed": float(evt["value_observed"]),
                    "threshold": float(evt["threshold"]),
                    "context": evt["context"],
                    "acknowledged_at": evt["acknowledged_at"],
                    "acknowledged_by": evt["acknowledged_by"],
                }
                for evt in events
            ]
        
        result_alerts.append(alert_data)
    
    # Calculate summary
    total = len(alerts)
    enabled = sum(1 for a in alerts if a["is_enabled"])
    
    # Count alerts triggered in last 24h
    triggered_24h_count = await db.fetch_one(
        """
        SELECT COUNT(DISTINCT alert_id) as count
        FROM alert_events
        WHERE triggered_at >= $1
        """,
        int(time.time()) - 86400,
    )
    
    triggered_24h = triggered_24h_count["count"] if triggered_24h_count else 0
    
    return {
        "alerts": result_alerts,
        "summary": {
            "total": total,
            "enabled": enabled,
            "triggered_24h": triggered_24h,
        },
    }


@router.post("")
async def create_alert(request: CreateAlertRequest) -> dict:
    """Create a new alert rule."""
    now = int(time.time())
    
    # Insert alert
    row = await db.fetch_one(
        """
        INSERT INTO alerts (
            name, description, alert_type, conditions, threshold,
            window_minutes, cooldown_minutes, severity, is_enabled,
            contract_ids, created_at, updated_at
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, true, $9, $10, $10)
        RETURNING *
        """,
        request.name,
        request.description,
        request.alert_type,
        request.conditions,
        request.threshold,
        request.window_minutes,
        request.cooldown_minutes,
        request.severity,
        request.contract_ids,
        now,
    )
    
    return {
        "alert": {
            "id": row["id"],
            "name": row["name"],
            "alert_type": row["alert_type"],
            "threshold": float(row["threshold"]),
            "is_enabled": row["is_enabled"],
            "created_at": row["created_at"],
        }
    }


@router.patch("/{alert_id}")
async def update_alert(alert_id: int, request: UpdateAlertRequest) -> dict:
    """Update an existing alert rule."""
    # Check if alert exists
    existing = await db.fetch_one(
        "SELECT * FROM alerts WHERE id = $1",
        alert_id,
    )
    
    if not existing:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Build update query
    updates = []
    params = []
    param_idx = 1
    
    if request.name is not None:
        updates.append(f"name = ${param_idx}")
        params.append(request.name)
        param_idx += 1
    
    if request.description is not None:
        updates.append(f"description = ${param_idx}")
        params.append(request.description)
        param_idx += 1
    
    if request.threshold is not None:
        updates.append(f"threshold = ${param_idx}")
        params.append(request.threshold)
        param_idx += 1
    
    if request.window_minutes is not None:
        updates.append(f"window_minutes = ${param_idx}")
        params.append(request.window_minutes)
        param_idx += 1
    
    if request.cooldown_minutes is not None:
        updates.append(f"cooldown_minutes = ${param_idx}")
        params.append(request.cooldown_minutes)
        param_idx += 1
    
    if request.severity is not None:
        updates.append(f"severity = ${param_idx}")
        params.append(request.severity)
        param_idx += 1
    
    if request.is_enabled is not None:
        updates.append(f"is_enabled = ${param_idx}")
        params.append(request.is_enabled)
        param_idx += 1
    
    if request.contract_ids is not None:
        updates.append(f"contract_ids = ${param_idx}")
        params.append(request.contract_ids)
        param_idx += 1
    
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Add updated_at
    now = int(time.time())
    updates.append(f"updated_at = ${param_idx}")
    params.append(now)
    param_idx += 1
    
    # Add alert_id for WHERE clause
    params.append(alert_id)
    
    # Execute update
    query = f"""
        UPDATE alerts
        SET {', '.join(updates)}
        WHERE id = ${param_idx}
        RETURNING *
    """
    
    row = await db.fetch_one(query, *params)
    
    return {
        "alert": {
            "id": row["id"],
            "name": row["name"],
            "threshold": float(row["threshold"]),
            "is_enabled": row["is_enabled"],
            "updated_at": row["updated_at"],
        }
    }


@router.delete("/{alert_id}")
async def delete_alert(alert_id: int) -> dict:
    """Delete an alert rule."""
    # Check if exists
    existing = await db.fetch_one(
        "SELECT id FROM alerts WHERE id = $1",
        alert_id,
    )
    
    if not existing:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    # Delete (will cascade to alert_events)
    await db.execute(
        "DELETE FROM alerts WHERE id = $1",
        alert_id,
    )
    
    return {"message": "Alert deleted"}
