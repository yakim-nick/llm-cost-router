from __future__ import annotations

from openai import AsyncOpenAI

from src.config import settings


class OpenAIProvider:
    """Thin adapter over the OpenAI chat-completions SDK."""

    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def chat_completion(self, model: str, messages: list[dict], **kwargs) -> dict:
        """Call the model and normalize the SDK response to the gateway shape."""
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        return {
            "content": response.choices[0].message.content or "",
            "model": response.model,
            "usage": _extract_usage(response.usage),
            "provider": "openai",
        }


def _extract_usage(usage) -> dict:
    """Normalize the SDK usage object; missing usage degrades to zeros."""
    return {
        "prompt_tokens": usage.prompt_tokens if usage else 0,
        "completion_tokens": usage.completion_tokens if usage else 0,
        "total_tokens": usage.total_tokens if usage else 0,
    }
