"""Pins the pure decision-vs-outcome math: direction-aware returns,
SPY-excess None propagation, nearest-offset boundaries, snapshot
comparison, and summary rollups."""
from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from backend.app.services.journal_comparison import (
    ClosedTradeStat,
    decision_vs_outcome,
    nearest_offset,
    summarize,
    trade_returns,
)


def _returns(**overrides):
    kwargs = dict(
        direction="long",
        entry_date=date(2026, 1, 5),
        entry_price=Decimal("100"),
        exit_date=date(2026, 4, 6),
        exit_price=Decimal("110"),
        spy_entry_price=Decimal("500"),
        spy_exit_price=Decimal("510"),
    )
    kwargs.update(overrides)
    return trade_returns(**kwargs)


class TradeReturnsTests(unittest.TestCase):
    def test_long_return_and_spy_excess(self):
        r = _returns()
        self.assertEqual(r.return_pct, Decimal("0.1"))
        self.assertEqual(r.spy_excess_pct, Decimal("0.08"))
        self.assertEqual(r.holding_days, 91)

    def test_short_return_is_negated_but_excess_still_trade_minus_spy(self):
        r = _returns(direction="short")
        self.assertEqual(r.return_pct, Decimal("-0.1"))
        self.assertEqual(r.spy_excess_pct, Decimal("-0.12"))

    def test_open_trade_returns_all_none(self):
        r = _returns(exit_date=None, exit_price=None)
        self.assertIsNone(r.return_pct)
        self.assertIsNone(r.spy_excess_pct)
        self.assertIsNone(r.holding_days)

    def test_missing_spy_price_propagates_none_excess(self):
        r = _returns(spy_exit_price=None)
        self.assertEqual(r.return_pct, Decimal("0.1"))
        self.assertIsNone(r.spy_excess_pct)


class NearestOffsetTests(unittest.TestCase):
    def test_boundaries(self):
        cases = [(0, "1d"), (4, "1d"), (5, "1w"), (18, "1w"), (19, "1m"),
                 (60, "1m"), (61, "3m"), (136, "3m"), (137, "6m"), (200, "6m")]
        for days, expected in cases:
            with self.subTest(days=days):
                self.assertEqual(nearest_offset(days), expected)


def _snap(offset, ret, excess):
    return {
        "snapshot_offset": offset,
        "ticker_return_pct": ret,
        "spy_excess_pct": excess,
    }


class DecisionVsOutcomeTests(unittest.TestCase):
    def test_picks_nearest_offset_and_computes_delta(self):
        r = _returns()  # 91 holding days -> '3m'
        snaps = [_snap("1m", Decimal("0.05"), Decimal("0.02")),
                 _snap("3m", Decimal("0.15"), Decimal("0.11"))]
        c = decision_vs_outcome(r, snaps)
        self.assertEqual(c.offset, "3m")
        self.assertEqual(c.paper_return_pct, Decimal("0.15"))
        self.assertEqual(c.execution_delta_pct, Decimal("0.08") - Decimal("0.11"))

    def test_none_when_snapshot_missing(self):
        r = _returns()
        self.assertIsNone(decision_vs_outcome(r, [_snap("1d", Decimal("0.01"), None)]))

    def test_none_for_open_trade(self):
        r = _returns(exit_date=None, exit_price=None)
        self.assertIsNone(decision_vs_outcome(r, [_snap("3m", Decimal("0.1"), None)]))

    def test_delta_none_when_either_excess_missing(self):
        r = _returns(spy_exit_price=None)  # trade excess None
        c = decision_vs_outcome(r, [_snap("3m", Decimal("0.15"), Decimal("0.11"))])
        self.assertIsNotNone(c)
        self.assertIsNone(c.execution_delta_pct)


def _stat(ret, excess, days=30, reason="stop_loss", delta=None):
    return ClosedTradeStat(
        return_pct=Decimal(str(ret)),
        spy_excess_pct=None if excess is None else Decimal(str(excess)),
        holding_days=days,
        exit_reason=reason,
        execution_delta_pct=None if delta is None else Decimal(str(delta)),
    )


class SummarizeTests(unittest.TestCase):
    def test_empty_journal_shape(self):
        s = summarize([])
        self.assertEqual(s["closed_count"], 0)
        self.assertIsNone(s["hit_rate"])
        self.assertEqual(s["by_exit_reason"], [])
        self.assertEqual(s["execution_vs_paper"], {"n": 0, "avg_delta_pct": None})

    def test_hit_rate_uses_excess_when_available_else_raw_return(self):
        stats = [
            _stat("0.10", "0.05"),   # hit on excess
            _stat("0.10", "-0.02"),  # miss on excess despite positive return
            _stat("0.10", None),     # falls back to raw return -> hit
        ]
        s = summarize(stats)
        self.assertAlmostEqual(s["hit_rate"], 2 / 3)
        self.assertEqual(s["excess_basis_count"], 2)

    def test_median_even_count_and_exit_reason_grouping(self):
        stats = [_stat("0.10", "0.01", reason="stop_loss"),
                 _stat("0.20", "0.02", reason="thesis_played_out"),
                 _stat("-0.10", None, reason=None),
                 _stat("0.40", "0.03", reason="stop_loss", delta="0.01")]
        s = summarize(stats)
        self.assertEqual(s["median_return_pct"], Decimal("0.15"))
        reasons = {r["exit_reason"]: r for r in s["by_exit_reason"]}
        self.assertEqual(reasons["stop_loss"]["count"], 2)
        self.assertEqual(reasons["unspecified"]["count"], 1)
        self.assertEqual(s["execution_vs_paper"], {"n": 1, "avg_delta_pct": Decimal("0.01")})


if __name__ == "__main__":
    unittest.main()
