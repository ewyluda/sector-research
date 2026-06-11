"""Unittest for parse_structured_output + DeepDiveCategoryOutput.

Converted from backend/scripts/verify_deep_dive_parser.py (2026-06-10).
"""

from __future__ import annotations

import json
import unittest

from backend.app.graph.output_parser import parse_structured_output
from backend.app.models.phase_schemas import DeepDiveCategoryOutput


def _make_good_json(**overrides) -> str:
    payload = {
        "score": 72,
        "score_rationale": "Strong revenue growth and margins offset by elevated valuation multiple. Business model is high quality but priced for perfection.",
        "key_findings": [
            {
                "finding": "Revenue growing 28% YoY, accelerating from 22% prior quarter",
                "evidence": "FMP income statement FY2025 vs FY2024: $4.2B → $5.4B",
            },
            {
                "finding": "Gross margins expanding to 68%, up 200bps YoY",
                "evidence": "FMP income statement: gross profit $3.67B on $5.4B revenue",
            },
            {
                "finding": "Net retention rate above 130% indicating strong upsell motion",
                "evidence": "Management commentary in Q4 2025 earnings call",
            },
        ],
        "analysis": "The business demonstrates exceptional quality across multiple dimensions. "
                    "Revenue growth is accelerating driven by enterprise adoption and platform "
                    "expansion. The gross margin profile at 68% is best-in-class for the sector "
                    "and continues to expand as the company scales. Operating leverage is evident "
                    "with operating margins improving 400bps YoY to 22%. Free cash flow conversion "
                    "is strong at 85% of operating income. The primary concern is valuation — trading "
                    "at 45x forward earnings vs sector median of 28x. This premium is partially "
                    "justified by the growth differential but leaves limited margin of safety.",
        "data_gaps": ["No insider transaction data available for last 6 months"],
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestDeepDiveParser(unittest.TestCase):

    def test_well_formed_json(self) -> None:
        raw = _make_good_json()
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.score == 72
        assert len(parsed.key_findings) == 3
        assert parsed.key_findings[0].finding.startswith("Revenue growing")
        assert len(parsed.data_gaps) == 1

    def test_json_with_markdown_fences(self) -> None:
        raw = f"```json\n{_make_good_json()}\n```"
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.score == 72

    def test_json_with_prose_preamble(self) -> None:
        raw = f"Here is my analysis:\n\n{_make_good_json()}\n\nEnd of analysis."
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None

    def test_five_findings_maximum(self) -> None:
        extra = [
            {"finding": f"Finding {i}", "evidence": f"Evidence {i}"}
            for i in range(5)
        ]
        raw = _make_good_json(key_findings=extra)
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert len(parsed.key_findings) == 5

    def test_too_few_findings(self) -> None:
        two = [
            {"finding": "Finding A", "evidence": "Evidence A"},
            {"finding": "Finding B", "evidence": "Evidence B"},
        ]
        raw = _make_good_json(key_findings=two)
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert parsed is None
        assert err is not None

    def test_score_out_of_range(self) -> None:
        raw = _make_good_json(score=150)
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert parsed is None
        assert err is not None

    def test_missing_required_field(self) -> None:
        payload = json.loads(_make_good_json())
        del payload["score_rationale"]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert parsed is None
        assert err is not None

    def test_empty_input(self) -> None:
        parsed, err = parse_structured_output("", DeepDiveCategoryOutput)
        assert parsed is None
        assert err == "empty response"

    def test_malformed_garbage(self) -> None:
        parsed, err = parse_structured_output("not json at all", DeepDiveCategoryOutput)
        assert parsed is None
        assert err is not None
        assert "json" in err.lower()

    def test_empty_data_gaps(self) -> None:
        raw = _make_good_json(data_gaps=[])
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.data_gaps == []

    def test_no_data_gaps_field(self) -> None:
        payload = json.loads(_make_good_json())
        del payload["data_gaps"]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, DeepDiveCategoryOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.data_gaps == []


if __name__ == "__main__":
    unittest.main()
