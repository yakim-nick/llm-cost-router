from __future__ import annotations

import time
import logging

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from src.services.router import ComplexityRouter
from src.services.cache import SemanticCache
from src.services.metrics import MetricsCollector
from src.services.providers.openai_provider import OpenAIProvider
from src.services.providers.anthropic_provider import AnthropicProvider
from src.services.auth import AuthService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])

_complexity_router = ComplexityRouter()
_openai = OpenAIProvider()
_anthropic = AnthropicProvider()
_auth = AuthService()

COST_PER_TOKEN = {
    "gpt-4o": {"prompt": 0.000005, "completion": 0.000015},
    "gpt-4o-mini": {"prompt": 0.00000015, "completion": 0.0000006},
    "claude-3-haiku": {"prompt": 0.00000025, "completion": 0.00000125},
    "claude-3-sonnet": {"prompt": 0.000003, "completion": 0.000015},
    "claude-3-opus": {"prompt": 0.000015, "completion": 0.000075},
}


class ChatRequest(BaseModel):
    model: str = "auto"
    messages: list[dict]
    temperature: float | None = None
    max_tokens: int | None = None

    class Config:
        extra = "forbid"


@router.post("/chat/completions")
async def chat_completions(request: Request, body: ChatRequest):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header.removeprefix("Bearer ")
    api_key = await _auth.validate_key(token)
    if not api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    complexity = _complexity_router.assess_complexity(body.messages)
    provider_name, tier = _complexity_router.select_provider(complexity)
    request.state.provider = provider_name

    model = body.model if body.model != "auto" else _complexity_router.select_model(provider_name, tier, complexity)
    request.state.model = model

    cache_key = body.messages
    cached = await request.app.state.cache.get(cache_key, model)
    if cached:
        await request.app.state.cache.increment_hits()
        logger.info(f"Cache HIT | model={model} provider={provider_name}")
        return {"choices": [{"message": {"content": cached}}], "model": model, "cached": True}

    kwargs = {}
    if body.temperature is not None:
        kwargs["temperature"] = body.temperature
    if body.max_tokens is not None:
        kwargs["max_tokens"] = body.max_tokens

    start = time.perf_counter()
    try:
        if provider_name == "anthropic":
            result = await _anthropic.chat_completion(model, body.messages, **kwargs)
        else:
            result = await _openai.chat_completion(model, body.messages, **kwargs)
    except Exception as exc:
        logger.error(f"Provider call failed: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Provider error: {str(exc)}")

    elapsed = time.perf_counter() - start
    usage = result["usage"]
    cost = (
        usage["prompt_tokens"] * COST_PER_TOKEN.get(model, {}).get("prompt", 0)
        + usage["completion_tokens"] * COST_PER_TOKEN.get(model, {}).get("completion", 0)
    )

    request.app.state.metrics.record_latency(provider_name, model, elapsed)
    request.app.state.metrics.record_cost(provider_name, model, cost)
    request.app.state.metrics.record_tokens(provider_name, model, "prompt", usage["prompt_tokens"])
    request.app.state.metrics.record_tokens(provider_name, model, "completion", usage["completion_tokens"])

    await request.app.state.cache.set(cache_key, model, result["content"])

    logger.info(
        f"PROXY | model={model} provider={provider_name} "
        f"complexity={complexity:.2f} cost=${cost:.6f} latency={elapsed:.2f}s"
    )

    return {
        "choices": [{"message": {"content": result["content"]}}],
        "model": result["model"],
        "usage": usage,
        "cost": round(cost, 6),
        "cached": False,
    }
