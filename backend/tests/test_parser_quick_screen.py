"""Unittest for parse_structured_output + QuickScreenOutput.

Converted from backend/scripts/verify_quick_screen_parser.py (2026-06-10).
"""

from __future__ import annotations

import json
import unittest

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


class TestQuickScreenParser(unittest.TestCase):

    def test_well_formed_json(self) -> None:
        """Well-formed JSON matching the schema parses successfully."""
        raw = _make_good_json()
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.overall_score == 73
        assert parsed.recommendation == "GO"
        assert len(parsed.dimensions) == 5
        assert parsed.dimensions[0].name == "Business Quality"

    def test_json_with_markdown_fences(self) -> None:
        """JSON wrapped in ```json ... ``` fences still parses."""
        raw = f"```json\n{_make_good_json()}\n```"
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.overall_score == 73

    def test_json_with_prose_preamble(self) -> None:
        """JSON preceded by prose preamble still parses via regex extraction."""
        raw = f"Here is my analysis:\n\n{_make_good_json()}\n\nLet me know if you need more."
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None

    def test_missing_dimensions_field(self) -> None:
        """Output missing the `dimensions` key fails validation."""
        payload = json.loads(_make_good_json())
        del payload["dimensions"]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert parsed is None
        assert err is not None
        assert "dimensions" in err.lower()

    def test_four_dimensions_instead_of_five(self) -> None:
        """Only 4 dimensions returned -> length validator fails."""
        payload = json.loads(_make_good_json())
        payload["dimensions"] = payload["dimensions"][:4]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert parsed is None
        assert err is not None

    def test_wrong_dimension_name(self) -> None:
        """A dimension with an unknown name fails the field validator."""
        payload = json.loads(_make_good_json())
        payload["dimensions"][0]["name"] = "Biz Quality"
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert parsed is None
        assert err is not None
        assert "biz quality" in err.lower() or "name" in err.lower()

    def test_dimension_score_out_of_range(self) -> None:
        """A dimension score > 20 fails the range validator."""
        payload = json.loads(_make_good_json())
        payload["dimensions"][0]["score"] = 25
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert parsed is None
        assert err is not None

    def test_overall_score_out_of_range(self) -> None:
        """overall_score > 100 fails the range validator."""
        raw = _make_good_json(overall_score=150)
        parsed, err = parse_structured_output(raw, QuickScreenOutput)
        assert parsed is None
        assert err is not None

    def test_empty_input(self) -> None:
        """Empty string input returns a parse error, never raises."""
        parsed, err = parse_structured_output("", QuickScreenOutput)
        assert parsed is None
        assert err == "empty response"

    def test_malformed_garbage(self) -> None:
        """Non-JSON garbage returns a parse error mentioning 'no JSON'."""
        parsed, err = parse_structured_output("hello world, definitely not json", QuickScreenOutput)
        assert parsed is None
        assert err is not None
        assert "no json" in err.lower() or "json" in err.lower()


if __name__ == "__main__":
    unittest.main()
