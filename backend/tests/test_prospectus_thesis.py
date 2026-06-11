import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    IPOVerdict,
    ProspectusCategoryResult,
)
from backend.app.services.prospectus_thesis import synthesize_thesis


def _sample_categories() -> CategoriesStepOutput:
    return CategoriesStepOutput(
        results={
            "Business Quality": ProspectusCategoryResult(
                category="Business Quality", content="strong",
                score=80, key_findings=["bq1", "bq2"],
            ),
            "Risk Assessment": ProspectusCategoryResult(
                category="Risk Assessment", content="moderate",
                score=55, key_findings=["ra1"],
            ),
        },
        failures={},
    )


class TestSynthesizeThesis(unittest.IsolatedAsyncioTestCase):
    async def test_parses_sonnet_thesis_response(self):
        payload = json.dumps({
            "thesis_statement": "ACME has strong unit economics, gated by regulatory risk.",
            "key_risks": [
                {"risk": "FAA approval cadence", "severity": "high", "category_source": "Risk Assessment"},
            ],
            "ipo_verdict": "watch_post_lockup",
            "price_range_commentary": "Range implies 8x forward sales vs peers at 6x.",
            "post_ipo_research_plan": [
                {
                    "question": "Did Q3 launch cadence beat S-1 guidance?",
                    "why_it_matters": "Validates unit economics",
                    "expected_data_source": "FMP quarterly + first earnings call",
                },
            ],
        })
        with patch("backend.app.services.prospectus_thesis.complete",
                   new=AsyncMock(return_value=payload)):
            out = await synthesize_thesis(
                issuer_name="ACME Rockets",
                categories=_sample_categories(),
                financials_json={"annual": []},
            )
        self.assertEqual(out.ipo_verdict, IPOVerdict.WATCH_POST_LOCKUP)
        self.assertEqual(len(out.key_risks), 1)
        self.assertEqual(out.key_risks[0].severity, "high")
        self.assertEqual(len(out.post_ipo_research_plan), 1)
