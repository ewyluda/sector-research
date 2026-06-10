"""Pins journal service behavior: adjusted-close on-or-before lookup,
create/close auto-fill with best-effort SPY, reopen clearing, and the
commit-free contract."""
from __future__ import annotations

import os
import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services import journal


def _fmp_with_history(rows, fail=False):
    fmp = MagicMock()
    if fail:
        fmp.get_historical_price_adjusted = AsyncMock(side_effect=RuntimeError("fmp down"))
    else:
        fmp.get_historical_price_adjusted = AsyncMock(return_value=(rows, MagicMock()))
    return fmp


def _db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


class AdjustedCloseTests(unittest.IsolatedAsyncioTestCase):
    async def test_picks_newest_row_on_or_before_target(self):
        rows = [
            {"date": "2026-06-08", "adjClose": 101.5},  # Monday, after target
            {"date": "2026-06-05", "adjClose": 100.0},  # Friday
        ]
        fmp = _fmp_with_history(rows)
        # Saturday target -> Monday row is beyond target, Friday close wins
        result = await journal.adjusted_close_on_or_before(fmp, "NVDA", date(2026, 6, 6))
        self.assertEqual(result, (Decimal("100.0"), date(2026, 6, 5)))

    async def test_none_on_fmp_failure(self):
        fmp = _fmp_with_history([], fail=True)
        self.assertIsNone(
            await journal.adjusted_close_on_or_before(fmp, "NVDA", date(2026, 6, 6))
        )

    async def test_none_on_empty_rows_and_skips_malformed(self):
        fmp = _fmp_with_history([{"date": "garbage", "adjClose": 1}, {"adjClose": 2}])
        self.assertIsNone(
            await journal.adjusted_close_on_or_before(fmp, "NVDA", date(2026, 6, 6))
        )


class CreateTradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_autofill_entry_price_and_spy_best_effort(self):
        rows = [{"date": "2026-06-05", "adjClose": 100.0}]
        fmp = _fmp_with_history(rows)
        db = _db()
        trade = await journal.create_trade(
            db, fmp, ticker="NVDA", entry_date=date(2026, 6, 5),
            entry_price=None, quantity=None, direction="long",
            outcome_id=None, entry_rationale=None,
        )
        self.assertEqual(trade.entry_price, Decimal("100.0"))
        self.assertEqual(trade.entry_price_source, "fmp_eod_adjusted")
        self.assertEqual(trade.spy_entry_price, Decimal("100.0"))
        db.add.assert_called_once()
        db.commit.assert_not_awaited()  # commit-free contract

    async def test_manual_price_skips_ticker_lookup_but_spy_failure_is_null(self):
        fmp = _fmp_with_history([], fail=True)
        db = _db()
        trade = await journal.create_trade(
            db, fmp, ticker="NVDA", entry_date=date(2026, 6, 5),
            entry_price=Decimal("99.5"), quantity=Decimal("10"), direction="long",
            outcome_id=None, entry_rationale="dip buy",
        )
        self.assertEqual(trade.entry_price_source, "manual")
        self.assertIsNone(trade.spy_entry_price)  # degraded, not raised

    async def test_autofill_failure_without_manual_price_raises(self):
        fmp = _fmp_with_history([], fail=True)
        with self.assertRaises(journal.PriceUnavailableError):
            await journal.create_trade(
                _db(), fmp, ticker="NVDA", entry_date=date(2026, 6, 5),
                entry_price=None, quantity=None, direction="long",
                outcome_id=None, entry_rationale=None,
            )


def _open_trade(**overrides):
    from backend.app.models.journal_trade import JournalTrade

    kwargs = dict(
        ticker="NVDA", direction="long",
        entry_date=date(2026, 6, 1), entry_price=Decimal("100"),
        entry_price_source="manual", spy_entry_price=Decimal("500"),
    )
    kwargs.update(overrides)
    return JournalTrade(**kwargs)


class UpdateTradeTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_autofills_exit_and_spy(self):
        rows = [{"date": "2026-06-08", "adjClose": 110.0}]
        fmp = _fmp_with_history(rows)
        trade = _open_trade()
        await journal.update_trade(_db(), fmp, trade, {"exit_date": date(2026, 6, 8),
                                                       "exit_reason": "stop_loss"})
        self.assertEqual(trade.exit_price, Decimal("110.0"))
        self.assertEqual(trade.exit_price_source, "fmp_eod_adjusted")
        self.assertEqual(trade.spy_exit_price, Decimal("110.0"))
        self.assertEqual(trade.exit_reason, "stop_loss")

    async def test_close_with_manual_price_spy_failure_degrades(self):
        fmp = _fmp_with_history([], fail=True)
        trade = _open_trade()
        await journal.update_trade(
            _db(), fmp, trade,
            {"exit_date": date(2026, 6, 8), "exit_price": Decimal("111")},
        )
        self.assertEqual(trade.exit_price, Decimal("111"))
        self.assertEqual(trade.exit_price_source, "manual")
        self.assertIsNone(trade.spy_exit_price)

    async def test_exit_before_entry_raises_value_error(self):
        trade = _open_trade()
        with self.assertRaises(ValueError):
            await journal.update_trade(
                _db(), _fmp_with_history([]), trade, {"exit_date": date(2026, 5, 1),
                                                      "exit_price": Decimal("1")},
            )

    async def test_exit_fields_without_exit_date_raise(self):
        trade = _open_trade()
        with self.assertRaises(ValueError):
            await journal.update_trade(
                _db(), _fmp_with_history([]), trade, {"exit_reason": "mistake"}
            )

    async def test_reopen_clears_all_exit_fields(self):
        trade = _open_trade(
            exit_date=date(2026, 6, 8), exit_price=Decimal("110"),
            exit_price_source="manual", exit_reason="stop_loss",
            exit_note="note", spy_exit_price=Decimal("510"),
        )
        await journal.update_trade(_db(), _fmp_with_history([]), trade, {"exit_date": None})
        for field in ("exit_date", "exit_price", "exit_price_source",
                      "exit_reason", "exit_note", "spy_exit_price"):
            self.assertIsNone(getattr(trade, field), field)

    async def test_reclose_with_moved_date_refreshes_fmp_sourced_fills(self):
        rows = [{"date": "2026-06-10", "adjClose": 120.0}]
        fmp = _fmp_with_history(rows)
        trade = _open_trade(
            exit_date=date(2026, 6, 8), exit_price=Decimal("110"),
            exit_price_source="fmp_eod_adjusted", spy_exit_price=Decimal("510"),
        )
        await journal.update_trade(_db(), fmp, trade, {"exit_date": date(2026, 6, 10)})
        self.assertEqual(trade.exit_price, Decimal("120.0"))
        self.assertEqual(trade.exit_price_source, "fmp_eod_adjusted")
        self.assertEqual(trade.spy_exit_price, Decimal("120.0"))

    async def test_reclose_with_moved_date_keeps_manual_price_sticky(self):
        rows = [{"date": "2026-06-10", "adjClose": 120.0}]
        fmp = _fmp_with_history(rows)
        trade = _open_trade(
            exit_date=date(2026, 6, 8), exit_price=Decimal("111"),
            exit_price_source="manual", spy_exit_price=Decimal("510"),
        )
        await journal.update_trade(_db(), fmp, trade, {"exit_date": date(2026, 6, 10)})
        self.assertEqual(trade.exit_price, Decimal("111"))  # manual stays
        self.assertEqual(trade.exit_price_source, "manual")
        self.assertEqual(trade.spy_exit_price, Decimal("120.0"))  # benchmark refreshed

    async def test_entry_date_move_refreshes_fmp_sourced_entry(self):
        rows = [{"date": "2026-06-03", "adjClose": 95.0}]
        fmp = _fmp_with_history(rows)
        trade = _open_trade(
            entry_price_source="fmp_eod_adjusted", spy_entry_price=Decimal("500"),
        )
        await journal.update_trade(_db(), fmp, trade, {"entry_date": date(2026, 6, 3)})
        self.assertEqual(trade.entry_price, Decimal("95.0"))
        self.assertEqual(trade.spy_entry_price, Decimal("95.0"))

    async def test_entry_date_move_with_manual_source_keeps_price(self):
        rows = [{"date": "2026-06-03", "adjClose": 95.0}]
        fmp = _fmp_with_history(rows)
        trade = _open_trade()  # entry_price_source="manual"
        await journal.update_trade(_db(), fmp, trade, {"entry_date": date(2026, 6, 3)})
        self.assertEqual(trade.entry_price, Decimal("100"))  # manual stays
        self.assertEqual(trade.spy_entry_price, Decimal("95.0"))  # benchmark refreshed

    async def test_null_entry_date_or_direction_raises(self):
        for field in ("entry_date", "direction"):
            with self.assertRaises(ValueError):
                await journal.update_trade(
                    _db(), _fmp_with_history([]), _open_trade(), {field: None}
                )

    async def test_explicit_null_clears_nullable_fields(self):
        trade = _open_trade(quantity=Decimal("10"), entry_rationale="note",
                            outcome_id="some-outcome-id")
        await journal.update_trade(
            _db(), _fmp_with_history([]), trade,
            {"quantity": None, "entry_rationale": None, "outcome_id": None},
        )
        self.assertIsNone(trade.quantity)
        self.assertIsNone(trade.entry_rationale)
        self.assertIsNone(trade.outcome_id)

    async def test_reopen_with_exit_fields_raises(self):
        trade = _open_trade(exit_date=date(2026, 6, 8), exit_price=Decimal("110"),
                            exit_price_source="manual")
        with self.assertRaises(ValueError):
            await journal.update_trade(
                _db(), _fmp_with_history([]), trade,
                {"exit_date": None, "exit_price": Decimal("50")},
            )


if __name__ == "__main__":
    unittest.main()
