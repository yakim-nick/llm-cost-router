from __future__ import annotations

import asyncpg

from src.config import settings

_pool: asyncpg.Pool | None = None

# Schema is created idempotently at startup so the app can boot on a fresh DB.
_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        key_hash TEXT NOT NULL UNIQUE,
        tier TEXT NOT NULL DEFAULT 'standard',
        is_active BOOLEAN DEFAULT true,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE TABLE IF NOT EXISTS usage_logs (
        id SERIAL PRIMARY KEY,
        api_key_id INT REFERENCES api_keys(id),
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        prompt_tokens INT DEFAULT 0,
        completion_tokens INT DEFAULT 0,
        cost NUMERIC(10,6) DEFAULT 0,
        latency_ms INT DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now()
    );
"""


async def init_db() -> None:
    """Open the connection pool and ensure the required tables exist."""
    global _pool
    dsn = _normalize_dsn(settings.database_url)
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute(_SCHEMA_SQL)


async def close_db() -> None:
    """Close the connection pool if it was opened."""
    global _pool
    if _pool:
        await _pool.close()


async def get_pool() -> asyncpg.Pool:
    """Return the shared connection pool; raise if it was never initialized."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool


def _normalize_dsn(dsn: str) -> str:
    """Convert SQLAlchemy-style async DSNs to a plain asyncpg DSN.

    asyncpg does not understand the `+asyncpg` driver suffix, so it is
    stripped here rather than forcing callers to supply two DSNs.
    """
    return dsn.replace("postgresql+asyncpg://", "postgresql://")
