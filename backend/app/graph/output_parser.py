"""Lenient JSON helpers for LLM text output.

App code gets JSON through graph/llm.py::complete_structured (native
structured outputs). parse_structured_output below is no longer called by the
app; it remains as the harness for the schema tests (test_parser_*.py).
extract_json_value serves outputs with no fixed schema (transcript passes).

Original notes:

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
        logger.warning("parse_structured_output JSONDecodeError for %s: %s", schema.__name__, e)
        return None, f"JSONDecodeError: {e}"

    try:
        parsed = schema.model_validate_json(candidate)
        return parsed, None
    except ValidationError as e:
        # Pydantic v2 has a readable __str__
        logger.warning("parse_structured_output ValidationError for %s: %s", schema.__name__, e)
        return None, f"ValidationError: {e}"


def extract_json_value(raw_text: str) -> object | None:
    """Return the first JSON object/array embedded in free text, or None.

    For outputs whose shape varies too much for a fixed schema (the transcript
    passes). Handles markdown fences, prose before the JSON and notes after it:
    raw_decode stops at the end of the first complete value, so trailing text
    can't break the parse the way the greedy regex above can.
    """
    if not raw_text:
        return None
    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, ValueError):
        pass
    decoder = json.JSONDecoder()
    for i, ch in enumerate(raw_text):
        if ch in "{[":
            try:
                value, _end = decoder.raw_decode(raw_text, i)
            except json.JSONDecodeError:
                continue
            return value
    return None
