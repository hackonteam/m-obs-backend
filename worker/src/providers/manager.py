"""Provider selection and failover management."""
import asyncio
import logging
from typing import Optional
import time

from ..database import db
from .rpc_client import RPCClient, RPCError

logger = logging.getLogger(__name__)


class ProviderManager:
    """Manages RPC provider selection and failover."""

    def __init__(self) -> None:
        self.providers: dict[int, RPCClient] = {}
        self.last_switch_time: float = 0
        self.switch_cooldown: int = 30  # seconds

    async def load_providers(self) -> None:
        """Load active providers from database."""
        rows = await db.fetch_all(
            """
            SELECT id, url FROM rpc_endpoints 
            WHERE is_active = true 
            ORDER BY score DESC
            """
        )
        
        self.providers = {
            row["id"]: RPCClient(row["url"])
            for row in rows
        }
        
        logger.info(f"Loaded {len(self.providers)} active providers")

    async def get_primary(self) -> tuple[int, RPCClient]:
        """Get primary provider (highest score)."""
        if not self.providers:
            await self.load_providers()
        
        row = await db.fetch_one(
            """
            SELECT id, url FROM rpc_endpoints 
            WHERE is_active = true AND status = 'healthy'
            ORDER BY score DESC 
            LIMIT 1
            """
        )
        
        if not row:
            # Fallback to degraded providers
            row = await db.fetch_one(
                """
                SELECT id, url FROM rpc_endpoints 
                WHERE is_active = true 
                ORDER BY score DESC 
                LIMIT 1
                """
            )
        
        if not row:
            raise RuntimeError("No active providers available")
        
        provider_id = row["id"]
        
        if provider_id not in self.providers:
            self.providers[provider_id] = RPCClient(row["url"])
        
        return provider_id, self.providers[provider_id]

    async def get_trace_provider(self) -> Optional[tuple[int, RPCClient]]:
        """Get provider that supports traces."""
        row = await db.fetch_one(
            """
            SELECT id, url FROM rpc_endpoints 
            WHERE is_active = true 
            AND supports_traces = true 
            AND status = 'healthy'
            ORDER BY score DESC 
            LIMIT 1
            """
        )
        
        if not row:
            return None
        
        provider_id = row["id"]
        
        if provider_id not in self.providers:
            self.providers[provider_id] = RPCClient(row["url"])
        
        return provider_id, self.providers[provider_id]

    async def mark_failure(self, provider_id: int) -> None:
        """Record provider failure for scoring."""
        # Provider scoring happens in the probe pipeline
        # This just logs for now
        logger.warning(f"Provider {provider_id} failed")

    async def should_switch(self, current_id: int) -> bool:
        """Check if provider switch is recommended."""
        now = time.time()
        if now - self.last_switch_time < self.switch_cooldown:
            return False
        
        row = await db.fetch_one(
            "SELECT score FROM rpc_endpoints WHERE id = $1",
            current_id,
        )
        
        if not row or row["score"] < 50:
            self.last_switch_time = now
            return True
        
        return False


provider_manager = ProviderManager()
