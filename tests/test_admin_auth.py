"""The admin API must be closed unless the configured bearer token is sent."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.config import settings
from src.routes import admin


class FakeAuth:
    async def create_key(self, name: str, tier: str = "standard") -> str:
        return "lkg_fake"

    async def list_keys(self) -> list[dict]:
        return []


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(admin, "_get_auth", lambda: FakeAuth())
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    return TestClient(app)


KEY_BODY = {"name": "ci", "tier": "standard"}


def test_disabled_when_no_token_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    assert client.post("/admin/keys", json=KEY_BODY).status_code == 503
    # Even a bearer header cannot open it while it is disabled.
    headers = {"Authorization": "Bearer "}
    assert client.get("/admin/keys", headers=headers).status_code == 503


def test_missing_token_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "s3cret")
    assert client.post("/admin/keys", json=KEY_BODY).status_code == 401
    assert client.get("/admin/keys").status_code == 401
    assert client.get("/admin/usage").status_code == 401


def test_wrong_token_rejected(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "s3cret")
    headers = {"Authorization": "Bearer nope"}
    assert client.post("/admin/keys", json=KEY_BODY, headers=headers).status_code == 401


def test_correct_token_allowed(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "s3cret")
    headers = {"Authorization": "Bearer s3cret"}
    res = client.post("/admin/keys", json=KEY_BODY, headers=headers)
    assert res.status_code == 200
    assert res.json()["api_key"] == "lkg_fake"
    assert client.get("/admin/keys", headers=headers).json() == {"keys": []}


def test_usage_sql_keeps_six_decimals():
    """Per-call costs are ~1e-5 USD; rounding the sum to 4 decimals showed 0."""
    assert "numeric(12,6)" in admin._USAGE_AGGREGATION_SQL
