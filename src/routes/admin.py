from __future__ import annotations

import secrets
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.config import settings
from src.models.database import get_pool
from src.services.auth import AuthService


async def require_admin(request: Request) -> None:
    """Allow the request only with the configured admin bearer token.

    Fails closed: when ADMIN_TOKEN is unset the admin API is disabled (503),
    and a wrong or missing token is rejected (401). The comparison is
    constant-time so the token cannot be guessed from response timing.
    """
    expected = settings.admin_token
    if not expected:
        raise HTTPException(status_code=503, detail="Admin API disabled: ADMIN_TOKEN is not set")
    header = request.headers.get("Authorization", "")
    supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    if not secrets.compare_digest(supplied.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing admin token")


router = APIRouter(tags=["admin"], dependencies=[Depends(require_admin)])

VALID_TIERS = ("standard", "premium", "unlimited")

# Aggregate usage per provider/model; costs are rounded to 4 decimals.
_USAGE_AGGREGATION_SQL = """
    SELECT provider, model,
           sum(cost)::numeric(10,4) as total_cost,
           sum(prompt_tokens) as total_prompt,
           sum(completion_tokens) as total_completion,
           count(*) as request_count
    FROM usage_logs
    GROUP BY provider, model
    ORDER BY total_cost DESC
"""


@lru_cache(maxsize=1)
def _get_auth() -> AuthService:
    return AuthService()


class CreateKeyRequest(BaseModel):
    """Request body for creating a new API key."""

    name: str
    tier: str = "standard"


@router.post("/keys")
async def create_api_key(body: CreateKeyRequest):
    """Create an API key with the requested usage tier.

    Returns the plaintext key exactly once; only its hash is stored.
    """
    if body.tier not in VALID_TIERS:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {body.tier}")

    raw_key = await _get_auth().create_key(body.name, body.tier)
    return {"api_key": raw_key, "name": body.name, "tier": body.tier}


@router.get("/keys")
async def list_api_keys():
    """List all API keys (id, name, tier, status, created date)."""
    keys = await _get_auth().list_keys()
    return {"keys": keys}


@router.get("/usage")
async def get_usage():
    """Return per provider/model usage aggregated from the usage log."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_USAGE_AGGREGATION_SQL)
        return {"usage": [dict(row) for row in rows]}
