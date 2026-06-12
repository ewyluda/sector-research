"""Tests for the _fetch_institutional helper in node_deep_dive.

Exercises the quarter-walk-back logic, citation collection, holders-failure
degradation, and total-failure fallback — all via a mocked FMPClient.
"""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.graph.nodes import _fetch_institutional
from backend.app.models.citation import Citation

# ── Fixtures ──────────────────────────────────────────────────────────────────

SUMMARY = {
    "symbol": "NVDA",
    "date": "2026-03-31",
    "investorsHolding": 6215,
    "investorsHoldingChange": -3,
    "numberOf13Fshares": 16101332088,
    "numberOf13FsharesChange": -366099525,
    "ownershipPercent": 66.25,
    "newPositions": 264,
    "increasedPositions": 2990,
    "reducedPositions": 2452,
    "closedPositions": 290,
    "putCallRatio": 1.15,
    "putCallRatioChange": -5.13,
}

HOLDER = {
    "investorName": "BLACKROCK, INC.",
    "sharesNumber": 1925533174,
    "marketValue": 335812985602,
    "changeInSharesNumber": -18279710,
    "isNew": False,
}

_SUM_CIT = Citation(
    value="NVDA",
    metric="13F institutional ownership summary",
    source_name="FMP /institutional-ownership/symbol-positions-summary",
    source_url="https://financialmodelingprep.com/stable/institutional-ownership/symbol-positions-summary?apikey=***&symbol=NVDA",
    tier=1,
)
_HLD_CIT = Citation(
    value="NVDA",
    metric="13F institutional holders",
    source_name="FMP /institutional-ownership/extract-analytics/holder",
    source_url="https://financialmodelingprep.com/stable/institutional-ownership/extract-analytics/holder?apikey=***&symbol=NVDA",
    tier=1,
)


def _make_fmp(*, summary_sequence, holders_result=None, holders_exception=None):
    """Build a mock FMPClient with canned responses.

    summary_sequence: list of (data | None) to return on successive summary calls.
    holders_result: (list, Citation) tuple returned on holders call.
    holders_exception: Exception raised on holders call (mutually exclusive with holders_result).
    """
    fmp = MagicMock()
    summary_returns = [
        (val, _SUM_CIT) for val in summary_sequence
    ]
    fmp.get_institutional_summary = AsyncMock(side_effect=summary_returns)

    if holders_exception is not None:
        fmp.get_institutional_holders = AsyncMock(side_effect=holders_exception)
    elif holders_result is not None:
        fmp.get_institutional_holders = AsyncMock(return_value=holders_result)
    else:
        fmp.get_institutional_holders = AsyncMock(return_value=([], _HLD_CIT))

    return fmp


# ── Tests ─────────────────────────────────────────────────────────────────────

class FetchInstitutionalTests(unittest.IsolatedAsyncioTestCase):

    async def test_first_quarter_hit(self):
        """Summary present on the first quarter — returns data + both citations."""
        fmp = _make_fmp(
            summary_sequence=[SUMMARY],
            holders_result=([HOLDER], _HLD_CIT),
        )
        (summary, holders), citations = await _fetch_institutional(fmp, "NVDA")
        self.assertEqual(summary, SUMMARY)
        self.assertEqual(holders, [HOLDER])
        self.assertEqual(len(citations), 2)
        self.assertIs(citations[0], _SUM_CIT)
        self.assertIs(citations[1], _HLD_CIT)
        # Only called once — no walk-back needed
        fmp.get_institutional_summary.assert_awaited_once()

    async def test_walkback_past_two_empty_quarters(self):
        """Two quarters return None before the third has data."""
        fmp = _make_fmp(
            summary_sequence=[None, None, SUMMARY],
            holders_result=([HOLDER], _HLD_CIT),
        )
        (summary, holders), citations = await _fetch_institutional(fmp, "NVDA")
        self.assertEqual(summary, SUMMARY)
        self.assertEqual(holders, [HOLDER])
        # Summary called 3 times (2 misses + 1 hit); holders called once
        self.assertEqual(fmp.get_institutional_summary.await_count, 3)
        fmp.get_institutional_holders.assert_awaited_once()
        # 2 citation objects: summary + holders (misses don't contribute)
        self.assertEqual(len(citations), 2)

    async def test_summary_present_holders_failure_degrades(self):
        """Summary found but holders raises — returns (summary, []) with summary citation only."""
        fmp = _make_fmp(
            summary_sequence=[SUMMARY],
            holders_exception=RuntimeError("holders 503"),
        )
        (summary, holders), citations = await _fetch_institutional(fmp, "NVDA")
        self.assertEqual(summary, SUMMARY)
        self.assertEqual(holders, [])
        # Only the summary citation; holders failure contributes nothing
        self.assertEqual(len(citations), 1)
        self.assertIs(citations[0], _SUM_CIT)

    async def test_all_quarters_empty_returns_empty(self):
        """All 4 quarters return None — returns ((None, []), [])."""
        fmp = _make_fmp(summary_sequence=[None, None, None, None])
        (summary, holders), citations = await _fetch_institutional(fmp, "NVDA")
        self.assertIsNone(summary)
        self.assertEqual(holders, [])
        self.assertEqual(citations, [])
        # Holders never called
        fmp.get_institutional_holders.assert_not_awaited()

    async def test_total_failure_returns_empty(self):
        """Unexpected exception in summary → ((None, []), []) without propagating."""
        fmp = MagicMock()
        fmp.get_institutional_summary = AsyncMock(side_effect=RuntimeError("API down"))
        (summary, holders), citations = await _fetch_institutional(fmp, "NVDA")
        self.assertIsNone(summary)
        self.assertEqual(holders, [])
        self.assertEqual(citations, [])

    async def test_citations_collected_for_hit_quarter(self):
        """Both summary and holder citations are returned when both calls succeed."""
        fmp = _make_fmp(
            summary_sequence=[SUMMARY],
            holders_result=([HOLDER, HOLDER], _HLD_CIT),
        )
        (_, _), citations = await _fetch_institutional(fmp, "NVDA")
        urls = [c.source_url for c in citations]
        self.assertIn(_SUM_CIT.source_url, urls)
        self.assertIn(_HLD_CIT.source_url, urls)

    async def test_return_type_matches_contract(self):
        """Return type is always ((dict|None, list), list) — never raises."""
        fmp = MagicMock()
        # Make both methods raise to hit the outer except
        fmp.get_institutional_summary = AsyncMock(side_effect=ValueError("boom"))
        result = await _fetch_institutional(fmp, "AAPL")
        (summary, holders), citations = result
        self.assertIsNone(summary)
        self.assertIsInstance(holders, list)
        self.assertIsInstance(citations, list)


if __name__ == "__main__":
    unittest.main()
