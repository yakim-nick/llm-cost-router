from __future__ import annotations

import re
import tiktoken

from src.config import settings


class ComplexityRouter:
    """Estimates how hard a prompt is and picks the cheapest fitting provider/model."""

    # Token-count magnitude is capped so long casual chats do not dominate the score.
    TOKEN_COUNT_CAP = 2000.0
    TOKEN_WEIGHT = 0.4
    # Average word length (above the baseline of 4) contributes at most this much.
    WORD_LENGTH_SCALE = 6.0
    WORD_LENGTH_WEIGHT = 0.2
    # Code signatures are scaled against this many possible pattern hits.
    CODE_SCALE = 10
    CODE_WEIGHT = 0.25
    QUESTION_WEIGHT = 0.15
    # Combined weights above sum to 1.0, so the final score is clamped to [0, 1].
    MAX_SCORE = 1.0

    def __init__(self):
        self._tokenizer = tiktoken.get_encoding("cl100k_base")
        self._low_threshold = settings.complexity_threshold_low
        self._high_threshold = settings.complexity_threshold_high
        self._provider_order = [p.strip() for p in settings.provider_preference_order.split(",")]

    def assess_complexity(self, messages: list[dict]) -> float:
        """Score prompt complexity in [0, 1]; 0 is trivial, 1 is very complex.

        The score blends token count, average word length, code presence, and
        question density so a short code-heavy request ranks above a long
        casual conversation.
        """
        text = self._join_messages(messages)
        if not text:
            return 0.0

        score = 0.0
        score += self._token_contribution(text)
        score += self._word_length_contribution(text)
        score += self._code_contribution(text)
        score += self._question_contribution(text)
        return min(score, self.MAX_SCORE)

    def select_provider(self, complexity: float) -> tuple[str, str]:
        """Return (provider, tier) for the given complexity.

        Cheap provider below the low threshold, strongest provider above the
        high threshold, and the first preferred provider in between.
        """
        if complexity <= self._low_threshold:
            return self._provider_order[0], "cheapest"
        if complexity >= self._high_threshold:
            best = (
                self._provider_order[1]
                if len(self._provider_order) > 1
                else self._provider_order[0]
            )
            return best, "best"
        return self._provider_order[0], "balanced"

    def select_model(self, provider: str, tier: str, complexity: float) -> str:
        """Pick the concrete model name for a provider/tier pairing."""
        tier_models = {
            "openai": {"cheapest": "gpt-4o-mini", "balanced": "gpt-4o", "best": "gpt-4o"},
            "anthropic": {
                "cheapest": "claude-3-haiku",
                "balanced": "claude-3-sonnet",
                "best": "claude-3-opus",
            },
        }
        provider_models = tier_models.get(provider, tier_models["openai"])
        return provider_models.get(tier, provider_models["balanced"])

    @staticmethod
    def _join_messages(messages: list[dict]) -> str:
        """Concatenate every non-empty message into one blob for analysis."""
        parts = [m.get("content", "") for m in messages if m.get("content")]
        return " ".join(parts)

    def _token_contribution(self, text: str) -> float:
        """Score share for raw prompt length (token count), capped and weighted."""
        token_count = len(self._tokenizer.encode(text))
        return min(token_count / self.TOKEN_COUNT_CAP, self.TOKEN_WEIGHT)

    def _word_length_contribution(self, text: str) -> float:
        """Score share for long-winded phrasing, capped and weighted."""
        words = text.split()
        if not words:
            return 0.0
        avg_word_len = len(text.replace(" ", "")) / len(words)
        return min(max(avg_word_len - 4, 0) / self.WORD_LENGTH_SCALE, self.WORD_LENGTH_WEIGHT)

    def _code_contribution(self, text: str) -> float:
        """Score share for how code-like the text is (syntax fingerprints)."""
        code_patterns = [
            r"\b(def |class |import |from |return |if __)",
            r"\bfunction\s*\(",
            r"\bconst\s+\w+\s*=",
            r"\bSELECT\b.*\bFROM\b",
            r'\{\s*"[^"]+"\s*:',
            r"->|=>|===|!=",
        ]
        matches = sum(1 for p in code_patterns if re.search(p, text, re.IGNORECASE))
        return min(matches / self.CODE_SCALE, 1.0) * self.CODE_WEIGHT

    def _question_contribution(self, text: str) -> float:
        """Score share for how conversational (question-heavy) the text is."""
        sentences = re.split(r"[.!?]+", text)
        if not sentences:
            return 0.0
        questions = sum(1 for s in sentences if "?" in s)
        return min(questions / len(sentences) * 3, 1.0) * self.QUESTION_WEIGHT
