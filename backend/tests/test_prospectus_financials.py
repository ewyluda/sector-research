"""Tests for prospectus_financials.extract_financials."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.services.prospectus_financials import extract_financials
from backend.app.models.prospectus_schemas import ProspectusFinancials


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
            "backend.app.services.prospectus_financials.complete",
            new=AsyncMock(return_value=mock_response),
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

    def test_garbled_response_returns_empty_struct(self):
        with patch(
            "backend.app.services.prospectus_financials.complete",
            new=AsyncMock(return_value="not json at all"),
        ):
            import asyncio
            fin = asyncio.run(extract_financials(
                mda_text="x", selected_financials_text="y",
            ))
        self.assertEqual(fin.annual, [])
