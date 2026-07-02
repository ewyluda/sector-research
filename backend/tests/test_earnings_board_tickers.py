"""fetch_active_board_tickers: pinned to the shared universe latest-run
definition (services/universe.py::latest_runs_sql) after the 2026-07-01
consolidation — no more private completed-only copy."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.earnings_prints import fetch_active_board_tickers


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)


class FetchActiveBoardTickersTests(unittest.IsolatedAsyncioTestCase):
    async def test_uppercased_deduped_sorted(self):
        db = AsyncMock()
        db.execute.return_value = _Result([
            {"ticker": "nvda"},
            {"ticker": "NVDA"},   # same ticker via a second theme row
            {"ticker": "pltr"},
        ])

        tickers = await fetch_active_board_tickers(db)

        self.assertEqual(tickers, ["NVDA", "PLTR"])

    async def test_uses_shared_universe_latest_run_definition(self):
        """The executed SQL must be the universe CTE (completed AND watchlist,
        archive-filtered) — not the retired private completed-only copy."""
        db = AsyncMock()
        db.execute.return_value = _Result([])

        await fetch_active_board_tickers(db)

        sql_text = str(db.execute.call_args.args[0])
        self.assertIn("'watchlist'", sql_text)
        self.assertIn("archived_at IS NULL", sql_text)
        self.assertIn("DISTINCT ON (r.ticker, r.theme_id)", sql_text)


if __name__ == "__main__":
    unittest.main()
