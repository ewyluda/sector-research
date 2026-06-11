"""Characterization tests for FMP client parser / normalization behavior.

Top-5 most-consumed methods by call-site count (grepped 2026-06-11):
  1. get_company_profile   (10 call sites)
  2. get_income_statement   (5 call sites) — raw passthrough
  3. get_balance_sheet      (5 call sites) — raw passthrough
  4. get_cash_flow          (5 call sites) — raw passthrough
  5. get_quote              (5 call sites)

Mocking convention: replace client._request with AsyncMock (same as
test_fmp_calendar.py and test_fmp_stock_peers.py). No HTTP is exercised.

Surprising behaviors documented inline with NOTE comments.
"""
import os
import unittest
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.clients.fmp import FMPClient
from backend.app.models.citation import Citation


# ── 1. get_company_profile ────────────────────────────────────────────────────

class TestGetCompanyProfile(unittest.IsolatedAsyncioTestCase):
    """Profile parsing: returns data[0] when data is a list, else data as-is."""

    async def test_happy_path_returns_first_element_of_list(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"symbol": "AAPL", "companyName": "Apple Inc", "sector": "Technology"}
        ])
        result, citation = await client.get_company_profile("AAPL")
        self.assertEqual(result["companyName"], "Apple Inc")
        self.assertIsInstance(citation, Citation)
        self.assertIn("profile", citation.source_name)

    async def test_empty_list_returns_empty_list(self):
        # NOTE: empty list → `data[0] if isinstance(data, list) and data else data`
        # → condition is False (empty list is falsy) → returns the empty list itself,
        # NOT None or {}. Callers that do result.get("sector") will raise AttributeError.
        client = FMPClient()
        client._request = AsyncMock(return_value=[])
        result, _ = await client.get_company_profile("ZZZQ")
        self.assertEqual(result, [])

    async def test_dict_response_returned_as_is(self):
        # Some FMP endpoints return a single dict rather than a list.
        # NOTE: the profile method passes it through unchanged — no unwrapping.
        client = FMPClient()
        client._request = AsyncMock(return_value={"symbol": "MSFT", "companyName": "Microsoft"})
        result, _ = await client.get_company_profile("MSFT")
        self.assertEqual(result["companyName"], "Microsoft")

    async def test_error_shaped_response_returned_as_is(self):
        # NOTE: FMP error responses {"Error Message": "..."} are NOT caught here —
        # the dict is returned verbatim. Callers checking for string fields will
        # silently get None from .get() rather than an exception.
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "Invalid API KEY."})
        result, _ = await client.get_company_profile("AAPL")
        self.assertIn("Error Message", result)

    async def test_null_fields_in_profile_returned_intact(self):
        # Fields missing from the API response come back as None via .get() in callers.
        # The client does not normalize missing keys — they remain absent.
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"symbol": "NVDA", "companyName": None, "sector": None}
        ])
        result, _ = await client.get_company_profile("NVDA")
        self.assertIsNone(result.get("companyName"))
        self.assertIsNone(result.get("sector"))

    async def test_none_response_returned_as_none(self):
        # NOTE: if _request returns None (e.g., severe FMP failure that was
        # somehow swallowed), the condition `isinstance(None, list)` is False,
        # so result = None. Callers must handle None explicitly.
        client = FMPClient()
        client._request = AsyncMock(return_value=None)
        result, _ = await client.get_company_profile("AAPL")
        self.assertIsNone(result)

    async def test_wrong_type_string_field_for_market_cap_returned_intact(self):
        # FMP occasionally returns numeric fields as strings (e.g., "2800000000000").
        # The client does NOT cast them — callers receive the raw string.
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"symbol": "AAPL", "marketCap": "2800000000000"}
        ])
        result, _ = await client.get_company_profile("AAPL")
        self.assertEqual(result["marketCap"], "2800000000000")
        self.assertIsInstance(result["marketCap"], str)


# ── 2. get_income_statement ───────────────────────────────────────────────────

class TestGetIncomeStatement(unittest.IsolatedAsyncioTestCase):
    """Raw passthrough: _request result is returned directly with no transformation."""

    async def test_happy_path_list_returned_as_is(self):
        client = FMPClient()
        payload = [{"revenue": 1000.0, "grossProfit": 600.0, "date": "2025-12-31"}]
        client._request = AsyncMock(return_value=payload)
        data, citation = await client.get_income_statement("AAPL")
        self.assertIs(data, payload)
        self.assertIn("income-statement", citation.source_name)

    async def test_empty_list_returned_as_empty_list(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[])
        data, _ = await client.get_income_statement("ZZZQ")
        self.assertEqual(data, [])

    async def test_none_fields_returned_intact(self):
        # Revenue = None: callers like _extract_gross_margin guard with `if not revenue`
        # and return None safely, but only because they check. The client itself does not.
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"revenue": None, "grossProfit": None}
        ])
        data, _ = await client.get_income_statement("AAPL")
        self.assertIsNone(data[0]["revenue"])

    async def test_error_shaped_response_returned_as_is(self):
        # NOTE: FMP error dict is NOT filtered here — caller receives the dict
        # directly, which will cause issues if caller expects list[dict] and
        # iterates without checking.
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "Unauthorized"})
        data, _ = await client.get_income_statement("AAPL")
        self.assertIsInstance(data, dict)
        self.assertIn("Error Message", data)

    async def test_string_where_number_expected_returned_intact(self):
        # NOTE: Callers (_extract_gross_margin, etc.) catch TypeError from string
        # division via bare `except Exception`, so this degrades safely. The client
        # itself does NOT sanitize the types.
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"revenue": "N/A", "grossProfit": "N/A"}
        ])
        data, _ = await client.get_income_statement("AAPL")
        self.assertEqual(data[0]["revenue"], "N/A")

    async def test_missing_keys_not_added_by_client(self):
        # A row missing 'revenue' entirely — caller's .get("revenue", 0) handles it.
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"grossProfit": 600.0}])
        data, _ = await client.get_income_statement("AAPL")
        self.assertNotIn("revenue", data[0])


# ── 3. get_balance_sheet ──────────────────────────────────────────────────────

class TestGetBalanceSheet(unittest.IsolatedAsyncioTestCase):
    """Raw passthrough: identical contract to get_income_statement."""

    async def test_happy_path_list_returned_as_is(self):
        client = FMPClient()
        payload = [{"totalEquity": 800.0, "longTermDebt": 200.0}]
        client._request = AsyncMock(return_value=payload)
        data, citation = await client.get_balance_sheet("AAPL")
        self.assertIs(data, payload)
        self.assertIn("balance-sheet-statement", citation.source_name)

    async def test_empty_list_returned_directly(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[])
        data, _ = await client.get_balance_sheet("ZZZQ")
        self.assertEqual(data, [])

    async def test_error_shaped_response_returned_as_is(self):
        # Same raw passthrough behavior as income statement.
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "Limit Reached"})
        data, _ = await client.get_balance_sheet("AAPL")
        self.assertIsInstance(data, dict)

    async def test_null_equity_field_returned_intact(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"totalEquity": None, "longTermDebt": 200.0}])
        data, _ = await client.get_balance_sheet("AAPL")
        self.assertIsNone(data[0]["totalEquity"])

    async def test_wrong_type_field_not_coerced(self):
        # totalEquity as string — the client does not coerce to float.
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"totalEquity": "800000000", "longTermDebt": 0}])
        data, _ = await client.get_balance_sheet("AAPL")
        self.assertIsInstance(data[0]["totalEquity"], str)


# ── 4. get_cash_flow ──────────────────────────────────────────────────────────

class TestGetCashFlow(unittest.IsolatedAsyncioTestCase):
    """Raw passthrough: identical contract to get_income_statement and get_balance_sheet."""

    async def test_happy_path_list_returned_as_is(self):
        client = FMPClient()
        payload = [{"operatingCashFlow": 150.0, "freeCashFlow": 100.0}]
        client._request = AsyncMock(return_value=payload)
        data, citation = await client.get_cash_flow("AAPL")
        self.assertIs(data, payload)
        self.assertIn("cash-flow-statement", citation.source_name)

    async def test_empty_list_returned_directly(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[])
        data, _ = await client.get_cash_flow("ZZZQ")
        self.assertEqual(data, [])

    async def test_error_shaped_response_returned_as_is(self):
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "Access Denied"})
        data, _ = await client.get_cash_flow("AAPL")
        self.assertIsInstance(data, dict)

    async def test_missing_operating_cash_flow_key(self):
        # Client does not add defaults — missing keys stay missing.
        # _extract_roic uses .get("operatingCashFlow", 0) so this degrades cleanly.
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"freeCashFlow": 50.0}])
        data, _ = await client.get_cash_flow("AAPL")
        self.assertNotIn("operatingCashFlow", data[0])

    async def test_null_free_cash_flow_returned_intact(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"operatingCashFlow": 100.0, "freeCashFlow": None}])
        data, _ = await client.get_cash_flow("AAPL")
        self.assertIsNone(data[0]["freeCashFlow"])


# ── 5. get_quote ─────────────────────────────────────────────────────────────

class TestGetQuote(unittest.IsolatedAsyncioTestCase):
    """Quote parsing mirrors profile: returns data[0] for list, else data as-is."""

    async def test_happy_path_returns_first_element(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"symbol": "AAPL", "price": 195.50, "volume": 50_000_000}
        ])
        result, citation = await client.get_quote("AAPL")
        self.assertEqual(result["price"], 195.50)
        self.assertEqual(citation.source_name, "FMP /quote")

    async def test_empty_list_returns_empty_list(self):
        # NOTE: same surprising behavior as get_company_profile — empty list is
        # returned, NOT {}. result.get("price") would raise AttributeError on a list.
        client = FMPClient()
        client._request = AsyncMock(return_value=[])
        result, citation = await client.get_quote("ZZZQ")
        self.assertEqual(result, [])
        # Citation still reflects "N/A" price because result.get() is never reached
        self.assertEqual(citation.value, "N/A")

    async def test_dict_response_returned_as_is(self):
        # If FMP returns a single dict (non-list), it's passed through unchanged.
        client = FMPClient()
        client._request = AsyncMock(return_value={"symbol": "MSFT", "price": 420.0})
        result, _ = await client.get_quote("MSFT")
        self.assertEqual(result["price"], 420.0)

    async def test_error_shaped_response_returned_as_is(self):
        # NOTE: error dict is NOT filtered — same as profile behavior.
        # The citation value is "N/A" because the "price" KEY is absent from the
        # error dict, so .get's default fires (contrast: an explicit None value
        # bypasses the default — see test_null_price_field above).
        client = FMPClient()
        client._request = AsyncMock(return_value={"Error Message": "Invalid API KEY."})
        result, citation = await client.get_quote("AAPL")
        self.assertIn("Error Message", result)
        self.assertEqual(citation.value, "N/A")

    async def test_null_price_field(self):
        # FMP may return price=null for halted tickers.
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"symbol": "AAPL", "price": None}])
        result, citation = await client.get_quote("AAPL")
        self.assertIsNone(result.get("price"))
        # NOTE: citation.value is None here (not "N/A") because result.get("price", "N/A")
        # returns the explicit None — .get() only falls back to the default on KEY ABSENCE,
        # not on None values. This is a subtle Python .get() footgun.
        self.assertIsNone(citation.value)

    async def test_none_response(self):
        # NOTE: if _request returns None, result is None (not {}).
        # Same behavior as get_company_profile.
        client = FMPClient()
        client._request = AsyncMock(return_value=None)
        result, _ = await client.get_quote("AAPL")
        self.assertIsNone(result)

    async def test_string_price_not_coerced(self):
        # If FMP returns price as string, the client does not coerce to float.
        client = FMPClient()
        client._request = AsyncMock(return_value=[{"symbol": "AAPL", "price": "195.50"}])
        result, citation = await client.get_quote("AAPL")
        self.assertIsInstance(result["price"], str)
        self.assertEqual(citation.value, "195.50")


if __name__ == "__main__":
    unittest.main()
