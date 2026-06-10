"""Pins the 90-day insider aggregate + discovery modifier semantics
(spec: docs/superpowers/specs/2026-06-10-material-events-design.md)."""

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

from backend.app.services.insider_signal import (
    compute_insider_aggregate,
    modifier_from_aggregate,
    signal_value,
)

TODAY = date(2026, 6, 10)


def tx(direction="buy", days_ago=5, shares=100, price=10.0, insider="Alice"):
    from datetime import timedelta
    return SimpleNamespace(
        direction=direction,
        transaction_date=TODAY - timedelta(days=days_ago),
        shares=shares,
        price=price,
        insider_name=insider,
    )


class AggregateTests(unittest.TestCase):
    def test_empty_input(self):
        agg = compute_insider_aggregate([], TODAY)
        self.assertEqual(agg.buy_count, 0)
        self.assertEqual(agg.sell_count, 0)
        self.assertIsNone(agg.net_value)
        self.assertFalse(agg.cluster_buy)

    def test_other_direction_excluded(self):
        agg = compute_insider_aggregate([tx(direction="other")], TODAY)
        self.assertEqual(agg.buy_count, 0)
        self.assertIsNone(agg.net_value)

    def test_outside_window_excluded(self):
        agg = compute_insider_aggregate([tx(days_ago=120)], TODAY)
        self.assertEqual(agg.buy_count, 0)

    def test_null_date_excluded(self):
        t = tx()
        t.transaction_date = None
        agg = compute_insider_aggregate([t], TODAY)
        self.assertEqual(agg.buy_count, 0)

    def test_net_value_buy_minus_sell(self):
        agg = compute_insider_aggregate(
            [tx(shares=100, price=10.0), tx(direction="sell", shares=30, price=10.0, insider="Bob")],
            TODAY,
        )
        self.assertEqual(agg.buy_count, 1)
        self.assertEqual(agg.sell_count, 1)
        self.assertAlmostEqual(agg.net_value, 700.0)

    def test_null_price_counts_but_no_value(self):
        # spec: null-price rows count toward counts but not net_value
        agg = compute_insider_aggregate([tx(price=None)], TODAY)
        self.assertEqual(agg.buy_count, 1)
        self.assertIsNone(agg.net_value)

    def test_cluster_two_distinct_buyers_within_30d(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice", days_ago=5), tx(insider="Bob", days_ago=20)], TODAY
        )
        self.assertTrue(agg.cluster_buy)

    def test_no_cluster_same_buyer_twice(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice", days_ago=5), tx(insider="Alice", days_ago=10)], TODAY
        )
        self.assertFalse(agg.cluster_buy)

    def test_no_cluster_buyers_more_than_30d_apart(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice", days_ago=2), tx(insider="Bob", days_ago=80)], TODAY
        )
        self.assertFalse(agg.cluster_buy)


class ModifierTests(unittest.TestCase):
    def test_cluster_buy_plus_5(self):
        agg = compute_insider_aggregate(
            [tx(insider="Alice"), tx(insider="Bob", days_ago=8)], TODAY
        )
        self.assertEqual(modifier_from_aggregate(agg), 5)

    def test_net_buying_plus_2(self):
        agg = compute_insider_aggregate([tx(insider="Alice")], TODAY)
        self.assertEqual(modifier_from_aggregate(agg), 2)

    def test_buys_with_null_price_still_plus_2(self):
        agg = compute_insider_aggregate([tx(price=None)], TODAY)
        self.assertEqual(modifier_from_aggregate(agg), 2)

    def test_pronounced_selling_minus_3(self):
        sells = [
            tx(direction="sell", insider=name, shares=100_000, price=20.0)
            for name in ("A", "B", "C")
        ]
        agg = compute_insider_aggregate(sells, TODAY)
        self.assertEqual(modifier_from_aggregate(agg), -3)

    def test_mild_selling_zero(self):
        # below the -$1M threshold OR fewer than 3 sellers → 0
        agg = compute_insider_aggregate(
            [tx(direction="sell", shares=100, price=10.0)], TODAY
        )
        self.assertEqual(modifier_from_aggregate(agg), 0)

    def test_empty_zero(self):
        agg = compute_insider_aggregate([], TODAY)
        self.assertEqual(modifier_from_aggregate(agg), 0)


class SignalValueTests(unittest.TestCase):
    def test_jsonb_payload_shape(self):
        agg = compute_insider_aggregate([tx()], TODAY)
        value = signal_value(agg)
        for key in (
            "buy_count", "sell_count", "distinct_buyers", "distinct_sellers",
            "net_value", "cluster_buy", "window_days", "modifier",
        ):
            self.assertIn(key, value)
        self.assertEqual(value["modifier"], 2)


if __name__ == "__main__":
    unittest.main()
