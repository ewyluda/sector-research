"""Pins signal-history endpoint contract: 404 unknown theme, 400 bad
signal_type, response shape. Ticker normalization now happens at the
``TickerPath`` boundary (see test_ticker.py), so the handler receives an
already-normalized ticker — these direct calls pass it pre-normalized."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import HTTPException

from backend.app.api.discovery import get_signal_history_endpoint
from backend.app.models.signal_history import SignalHistory
from backend.app.models.theme import Theme


def _theme(id_: str = "t1", name: str = "AI Infra") -> Theme:
    return Theme(id=id_, name=name, x_search_terms=[], seed_tickers=[])


class SignalHistoryEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_404_when_theme_missing(self):
        db = MagicMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=scalar_result)

        with self.assertRaises(HTTPException) as ctx:
            await get_signal_history_endpoint(
                theme_id="missing",
                ticker="NVDA",
                signal_type="velocity",
                days=90,
                db=db,
            )
        self.assertEqual(ctx.exception.status_code, 404)

    async def test_400_when_signal_type_invalid(self):
        db = MagicMock()
        db.execute = AsyncMock()  # should never be called

        with self.assertRaises(HTTPException) as ctx:
            await get_signal_history_endpoint(
                theme_id="t1",
                ticker="NVDA",
                signal_type="bogus",
                days=90,
                db=db,
            )
        self.assertEqual(ctx.exception.status_code, 400)
        db.execute.assert_not_called()

    async def test_returns_serialized_rows(self):
        db = MagicMock()
        scalar_result = MagicMock()
        scalar_result.scalar_one_or_none.return_value = _theme()
        db.execute = AsyncMock(return_value=scalar_result)

        rows = [
            SignalHistory(
                ticker="NVDA",
                theme_id="t1",
                signal_type="velocity",
                value={"ratio": 1.2, "direction": "accelerating"},
                computed_at=datetime(2026, 5, 1, 2, 0, tzinfo=timezone.utc),
            ),
            SignalHistory(
                ticker="NVDA",
                theme_id="t1",
                signal_type="velocity",
                value={"ratio": 1.4, "direction": "accelerating"},
                computed_at=datetime(2026, 5, 2, 2, 0, tzinfo=timezone.utc),
            ),
        ]

        with patch(
            "backend.app.api.discovery.list_signal_history",
            AsyncMock(return_value=rows),
        ):
            out = await get_signal_history_endpoint(
                theme_id="t1",
                ticker="NVDA",
                signal_type="velocity",
                days=90,
                db=db,
            )

        self.assertEqual(out["ticker"], "NVDA")
        self.assertEqual(out["theme_id"], "t1")
        self.assertEqual(out["signal_type"], "velocity")
        self.assertEqual(len(out["points"]), 2)
        self.assertEqual(out["points"][0]["computed_at"], "2026-05-01T02:00:00+00:00")
        self.assertEqual(out["points"][0]["value"], {"ratio": 1.2, "direction": "accelerating"})


if __name__ == "__main__":
    unittest.main()
