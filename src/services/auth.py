from __future__ import annotations

import secrets
import logging

import bcrypt

from src.models.database import get_pool

logger = logging.getLogger(__name__)

# Prefix makes generated keys recognizable and greppable in logs.
_KEY_PREFIX = "lkg_"

# Only active keys can authenticate; deactivated keys are skipped at lookup.
_ACTIVE_ONLY_SQL = "SELECT * FROM api_keys WHERE is_active = true"


class AuthService:
    """Manage API keys: generation, hashing, validation, persistence.

    Plaintext keys are returned to the caller exactly once at creation;
    only their bcrypt hash is stored. Validation therefore has to scan the
    active key hashes and bcrypt-compare each one.
    """

    @staticmethod
    def generate_key() -> str:
        """Return a new cryptographically random API key."""
        return f"{_KEY_PREFIX}{secrets.token_hex(32)}"

    @staticmethod
    def hash_key(key: str) -> str:
        """Return the bcrypt hash of a plaintext key."""
        return bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()

    @staticmethod
    def verify_key(key: str, key_hash: str) -> bool:
        """Return True when the plaintext key matches the stored hash."""
        return bcrypt.checkpw(key.encode(), key_hash.encode())

    async def create_key(self, name: str, tier: str = "standard") -> str:
        """Persist a hashed key and return the one-time plaintext value."""
        raw_key = self.generate_key()
        key_hash = self.hash_key(raw_key)
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO api_keys (name, key_hash, tier) VALUES ($1, $2, $3)",
                name,
                key_hash,
                tier,
            )
        logger.info(f"Created API key for '{name}' (tier={tier})")
        return raw_key

    async def validate_key(self, token: str) -> dict | None:
        """Return the active key row matching *token*, or None if it is unknown."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(_ACTIVE_ONLY_SQL)

        for row in rows:
            if self.verify_key(token, row["key_hash"]):
                return dict(row)
        return None

    async def list_keys(self) -> list[dict]:
        """Return all keys (without hashes), newest first."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, tier, is_active, created_at FROM api_keys "
                "ORDER BY created_at DESC"
            )
            return [dict(row) for row in rows]
