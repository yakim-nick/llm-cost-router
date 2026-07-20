from __future__ import annotations

from anthropic import AsyncAnthropic
from src.config import settings


class AnthropicProvider:
    def __init__(self):
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat_completion(self, model: str, messages: list[dict], **kwargs) -> dict:
        system = ""
        chat_messages = []
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            else:
                chat_messages.append({"role": m["role"], "content": m.get("content", "")})

        response = await self._client.messages.create(
            model=model,
            system=system or None,
            messages=chat_messages,
            **kwargs,
        )
        return {
            "content": response.content[0].text if response.content else "",
            "model": response.model,
            "usage": {
                "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                "completion_tokens": response.usage.output_tokens if response.usage else 0,
                "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
            },
            "provider": "anthropic",
        }
