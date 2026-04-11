"""Standalone verification for parse_structured_output + QuickScreenOutput.

Run from project root:
    python -m backend.scripts.verify_quick_screen_parser

Exits non-zero on any assertion failure.
"""

from __future__ import annotations

import json
import sys

from backend.app.graph.output_parser import parse_structured_output
from backend.app.models.phase_schemas import (
    QuickScreenOutput,
    QUICK_SCREEN_DIMENSIONS,
)


def _make_good_json(**overrides) -> str:
    """Build a well-formed JSON string, optionally with a field overridden."""
    payload = {
        "overall_score": 73,
        "recommendation": "GO",
        "dimensions": [
            {"name": name, "score": 15, "max_score": 20, "rationale": f"Rationale for {name}"}
            for name in QUICK_SCREEN_DIMENSIONS
        ],
        "thesis": "A plausible thesis paragraph about the company and its prospects.",
        "key_risk": "A plausible key risk statement.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_1_well_formed_json() -> None:
    """Well-formed JSON matching the schema parses successfully."""
    raw = _make_good_json()
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None
    assert parsed.overall_score == 73
    assert parsed.recommendation == "GO"
    assert len(parsed.dimensions) == 5
    assert parsed.dimensions[0].name == "Business Quality"


def test_2_json_with_markdown_fences() -> None:
    """JSON wrapped in ```json ... ``` fences still parses."""
    raw = f"```json\n{_make_good_json()}\n```"
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None
    assert parsed.overall_score == 73


def test_3_json_with_prose_preamble() -> None:
    """JSON preceded by prose preamble still parses via regex extraction."""
    raw = f"Here is my analysis:\n\n{_make_good_json()}\n\nLet me know if you need more."
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None


def test_4_missing_dimensions_field() -> None:
    """Output missing the `dimensions` key fails validation."""
    payload = json.loads(_make_good_json())
    del payload["dimensions"]
    raw = json.dumps(payload)
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert parsed is None
    assert err is not None
    assert "dimensions" in err.lower()


def test_5_four_dimensions_instead_of_five() -> None:
    """Only 4 dimensions returned -> length validator fails."""
    payload = json.loads(_make_good_json())
    payload["dimensions"] = payload["dimensions"][:4]
    raw = json.dumps(payload)
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert parsed is None
    assert err is not None


def test_6_wrong_dimension_name() -> None:
    """A dimension with an unknown name fails the field validator."""
    payload = json.loads(_make_good_json())
    payload["dimensions"][0]["name"] = "Biz Quality"
    raw = json.dumps(payload)
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert parsed is None
    assert err is not None
    assert "biz quality" in err.lower() or "name" in err.lower()


def test_7_dimension_score_out_of_range() -> None:
    """A dimension score > 20 fails the range validator."""
    payload = json.loads(_make_good_json())
    payload["dimensions"][0]["score"] = 25
    raw = json.dumps(payload)
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert parsed is None
    assert err is not None


def test_8_overall_score_out_of_range() -> None:
    """overall_score > 100 fails the range validator."""
    raw = _make_good_json(overall_score=150)
    parsed, err = parse_structured_output(raw, QuickScreenOutput)
    assert parsed is None
    assert err is not None


def test_9_empty_input() -> None:
    """Empty string input returns a parse error, never raises."""
    parsed, err = parse_structured_output("", QuickScreenOutput)
    assert parsed is None
    assert err == "empty response"


def test_10_malformed_garbage() -> None:
    """Non-JSON garbage returns a parse error mentioning 'no JSON'."""
    parsed, err = parse_structured_output("hello world, definitely not json", QuickScreenOutput)
    assert parsed is None
    assert err is not None
    assert "no json" in err.lower() or "json" in err.lower()


def main() -> int:
    tests = [
        test_1_well_formed_json,
        test_2_json_with_markdown_fences,
        test_3_json_with_prose_preamble,
        test_4_missing_dimensions_field,
        test_5_four_dimensions_instead_of_five,
        test_6_wrong_dimension_name,
        test_7_dimension_score_out_of_range,
        test_8_overall_score_out_of_range,
        test_9_empty_input,
        test_10_malformed_garbage,
    ]

    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  ✗ {fn.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ! {fn.__name__}: unexpected {type(e).__name__}: {e}")

    print()
    if failures:
        print(f"FAILED: {failures}/{len(tests)}")
        return 1
    print(f"OK: {len(tests)}/{len(tests)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
