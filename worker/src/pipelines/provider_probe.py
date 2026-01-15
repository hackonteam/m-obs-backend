"""Provider health probe pipeline."""
import asyncio
import logging
import time
from typing import Optional

from ..config import config
from ..database import db
from ..providers.rpc_client import RPCClient, RPCError
from ..providers.scoring import calculate_score, score_to_status

logger = logging.getLogger(__name__)


class ProviderProbe:
    """Monitors RPC provider health and updates scores."""

    def __init__(self) -> None:
        self.consecutive_failures: dict[int, int] = {}
        self.leader_block: int = 0

    async def run(self) -> None:
        """Run probe loop indefinitely."""
        logger.info("Starting provider probe pipeline")
        
        while True:
            try:
                await self.probe_cycle()
                await asyncio.sleep(config.poll_interval_probe)
            except Exception as e:
                logger.error(f"Probe cycle error: {e}")
                await asyncio.sleep(5)

    async def probe_cycle(self) -> None:
        """Execute one probe cycle for all active providers."""
        # Load active endpoints
        endpoints = await db.fetch_all(
            "SELECT id, url, score FROM rpc_endpoints WHERE is_active = true"
        )
        
        if not endpoints:
            logger.warning("No active endpoints to probe")
            return
        
        # Reset leader block
        self.leader_block = 0
        
        # Probe all endpoints in parallel (limited concurrency)
        results = await asyncio.gather(
            *[self.probe_endpoint(ep) for ep in endpoints],
            return_exceptions=True,
        )
        
        # Update leader block
        for result in results:
            if isinstance(result, dict) and result.get("block_number"):
                self.leader_block = max(self.leader_block, result["block_number"])
        
        # Process results and update scores
        for endpoint, result in zip(endpoints, results):
            if isinstance(result, Exception):
                logger.error(f"Probe failed for {endpoint['id']}: {result}")
                continue
            
            if result:
                await self.update_endpoint(endpoint["id"], result)

    async def probe_endpoint(self, endpoint: dict) -> Optional[dict]:
        """Probe single endpoint."""
        endpoint_id = endpoint["id"]
        url = endpoint["url"]
        
        client = RPCClient(url, timeout=config.rpc_timeout_default)
        
        start_time = time.time()
        is_success = False
        latency_ms: Optional[int] = None
        block_number: Optional[int] = None
        error_code: Optional[str] = None
        supports_traces = False
        
        try:
            # Call eth_blockNumber
            block_number = await client.eth_block_number()
            latency_ms = int((time.time() - start_time) * 1000)
            is_success = True
            
            # Reset consecutive failures on success
            self.consecutive_failures[endpoint_id] = 0
            
            # Try trace API (best-effort)
            try:
                # Use a known transaction or skip if none available
                # For now, just mark as not supporting traces
                supports_traces = False
            except RPCError:
                supports_traces = False
        
        except RPCError as e:
            error_code = f"rpc_{e.code}" if e.code else "rpc_error"
            self.consecutive_failures[endpoint_id] = (
                self.consecutive_failures.get(endpoint_id, 0) + 1
            )
        
        except Exception as e:
            error_code = "unknown"
            self.consecutive_failures[endpoint_id] = (
                self.consecutive_failures.get(endpoint_id, 0) + 1
            )
        
        # Calculate score
        block_lag = 0
        if block_number and self.leader_block > 0:
            block_lag = max(0, self.leader_block - block_number)
        
        consecutive_failures = self.consecutive_failures.get(endpoint_id, 0)
        score = calculate_score(latency_ms, consecutive_failures, block_lag)
        status = score_to_status(score)
        
        # Record sample
        sampled_at = int(time.time())
        await db.execute(
            """
            INSERT INTO rpc_health_samples 
            (endpoint_id, sampled_at, latency_ms, block_number, is_success, error_code)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            endpoint_id,
            sampled_at,
            latency_ms,
            block_number,
            is_success,
            error_code,
        )
        
        return {
            "endpoint_id": endpoint_id,
            "score": score,
            "status": status,
            "latency_ms": latency_ms,
            "block_number": block_number,
            "supports_traces": supports_traces,
        }

    async def update_endpoint(self, endpoint_id: int, result: dict) -> None:
        """Update endpoint with probe results."""
        await db.execute(
            """
            UPDATE rpc_endpoints 
            SET score = $1, 
                status = $2, 
                supports_traces = $3,
                last_probe_at = $4,
                updated_at = $4
            WHERE id = $5
            """,
            result["score"],
            result["status"],
            result["supports_traces"],
            int(time.time()),
            endpoint_id,
        )
        
        logger.info(
            f"Endpoint {endpoint_id}: score={result['score']} "
            f"status={result['status']} latency={result['latency_ms']}ms"
        )


probe = ProviderProbe()
