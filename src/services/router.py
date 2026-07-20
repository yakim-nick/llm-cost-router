from __future__ import annotations

import re
import tiktoken
from src.config import settings


class ComplexityRouter:
    def __init__(self):
        self._tokenizer = tiktoken.get_encoding("cl100k_base")
        self._low_threshold = settings.complexity_threshold_low
        self._high_threshold = settings.complexity_threshold_high
        self._provider_order = [p.strip() for p in settings.provider_preference_order.split(",")]

    def assess_complexity(self, messages: list[dict]) -> float:
        text = " ".join(m.get("content", "") for m in messages if m.get("content"))
        if not text:
            return 0.0

        tokens = self._tokenizer.encode(text)
        token_count = len(tokens)
        avg_word_len = len(text.replace(" ", "")) / max(len(text.split()), 1)
        code_ratio = self._estimate_code_ratio(text)
        question_ratio = self._estimate_question_ratio(text)

        score = 0.0
        score += min(token_count / 2000, 0.4)
        score += min(max(avg_word_len - 4, 0) / 6, 0.2)
        score += code_ratio * 0.25
        score += question_ratio * 0.15
        return min(score, 1.0)

    def _estimate_code_ratio(self, text: str) -> float:
        code_patterns = [
            r"\b(def |class |import |from |return |if __)",
            r"\bfunction\s*\(", r"\bconst\s+\w+\s*=",
            r"\bSELECT\b.*\bFROM\b", r"\{\s*\"[^\"]+\"\s*:",
            r"->|=>|===|!=",
        ]
        matches = sum(1 for p in code_patterns if re.search(p, text, re.IGNORECASE))
        return min(matches / 10, 1.0)

    def _estimate_question_ratio(self, text: str) -> float:
        sentences = re.split(r'[.!?]+', text)
        if not sentences:
            return 0.0
        questions = sum(1 for s in sentences if "?" in s)
        return min(questions / len(sentences) * 3, 1.0)

    def select_provider(self, complexity: float) -> tuple[str, str]:
        if complexity <= self._low_threshold:
            return self._provider_order[0], "cheapest"
        elif complexity >= self._high_threshold:
            return self._provider_order[1] if len(self._provider_order) > 1 else self._provider_order[0], "best"
        else:
            return self._provider_order[0], "balanced"

    def select_model(self, provider: str, tier: str, complexity: float) -> str:
        models = {
            "openai": {"cheapest": "gpt-4o-mini", "balanced": "gpt-4o", "best": "gpt-4o"},
            "anthropic": {"cheapest": "claude-3-haiku", "balanced": "claude-3-sonnet", "best": "claude-3-opus"},
        }
        provider_models = models.get(provider, models["openai"])
        return provider_models.get(tier, provider_models["balanced"])
