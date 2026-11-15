from __future__ import annotations

import logging

from src.models.database import get_pool

logger = logging.getLogger(__name__)

_INSERT_USAGE_SQL = """
    INSERT INTO usage_logs
        (api_key_id, provider, model, prompt_tokens, completion_tokens, cost, latency_ms)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
"""


async def record_usage(
    api_key_id: int | None,
    provider: str,
    model: str,
    usage: dict,
    cost: float,
    latency_seconds: float,
) -> None:
    """Persist one provider call so /admin/usage can aggregate spend.

    Logging must never break a request that already succeeded, so database
    errors are logged and swallowed.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                _INSERT_USAGE_SQL,
                api_key_id,
                provider,
                model,
                usage["prompt_tokens"],
                usage["completion_tokens"],
                round(cost, 6),
                int(latency_seconds * 1000),
            )
    except Exception:
        logger.exception("Failed to record usage")
