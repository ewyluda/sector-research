"""Pins the pure material-events summarizer the board join uses: count,
max-materiality escalation, latest-headline = first row (rows arrive
ordered filing_date DESC)."""

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


def ev(ticker="NVDA", materiality="low", headline="h", days=1):
    return SimpleNamespace(
        ticker=ticker, materiality=materiality, headline=headline,
        filing_date=date(2026, 6, 10),
    )


class SummarizeTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_summarize_material_events([]), {})

    def test_counts_and_latest_headline(self):
        # ordered DESC by filing_date — first row per ticker is the latest
        out = _summarize_material_events([
            ev(headline="newest", materiality="low"),
            ev(headline="older", materiality="high"),
        ])
        s = out["NVDA"]
        self.assertEqual(s.count_14d, 2)
        self.assertEqual(s.latest_headline, "newest")
        self.assertEqual(s.max_materiality, "high")

    def test_groups_by_ticker(self):
        out = _summarize_material_events([
            ev(ticker="NVDA"), ev(ticker="MSFT", materiality="medium"),
        ])
        self.assertEqual(set(out), {"NVDA", "MSFT"})
        self.assertEqual(out["MSFT"].max_materiality, "medium")


if __name__ == "__main__":
    unittest.main()
