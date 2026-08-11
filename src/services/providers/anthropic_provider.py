from __future__ import annotations

from anthropic import AsyncAnthropic

from src.config import settings


class AnthropicProvider:
    """Thin adapter over the Anthropic Messages SDK.

    System prompts and chat messages use separate fields in the Anthropic API,
    so the combined OpenAI-style message list is split before the call.
    """

    def __init__(self):
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def chat_completion(self, model: str, messages: list[dict], **kwargs) -> dict:
        """Call the model and normalize the SDK response to the gateway shape."""
        system_prompt, chat_messages = _split_system_prompt(messages)
        response = await self._client.messages.create(
            model=model,
            system=system_prompt or None,
            messages=chat_messages,
            **kwargs,
        )
        return {
            "content": response.content[0].text if response.content else "",
            "model": response.model,
            "usage": _extract_usage(response.usage),
            "provider": "anthropic",
        }


def _split_system_prompt(messages: list[dict]) -> tuple[str, list[dict]]:
    """Return (system_prompt, non_system_messages) from a mixed message list."""
    system_prompt = ""
    chat_messages = []
    for message in messages:
        if message.get("role") == "system":
            system_prompt = message.get("content", "")
        else:
            chat_messages.append({"role": message["role"], "content": message.get("content", "")})
    return system_prompt, chat_messages


def _extract_usage(usage) -> dict:
    """Normalize the SDK usage object; missing usage degrades to zeros."""
    if not usage:
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    return {
        "prompt_tokens": usage.input_tokens,
        "completion_tokens": usage.output_tokens,
        "total_tokens": usage.input_tokens + usage.output_tokens,
    }
