from __future__ import annotations

import time
import asyncio
from collections import defaultdict


class TokenBucketRateLimiter:
    """In-memory token-bucket rate limiter using an async-safe dict.

    Each unique *key* (e.g. an API key or IP) gets its own bucket that
    refills at *rate* tokens/second up to *burst* capacity.
    """

    def __init__(self, default_rate: float = 10.0, default_burst: int = 20):
        self._default_rate = default_rate
        self._default_burst = default_burst
        self._tokens: dict[str, float] = {}
        self._last_refill: dict[str, float] = defaultdict(float)
        self._lock = asyncio.Lock()

    async def check(
        self,
        key: str,
        rate: float | None = None,
        burst: int | None = None,
    ) -> bool:
        """Return True if the request is allowed, False if rate-limited."""
        rate = rate if rate is not None else self._default_rate
        burst = burst if burst is not None else self._default_burst
        now = time.monotonic()

        async with self._lock:
            tokens = self._tokens.get(key, burst)
            elapsed = now - self._last_refill.get(key, now)
            tokens = min(burst, tokens + elapsed * rate)
            self._last_refill[key] = now

            if tokens >= 1.0:
                self._tokens[key] = tokens - 1.0
                return True

            self._tokens[key] = tokens
            return False

    async def reset(self, key: str) -> None:
        """Remove the bucket for *key* so it starts fresh."""
        async with self._lock:
            self._tokens.pop(key, None)
            self._last_refill.pop(key, None)
