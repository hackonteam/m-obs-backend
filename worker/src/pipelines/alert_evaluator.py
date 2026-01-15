"""Alert evaluation pipeline."""
import asyncio
import logging
import time
from typing import Optional

from ..config import config
from ..database import db
from ..state.worker_state import get_state, set_state

logger = logging.getLogger(__name__)


class AlertEvaluator:
    """Evaluates alert rules and generates events."""

    def __init__(self) -> None:
        self.last_eval_ts: int = 0

    async def run(self) -> None:
        """Run evaluator loop indefinitely."""
        logger.info("Starting alert evaluator pipeline")
        
        # Load last eval timestamp
        state = await get_state("alert_eval_cursor")
        if state:
            self.last_eval_ts = state.get("last_eval_ts", 0)
        
        while True:
            try:
                await self.eval_cycle()
                await asyncio.sleep(config.poll_interval_alerts)
            except Exception as e:
                logger.error(f"Alert eval cycle error: {e}")
                await asyncio.sleep(5)

    async def eval_cycle(self) -> None:
        """Execute one evaluation cycle."""
        now = int(time.time())
        
        # Load all enabled alerts
        alerts = await db.fetch_all(
            "SELECT * FROM alerts WHERE is_enabled = true"
        )
        
        if not alerts:
            return
        
        logger.debug(f"Evaluating {len(alerts)} alerts")
        
        for alert in alerts:
            try:
                await self.evaluate_alert(alert, now)
            except Exception as e:
                logger.error(f"Failed to evaluate alert {alert['id']}: {e}")
        
        # Update cursor
        self.last_eval_ts = now
        await set_state("alert_eval_cursor", {"last_eval_ts": now})

    async def evaluate_alert(self, alert: dict, now: int) -> None:
        """Evaluate single alert rule."""
        alert_id = alert["id"]
        alert_type = alert["alert_type"]
        threshold = float(alert["threshold"])
        window_minutes = alert["window_minutes"]
        cooldown_minutes = alert["cooldown_minutes"]
        last_triggered_at = alert.get("last_triggered_at")
        
        # Check cooldown
        if last_triggered_at:
            cooldown_seconds = cooldown_minutes * 60
            if now - last_triggered_at < cooldown_seconds:
                return  # Still in cooldown
        
        # Calculate window
        window_start = now - (window_minutes * 60)
        
        # Evaluate based on alert type
        value_observed: Optional[float] = None
        triggered = False
        context = {}
        
        if alert_type == "failure_rate":
            value_observed, triggered = await self.eval_failure_rate(
                threshold, window_start, now, alert.get("contract_ids", [])
            )
            context["window_minutes"] = window_minutes
        
        elif alert_type == "gas_spike":
            value_observed, triggered = await self.eval_gas_spike(
                threshold, window_start, now
            )
            context["baseline_window"] = "1 hour"
        
        elif alert_type == "provider_down":
            value_observed, triggered = await self.eval_provider_down(threshold)
            context["check_time"] = now
        
        else:
            logger.warning(f"Unknown alert type: {alert_type}")
            return
        
        # If triggered, create event
        if triggered and value_observed is not None:
            await self.create_alert_event(
                alert_id,
                alert["severity"],
                value_observed,
                threshold,
                context,
                now,
            )
            
            # Update last_triggered_at
            await db.execute(
                "UPDATE alerts SET last_triggered_at = $1 WHERE id = $2",
                now,
                alert_id,
            )
            
            logger.info(
                f"Alert {alert_id} ({alert['name']}) triggered: "
                f"value={value_observed:.2f}, threshold={threshold}"
            )

    async def eval_failure_rate(
        self,
        threshold: float,
        window_start: int,
        window_end: int,
        contract_ids: list[int],
    ) -> tuple[Optional[float], bool]:
        """Evaluate failure_rate alert."""
        # Build query
        where_clauses = ["block_timestamp >= $1", "block_timestamp < $2"]
        params = [window_start, window_end]
        
        if contract_ids:
            where_clauses.append("contract_id = ANY($3)")
            params.append(contract_ids)
        
        where_clause = " AND ".join(where_clauses)
        
        # Query transaction counts
        result = await db.fetch_one(
            f"""
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 0) as failed
            FROM txs
            WHERE {where_clause}
            """,
            *params,
        )
        
        if not result or result["total"] == 0:
            return None, False
        
        total = result["total"]
        failed = result["failed"]
        failure_rate = (failed / total) * 100
        
        triggered = failure_rate > threshold
        
        return failure_rate, triggered

    async def eval_gas_spike(
        self,
        threshold: float,
        window_start: int,
        window_end: int,
    ) -> tuple[Optional[float], bool]:
        """Evaluate gas_spike alert (threshold = multiplier, e.g., 2.0 = 200%)."""
        # Get current average gas price
        current_result = await db.fetch_one(
            """
            SELECT AVG(gas_price_avg) as avg_gas
            FROM metrics_minute
            WHERE bucket_ts >= $1 AND bucket_ts < $2
            """,
            window_start,
            window_end,
        )
        
        if not current_result or current_result["avg_gas"] is None:
            return None, False
        
        current_avg = float(current_result["avg_gas"])
        
        # Get baseline (1 hour before window)
        baseline_start = window_start - 3600
        baseline_end = window_start
        
        baseline_result = await db.fetch_one(
            """
            SELECT AVG(gas_price_avg) as avg_gas
            FROM metrics_minute
            WHERE bucket_ts >= $1 AND bucket_ts < $2
            """,
            baseline_start,
            baseline_end,
        )
        
        if not baseline_result or baseline_result["avg_gas"] is None:
            return None, False
        
        baseline_avg = float(baseline_result["avg_gas"])
        
        if baseline_avg == 0:
            return None, False
        
        # Calculate multiplier
        multiplier = current_avg / baseline_avg
        
        triggered = multiplier > threshold
        
        return multiplier, triggered

    async def eval_provider_down(self, threshold: float) -> tuple[Optional[float], bool]:
        """Evaluate provider_down alert (threshold = number of down providers)."""
        result = await db.fetch_one(
            """
            SELECT COUNT(*) as count
            FROM rpc_endpoints
            WHERE is_active = true AND status = 'unhealthy'
            """
        )
        
        if not result:
            return None, False
        
        unhealthy_count = float(result["count"])
        
        triggered = unhealthy_count >= threshold
        
        return unhealthy_count, triggered

    async def create_alert_event(
        self,
        alert_id: int,
        severity: str,
        value_observed: float,
        threshold: float,
        context: dict,
        triggered_at: int,
    ) -> None:
        """Create alert event record."""
        await db.execute(
            """
            INSERT INTO alert_events (
                alert_id,
                triggered_at,
                severity,
                value_observed,
                threshold,
                context
            ) VALUES ($1, $2, $3, $4, $5, $6)
            """,
            alert_id,
            triggered_at,
            severity,
            value_observed,
            threshold,
            context,
        )


evaluator = AlertEvaluator()
