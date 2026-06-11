"""Pins that _merge_results issues exactly ONE SurpriseAlert query regardless of ticker count.

The test intercepts db.execute, records every SQL/ORM statement that touches
surprise_alert, and asserts the count is 1 even when multiple tickers are present.
"""

import os
import uuid
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.discovery import DiscoveryEngine
from backend.app.models.surprise_alert import SurpriseAlert


def _make_theme(tickers=("AAPL", "MSFT", "GOOG")):
    theme = MagicMock()
    theme.id = str(uuid.uuid4())
    theme.seed_tickers = list(tickers)
    theme.signal_weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
    return theme


def _make_fmp_item(ticker: str) -> dict:
    """Minimal fmp_results item that _merge_results can process without errors."""
    return {
        "ticker": ticker,
        "profile": {"companyName": f"{ticker} Inc", "marketCap": 1e9, "sector": "Tech", "industry": "Software"},
        "income": [{"revenue": 1000.0, "grossProfit": 600.0}, {"revenue": 900.0, "grossProfit": 540.0}],
        "balance": [{"totalEquity": 800.0, "longTermDebt": 200.0}],
        "cashflow": [{"operatingCashFlow": 100.0}],
        "citations": [],
    }


class _RecordingExecute:
    """Collects every SQLAlchemy statement that passes through db.execute.

    Returns an empty result for all queries (scalars() → []).
    """

    def __init__(self):
        self.statements: list = []

    async def __call__(self, stmt, *args, **kwargs):
        self.statements.append(stmt)
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_result.scalar_one_or_none.return_value = None
        return mock_result

    def surprise_alert_call_count(self) -> int:
        """Count how many recorded statements reference SurpriseAlert."""
        count = 0
        for stmt in self.statements:
            # SQLAlchemy Select objects carry their entity info; check the repr/str.
            stmt_str = str(stmt)
            if "surprise_alert" in stmt_str.lower():
                count += 1
        return count


class TestSurpriseAlertBatched(unittest.IsolatedAsyncioTestCase):
    async def test_single_surprise_alert_query_for_multiple_tickers(self):
        """_merge_results must issue exactly one DB query for SurpriseAlert
        regardless of the number of tickers in fmp_results."""
        tickers = ["AAPL", "MSFT", "GOOG", "NVDA", "META"]
        theme = _make_theme(tickers)

        recorder = _RecordingExecute()
        db = MagicMock()
        db.execute = recorder

        engine = DiscoveryEngine(fmp=MagicMock(), x_client=MagicMock())

        fmp_results = [_make_fmp_item(t) for t in tickers]
        cached_signals: dict = {}

        await engine._merge_results(
            theme=theme,
            fmp_results=fmp_results,
            cached_signals=cached_signals,
            db=db,
        )

        count = recorder.surprise_alert_call_count()
        self.assertEqual(
            count,
            1,
            f"Expected exactly 1 SurpriseAlert query, got {count}. "
            f"Statements recorded: {[str(s) for s in recorder.statements]}",
        )

    async def test_surprise_flag_set_when_ticker_in_batch_result(self):
        """Cards for tickers that appear in the batch result have is_surprise=True."""
        tickers = ["AAPL", "MSFT"]
        theme = _make_theme(tickers)

        # The batch query should return tickers ["AAPL"]
        surprise_tickers_returned = ["AAPL"]

        async def _patched_execute(stmt, *args, **kwargs):
            stmt_str = str(stmt)
            mock_result = MagicMock()
            if "surprise_alert" in stmt_str.lower():
                # Simulate the scalars() returning ticker strings for the IN() query
                mock_result.scalars.return_value.all.return_value = surprise_tickers_returned
            else:
                mock_result.scalars.return_value.all.return_value = []
                mock_result.scalar_one_or_none.return_value = None
            return mock_result

        db = MagicMock()
        db.execute = _patched_execute

        engine = DiscoveryEngine(fmp=MagicMock(), x_client=MagicMock())
        fmp_results = [_make_fmp_item(t) for t in tickers]

        cards = await engine._merge_results(
            theme=theme,
            fmp_results=fmp_results,
            cached_signals={},
            db=db,
        )

        card_by_ticker = {c.ticker: c for c in cards}
        self.assertTrue(card_by_ticker["AAPL"].is_surprise)
        self.assertFalse(card_by_ticker["MSFT"].is_surprise)

    async def test_no_surprise_alerts_when_empty_result(self):
        """All cards have is_surprise=False when the batch returns nothing."""
        tickers = ["AAPL", "MSFT"]
        theme = _make_theme(tickers)

        recorder = _RecordingExecute()
        db = MagicMock()
        db.execute = recorder

        engine = DiscoveryEngine(fmp=MagicMock(), x_client=MagicMock())
        fmp_results = [_make_fmp_item(t) for t in tickers]

        cards = await engine._merge_results(
            theme=theme,
            fmp_results=fmp_results,
            cached_signals={},
            db=db,
        )

        for card in cards:
            self.assertFalse(card.is_surprise, f"{card.ticker} should not be a surprise")


if __name__ == "__main__":
    unittest.main()
