"""Worker state persistence helpers."""
import json
import time
from typing import Any, Optional

from ..database import db


async def get_state(key: str) -> Optional[dict]:
    """Get state value by key."""
    row = await db.fetch_one(
        "SELECT value FROM worker_state WHERE key = $1",
        key,
    )
    if row and row["value"]:
        # Parse JSON string back to dict
        value_str = row["value"]
        return json.loads(value_str) if isinstance(value_str, str) else value_str
    return None


async def set_state(key: str, value: dict) -> None:
    """Set state value."""
    await db.execute(
        """
        INSERT INTO worker_state (key, value, updated_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (key) 
        DO UPDATE SET value = $2, updated_at = $3
        """,
        key,
        json.dumps(value),
        int(time.time()),
    )


async def get_last_scanned_block() -> dict:
    """Get last scanned block info."""
    state = await get_state("last_scanned_block")
    return state or {"block_number": 0, "block_hash": "0x0"}


async def set_last_scanned_block(block_number: int, block_hash: str) -> None:
    """Update last scanned block."""
    await set_state(
        "last_scanned_block",
        {
            "block_number": block_number,
            "block_hash": block_hash,
            "timestamp": int(time.time()),
        },
    )
