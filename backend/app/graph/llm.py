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

import json
import logging
import time
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

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
    API cannot enforce (min/max, lengths — sent to the model only as hints and
    checked here) fails. Over-length lists and strings are clamped to their
    bound (see clamp_too_long); nothing is ever invented — callers decide how
    to degrade.

    Uses messages.create + an explicit schema rather than messages.parse:
    parse validates inside the SDK before stop_reason can be checked, so a
    max_tokens truncation surfaced as an opaque "EOF while parsing" error.
    """
    params = _request_params(model, max_tokens)
    params["output_config"] = {
        **params.get("output_config", {}),
        "format": {"type": "json_schema", "schema": anthropic.transform_schema(output_model)},
    }
    started = time.monotonic()
    message = await get_client().messages.create(
        model=model,
        system=_system_blocks(system, use_cache),  # type: ignore[arg-type]
        messages=[{"role": "user", "content": user}],
        **params,
    )
    _log_usage(f"structured:{output_model.__name__}", model, message, started)
    _check_stop_reason(message, model)
    text = "".join(b.text for b in message.content if b.type == "text")
    if not text:
        raise LLMOutputError(f"{model} returned no {output_model.__name__}")
    try:
        return output_model.model_validate_json(text)
    except ValidationError as e:
        failure = e
    data = json.loads(text)  # the API guarantees schema-shaped JSON
    clamped: list[str] = []
    # Pydantic stops at a too-long list without validating its items, so a
    # string inside it only surfaces on the next round.
    for _ in range(3):
        errors = failure.errors()
        if not clamp_too_long(data, errors):
            raise failure
        clamped += [".".join(map(str, err["loc"])) for err in errors]
        try:
            result = output_model.model_validate(data)
        except ValidationError as e:
            failure = e
            continue
        logger.warning("%s: clamped over-length fields in %s: %s", model, output_model.__name__, clamped)
        return result
    raise failure


_TOO_LONG = {"too_long", "string_too_long"}


def clamp_too_long(data: object, errors: list) -> bool:
    """Trim lists and strings that exceed their declared max_length, in place.

    Structured outputs pass maxItems/maxLength to the model as hints only, so a
    sixth item in a five-item list (seen live: a quick screen with an extra,
    empty dimension) would otherwise fail the whole phase. Over-length output
    has the required content plus extra, so keeping the first N is safe.
    Returns False — clamp nothing — if any error is of another kind: too-short
    or wrong content can't be repaired without inventing it.
    """
    if not errors or any(err["type"] not in _TOO_LONG for err in errors):
        return False
    # Deepest paths first, so trimming a list can't invalidate a string path inside it.
    for err in sorted(errors, key=lambda err: len(err["loc"]), reverse=True):
        *parents, key = err["loc"]
        node = data
        try:
            for part in parents:
                node = node[part]  # type: ignore[index]
            node[key] = node[key][: err["ctx"]["max_length"]]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            return False
    return True
