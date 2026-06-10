"""Unittest for parse_structured_output + ThesisOutput.

Converted from backend/scripts/verify_thesis_parser.py (2026-06-10).
"""

from __future__ import annotations

import json
import unittest

from backend.app.graph.output_parser import parse_structured_output
from backend.app.models.phase_schemas import ThesisOutput


def _make_good_json(**overrides) -> str:
    payload = {
        "core_thesis": "A plausible thesis paragraph about the company and its investment merits over the next 12-18 months.",
        "bull_case": [
            {"title": "Strong market position", "evidence": "23% unit share per industry data"},
            {"title": "Revenue growth acceleration", "evidence": "Q4 earnings showed 32% YoY growth"},
            {"title": "Margin expansion trajectory", "evidence": "FMP income statement series 2024-2025"},
        ],
        "bear_case": [
            {"title": "Valuation premium vs peers", "evidence": "Fwd P/E 32x vs peer median 24x"},
            {"title": "Customer concentration risk", "evidence": "Top 5 customers = 38% revenue per 10-K"},
            {"title": "Competitive pricing pressure", "evidence": "New entrants undercutting by 15-20%"},
        ],
        "variant_perception": "Consensus views the company as a cyclical proxy. Variant: structural transition to a platform business.",
        "catalysts": [
            {"timeframe": "Next 1-3 mo", "description": "Q2 2026 earnings call"},
            {"timeframe": "3-6 mo", "description": "Major customer vendor announcement"},
            {"timeframe": "6-12 mo", "description": "New facility scale-up impact"},
        ],
        "conviction_score": 82,
        "conviction_rationale": "High conviction based on durable moat and clear demand visibility.",
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestThesisParser(unittest.TestCase):

    def test_well_formed_json(self) -> None:
        raw = _make_good_json()
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.conviction_score == 82
        assert len(parsed.bull_case) == 3
        assert len(parsed.bear_case) == 3
        assert len(parsed.catalysts) == 3
        assert parsed.bull_case[0].title == "Strong market position"

    def test_json_with_markdown_fences(self) -> None:
        raw = f"```json\n{_make_good_json()}\n```"
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.conviction_score == 82

    def test_json_with_prose_preamble(self) -> None:
        raw = f"Here is my analysis:\n\n{_make_good_json()}\n\nLet me know if you need more."
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None

    def test_missing_core_thesis(self) -> None:
        payload = json.loads(_make_good_json())
        del payload["core_thesis"]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert parsed is None
        assert err is not None
        assert "core_thesis" in err.lower()

    def test_bull_case_too_few(self) -> None:
        payload = json.loads(_make_good_json())
        payload["bull_case"] = payload["bull_case"][:1]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert parsed is None
        assert err is not None

    def test_bull_case_too_many(self) -> None:
        payload = json.loads(_make_good_json())
        payload["bull_case"] = payload["bull_case"] + [
            {"title": f"Extra point {i}", "evidence": f"Evidence {i}"}
            for i in range(3)
        ]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert parsed is None
        assert err is not None

    def test_catalysts_too_few(self) -> None:
        payload = json.loads(_make_good_json())
        payload["catalysts"] = payload["catalysts"][:2]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert parsed is None
        assert err is not None

    def test_conviction_score_out_of_range(self) -> None:
        raw = _make_good_json(conviction_score=150)
        parsed, err = parse_structured_output(raw, ThesisOutput)
        assert parsed is None
        assert err is not None

    def test_empty_input(self) -> None:
        parsed, err = parse_structured_output("", ThesisOutput)
        assert parsed is None
        assert err == "empty response"

    def test_malformed_garbage(self) -> None:
        parsed, err = parse_structured_output("hello world, not json", ThesisOutput)
        assert parsed is None
        assert err is not None
        assert "no json" in err.lower() or "json" in err.lower()


if __name__ == "__main__":
    unittest.main()
