"""Pins the congress side of the daily material scan: fault isolation
(a congress FMP failure can't suppress the already-committed insider work,
and vice versa the congress block only rolls back itself), the happy-path
signal persist (signal_type='congress' + history dual-write), and the
generalized _persist_insider_signal signal_type param."""

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

from backend.app.models.signal import Signal
from backend.app.services.material_events_scheduler import _persist_insider_signal

SENATE_ROW = {
    "symbol": "NVDA",
    "firstName": "Jane",
    "lastName": "Doe",
    "office": "Jane Doe",
    "district": "RI",
    "owner": "Self",
    "type": "Purchase",
    "transactionDate": "2026-06-01",
    "disclosureDate": "2026-06-08",
    "amount": "$15,001 - $50,000",
    "assetType": "Stock",
    "link": "https://efdsearch.senate.gov/search/view/ptr/x/",
}


def _scan_mocks():
    """(db, edgar, fmp, session_cm, added) with a quiet 8-K + insider side."""
    added: list[object] = []
    db = MagicMock()
    db.add = MagicMock(side_effect=added.append)
    empty = MagicMock()
    empty.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=empty)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=db)
    session_cm.__aexit__ = AsyncMock(return_value=False)

    edgar = MagicMock()
    edgar.get_ticker_to_cik = AsyncMock(return_value=("0001045810", MagicMock()))
    edgar.get_submissions = AsyncMock(return_value=({}, MagicMock()))

    fmp = MagicMock()
    fmp.get_insider_trading = AsyncMock(return_value=([], MagicMock()))
    fmp.get_senate_trades = AsyncMock(return_value=([SENATE_ROW], MagicMock()))
    fmp.get_house_trades = AsyncMock(return_value=([], MagicMock()))
    return db, edgar, fmp, session_cm, added


class CongressOrchestrationTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, db, edgar, fmp, session_cm):
        from backend.app.services import material_events_scheduler as mes
        with patch.object(mes, "async_session", MagicMock(return_value=session_cm)), \
             patch.object(mes, "_theme_universe",
                          new=AsyncMock(return_value={"theme-1": {"NVDA"}})):
            return await mes.run_daily_material_scan(edgar=edgar, fmp=fmp)

    async def test_happy_path_writes_congress_signal(self):
        db, edgar, fmp, session_cm, added = _scan_mocks()
        summary = await self._run(db, edgar, fmp, session_cm)

        fmp.get_senate_trades.assert_awaited_once()
        fmp.get_house_trades.assert_awaited_once()
        self.assertEqual(summary["congress_transactions_added"], 1)
        congress_signals = [
            a for a in added
            if isinstance(a, Signal) and a.signal_type == "congress"
        ]
        insider_signals = [
            a for a in added
            if isinstance(a, Signal) and a.signal_type == "insider"
        ]
        self.assertEqual(len(congress_signals), 1)
        self.assertEqual(len(insider_signals), 1)
        self.assertEqual(summary["signals_written"], 2)

    async def test_congress_failure_does_not_suppress_insider(self):
        db, edgar, fmp, session_cm, added = _scan_mocks()
        fmp.get_senate_trades = AsyncMock(side_effect=RuntimeError("FMP 503"))
        summary = await self._run(db, edgar, fmp, session_cm)

        # Insider side already committed; congress block rolled back alone.
        insider_signals = [
            a for a in added
            if isinstance(a, Signal) and a.signal_type == "insider"
        ]
        self.assertEqual(len(insider_signals), 1)
        self.assertEqual(summary["signals_written"], 1)
        self.assertEqual(summary["tickers_scanned"], 1)
        self.assertTrue(any("congress" in e for e in summary["errors"]))
        db.rollback.assert_awaited()


class PersistSignalTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_signal_type_param_writes_congress_rows(self):
        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)
        db.execute = AsyncMock(return_value=MagicMock())

        now = datetime(2026, 6, 11, 6, 30, tzinfo=timezone.utc)
        await _persist_insider_signal(
            db=db, ticker="NVDA",
            theme_id="00000000-0000-0000-0000-000000000001",
            value={"buy_count": 1, "modifier": 1}, computed_at=now,
            signal_type="congress",
        )
        signals = [a for a in added if isinstance(a, Signal)]
        self.assertEqual(len(signals), 1)
        self.assertEqual(signals[0].signal_type, "congress")


if __name__ == "__main__":
    unittest.main()
