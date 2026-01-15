"""Provider health endpoints."""
import time
from fastapi import APIRouter, Query, HTTPException

from ..database import db
from ..models.schemas import ProvidersResponse, Provider, ProviderStats

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("/health", response_model=ProvidersResponse)
async def get_providers_health(
    hours: int = Query(24, ge=1, le=168),
    endpoint_id: int | None = Query(None),
) -> ProvidersResponse:
    """Get current and historical provider health data."""
    # Fetch providers
    if endpoint_id:
        provider_rows = await db.fetch_all(
            "SELECT * FROM rpc_endpoints WHERE id = $1",
            endpoint_id,
        )
    else:
        provider_rows = await db.fetch_all(
            "SELECT * FROM rpc_endpoints WHERE is_active = true ORDER BY score DESC"
        )
    
    if not provider_rows:
        raise HTTPException(status_code=404, detail="Provider not found")
    
    # Build provider list with stats
    providers = []
    for row in provider_rows:
        # Calculate stats from recent samples
        stats_row = await db.fetch_one(
            """
            SELECT 
                AVG(latency_ms) as avg_latency_ms,
                AVG(CASE WHEN is_success THEN 1.0 ELSE 0.0 END) * 100 as success_rate,
                MAX(block_number) as current_block
            FROM rpc_health_samples
            WHERE endpoint_id = $1
            AND sampled_at >= $2
            """,
            row["id"],
            int(time.time()) - (hours * 3600),
        )
        
        stats = None
        if stats_row and stats_row["avg_latency_ms"] is not None:
            stats = ProviderStats(
                avg_latency_ms=int(stats_row["avg_latency_ms"]),
                success_rate=round(float(stats_row["success_rate"]), 2),
                current_block=stats_row["current_block"] or 0,
            )
        
        providers.append(
            Provider(
                id=row["id"],
                name=row["name"],
                url=row["url"],
                status=row["status"],
                score=row["score"],
                supports_traces=row["supports_traces"],
                last_probe_at=row["last_probe_at"],
                stats=stats,
            )
        )
    
    # Fetch history if requested
    history = None
    if hours <= 48:  # Only include history for shorter windows
        # Get time series data
        sample_rows = await db.fetch_all(
            """
            SELECT endpoint_id, sampled_at, latency_ms, is_success
            FROM rpc_health_samples
            WHERE sampled_at >= $1
            ORDER BY sampled_at ASC
            """,
            int(time.time()) - (hours * 3600),
        )
        
        # Group by endpoint
        series_data: dict[int, dict] = {}
        timestamps: set[int] = set()
        
        for row in sample_rows:
            ep_id = row["endpoint_id"]
            if ep_id not in series_data:
                series_data[ep_id] = {"latency_ms": [], "success": []}
            
            timestamps.add(row["sampled_at"])
            series_data[ep_id]["latency_ms"].append(row["latency_ms"])
            series_data[ep_id]["success"].append(row["is_success"])
        
        history = {
            "timestamps": sorted(timestamps),
            "series": {str(k): v for k, v in series_data.items()},
        }
    
    return ProvidersResponse(
        providers=providers,
        history=history,
        generated_at=int(time.time()),
    )
