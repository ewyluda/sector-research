"""Pins the pure material-events summarizer the board join uses: groups
(not raw filings) are counted, max-materiality escalates over every raw
event, latest-headline = newest group's primary."""

import os
import unittest
from datetime import date
from types import SimpleNamespace

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.status_board import _summarize_material_events


def ev(ticker="NVDA", materiality="low", headline="h", etype="guidance", day=10, id="e1"):
    return SimpleNamespace(
        id=id, ticker=ticker, materiality=materiality, headline=headline,
        event_type=etype, filing_date=date(2026, 6, day),
    )


class SummarizeTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_summarize_material_events([]), {})

    def test_counts_and_latest_headline(self):
        # distinct event types don't group — both count
        out = _summarize_material_events([
            ev(headline="newest", materiality="low", etype="guidance", day=10),
            ev(headline="older", materiality="high", etype="financing", day=9, id="e2"),
        ])
        s = out["NVDA"]
        self.assertEqual(s.count_14d, 2)
        self.assertEqual(s.latest_headline, "newest")
        self.assertEqual(s.max_materiality, "high")

    def test_near_duplicates_count_once(self):
        # same ticker + type within 4 days → one group; materiality still
        # escalates over the grouped member
        out = _summarize_material_events([
            ev(headline="newest", materiality="low", day=10),
            ev(headline="dup", materiality="high", day=8, id="e2"),
        ])
        s = out["NVDA"]
        self.assertEqual(s.count_14d, 1)
        self.assertEqual(s.latest_headline, "newest")
        self.assertEqual(s.max_materiality, "high")

    def test_groups_by_ticker(self):
        out = _summarize_material_events([
            ev(ticker="NVDA"), ev(ticker="MSFT", materiality="medium", id="e2"),
        ])
        self.assertEqual(set(out), {"NVDA", "MSFT"})
        self.assertEqual(out["MSFT"].max_materiality, "medium")


if __name__ == "__main__":
    unittest.main()
