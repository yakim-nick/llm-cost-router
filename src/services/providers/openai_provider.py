from __future__ import annotations

from openai import AsyncOpenAI
from src.config import settings


class OpenAIProvider:
    def __init__(self):
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)

    async def chat_completion(self, model: str, messages: list[dict], **kwargs) -> dict:
        response = await self._client.chat.completions.create(
            model=model,
            messages=messages,
            **kwargs,
        )
        return {
            "content": response.choices[0].message.content or "",
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                "total_tokens": response.usage.total_tokens if response.usage else 0,
            },
            "provider": "openai",
        }
