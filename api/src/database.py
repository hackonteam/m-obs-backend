"""Database connection and query helpers."""
import asyncpg
from typing import Any, Optional

from .config import config


class Database:
    """Database connection manager."""

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self) -> None:
        """Establish database connection pool."""
        # Extract database URL from Supabase URL
        db_url = config.supabase_url.replace("https://", "").replace("http://", "")
        project_ref = db_url.split(".")[0]
        
        connection_string = (
            f"postgresql://postgres:{config.supabase_service_key}"
            f"@db.{project_ref}.supabase.co:5432/postgres"
        )
        
        self.pool = await asyncpg.create_pool(
            connection_string,
            min_size=2,
            max_size=20,
            command_timeout=30,
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
