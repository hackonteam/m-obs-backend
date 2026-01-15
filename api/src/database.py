"""Database connection and query helpers."""
import asyncpg
import ssl
from typing import Any, Optional

from .config import config


class Database:
    """Database connection manager."""

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Establish database connection pool."""
        # Use DATABASE_URL directly with SSL configuration
        # Supabase requires SSL connections
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        self.pool = await asyncpg.create_pool(
            config.database_url,
            min_size=2,
            max_size=20,
            command_timeout=30,
            ssl=ssl_context,
        )

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
