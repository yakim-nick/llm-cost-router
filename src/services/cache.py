from __future__ import annotations

import hashlib
import json

import redis.asyncio as redis

from src.config import settings

# Redis key namespace for cached completions and stats counters.
_CACHE_KEY_PREFIX = "response:"
_HITS_COUNTER_KEY = "stats:cache_hits"


class ResponseCache:
    """Exact-match response cache keyed by messages + model.

    This is NOT a semantic cache: only byte-identical message lists (same order,
    same text) for the same model hit. Similar-but-different prompts miss.
    Before ``connect()`` all reads/writes no-op, so the gateway still works
    (without caching) when Redis was never connected.
    """

    def __init__(self, ttl: int = 3600):
        self._ttl = ttl
        self._client: redis.Redis | None = None

    async def connect(self):
        """Open the Redis client used for all cache operations."""
        self._client = await redis.from_url(settings.redis_url, decode_responses=True)

    async def disconnect(self):
        """Close the Redis client if it was opened."""
        if self._client:
            await self._client.aclose()

    def _make_key(self, messages: list[dict], model: str) -> str:
        """Derive a stable cache key from messages+model (message order matters)."""
        raw = json.dumps(messages, sort_keys=True) + model
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"{_CACHE_KEY_PREFIX}{digest}"

    async def get(self, messages: list[dict], model: str) -> str | None:
        """Return the cached completion for messages+model, or None on miss."""
        if not self._client:
            return None
        return await self._client.get(self._make_key(messages, model))

    async def set(self, messages: list[dict], model: str, response: str) -> None:
        """Cache a completion for messages+model with the configured TTL."""
        if not self._client:
            return
        await self._client.setex(self._make_key(messages, model), self._ttl, response)

    async def count_cache_hits(self) -> int:
        """Return the total number of cache hits recorded so far."""
        if not self._client:
            return 0
        value = await self._client.get(_HITS_COUNTER_KEY)
        return int(value) if value is not None else 0

    async def increment_hits(self) -> None:
        """Record one cache hit in the shared counter."""
        if self._client:
            await self._client.incr(_HITS_COUNTER_KEY)
