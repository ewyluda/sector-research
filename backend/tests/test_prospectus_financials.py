"""Tests for prospectus_financials.extract_financials."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.services.prospectus_financials import extract_financials
from backend.app.models.prospectus_schemas import ProspectusFinancials
from backend.app.graph.llm import LLMOutputError
from backend.tests.llm_fakes import structured_returning


class TestExtractFinancials(unittest.TestCase):
    def test_parses_sonnet_response(self):
        mock_response = json.dumps({
            "annual": [
                {
                    "period_label": "FY2024",
                    "revenue": 14000000000.0,
                    "operating_income": 2000000000.0,
                    "net_income": 1500000000.0,
                    "cash_and_equivalents": 4000000000.0,
                    "total_debt": 1000000000.0,
                    "cost_of_revenue": 9000000000.0,
                    "source_snippet": "Revenues for the year ended December 31, 2024 were $14.0 billion"
                }
            ],
            "interim": []
        })
        with patch(
            "backend.app.services.prospectus_financials.complete_structured",
            new=structured_returning(mock_response),
        ):
            import asyncio
            fin = asyncio.run(extract_financials(
                mda_text="Some narrative",
                selected_financials_text="Table of figures",
            ))
        self.assertIsInstance(fin, ProspectusFinancials)
        self.assertEqual(len(fin.annual), 1)
        self.assertEqual(fin.annual[0].revenue, 14_000_000_000.0)

    def test_empty_text_returns_empty_struct(self):
        import asyncio
        fin = asyncio.run(extract_financials(mda_text="", selected_financials_text=""))
        self.assertEqual(fin.annual, [])
        self.assertEqual(fin.interim, [])

    def test_unusable_output_returns_empty_struct(self):
        # Structured outputs can't return non-JSON; the failure mode is now a
        # truncated/refused response surfaced as LLMOutputError.
        with patch(
            "backend.app.services.prospectus_financials.complete_structured",
            new=AsyncMock(side_effect=LLMOutputError("truncated at max_tokens")),
        ):
            import asyncio
            fin = asyncio.run(extract_financials(
                mda_text="x", selected_financials_text="y",
            ))
        self.assertEqual(fin.annual, [])
