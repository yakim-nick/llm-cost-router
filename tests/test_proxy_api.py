"""HTTP-level tests for POST /v1/chat/completions with all I/O faked."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.routes import proxy
from src.services.cache import ResponseCache
from src.services.metrics import MetricsCollector


class FakeCache:
    """In-memory stand-in for the Redis-backed cache; reuses the real key logic."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.hits = 0
        self._keys = ResponseCache()

    async def get(self, messages, model):
        return self.store.get(self._keys._make_key(messages, model))

    async def set(self, messages, model, response):
        self.store[self._keys._make_key(messages, model)] = response

    async def increment_hits(self):
        self.hits += 1


class FakeAuth:
    async def validate_key(self, token: str):
        return {"id": 1, "name": "test"} if token == "good-key" else None


class FakeProvider:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[dict] = []
        self.fail = fail

    async def chat_completion(self, model, messages, **kwargs):
        self.calls.append({"model": model, "kwargs": kwargs})
        if self.fail:
            raise RuntimeError("secret upstream detail sk-123")
        return {
            "content": "hi there",
            "model": model,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }


@pytest.fixture
def ctx(monkeypatch: pytest.MonkeyPatch):
    openai, anthropic = FakeProvider(), FakeProvider()
    monkeypatch.setattr(proxy, "_get_auth", lambda: FakeAuth())
    monkeypatch.setattr(proxy, "_get_openai", lambda: openai)
    monkeypatch.setattr(proxy, "_get_anthropic", lambda: anthropic)
    app = FastAPI()
    app.state.cache = FakeCache()
    app.state.metrics = MetricsCollector()
    app.include_router(proxy.router, prefix="/v1")
    return TestClient(app), app, openai, anthropic


AUTH = {"Authorization": "Bearer good-key"}
BODY = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hello"}]}


def test_requires_bearer_token(ctx):
    client, *_ = ctx
    assert client.post("/v1/chat/completions", json=BODY).status_code == 401


def test_rejects_unknown_key(ctx):
    client, *_ = ctx
    res = client.post("/v1/chat/completions", json=BODY, headers={"Authorization": "Bearer bad"})
    assert res.status_code == 403


def test_second_identical_request_is_served_from_cache(ctx):
    client, app, openai, _ = ctx
    first = client.post("/v1/chat/completions", json=BODY, headers=AUTH).json()
    second = client.post("/v1/chat/completions", json=BODY, headers=AUTH).json()
    assert first["cached"] is False and second["cached"] is True
    assert len(openai.calls) == 1
    assert app.state.cache.hits == 1


def test_similar_but_different_prompt_is_a_cache_miss(ctx):
    """Documents that the cache is exact-match, not semantic."""
    client, _, openai, _ = ctx
    client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    other = {**BODY, "messages": [{"role": "user", "content": "hello!"}]}
    client.post("/v1/chat/completions", json=other, headers=AUTH)
    assert len(openai.calls) == 2


@pytest.mark.parametrize(
    "patch",
    [
        {"model": "gpt-5-ultra-expensive"},
        {"messages": []},
        {"messages": [{"role": "hacker", "content": "x"}]},
        {"messages": [{"role": "user", "content": 123}]},
        {"max_tokens": 10**9},
        {"max_tokens": 0},
        {"temperature": 5},
        {"unexpected": True},
    ],
)
def test_invalid_requests_are_rejected_before_any_provider_call(ctx, patch):
    client, _, openai, anthropic = ctx
    res = client.post("/v1/chat/completions", json={**BODY, **patch}, headers=AUTH)
    assert res.status_code == 422
    assert not openai.calls and not anthropic.calls


def test_anthropic_always_gets_max_tokens(ctx):
    client, _, _, anthropic = ctx
    body = {"model": "claude-3-haiku", "messages": BODY["messages"]}
    res = client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert res.status_code == 200
    assert anthropic.calls[0]["kwargs"]["max_tokens"] == 1024


def test_provider_failure_returns_502_without_leaking_details(ctx):
    client, _, openai, _ = ctx
    openai.fail = True
    res = client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    assert res.status_code == 502
    assert "sk-123" not in res.text and "secret" not in res.text


def test_explicit_model_is_sent_to_its_own_provider(ctx):
    client, _, openai, anthropic = ctx
    simple = {"model": "claude-3-haiku", "messages": BODY["messages"]}
    client.post("/v1/chat/completions", json=simple, headers=AUTH)
    assert len(anthropic.calls) == 1 and not openai.calls


def test_successful_call_is_recorded_in_usage_log(ctx, monkeypatch):
    client, *_ = ctx
    rows = []

    async def fake_record(api_key_id, provider, model, usage, cost, latency):
        rows.append((api_key_id, provider, model, usage["prompt_tokens"], cost))

    monkeypatch.setattr(proxy, "record_usage", fake_record)
    client.post("/v1/chat/completions", json=BODY, headers=AUTH)
    client.post("/v1/chat/completions", json=BODY, headers=AUTH)  # cache hit, not logged
    assert len(rows) == 1
    key_id, provider, model, prompt_tokens, cost = rows[0]
    assert (key_id, provider, model, prompt_tokens) == (1, "openai", "gpt-4o-mini", 10)
    assert cost > 0
