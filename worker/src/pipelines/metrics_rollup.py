"""Metrics rollup pipeline for pre-aggregated dashboard metrics."""
import asyncio
import logging
import time
from typing import Optional

from ..config import config
from ..database import db
from ..state.worker_state import get_state, set_state

logger = logging.getLogger(__name__)


class MetricsRollup:
    """Aggregates transaction data into per-minute metrics."""

    def __init__(self) -> None:
        self.last_bucket_ts: int = 0

    async def run(self) -> None:
        """Run rollup loop indefinitely."""
        logger.info("Starting metrics rollup pipeline")
        
        # Load last processed bucket
        state = await get_state("metrics_rollup_cursor")
        if state:
            self.last_bucket_ts = state.get("last_bucket_ts", 0)
        
        while True:
            try:
                await self.rollup_cycle()
                await asyncio.sleep(config.poll_interval_rollup)
            except Exception as e:
                logger.error(f"Rollup cycle error: {e}")
                await asyncio.sleep(5)

    async def rollup_cycle(self) -> None:
        """Execute one rollup cycle."""
        # Calculate current bucket (minute-aligned)
        now = int(time.time())
        current_bucket = (now // 60) * 60
        
        # Target bucket is the completed minute (not current)
        target_bucket = current_bucket - 60
        
        # Skip if already processed
        if target_bucket <= self.last_bucket_ts:
            return
        
        # Check if we have data for this bucket
        data_check = await db.fetch_one(
            """
            SELECT COUNT(*) as count FROM txs 
            WHERE block_timestamp >= $1 AND block_timestamp < $2
            """,
            target_bucket,
            target_bucket + 60,
        )
        
        if not data_check or data_check["count"] == 0:
            logger.debug(f"No transactions for bucket {target_bucket}, skipping")
            # Still update cursor to avoid checking again
            self.last_bucket_ts = target_bucket
            await set_state("metrics_rollup_cursor", {"last_bucket_ts": target_bucket})
            return
        
        logger.info(f"Rolling up metrics for bucket {target_bucket}")
        
        # Aggregate basic metrics
        metrics = await db.fetch_one(
            """
            SELECT
                COUNT(*) as tx_count,
                COUNT(*) FILTER (WHERE status = 0) as tx_failed_count,
                SUM(gas_used) as gas_used_total,
                AVG(gas_price) as gas_price_avg,
                COUNT(DISTINCT block_number) as block_count,
                COUNT(DISTINCT from_address) as unique_senders
            FROM txs
            WHERE block_timestamp >= $1 AND block_timestamp < $2
            """,
            target_bucket,
            target_bucket + 60,
        )
        
        if not metrics:
            logger.warning(f"Failed to aggregate metrics for bucket {target_bucket}")
            return
        
        # Aggregate top errors
        top_errors_rows = await db.fetch_all(
            """
            SELECT 
                error_signature,
                error_decoded,
                COUNT(*) as count
            FROM txs
            WHERE status = 0
            AND block_timestamp >= $1 
            AND block_timestamp < $2
            AND error_signature IS NOT NULL
            GROUP BY error_signature, error_decoded
            ORDER BY count DESC
            LIMIT 5
            """,
            target_bucket,
            target_bucket + 60,
        )
        
        # Format top errors as JSON array
        top_errors = [
            {
                "signature": row["error_signature"],
                "name": row["error_decoded"] or "Unknown",
                "count": row["count"],
            }
            for row in top_errors_rows
        ]
        
        # Insert or update metrics
        await db.execute(
            """
            INSERT INTO metrics_minute (
                bucket_ts,
                tx_count,
                tx_failed_count,
                gas_used_total,
                gas_price_avg,
                block_count,
                unique_senders,
                top_errors
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (bucket_ts) 
            DO UPDATE SET
                tx_count = $2,
                tx_failed_count = $3,
                gas_used_total = $4,
                gas_price_avg = $5,
                block_count = $6,
                unique_senders = $7,
                top_errors = $8
            """,
            target_bucket,
            metrics["tx_count"] or 0,
            metrics["tx_failed_count"] or 0,
            metrics["gas_used_total"] or 0,
            int(metrics["gas_price_avg"] or 0),
            metrics["block_count"] or 0,
            metrics["unique_senders"] or 0,
            top_errors,
        )
        
        # Update cursor
        self.last_bucket_ts = target_bucket
        await set_state("metrics_rollup_cursor", {"last_bucket_ts": target_bucket})
        
        logger.info(
            f"Rolled up metrics: {metrics['tx_count']} txs, "
            f"{metrics['tx_failed_count']} failed, "
            f"{metrics['block_count']} blocks"
        )


rollup = MetricsRollup()
