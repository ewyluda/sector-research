"""Unittest for parse_structured_output + RiskStressTestOutput.

Converted from backend/scripts/verify_risk_parser.py (2026-06-10).
"""

from __future__ import annotations

import json
import unittest

from backend.app.graph.output_parser import parse_structured_output
from backend.app.models.phase_schemas import RiskStressTestOutput


def _make_good_json(**overrides) -> str:
    payload = {
        "risks": [
            {
                "risk": "Customer concentration — top 3 customers account for 45% of revenue",
                "category": "Execution",
                "probability": "Medium",
                "impact": "-20% revenue if largest customer churns",
                "mitigation": "Diversification initiative targeting 10 new enterprise accounts in FY26",
            },
            {
                "risk": "Regulatory headwinds in EU market",
                "category": "Macro",
                "probability": "Low",
                "impact": "-8% to international revenue stream",
                "mitigation": "Pre-compliance program already underway; legal team sized for regulatory shift",
            },
            {
                "risk": "Valuation premium vs sector median",
                "category": "Valuation",
                "probability": "High",
                "impact": "-25% if multiple compresses to peer average of 18x",
                "mitigation": "Premium justified by 2x growth rate vs peers; watch for growth deceleration",
            },
            {
                "risk": "Key person dependency on CTO",
                "category": "Execution",
                "probability": "Low",
                "impact": "-10% on departure announcement based on historical comps",
                "mitigation": "Deep bench of VPs; succession plan documented in proxy",
            },
            {
                "risk": "Competitive pricing pressure from new entrants",
                "category": "Competitive",
                "probability": "Medium",
                "impact": "-15% gross margin compression over 2 years",
                "mitigation": "Switching costs and platform lock-in provide 18-month moat",
            },
        ],
        "rr_ratio": 2.8,
        "rr_verdict": "Upside case of 40% to fair value vs downside of ~14% gives a favorable 2.8:1 ratio. Thesis intact with manageable risk profile.",
        "loop_required": False,
        "loop_categories": [],
        "loop_reason": "",
    }
    payload.update(overrides)
    return json.dumps(payload)


class TestRiskParser(unittest.TestCase):

    def test_well_formed_json(self) -> None:
        raw = _make_good_json()
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.rr_ratio == 2.8
        assert len(parsed.risks) == 5
        assert parsed.risks[0].probability == "Medium"
        assert parsed.loop_required is False
        assert parsed.loop_categories == []

    def test_json_with_markdown_fences(self) -> None:
        raw = f"```json\n{_make_good_json()}\n```"
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.rr_ratio == 2.8

    def test_json_with_prose_preamble(self) -> None:
        raw = f"Here is the risk analysis:\n\n{_make_good_json()}\n\nEnd of analysis."
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None

    def test_loop_required_true(self) -> None:
        raw = _make_good_json(
            rr_ratio=1.3,
            loop_required=True,
            loop_categories=["Financial Health", "Growth & Earnings"],
            loop_reason="Insufficient margin of safety — need deeper financial analysis",
        )
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert parsed.loop_required is True
        assert len(parsed.loop_categories) == 2
        assert "Financial Health" in parsed.loop_categories

    def test_too_few_risks(self) -> None:
        payload = json.loads(_make_good_json())
        payload["risks"] = payload["risks"][:2]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert parsed is None
        assert err is not None

    def test_invalid_probability(self) -> None:
        payload = json.loads(_make_good_json())
        payload["risks"][0]["probability"] = "Very High"
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert parsed is None
        assert err is not None

    def test_rr_ratio_negative(self) -> None:
        raw = _make_good_json(rr_ratio=-1.0)
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert parsed is None
        assert err is not None

    def test_missing_risks_field(self) -> None:
        payload = json.loads(_make_good_json())
        del payload["risks"]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert parsed is None
        assert err is not None

    def test_empty_input(self) -> None:
        parsed, err = parse_structured_output("", RiskStressTestOutput)
        assert parsed is None
        assert err == "empty response"

    def test_malformed_garbage(self) -> None:
        parsed, err = parse_structured_output("not json at all", RiskStressTestOutput)
        assert parsed is None
        assert err is not None
        assert "no json" in err.lower() or "json" in err.lower()

    def test_three_risks_minimum(self) -> None:
        """Minimum valid risk count is 3."""
        payload = json.loads(_make_good_json())
        payload["risks"] = payload["risks"][:3]
        raw = json.dumps(payload)
        parsed, err = parse_structured_output(raw, RiskStressTestOutput)
        assert err is None, f"expected no error, got: {err}"
        assert parsed is not None
        assert len(parsed.risks) == 3


if __name__ == "__main__":
    unittest.main()
