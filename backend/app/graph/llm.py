"""LLM client — one place that knows how to call Claude.

Two tiers, configured in settings:
  DEEP_MODEL (LLM_MODEL_DEEP): synthesis — deep dive, thesis, risk, workspace
      challenge, prospectus, model baseline. Claude Opus 5.5 by default; its
      thinking is always on and `output_config.effort` (LLM_DEEP_EFFORT) sets
      how much it thinks.
  FAST_MODEL (LLM_MODEL_FAST): extraction and classification — quick screen,
      relationships, 8-K classifier, transcript passes. Haiku 4.5.

JSON-producing calls go through `complete_structured`, which uses the API's
native structured outputs (constrained decoding against the Pydantic model's
schema). Assistant-turn prefill is deliberately unsupported: Sonnet 4.6 and
every newer model reject it with a 400 (found 2026-04-11, commit 68f99af, then
reintroduced at five call sites before this guard existed).
"""

import logging
import time
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from backend.app.config import get_settings

logger = logging.getLogger(__name__)

_client: anthropic.AsyncAnthropic | None = None

T = TypeVar("T", bound=BaseModel)

# Thinking tokens count toward max_tokens, so call sites sized for a bare
# reply (200–600 tokens) would be cut off on a thinking model. 16K keeps a
# non-streaming request well inside the SDK's timeout budget.
THINKING_MIN_MAX_TOKENS = 16_000


def get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=get_settings().anthropic_api_key)
    return _client


DEEP_MODEL = get_settings().llm_model_deep
FAST_MODEL = get_settings().llm_model_fast


def _request_params(model: str, max_tokens: int) -> dict:
    """Per-model request knobs. Haiku 4.5 rejects `effort`; every other
    configured model thinks, so it gets the effort setting and headroom."""
    if model.startswith("claude-haiku"):
        return {"max_tokens": max_tokens}
    return {
        "max_tokens": max(max_tokens, THINKING_MIN_MAX_TOKENS),
        "output_config": {"effort": get_settings().llm_deep_effort},
    }


class LLMOutputError(Exception):
    """The model returned no usable output (truncated, refused, or empty)."""


def _system_blocks(system: str, use_cache: bool) -> list[dict]:
    system_content: list[dict] = [{"type": "text", "text": system}]
    if use_cache and len(system) > 500:
        system_content[0]["cache_control"] = {"type": "ephemeral"}
    return system_content


def _log_usage(kind: str, model: str, message, started: float) -> None:
    """One structured log line per call — tokens, cache, latency, stop reason."""
    usage = getattr(message, "usage", None)
    logger.info(
        "llm_call kind=%s model=%s stop=%s in=%s out=%s cache_read=%s cache_write=%s latency_ms=%d",
        kind, model, getattr(message, "stop_reason", None),
        getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None),
        getattr(usage, "cache_read_input_tokens", None),
        getattr(usage, "cache_creation_input_tokens", None),
        int((time.monotonic() - started) * 1000),
    )


def _check_stop_reason(message, model: str) -> None:
    if message.stop_reason == "max_tokens":
        raise LLMOutputError(f"{model} output truncated at max_tokens")
    if message.stop_reason == "refusal":
        raise LLMOutputError(f"{model} refused the request")


async def complete(
    system: str,
    user: str,
    model: str = DEEP_MODEL,
    max_tokens: int = 4096,
    use_cache: bool = True,
) -> str:
    """Single-turn completion. Returns full response text."""
    started = time.monotonic()
    message = await get_client().messages.create(
        model=model,
        system=_system_blocks(system, use_cache),  # type: ignore[arg-type]
        messages=[{"role": "user", "content": user}],
        **_request_params(model, max_tokens),
    )
    _log_usage("text", model, message, started)
    _check_stop_reason(message, model)
    return "".join(b.text for b in message.content if b.type == "text")


async def complete_structured(
    system: str,
    user: str,
    output_model: type[T],
    model: str = DEEP_MODEL,
    max_tokens: int = 4096,
    use_cache: bool = True,
) -> T:
    """Single-turn completion constrained to `output_model`'s JSON schema.

    Returns a validated instance. Raises LLMOutputError when the output was
    truncated or refused, and pydantic.ValidationError when a constraint the
    API cannot enforce (min/max, lengths — the SDK checks those client-side)
    fails. Never invents defaults: callers decide how to degrade.
    """
    started = time.monotonic()
    message = await get_client().messages.parse(
        model=model,
        system=_system_blocks(system, use_cache),  # type: ignore[arg-type]
        messages=[{"role": "user", "content": user}],
        output_format=output_model,
        **_request_params(model, max_tokens),
    )
    _log_usage(f"structured:{output_model.__name__}", model, message, started)
    _check_stop_reason(message, model)
    parsed = message.parsed_output
    if parsed is None:
        raise LLMOutputError(f"{model} returned no {output_model.__name__}")
    return parsed

