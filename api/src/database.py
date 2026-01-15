"""Database connection and query helpers."""
import asyncpg
import logging
from typing import Any, Optional

from .config import config

logger = logging.getLogger(__name__)


class Database:
    """Database connection manager."""

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Establish database connection pool."""
        try:
            # Supabase connection with proper SSL (require SSL but don't verify cert for managed services)
            # asyncpg will use SSL automatically when connecting to Supabase
            # statement_cache_size=0 is required for pgbouncer (Supabase Connection Pooler)
            self.pool = await asyncpg.create_pool(
                config.database_url,
                min_size=2,
                max_size=20,
                command_timeout=60,
                timeout=30,
                ssl='require',  # Require SSL but let asyncpg handle it properly
                statement_cache_size=0,  # Disable prepared statements for pgbouncer
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    async def disconnect(self) -> None:
        """Close database connection pool."""
        if self.pool:
            await self.pool.close()

    async def fetch_one(self, query: str, *args: Any) -> Optional[dict]:
        """Execute query and fetch single row."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(query, *args)
            return dict(row) if row else None

    async def fetch_all(self, query: str, *args: Any) -> list[dict]:
        """Execute query and fetch all rows."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]

    async def execute(self, query: str, *args: Any) -> str:
        """Execute query without returning results."""
        if not self.pool:
            raise RuntimeError("Database not connected")
        
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *args)


db = Database()
