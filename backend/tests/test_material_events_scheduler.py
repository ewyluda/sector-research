"""Pins the daily material scan internals: recent-8-K extraction from the
submissions feed, accession-dedupe idempotency (classifier never re-invoked
for an existing event), and the insider-signal persist (delete-then-add +
history dual-write, mirroring _persist_signal_set)."""

import os
import unittest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.signal import Signal
from backend.app.models.signal_history import SignalHistory
from backend.app.services.material_events_scheduler import (
    _persist_insider_signal,
    _recent_8ks,
    _scan_ticker_8ks,
)

SUBMISSIONS = {
    "filings": {
        "recent": {
            "form": ["8-K", "10-Q", "8-K", "8-K"],
            "accessionNumber": ["0001-26-000001", "0001-26-000002", "0001-26-000003", "0001-26-000004"],
            "primaryDocument": ["a.htm", "b.htm", "c.htm", "d.htm"],
            "filingDate": ["2026-06-08", "2026-06-05", "2026-06-01", "2026-01-15"],
            "items": ["5.02", "", "7.01,9.01", "2.02,9.01"],
        }
    }
}


class Recent8KTests(unittest.TestCase):
    def test_filters_form_and_window(self):
        out = _recent_8ks(SUBMISSIONS, since=date(2026, 5, 28))
        # 10-Q excluded; the January 8-K is outside the window.
        self.assertEqual(
            [c["accession_number"] for c in out],
            ["0001-26-000001", "0001-26-000003"],
        )
        self.assertEqual(out[0]["item_codes"], "5.02")
        self.assertEqual(out[0]["filing_date"], date(2026, 6, 8))

    def test_empty_submissions(self):
        self.assertEqual(_recent_8ks({}, since=date(2026, 5, 28)), [])


class ScanTicker8KTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_accession_skips_classifier(self):
        edgar = MagicMock()
        edgar.get_submissions = AsyncMock(return_value=(SUBMISSIONS, MagicMock()))
        edgar.fetch_document = AsyncMock(return_value=("<html>x</html>", MagicMock()))

        db = MagicMock()
        existing = MagicMock()
        existing.first.return_value = ("some-id",)  # every accession already has an event
        db.execute = AsyncMock(return_value=existing)

        with patch(
            "backend.app.services.material_events_scheduler.classify_8k",
            new=AsyncMock(),
        ) as mock_classify:
            counts = await _scan_ticker_8ks(
                ticker="NVDA", cik="0001045810", edgar=edgar, db=db,
                since=date(2026, 5, 28),
            )

        mock_classify.assert_not_awaited()
        self.assertEqual(counts["events_created"], 0)
        # 5.02 8-K dedupe-skipped; 7.01,9.01 8-K prefilter-skipped
        self.assertEqual(counts["skipped_existing"], 1)
        self.assertEqual(counts["skipped_prefilter"], 1)

    async def test_new_8k_creates_event(self):
        edgar = MagicMock()
        edgar.get_submissions = AsyncMock(return_value=(SUBMISSIONS, MagicMock()))
        edgar.fetch_document = AsyncMock(return_value=("<html>CFO out</html>", MagicMock()))

        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)
        no_hit = MagicMock()
        no_hit.first.return_value = None
        no_hit.scalar_one_or_none.return_value = None  # for _upsert_filing's SELECT
        db.execute = AsyncMock(return_value=no_hit)
        db.flush = AsyncMock()

        from backend.app.services.event_classifier import EventClassification
        classification = EventClassification(
            event_type="personnel", materiality="high",
            headline="CFO resigns", summary="The CFO resigned.",
        )
        with patch(
            "backend.app.services.material_events_scheduler.classify_8k",
            new=AsyncMock(return_value=(classification, None)),
        ):
            counts = await _scan_ticker_8ks(
                ticker="NVDA", cik="0001045810", edgar=edgar, db=db,
                since=date(2026, 5, 28),
            )

        self.assertEqual(counts["events_created"], 1)
        from backend.app.models.material_event import MaterialEvent
        events = [a for a in added if isinstance(a, MaterialEvent)]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "personnel")
        self.assertEqual(events[0].ticker, "NVDA")


class PersistInsiderSignalTests(unittest.IsolatedAsyncioTestCase):
    async def test_delete_then_add_signal_and_history(self):
        added: list[object] = []
        deletes: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)
        db.execute = AsyncMock(side_effect=lambda stmt: deletes.append(stmt) or MagicMock())

        now = datetime(2026, 6, 10, 6, 30, tzinfo=timezone.utc)
        value = {"buy_count": 1, "modifier": 2}
        await _persist_insider_signal(
            db=db, ticker="NVDA",
            theme_id="00000000-0000-0000-0000-000000000001",
            value=value, computed_at=now,
        )

        self.assertEqual(len(deletes), 1)
        signals = [a for a in added if isinstance(a, Signal)]
        history = [a for a in added if isinstance(a, SignalHistory)]
        self.assertEqual(len(signals), 1)
        self.assertEqual(len(history), 1)
        self.assertEqual(signals[0].signal_type, "insider")
        self.assertEqual(signals[0].value, value)
        self.assertEqual(signals[0].computed_at, now)


class OrchestratorFaultIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def test_edgar_failure_does_not_suppress_insider_ingest(self):
        from backend.app.services import material_events_scheduler as mes

        db = MagicMock()
        empty = MagicMock()
        empty.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=empty)
        db.commit = AsyncMock()
        db.rollback = AsyncMock()
        db.add = MagicMock()

        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db)
        session_cm.__aexit__ = AsyncMock(return_value=False)

        edgar = MagicMock()
        edgar.get_ticker_to_cik = AsyncMock(return_value=("0001045810", MagicMock()))
        edgar.get_submissions = AsyncMock(side_effect=RuntimeError("EDGAR 503"))

        fmp = MagicMock()
        fmp.get_insider_trading = AsyncMock(return_value=([], MagicMock()))

        with patch.object(mes, "async_session", MagicMock(return_value=session_cm)), \
             patch.object(mes, "_theme_universe", new=AsyncMock(return_value={"theme-1": {"NVDA"}})):
            summary = await mes.run_daily_material_scan(edgar=edgar, fmp=fmp)

        fmp.get_insider_trading.assert_awaited_once()
        db.rollback.assert_awaited()
        self.assertEqual(summary["tickers_scanned"], 1)
        self.assertEqual(summary["signals_written"], 1)
        self.assertTrue(any("8-K scan" in e for e in summary["errors"]))


if __name__ == "__main__":
    unittest.main()
