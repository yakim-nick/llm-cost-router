from __future__ import annotations

import secrets
import logging
import bcrypt

from src.models.database import get_pool

logger = logging.getLogger(__name__)


class AuthService:
    @staticmethod
    def generate_key() -> str:
        return f"lkg_{secrets.token_hex(32)}"

    @staticmethod
    def hash_key(key: str) -> str:
        return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_key(key: str, key_hash: str) -> bool:
        return bcrypt.checkpw(key.encode(), key_hash.encode())

    async def create_key(self, name: str, tier: str = "standard") -> str:
        pool = await get_pool()
        raw_key = self.generate_key()
        key_hash = self.hash_key(raw_key)
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO api_keys (name, key_hash, tier) VALUES ($1, $2, $3)",
                name, key_hash, tier,
            )
        logger.info(f"Created API key for '{name}' (tier={tier})")
        return raw_key

    async def validate_key(self, token: str) -> dict | None:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM api_keys WHERE is_active = true")
        for row in rows:
            if self.verify_key(token, row["key_hash"]):
                return dict(row)
        return None

    async def list_keys(self) -> list[dict]:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, tier, is_active, created_at FROM api_keys ORDER BY created_at DESC"
            )
            return [dict(r) for r in rows]
