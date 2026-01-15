"""Transaction endpoints."""
import time
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, Path

from ..database import db

router = APIRouter(prefix="/txs", tags=["transactions"])


@router.get("")
async def get_transactions(
    status: str = Query("all", pattern="^(all|success|failed)$"),
    contract_id: Optional[int] = Query(None),
    address: Optional[str] = Query(None, min_length=42, max_length=42),
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
    error_signature: Optional[str] = Query(None, min_length=10, max_length=10),
    limit: int = Query(50, ge=1, le=100),
    cursor: Optional[str] = Query(None),
    sort: str = Query("time_desc", pattern="^(time_desc|time_asc|gas_desc)$"),
) -> dict:
    """Get paginated transaction list with filtering."""
    # Build query
    conditions = []
    params = []
    param_idx = 1
    
    # Status filter
    if status == "success":
        conditions.append(f"t.status = ${param_idx}")
        params.append(1)
        param_idx += 1
    elif status == "failed":
        conditions.append(f"t.status = ${param_idx}")
        params.append(0)
        param_idx += 1
    
    # Contract filter
    if contract_id is not None:
        conditions.append(f"t.contract_id = ${param_idx}")
        params.append(contract_id)
        param_idx += 1
    
    # Address filter (from OR to)
    if address:
        conditions.append(f"(LOWER(t.from_address) = LOWER(${param_idx}) OR LOWER(t.to_address) = LOWER(${param_idx}))")
        params.append(address)
        param_idx += 1
    
    # Time range
    if start_ts:
        conditions.append(f"t.block_timestamp >= ${param_idx}")
        params.append(start_ts)
        param_idx += 1
    else:
        # Default to last 24 hours
        conditions.append(f"t.block_timestamp >= ${param_idx}")
        params.append(int(time.time()) - 86400)
        param_idx += 1
    
    if end_ts:
        conditions.append(f"t.block_timestamp <= ${param_idx}")
        params.append(end_ts)
        param_idx += 1
    
    # Error signature filter
    if error_signature:
        conditions.append(f"t.error_signature = ${param_idx}")
        params.append(error_signature.lower())
        param_idx += 1
    
    # Cursor-based pagination (simple offset for now)
    offset = 0
    if cursor:
        try:
            import base64
            import json
            cursor_data = json.loads(base64.b64decode(cursor))
            offset = cursor_data.get("offset", 0)
        except Exception:
            pass
    
    # Sort order
    if sort == "time_asc":
        order_by = "t.block_timestamp ASC"
    elif sort == "gas_desc":
        order_by = "(t.gas_used * t.gas_price) DESC"
    else:  # time_desc
        order_by = "t.block_timestamp DESC"
    
    # Build WHERE clause
    where_clause = " AND ".join(conditions) if conditions else "1=1"
    
    # Execute query
    query = f"""
        SELECT 
            t.hash,
            t.block_number,
            t.block_timestamp,
            t.from_address,
            t.to_address,
            t.value_wei,
            t.gas_used,
            t.gas_price,
            t.status,
            t.error_decoded,
            t.method_name,
            c.name as contract_name
        FROM txs t
        LEFT JOIN contracts c ON t.contract_id = c.id
        WHERE {where_clause}
        ORDER BY {order_by}
        LIMIT ${param_idx} OFFSET ${param_idx + 1}
    """
    
    params.extend([limit + 1, offset])  # Fetch one extra to check has_more
    
    rows = await db.fetch_all(query, *params)
    
    # Process results
    has_more = len(rows) > limit
    transactions = rows[:limit]
    
    # Format response
    result_txs = []
    for row in transactions:
        # Convert wei to eth for display
        value_eth = float(row["value_wei"]) / 1e18
        gas_price_gwei = float(row["gas_price"]) / 1e9
        
        result_txs.append({
            "hash": row["hash"],
            "block_number": row["block_number"],
            "block_timestamp": row["block_timestamp"],
            "from_address": row["from_address"],
            "to_address": row["to_address"],
            "contract_name": row["contract_name"],
            "value_eth": f"{value_eth:.6f}",
            "gas_used": row["gas_used"],
            "gas_price_gwei": f"{gas_price_gwei:.6f}",
            "status": "success" if row["status"] == 1 else "failed",
            "error_decoded": row["error_decoded"],
            "method_name": row["method_name"],
        })
    
    # Build next cursor
    next_cursor = None
    if has_more:
        import base64
        import json
        cursor_data = {"offset": offset + limit}
        next_cursor = base64.b64encode(json.dumps(cursor_data).encode()).decode()
    
    # Get total count
    count_query = f"SELECT COUNT(*) FROM txs t WHERE {where_clause}"
    count_row = await db.fetch_one(count_query, *params[:-2])  # Exclude limit/offset
    total = count_row["count"] if count_row else 0
    
    return {
        "transactions": result_txs,
        "pagination": {
            "total": total,
            "has_more": has_more,
            "next_cursor": next_cursor,
        },
        "filters_applied": {
            "status": status,
            "contract_id": contract_id,
            "address": address,
            "start_ts": start_ts,
            "end_ts": end_ts,
            "error_signature": error_signature,
        },
    }


@router.get("/{tx_hash}")
async def get_transaction_detail(
    tx_hash: str = Path(..., min_length=66, max_length=66),
) -> dict:
    """Get full transaction detail including trace if available."""
    # Fetch transaction
    tx = await db.fetch_one(
        """
        SELECT 
            t.*,
            c.id as contract_id,
            c.name as contract_name,
            c.address as contract_address
        FROM txs t
        LEFT JOIN contracts c ON t.contract_id = c.id
        WHERE t.hash = $1
        """,
        tx_hash,
    )
    
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    
    # Format transaction
    value_eth = float(tx["value_wei"]) / 1e18
    gas_price_gwei = float(tx["gas_price"]) / 1e9
    
    transaction = {
        "hash": tx["hash"],
        "block_number": tx["block_number"],
        "block_timestamp": tx["block_timestamp"],
        "from_address": tx["from_address"],
        "to_address": tx["to_address"],
        "value_wei": str(tx["value_wei"]),
        "value_eth": f"{value_eth:.6f}",
        "gas_used": tx["gas_used"],
        "gas_limit": tx["gas_used"],  # TODO: Get from tx data
        "gas_price_wei": str(tx["gas_price"]),
        "gas_price_gwei": f"{gas_price_gwei:.6f}",
        "status": "success" if tx["status"] == 1 else "failed",
        "method_id": tx["method_id"],
        "method_name": tx["method_name"],
        "has_trace": tx["has_trace"],
        "is_tentative": tx["is_tentative"],
    }
    
    # Add contract info
    if tx["contract_name"]:
        transaction["contract"] = {
            "id": tx["contract_id"],
            "name": tx["contract_name"],
            "address": tx["contract_address"],
        }
    
    # Add error info for failed txs
    if tx["status"] == 0:
        transaction["error"] = {
            "raw": tx["error_raw"],
            "signature": tx["error_signature"],
            "decoded": tx["error_decoded"],
            "params": tx["error_params"],
        }
    
    # Fetch trace if available
    trace = None
    if tx["has_trace"]:
        trace_row = await db.fetch_one(
            "SELECT * FROM tx_traces WHERE tx_id = $1 LIMIT 1",
            tx["id"],
        )
        if trace_row:
            trace = {
                "type": trace_row["trace_type"],
                "depth_max": trace_row["depth_max"],
                "call_count": trace_row["call_count"],
                "calls": trace_row["trace_json"],  # Full trace JSON
            }
    
    # Build explorer link
    links = {
        "explorer": f"https://explorer.mantle.xyz/tx/{tx_hash}",
    }
    
    return {
        "transaction": transaction,
        "trace": trace,
        "links": links,
    }
