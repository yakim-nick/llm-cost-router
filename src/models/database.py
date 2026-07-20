from __future__ import annotations

import asyncpg
from src.config import settings

_pool: asyncpg.Pool | None = None


async def init_db():
    global _pool
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    _pool = await asyncpg.create_pool(dsn=dsn, min_size=2, max_size=10)
    async with _pool.acquire() as conn:
        await conn.execute("""
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
        """)


async def close_db():
    global _pool
    if _pool:
        await _pool.close()


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("Database pool not initialized")
    return _pool
