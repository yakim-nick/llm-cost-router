from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.auth import AuthService
from src.models.database import get_pool

router = APIRouter(tags=["admin"])
_auth = AuthService()


class CreateKeyRequest(BaseModel):
    name: str
    tier: str = "standard"


@router.post("/keys")
async def create_api_key(body: CreateKeyRequest):
    if body.tier not in ("standard", "premium", "unlimited"):
        raise HTTPException(status_code=400, detail=f"Invalid tier: {body.tier}")
    raw_key = await _auth.create_key(body.name, body.tier)
    return {"api_key": raw_key, "name": body.name, "tier": body.tier}


@router.get("/keys")
async def list_api_keys():
    keys = await _auth.list_keys()
    return {"keys": keys}


@router.get("/usage")
async def get_usage():
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT provider, model, sum(cost)::numeric(10,4) as total_cost, "
            "sum(prompt_tokens) as total_prompt, sum(completion_tokens) as total_completion, "
            "count(*) as request_count "
            "FROM usage_logs GROUP BY provider, model ORDER BY total_cost DESC"
        )
        return {"usage": [dict(r) for r in rows]}
