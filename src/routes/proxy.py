from __future__ import annotations

import logging
import time
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, field_validator

from src.config import settings
from src.services.auth import AuthService
from src.services.providers.anthropic_provider import AnthropicProvider
from src.services.providers.openai_provider import OpenAIProvider
from src.services.router import ComplexityRouter

logger = logging.getLogger(__name__)
router = APIRouter(tags=["proxy"])

_complexity_router = ComplexityRouter()


@lru_cache(maxsize=1)
def _get_openai() -> OpenAIProvider:
    """Build the OpenAI client on first use so the app boots without that key."""
    return OpenAIProvider()


@lru_cache(maxsize=1)
def _get_anthropic() -> AnthropicProvider:
    """Build the Anthropic client on first use so the app boots without that key."""
    return AnthropicProvider()


# USD per prompt/completion token for each routing model. Unknown models
# fall back to $0 so they never silently inflate the reported cost.
COST_PER_TOKEN = {
    "gpt-4o": {"prompt": 0.000005, "completion": 0.000015},
    "gpt-4o-mini": {"prompt": 0.00000015, "completion": 0.0000006},
    "claude-3-haiku": {"prompt": 0.00000025, "completion": 0.00000125},
    "claude-3-sonnet": {"prompt": 0.000003, "completion": 0.000015},
    "claude-3-opus": {"prompt": 0.000015, "completion": 0.000075},
}


@lru_cache(maxsize=1)
def _get_auth() -> AuthService:
    return AuthService()


ALLOWED_ROLES = {"system", "user", "assistant"}
MAX_MESSAGES = 100
MAX_MESSAGE_CHARS = 32_000


class ChatRequest(BaseModel):
    """Validated chat request. Only known models (or "auto") are accepted so a
    caller cannot make the gateway spend money on an arbitrary expensive model."""

    model_config = ConfigDict(extra="forbid")

    model: str = "auto"
    messages: list[dict]
    temperature: float | None = None
    max_tokens: int | None = None

    @field_validator("model")
    @classmethod
    def _known_model(cls, value: str) -> str:
        if value != "auto" and value not in COST_PER_TOKEN:
            allowed = ", ".join(["auto", *COST_PER_TOKEN])
            raise ValueError(f"unknown model; allowed: {allowed}")
        return value

    @field_validator("messages")
    @classmethod
    def _valid_messages(cls, value: list[dict]) -> list[dict]:
        if not value or len(value) > MAX_MESSAGES:
            raise ValueError(f"messages must contain 1-{MAX_MESSAGES} items")
        for message in value:
            content = message.get("content")
            if message.get("role") not in ALLOWED_ROLES or not isinstance(content, str):
                raise ValueError("each message needs a valid role and string content")
            if len(content) > MAX_MESSAGE_CHARS:
                raise ValueError(f"message content longer than {MAX_MESSAGE_CHARS} characters")
        return value

    @field_validator("temperature")
    @classmethod
    def _valid_temperature(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 2.0:
            raise ValueError("temperature must be between 0 and 2")
        return value

    @field_validator("max_tokens")
    @classmethod
    def _valid_max_tokens(cls, value: int | None) -> int | None:
        if value is not None and not 1 <= value <= settings.max_tokens_limit:
            raise ValueError(f"max_tokens must be between 1 and {settings.max_tokens_limit}")
        return value


@router.post("/chat/completions")
async def chat_completions(request: Request, body: ChatRequest):
    """Route one chat completion to the cheapest fitting provider and cache it."""
    api_key = await _authenticate_request(request)
    if not api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    provider, model, complexity = _resolve_route(body)
    request.state.provider = provider
    request.state.model = model

    cache_key = body.messages
    cached_response = await request.app.state.cache.get(cache_key, model)
    if cached_response is not None:
        await request.app.state.cache.increment_hits()
        logger.info(f"Cache HIT | model={model} provider={provider}")
        return _cached_result(model, cached_response)

    provider_result, elapsed = await _call_provider(provider, model, body)
    _record_metrics(request, provider, model, provider_result, elapsed)
    await request.app.state.cache.set(cache_key, model, provider_result["content"])

    logger.info(
        f"PROXY | model={model} provider={provider} "
        f"complexity={complexity:.2f} cost=${_estimate_cost(model, provider_result):.6f} "
        f"latency={elapsed:.2f}s"
    )
    return _fresh_result(provider_result, model)


async def _authenticate_request(request: Request) -> dict | None:
    """Resolve the Bearer token to an active API key, or None when invalid."""
    token = _extract_bearer_token(request.headers.get("Authorization", ""))
    if token is None:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    return await _get_auth().validate_key(token)


def _extract_bearer_token(authorization: str) -> str | None:
    """Return the token after 'Bearer ', or None if the header shape is wrong."""
    if not authorization.startswith("Bearer "):
        return None
    return authorization.removeprefix("Bearer ")


def _resolve_route(body: ChatRequest) -> tuple[str, str, float]:
    """Pick provider+model from complexity, or use the explicitly requested model.

    Returns (provider, model, complexity_score); the score is kept so the
    routing decision stays auditable in logs and metrics.
    """
    complexity = _complexity_router.assess_complexity(body.messages)
    if body.model != "auto":
        # An explicit model decides its own provider; complexity is only logged.
        return _provider_for_model(body.model), body.model, complexity
    provider, tier = _complexity_router.select_provider(complexity)
    return provider, _complexity_router.select_model(provider, tier, complexity), complexity


def _provider_for_model(model: str) -> str:
    """Map a concrete model name to the provider that serves it."""
    return "anthropic" if model.startswith("claude") else "openai"


async def _call_provider(provider: str, model: str, body: ChatRequest) -> tuple[dict, float]:
    """Forward the request to the selected provider; surface failures as 502.

    Returns (result, elapsed_seconds) so the caller can record both.
    """
    kwargs = _build_provider_kwargs(body)
    start = time.perf_counter()
    try:
        if provider == "anthropic":
            result = await _get_anthropic().chat_completion(model, body.messages, **kwargs)
        else:
            result = await _get_openai().chat_completion(model, body.messages, **kwargs)
        return result, time.perf_counter() - start
    except Exception as exc:
        logger.exception("Provider call failed")
        # The real error is logged above; do not leak provider details to clients.
        raise HTTPException(status_code=502, detail="Upstream provider error") from exc


def _build_provider_kwargs(body: ChatRequest) -> dict:
    """Collect the optional generation parameters into provider kwargs."""
    kwargs: dict = {}
    if body.temperature is not None:
        kwargs["temperature"] = body.temperature
    # Anthropic requires max_tokens; sending it for OpenAI as well keeps spend bounded.
    kwargs["max_tokens"] = body.max_tokens or settings.default_max_tokens
    return kwargs


def _record_metrics(request, provider: str, model: str, result: dict, elapsed: float) -> None:
    """Emit latency/cost/token metrics for the finished provider call."""
    usage = result["usage"]
    cost = _estimate_cost(model, result)
    request.app.state.metrics.record_latency(provider, model, elapsed)
    request.app.state.metrics.record_cost(provider, model, cost)
    request.app.state.metrics.record_tokens(provider, model, "prompt", usage["prompt_tokens"])
    request.app.state.metrics.record_tokens(
        provider, model, "completion", usage["completion_tokens"]
    )


def _estimate_cost(model: str, result: dict) -> float:
    """Compute the USD cost of a provider result using the price table."""
    usage = result["usage"]
    prices = COST_PER_TOKEN.get(model, {})
    return usage["prompt_tokens"] * prices.get("prompt", 0) + usage[
        "completion_tokens"
    ] * prices.get("completion", 0)


def _cached_result(model: str, content: str) -> dict:
    """Shape a cache-hit response without a new provider call."""
    return {"choices": [{"message": {"content": content}}], "model": model, "cached": True}


def _fresh_result(result: dict, model: str) -> dict:
    """Shape a fresh (non-cached) provider response for the caller."""
    return {
        "choices": [{"message": {"content": result["content"]}}],
        "model": result["model"],
        "usage": result["usage"],
        "cost": round(_estimate_cost(model, result), 6),
        "cached": False,
    }
