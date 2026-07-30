from __future__ import annotations

import json
import hashlib

import redis.asyncio as redis
from src.config import settings


class ResponseCache:
    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._client: redis.Redis | None = None

    async def connect(self):
        self._client = await redis.from_url(settings.redis_url, decode_responses=True)

    async def disconnect(self):
        if self._client:
            await self._client.aclose()

    def _make_key(self, messages: list[dict], model: str) -> str:
        raw = json.dumps(messages, sort_keys=True) + model
        return f"response:{hashlib.sha256(raw.encode()).hexdigest()}"

    async def get(self, messages: list[dict], model: str) -> str | None:
        if not self._client:
            return None
        key = self._make_key(messages, model)
        return await self._client.get(key)

    async def set(self, messages: list[dict], model: str, response: str) -> None:
        if not self._client:
            return
        key = self._make_key(messages, model)
        await self._client.setex(key, self._ttl, response)

    async def count_cache_hits(self) -> int:
        val = await self._client.get("stats:cache_hits")  # type: ignore
        return int(val) if val is not None else 0

    async def increment_hits(self) -> None:
        if self._client:
            await self._client.incr("stats:cache_hits")
