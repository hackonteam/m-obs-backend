"""Metrics endpoints for dashboard."""
import time
from fastapi import APIRouter, Query, HTTPException

from ..database import db

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/overview")
async def get_metrics_overview(
    start_ts: int = Query(None),
    end_ts: int = Query(None),
    resolution: str = Query("minute", pattern="^(minute|hour|day)$"),
) -> dict:
    """
    Get dashboard summary metrics for specified time range.
    
    Query Parameters:
    - start_ts: Unix timestamp range start (default: now - 1 hour)
    - end_ts: Unix timestamp range end (default: now)
    - resolution: minute/hour/day (default: minute)
    """
    # Default time range: last hour
    now = int(time.time())
    if not end_ts:
        end_ts = now
    if not start_ts:
        start_ts = end_ts - 3600  # 1 hour ago
    
    # Validate time range
    if start_ts >= end_ts:
        raise HTTPException(status_code=400, detail="start_ts must be before end_ts")
    
    if end_ts - start_ts > 2592000:  # 30 days
        raise HTTPException(status_code=400, detail="Time range cannot exceed 30 days")
    
    # Align timestamps to minute boundaries
    start_ts = (start_ts // 60) * 60
    end_ts = (end_ts // 60) * 60
    
    # Fetch metrics for the period
    metrics_rows = await db.fetch_all(
        """
        SELECT * FROM metrics_minute
        WHERE bucket_ts >= $1 AND bucket_ts <= $2
        ORDER BY bucket_ts ASC
        """,
        start_ts,
        end_ts,
    )
    
    if not metrics_rows:
        # Return empty response if no data
        return {
            "period": {
                "start_ts": start_ts,
                "end_ts": end_ts,
                "resolution": resolution,
            },
            "summary": {
                "tx_total": 0,
                "tx_failed": 0,
                "failure_rate": 0.0,
                "gas_used_total": "0",
                "gas_price_avg_gwei": 0.0,
                "blocks_processed": 0,
                "unique_senders": 0,
            },
            "series": {
                "timestamps": [],
                "tx_count": [],
                "tx_failed_count": [],
                "gas_price_avg": [],
            },
            "top_errors": [],
            "generated_at": now,
        }
    
    # Calculate summary
    tx_total = sum(row["tx_count"] for row in metrics_rows)
    tx_failed = sum(row["tx_failed_count"] for row in metrics_rows)
    failure_rate = (tx_failed / tx_total * 100) if tx_total > 0 else 0.0
    
    gas_used_total = sum(int(row["gas_used_total"]) for row in metrics_rows)
    
    # Calculate average gas price (weighted by tx count)
    total_weighted_gas = sum(
        int(row["gas_price_avg"]) * row["tx_count"] 
        for row in metrics_rows
    )
    gas_price_avg = (total_weighted_gas / tx_total) if tx_total > 0 else 0
    gas_price_avg_gwei = gas_price_avg / 1e9
    
    blocks_processed = sum(row["block_count"] for row in metrics_rows)
    
    # Unique senders (approximate - take max)
    unique_senders = max((row["unique_senders"] for row in metrics_rows), default=0)
    
    # Build time series
    timestamps = []
    tx_counts = []
    tx_failed_counts = []
    gas_prices = []
    
    for row in metrics_rows:
        timestamps.append(row["bucket_ts"])
        tx_counts.append(row["tx_count"])
        tx_failed_counts.append(row["tx_failed_count"])
        gas_prices.append(row["gas_price_avg"])
    
    # Aggregate top errors across the period
    error_map: dict[str, dict] = {}
    
    for row in metrics_rows:
        top_errors = row.get("top_errors", [])
        if isinstance(top_errors, list):
            for error in top_errors:
                sig = error.get("signature")
                if sig:
                    if sig not in error_map:
                        error_map[sig] = {
                            "signature": sig,
                            "name": error.get("name", "Unknown"),
                            "count": 0,
                        }
                    error_map[sig]["count"] += error.get("count", 0)
    
    # Sort and take top 5
    top_errors = sorted(
        error_map.values(),
        key=lambda x: x["count"],
        reverse=True,
    )[:5]
    
    return {
        "period": {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "resolution": resolution,
        },
        "summary": {
            "tx_total": tx_total,
            "tx_failed": tx_failed,
            "failure_rate": round(failure_rate, 2),
            "gas_used_total": str(gas_used_total),
            "gas_price_avg_gwei": round(gas_price_avg_gwei, 6),
            "blocks_processed": blocks_processed,
            "unique_senders": unique_senders,
        },
        "series": {
            "timestamps": timestamps,
            "tx_count": tx_counts,
            "tx_failed_count": tx_failed_counts,
            "gas_price_avg": gas_prices,
        },
        "top_errors": top_errors,
        "generated_at": now,
    }
