"""Fakes for `complete_structured` (no `test_` prefix: not collected as a suite).

The real call constrains the model to `output_model`'s JSON schema and returns a
validated instance, so the faithful fake validates a JSON fixture against the
`output_model` the caller asked for — a fixture that doesn't fit the schema
fails the same way a real schema mismatch would.
"""
from unittest.mock import AsyncMock


def structured_returning(raw_json: str) -> AsyncMock:
    """Every call returns `raw_json` validated as the requested output_model."""
    async def _fake(*, output_model, **_kwargs):
        return output_model.model_validate_json(raw_json)
    return AsyncMock(side_effect=_fake)


def structured_from(raw_fn) -> AsyncMock:
    """Delegate to `raw_fn(**kwargs)` (sync or async, returning a JSON string)
    so a fixture can vary by prompt, then validate as the output_model."""
    async def _fake(*, output_model, **kwargs):
        raw = raw_fn(**kwargs)
        if hasattr(raw, "__await__"):
            raw = await raw
        return output_model.model_validate_json(raw)
    return AsyncMock(side_effect=_fake)
