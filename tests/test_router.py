from __future__ import annotations

import pytest
from src.services.cache import SemanticCache
from src.services.router import ComplexityRouter
from src.services.auth import AuthService


class TestSemanticCache:
    def test_make_key_deterministic(self):
        cache = SemanticCache()
        messages = [{"role": "user", "content": "hello"}]
        key1 = cache._make_key(messages, "gpt-4o")
        key2 = cache._make_key(messages, "gpt-4o")
        assert key1 == key2

    def test_make_key_differs_by_model(self):
        cache = SemanticCache()
        messages = [{"role": "user", "content": "hello"}]
        key1 = cache._make_key(messages, "gpt-4o")
        key2 = cache._make_key(messages, "gpt-4o-mini")
        assert key1 != key2

    def test_make_key_differs_by_messages(self):
        cache = SemanticCache()
        key1 = cache._make_key([{"role": "user", "content": "hi"}], "gpt-4o")
        key2 = cache._make_key([{"role": "user", "content": "hello"}], "gpt-4o")
        assert key1 != key2


class TestComplexityRouter:
    def setup_method(self):
        self.router = ComplexityRouter()

    def test_empty_text_returns_zero(self):
        score = self.router.assess_complexity([{"role": "user", "content": ""}])
        assert score == 0.0

    def test_simple_greeting_low_complexity(self):
        score = self.router.assess_complexity([{"role": "user", "content": "Hello, how are you?"}])
        assert 0.0 <= score <= 1.0

    def test_code_increases_complexity(self):
        simple = self.router.assess_complexity([{"role": "user", "content": "What is the weather?"}])
        code = self.router.assess_complexity([{
            "role": "user",
            "content": "Write a Python function that implements merge sort with O(n log n) complexity",
        }])
        assert code > simple

    def test_select_provider_returns_tuple(self):
        provider, tier = self.router.select_provider(0.1)
        assert isinstance(provider, str)
        assert isinstance(tier, str)

    def test_select_model_returns_valid_model(self):
        model = self.router.select_model("openai", "cheapest", 0.1)
        assert model == "gpt-4o-mini"

    def test_high_complexity_selects_best_model(self):
        model = self.router.select_model("openai", "best", 0.9)
        assert model == "gpt-4o"


class TestAuthService:
    def test_generate_key_format(self):
        key = AuthService.generate_key()
        assert key.startswith("lkg_")
        assert len(key) > 32

    def test_hash_and_verify(self):
        key = AuthService.generate_key()
        key_hash = AuthService.hash_key(key)
        assert AuthService.verify_key(key, key_hash)

    def test_wrong_key_fails(self):
        key = AuthService.generate_key()
        key_hash = AuthService.hash_key(key)
        assert not AuthService.verify_key("wrong-key", key_hash)
