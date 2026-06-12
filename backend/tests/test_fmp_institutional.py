"""Pins FMPClient.get_institutional_summary / get_institutional_holders and the
recent_13f_quarters helper.

Recorded-payload convention: mocked _request returns real key names captured
from a live FMP call on 2026-06-12 (NVDA, 2026-Q1).
"""

import os
import unittest
from datetime import date
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.clients.fmp import FMPClient, recent_13f_quarters
from backend.app.models.citation import Citation

# ── Recorded payloads (live FMP, 2026-06-12) ─────────────────────────────────

SUMMARY_ROW = {
    "symbol": "NVDA",
    "cik": "0001045810",
    "date": "2026-03-31",
    "investorsHolding": 6215,
    "lastInvestorsHolding": 6218,
    "investorsHoldingChange": -3,
    "numberOf13Fshares": 16101332088,
    "lastNumberOf13Fshares": 16467431613,
    "numberOf13FsharesChange": -366099525,
    "totalInvested": 2803367000119,
    "lastTotalInvested": 3049039391841,
    "totalInvestedChange": -245672391722,
    "ownershipPercent": 66.2497,
    "lastOwnershipPercent": 67.692,
    "ownershipPercentChange": -1.4423,
    "newPositions": 264,
    "lastNewPositions": 692,
    "newPositionsChange": -428,
    "increasedPositions": 2990,
    "lastIncreasedPositions": 3081,
    "increasedPositionsChange": -91,
    "closedPositions": 290,
    "lastClosedPositions": 232,
    "closedPositionsChange": 58,
    "reducedPositions": 2452,
    "lastReducedPositions": 2424,
    "reducedPositionsChange": 28,
    "totalCalls": 445245771,
    "lastTotalCalls": 477996062,
    "totalCallsChange": -32750291,
    "totalPuts": 510467884,
    "lastTotalPuts": 572528861,
    "totalPutsChange": -62060977,
    "putCallRatio": 1.1465,
    "lastPutCallRatio": 1.1978,
    "putCallRatioChange": -5.1283,
}

HOLDER_ROW = {
    "date": "2026-03-31",
    "cik": "0002012383",
    "filingDate": "2026-05-13",
    "investorName": "BLACKROCK, INC.",
    "symbol": "NVDA",
    "securityName": "NVIDIA CORPORATION",
    "typeOfSecurity": "COM",
    "securityCusip": "67066G104",
    "sharesType": "SH",
    "putCallShare": "Share",
    "investmentDiscretion": "SOLE",
    "industryTitle": "SEMICONDUCTORS & RELATED DEVICES",
    "weight": 5.8672,
    "lastWeight": 6.1274,
    "changeInWeight": -0.2602,
    "changeInWeightPercentage": -4.2467,
    "marketValue": 335812985602,
    "lastMarketValue": 362521102837,
    "changeInMarketValue": -26708117235,
    "changeInMarketValuePercentage": -7.3673,
    "sharesNumber": 1925533174,
    "lastSharesNumber": 1943812884,
    "changeInSharesNumber": -18279710,
    "changeInSharesNumberPercentage": -0.9404,
    "quarterEndPrice": 174.4,
    "avgPricePaid": 122.9,
    "isNew": False,
    "isSoldOut": False,
    "ownership": 7.9227,
    "lastOwnership": 7.9904,
    "changeInOwnership": -0.0677,
    "changeInOwnershipPercentage": -0.8467,
    "holdingPeriod": 7,
    "firstAdded": "2024-09-30",
    "performance": -23520135896,
    "performancePercentage": -6.4879,
    "lastPerformance": -154340731,
    "changeInPerformance": -23365795165,
    "isCountedForPerformance": True,
}


# ── Quarter helper tests ──────────────────────────────────────────────────────

class QuarterHelperTests(unittest.TestCase):
    def test_mid_q2_date(self):
        """2026-06-12 is in Q2 2026, so previous quarter is Q1 2026."""
        result = recent_13f_quarters(date(2026, 6, 12), n=4)
        self.assertEqual(result, [(2026, 1), (2025, 4), (2025, 3), (2025, 2)])

    def test_january_date_crosses_year(self):
        """2026-01-15 is in Q1 2026, so previous quarter is Q4 2025."""
        result = recent_13f_quarters(date(2026, 1, 15), n=4)
        self.assertEqual(result, [(2025, 4), (2025, 3), (2025, 2), (2025, 1)])

    def test_quarter_boundary_date(self):
        """2026-04-01 is the first day of Q2, so previous quarter is Q1 2026."""
        result = recent_13f_quarters(date(2026, 4, 1), n=4)
        self.assertEqual(result, [(2026, 1), (2025, 4), (2025, 3), (2025, 2)])

    def test_q1_boundary_date(self):
        """2026-01-01 is the first day of Q1 2026, previous quarter is Q4 2025."""
        result = recent_13f_quarters(date(2026, 1, 1), n=4)
        self.assertEqual(result, [(2025, 4), (2025, 3), (2025, 2), (2025, 1)])

    def test_n_controls_length(self):
        result = recent_13f_quarters(date(2026, 6, 12), n=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result, [(2026, 1), (2025, 4)])

    def test_q3_date(self):
        """2026-09-15 is in Q3 2026, previous quarter is Q2 2026."""
        result = recent_13f_quarters(date(2026, 9, 15), n=2)
        self.assertEqual(result, [(2026, 2), (2026, 1)])

    def test_q4_date(self):
        """2026-12-15 is in Q4 2026, previous quarter is Q3 2026."""
        result = recent_13f_quarters(date(2026, 12, 15), n=2)
        self.assertEqual(result, [(2026, 3), (2026, 2)])


# ── get_institutional_summary tests ──────────────────────────────────────────

class InstitutionalSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_single_element_list_unwraps_to_dict(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[SUMMARY_ROW])
        result, citation = await client.get_institutional_summary("NVDA", 2026, 1)
        self.assertEqual(result, SUMMARY_ROW)
        self.assertIsInstance(citation, Citation)
        client._request.assert_awaited_once()

    async def test_empty_list_returns_none(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[])
        result, citation = await client.get_institutional_summary("NVDA", 2026, 1)
        self.assertIsNone(result)
        self.assertIsInstance(citation, Citation)

    async def test_error_dict_returns_none(self):
        """FMP error dicts pass through _request verbatim — must return None."""
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "Invalid API KEY."})
        result, citation = await client.get_institutional_summary("NVDA", 2026, 1)
        self.assertIsNone(result)
        self.assertIsInstance(citation, Citation)

    async def test_endpoint_name_in_request(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[SUMMARY_ROW])
        await client.get_institutional_summary("NVDA", 2026, 1)
        endpoint = client._request.await_args.args[0]
        self.assertEqual(endpoint, "institutional-ownership/symbol-positions-summary")

    async def test_citation_source_url_contains_endpoint_and_symbol(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[SUMMARY_ROW])
        _, citation = await client.get_institutional_summary("NVDA", 2026, 1)
        self.assertIn("institutional-ownership/symbol-positions-summary", citation.source_url)
        self.assertIn("NVDA", citation.source_url)

    async def test_citation_metric_label(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[SUMMARY_ROW])
        _, citation = await client.get_institutional_summary("NVDA", 2026, 1)
        self.assertEqual(citation.metric, "13F institutional ownership summary")


# ── get_institutional_holders tests ──────────────────────────────────────────

class InstitutionalHoldersTests(unittest.IsolatedAsyncioTestCase):
    async def test_list_passthrough_with_citation(self):
        payload = [HOLDER_ROW] * 10
        client = FMPClient()
        client._request = AsyncMock(return_value=payload)
        rows, citation = await client.get_institutional_holders("NVDA", 2026, 1)
        self.assertEqual(len(rows), 10)
        self.assertEqual(rows[0], HOLDER_ROW)
        self.assertIsInstance(citation, Citation)

    async def test_limit_caps_rows_client_side(self):
        payload = [HOLDER_ROW] * 30
        client = FMPClient()
        client._request = AsyncMock(return_value=payload)
        rows, _ = await client.get_institutional_holders("NVDA", 2026, 1, limit=5)
        self.assertEqual(len(rows), 5)

    async def test_non_list_returns_empty(self):
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "denied"})
        rows, citation = await client.get_institutional_holders("NVDA", 2026, 1)
        self.assertEqual(rows, [])
        self.assertIsInstance(citation, Citation)

    async def test_none_payload_returns_empty(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=None)
        rows, _ = await client.get_institutional_holders("NVDA", 2026, 1)
        self.assertEqual(rows, [])

    async def test_endpoint_name_in_request(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[HOLDER_ROW])
        await client.get_institutional_holders("NVDA", 2026, 1)
        endpoint = client._request.await_args.args[0]
        self.assertEqual(endpoint, "institutional-ownership/extract-analytics/holder")

    async def test_citation_source_url_contains_endpoint_and_symbol(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[HOLDER_ROW])
        _, citation = await client.get_institutional_holders("NVDA", 2026, 1)
        self.assertIn("institutional-ownership/extract-analytics/holder", citation.source_url)
        self.assertIn("NVDA", citation.source_url)

    async def test_citation_metric_label(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[HOLDER_ROW])
        _, citation = await client.get_institutional_holders("NVDA", 2026, 1)
        self.assertEqual(citation.metric, "13F institutional holders")


if __name__ == "__main__":
    unittest.main()
