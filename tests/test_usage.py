"""record_usage writes one parameterised row and never raises."""

from __future__ import annotations

import asyncio

from src.services import usage


class FakeConn:
    def __init__(self, fail: bool = False):
        self.calls: list[tuple] = []
        self.fail = fail

    async def execute(self, sql, *args):
        if self.fail:
            raise RuntimeError("db down")
        self.calls.append((sql, args))


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        conn = self.conn

        class Ctx:
            async def __aenter__(self_inner):
                return conn

            async def __aexit__(self_inner, *exc):
                return False

        return Ctx()


def test_inserts_one_row_with_bound_parameters(monkeypatch):
    conn = FakeConn()

    async def get_pool():
        return FakePool(conn)

    monkeypatch.setattr(usage, "get_pool", get_pool)
    asyncio.run(
        usage.record_usage(
            7, "openai", "gpt-4o", {"prompt_tokens": 3, "completion_tokens": 4}, 0.00012345678, 1.5
        )
    )
    sql, args = conn.calls[0]
    assert "$1" in sql and "INSERT INTO usage_logs" in sql
    assert args == (7, "openai", "gpt-4o", 3, 4, 0.000123, 1500)


def test_database_error_is_swallowed(monkeypatch):
    async def get_pool():
        return FakePool(FakeConn(fail=True))

    monkeypatch.setattr(usage, "get_pool", get_pool)
    usage_row = {"prompt_tokens": 1, "completion_tokens": 1}
    asyncio.run(usage.record_usage(1, "openai", "gpt-4o", usage_row, 0, 0))
