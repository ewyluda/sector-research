"""Unit tests for the earnings-board print-selection helper (issue #52)."""
import os
import unittest
from datetime import date

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.api.earnings import _choose_print
from backend.app.models.earnings_print import EarningsPrint


def _print(**over) -> EarningsPrint:
    base = dict(
        ticker="ORCL",
        fiscal_year=2026,
        fiscal_quarter=4,
        earnings_date=date(2026, 6, 10),
        eps_estimated=1.5,
        eps_actual=None,
    )
    base.update(over)
    return EarningsPrint(**base)


TODAY = date(2026, 6, 11)


class ChoosePrintTests(unittest.TestCase):
    def test_reported_print_is_post(self):
        chosen, phase = _choose_print([_print(eps_actual=1.62)], TODAY)
        self.assertEqual(phase, "post")

    def test_past_print_awaiting_actuals_is_post_pending(self):
        # Issue #52 repro: yesterday's print, nightly refresh hasn't landed.
        p = _print(earnings_date=date(2026, 6, 10), eps_actual=None)
        chosen, phase = _choose_print([p], TODAY)
        self.assertIs(chosen, p)
        self.assertEqual(phase, "post_pending")

    def test_future_print_is_pre(self):
        _, phase = _choose_print([_print(earnings_date=date(2026, 6, 20))], TODAY)
        self.assertEqual(phase, "pre")

    def test_today_print_without_actuals_is_pre(self):
        # Dated today (e.g. reports after close tonight) → still upcoming.
        _, phase = _choose_print([_print(earnings_date=TODAY)], TODAY)
        self.assertEqual(phase, "pre")

    def test_reported_beats_pending(self):
        reported = _print(earnings_date=date(2026, 6, 1), eps_actual=1.62)
        pending = _print(earnings_date=date(2026, 6, 10))
        chosen, phase = _choose_print([pending, reported], TODAY)
        self.assertIs(chosen, reported)
        self.assertEqual(phase, "post")

    def test_pending_beats_upcoming(self):
        pending = _print(earnings_date=date(2026, 6, 10))
        upcoming = _print(earnings_date=date(2026, 6, 24))
        chosen, phase = _choose_print([upcoming, pending], TODAY)
        self.assertIs(chosen, pending)
        self.assertEqual(phase, "post_pending")

    def test_empty_candidates_returns_none(self):
        self.assertIsNone(_choose_print([], TODAY))


if __name__ == "__main__":
    unittest.main()
