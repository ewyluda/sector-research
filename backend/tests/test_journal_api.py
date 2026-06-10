"""Tests for backend.app.api.journal — CRUD, validation, summary shape."""
from __future__ import annotations

import os
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi.testclient import TestClient

from backend.app.models.journal_trade import JournalTrade
from backend.app.models.outcome import VerdictOutcome, VerdictReturnSnapshot
from backend.app.services.journal import PriceUnavailableError


def _client():
    from backend.app.main import app

    app.state.fmp = MagicMock()
    return TestClient(app)


def _trade(**overrides):
    kwargs = dict(
        id=str(uuid4()),
        ticker="NVDA",
        direction="long",
        entry_date=date(2026, 6, 1),
        entry_price=Decimal("100"),
        entry_price_source="manual",
        spy_entry_price=Decimal("500"),
        outcome_id=None,
        quantity=None,
        entry_rationale=None,
        exit_date=None,
        exit_price=None,
        exit_price_source=None,
        exit_reason=None,
        exit_note=None,
        spy_exit_price=None,
    )
    kwargs.update(overrides)
    t = JournalTrade(**kwargs)
    t.created_at = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return t


def _closed_trade(**overrides):
    base = dict(
        exit_date=date(2026, 6, 8),
        exit_price=Decimal("110"),
        exit_price_source="manual",
        spy_exit_price=Decimal("510"),
        exit_reason="stop_loss",
    )
    base.update(overrides)
    return _trade(**base)


def _outcome_with_snapshot():
    o = VerdictOutcome(
        id=str(uuid4()),
        source_type="research_run",
        source_id=str(uuid4()),
        ticker="NVDA",
        theme_id=None,
        verdict="completed",
        verdict_emitted_at=datetime(2026, 5, 30, tzinfo=timezone.utc),
        entry_price_at=date(2026, 6, 1),
        entry_price=Decimal("100"),
        realized_spy_excess_pct=None,
    )
    o.snapshots = [
        VerdictReturnSnapshot(
            id=str(uuid4()),
            outcome_id=o.id,
            snapshot_offset="1w",
            snapshot_date=date(2026, 6, 8),
            ticker_price=Decimal("108"),
            ticker_return_pct=Decimal("0.08"),
            spy_excess_pct=Decimal("0.05"),
        )
    ]
    return o


class CreateTradeTests(unittest.TestCase):
    def test_create_201(self):
        trade = _trade()
        with patch("backend.app.api.journal.journal.create_trade",
                   new=AsyncMock(return_value=trade)), \
             patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=trade)):
            r = _client().post("/api/journal/trades", json={
                "ticker": "nvda", "entry_date": "2026-06-01",
                "entry_price": "100",
            })
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["ticker"], "NVDA")
        self.assertEqual(body["status"], "open")
        self.assertIsNone(body["comparison"])

    def test_create_422_when_autofill_unavailable(self):
        with patch("backend.app.api.journal.journal.create_trade",
                   new=AsyncMock(side_effect=PriceUnavailableError("no price"))):
            r = _client().post("/api/journal/trades", json={
                "ticker": "NVDA", "entry_date": "2026-06-01",
            })
        self.assertEqual(r.status_code, 422)

    def test_create_400_on_garbage_ticker(self):
        r = _client().post("/api/journal/trades", json={
            "ticker": "not a ticker!!", "entry_date": "2026-06-01",
            "entry_price": "1",
        })
        self.assertEqual(r.status_code, 400)


class PatchTradeTests(unittest.TestCase):
    def test_patch_close_returns_closed_status(self):
        closed = _closed_trade()
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=closed)), \
             patch("backend.app.api.journal.journal.update_trade",
                   new=AsyncMock(return_value=closed)):
            r = _client().patch(f"/api/journal/trades/{closed.id}", json={
                "exit_date": "2026-06-08", "exit_reason": "stop_loss",
            })
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "closed")
        # realized: (110-100)/100 = 0.1; spy (510-500)/500 = 0.02 -> excess 0.08
        self.assertAlmostEqual(float(body["returns"]["return_pct"]), 0.1)
        self.assertAlmostEqual(float(body["returns"]["spy_excess_pct"]), 0.08)
        self.assertFalse(body["returns"]["unrealized"])

    def test_patch_404_unknown_trade(self):
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=None)):
            r = _client().patch(f"/api/journal/trades/{uuid4()}", json={})
        self.assertEqual(r.status_code, 404)

    def test_patch_422_on_invariant_violation(self):
        trade = _trade()
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=trade)), \
             patch("backend.app.api.journal.journal.update_trade",
                   new=AsyncMock(side_effect=ValueError("exit_date is before entry_date"))):
            r = _client().patch(f"/api/journal/trades/{trade.id}", json={
                "exit_date": "2020-01-01",
            })
        self.assertEqual(r.status_code, 422)


class ListTradesTests(unittest.TestCase):
    def test_list_embeds_linked_outcome_and_comparison(self):
        outcome = _outcome_with_snapshot()
        closed = _closed_trade(outcome_id=outcome.id)
        closed.outcome = outcome
        with patch("backend.app.api.journal.journal.list_trades",
                   new=AsyncMock(return_value=[closed])):
            r = _client().get("/api/journal/trades?status=closed")
        self.assertEqual(r.status_code, 200)
        row = r.json()[0]
        self.assertEqual(row["linked_outcome"]["verdict"], "completed")
        # 7 holding days -> '1w' snapshot; delta = 0.08 - 0.05
        self.assertEqual(row["comparison"]["offset"], "1w")
        self.assertAlmostEqual(float(row["comparison"]["execution_delta_pct"]), 0.03)

    def test_list_open_trade_unrealized_quote_failure_degrades(self):
        trade = _trade()
        trade.outcome = None
        with patch("backend.app.api.journal.journal.list_trades",
                   new=AsyncMock(return_value=[trade])):
            client = _client()
            client.app.state.fmp.get_quote = AsyncMock(side_effect=RuntimeError("down"))
            r = client.get("/api/journal/trades")
        self.assertEqual(r.status_code, 200)
        row = r.json()[0]
        self.assertEqual(row["status"], "open")
        self.assertTrue(row["returns"]["unrealized"])
        self.assertIsNone(row["returns"]["return_pct"])


class DeleteTradeTests(unittest.TestCase):
    def test_delete_204(self):
        trade = _trade()
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=trade)), \
             patch("backend.app.api.journal.journal.delete_trade",
                   new=AsyncMock(return_value=None)):
            r = _client().delete(f"/api/journal/trades/{trade.id}")
        self.assertEqual(r.status_code, 204)

    def test_delete_404(self):
        with patch("backend.app.api.journal.journal.get_trade",
                   new=AsyncMock(return_value=None)):
            r = _client().delete(f"/api/journal/trades/{uuid4()}")
        self.assertEqual(r.status_code, 404)


class SummaryTests(unittest.TestCase):
    def test_summary_shape(self):
        outcome = _outcome_with_snapshot()
        closed = _closed_trade(outcome_id=outcome.id)
        closed.outcome = outcome
        with patch("backend.app.api.journal.journal.list_trades",
                   new=AsyncMock(return_value=[closed])), \
             patch("backend.app.api.journal.journal.trade_counts",
                   new=AsyncMock(return_value=(2, 1))), \
             patch("backend.app.api.journal.journal.coverage_counts",
                   new=AsyncMock(return_value=(1, 4))):
            r = _client().get("/api/journal/summary")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["trade_count"], 3)
        self.assertEqual(body["open_count"], 2)
        self.assertEqual(body["closed_count"], 1)
        self.assertEqual(body["coverage"], {"outcomes_traded": 1, "outcomes_total": 4})
        self.assertEqual(body["execution_vs_paper"]["n"], 1)
        self.assertEqual(body["hit_rate"], 1.0)


class PricePreviewTests(unittest.TestCase):
    def test_preview_200(self):
        with patch("backend.app.api.journal.journal.adjusted_close_on_or_before",
                   new=AsyncMock(return_value=(Decimal("101.5"), date(2026, 6, 5)))):
            r = _client().get("/api/journal/price-preview?ticker=nvda&date=2026-06-06")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["price_date"], "2026-06-05")
        self.assertEqual(body["source"], "fmp_eod_adjusted")

    def test_preview_404_when_unavailable(self):
        with patch("backend.app.api.journal.journal.adjusted_close_on_or_before",
                   new=AsyncMock(return_value=None)):
            r = _client().get("/api/journal/price-preview?ticker=NVDA&date=2026-06-06")
        self.assertEqual(r.status_code, 404)


class LinkCandidatesTests(unittest.TestCase):
    def test_candidates_serialized(self):
        outcome = _outcome_with_snapshot()
        with patch("backend.app.api.journal.journal.link_candidates",
                   new=AsyncMock(return_value=[outcome])):
            r = _client().get("/api/journal/link-candidates?ticker=NVDA")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["verdict"], "completed")


if __name__ == "__main__":
    unittest.main()
