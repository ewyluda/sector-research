"""Generic LLM-output → Pydantic-model parser.

Used by phase nodes to convert structured JSON responses into validated
dataclass-like objects. Forgiving enough to handle common LLM quirks
(prose preamble, markdown fences) but strict at the validation boundary.

The contract: parse_structured_output() never raises. On any failure it
returns (None, error_message: str) so callers can persist the error
alongside the raw response for debugging and fall through to a prose
rendering path without cascade failures.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Matches the outermost JSON object, including balanced braces.
# Greedy by design — we want the LARGEST valid-looking blob when the LLM
# emits preamble + JSON + postamble.
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_structured_output(
    raw_text: str,
    schema: type[T],
) -> tuple[T | None, str | None]:
    """Parse and validate an LLM response against a Pydantic schema.

    Returns (parsed_object, None) on success or (None, error_message) on
    failure. Never raises — all error paths return the error as a string.

    Handles:
        - Clean JSON (most common case when using the assistant-prefill pattern)
        - JSON wrapped in ```json ... ``` markdown fences
        - JSON with prose preamble before the opening brace
        - Schema validation errors (returns readable Pydantic error message)
    """
    if not raw_text:
        return None, "empty response"

    # Happy path: try direct parse first (works when prefill + no fences)
    try:
        parsed = schema.model_validate_json(raw_text)
        return parsed, None
    except (ValidationError, ValueError):
        pass

    # Fall back to regex extraction of the outermost {...} blob
    match = _JSON_OBJECT_RE.search(raw_text)
    if not match:
        return None, "no JSON object found in response"

    candidate = match.group(0)
    try:
        # json.loads first to produce a clearer error than Pydantic's
        json.loads(candidate)
    except json.JSONDecodeError as e:
        return None, f"JSONDecodeError: {e}"

    try:
        parsed = schema.model_validate_json(candidate)
        return parsed, None
    except ValidationError as e:
        # Pydantic v2 has a readable __str__
        return None, f"ValidationError: {e}"
