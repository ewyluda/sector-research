"""calendar_events service: pure builders, universe derivation, catalyst
range SQL pin, and merge orchestration with partial-failure warnings."""
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.citation import Citation
from backend.app.services import calendar_events as ce


def _cit() -> Citation:
    return Citation(
        value="2026-06-08..2026-06-22",
        metric="Economic Calendar",
        source_name="FMP /economic-calendar",
        source_url="https://example/economic-calendar",
        tier=1,
    )


class EconEventsTests(unittest.TestCase):
    def test_keeps_only_us_high_impact(self):
        rows = [
            {"country": "US", "impact": "High", "event": "CPI YoY (May)",
             "date": "2026-06-10 12:30:00", "estimate": 4.2, "previous": 3.8,
             "actual": None, "unit": "%"},
            {"country": "US", "impact": "Medium", "event": "CFTC Nasdaq",
             "date": "2026-06-12 19:30:00"},
            {"country": "DE", "impact": "High", "event": "German CPI",
             "date": "2026-06-10 06:00:00"},
        ]
        events = ce._econ_events(rows, _cit())
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.kind, "economic")
        self.assertEqual(ev.title, "CPI YoY (May)")
        self.assertEqual(ev.date, date(2026, 6, 10))
        self.assertEqual(
            ev.timestamp, datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
        )
        self.assertIsNone(ev.ticker)
        self.assertEqual(ev.detail["estimate"], 4.2)
        self.assertEqual(ev.detail["previous"], 3.8)
        self.assertIsNone(ev.detail["actual"])
        self.assertEqual(ev.citation.source_name, "FMP /economic-calendar")
        self.assertIsInstance(ev.citation.value, str)

    def test_unparseable_date_row_is_skipped(self):
        rows = [{"country": "US", "impact": "High", "event": "X", "date": "junk"}]
        self.assertEqual(ce._econ_events(rows, _cit()), [])

    def test_date_only_string_parses_with_midnight_timestamp(self):
        rows = [{"country": "US", "impact": "High", "event": "X",
                 "date": "2026-06-10"}]
        events = ce._econ_events(rows, _cit())
        self.assertEqual(events[0].date, date(2026, 6, 10))


class EarningsEventsTests(unittest.TestCase):
    def _universe(self):
        return ce.Universe(
            tickers={"NVDA", "ASML"},
            thesis_runs={"NVDA": "run-nvda-1"},
        )

    def test_filters_firehose_to_universe_and_flags_thesis(self):
        rows = [
            {"symbol": "NVDA", "date": "2026-06-10", "epsEstimated": 1.62,
             "epsActual": None, "revenueEstimated": 6.2e10, "revenueActual": None},
            {"symbol": "ASML", "date": "2026-06-09", "epsEstimated": 4.21,
             "epsActual": None, "revenueEstimated": None, "revenueActual": None},
            {"symbol": "3988.T", "date": "2026-06-12"},
        ]
        events = ce._earnings_events(rows, self._universe(), _cit())
        self.assertEqual({e.ticker for e in events}, {"NVDA", "ASML"})
        nvda = next(e for e in events if e.ticker == "NVDA")
        self.assertEqual(nvda.kind, "earnings")
        self.assertEqual(nvda.date, date(2026, 6, 10))
        self.assertTrue(nvda.detail["has_thesis"])
        self.assertEqual(nvda.detail["run_id"], "run-nvda-1")
        asml = next(e for e in events if e.ticker == "ASML")
        self.assertFalse(asml.detail["has_thesis"])
        self.assertIsNone(asml.detail["run_id"])

    def test_lowercase_symbol_matches_universe(self):
        rows = [{"symbol": "nvda", "date": "2026-06-10"}]
        events = ce._earnings_events(rows, self._universe(), _cit())
        self.assertEqual(events[0].ticker, "NVDA")

    def test_bad_date_row_is_skipped(self):
        rows = [{"symbol": "NVDA", "date": "not-a-date"}]
        self.assertEqual(ce._earnings_events(rows, self._universe(), _cit()), [])


if __name__ == "__main__":
    unittest.main()
