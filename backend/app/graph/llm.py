"""LLM client factory — returns the right Anthropic model for each phase.

Sonnet: deep_dive, thesis, risk
Haiku:  quick_screen, position, transcript passes 1–2
"""

import anthropic
from backend.app.config import get_settings

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


SONNET = "claude-sonnet-4-6"
HAIKU  = "claude-haiku-4-5-20251001"


async def complete(
    system: str,
    user: str,
    model: str = SONNET,
    max_tokens: int = 4096,
    use_cache: bool = True,
    assistant_prefill: str | None = None,
) -> str:
    """Single-turn completion. Returns full response text.

    When assistant_prefill is provided, an assistant turn is added with that
    content and the prefill is prepended to the returned text so callers see
    the complete document. This is the Anthropic-recommended pattern for
    locking the model into a specific output format (e.g. JSON).
    """
    client = get_client()

    system_content: list[dict] = [{"type": "text", "text": system}]
    if use_cache and len(system) > 500:
        system_content[0]["cache_control"] = {"type": "ephemeral"}  # type: ignore[index]

    messages: list[dict] = [{"role": "user", "content": user}]
    if assistant_prefill is not None:
        messages.append({"role": "assistant", "content": assistant_prefill})

    message = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_content,  # type: ignore[arg-type]
        messages=messages,  # type: ignore[arg-type]
    )
    text = message.content[0].text  # type: ignore[union-attr]

    # Anthropic returns only the continuation after the prefill — prepend it
    # back so callers see the complete document.
    if assistant_prefill is not None:
        text = assistant_prefill + text
    return text


async def stream_complete(
    system: str,
    user: str,
    model: str = SONNET,
    max_tokens: int = 4096,
    use_cache: bool = True,
):
    """Async generator that yields text chunks as they stream."""
    client = get_client()

    system_content: list[dict] = [{"type": "text", "text": system}]
    if use_cache and len(system) > 500:
        system_content[0]["cache_control"] = {"type": "ephemeral"}  # type: ignore[index]

    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_content,  # type: ignore[arg-type]
        messages=[{"role": "user", "content": user}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
