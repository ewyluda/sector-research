"""Pins the 90-day congressional-trading aggregate + discovery modifier.

Mirrors test_insider_signal.py. Net value comes from disclosed amount-range
midpoints (amount_mid), not shares×price; the modifier table is smaller than
the insider one (+3/+1/-2 vs +5/+2/-3) because disclosures lag up to 45 days
and amounts are coarse ranges.
"""

import os
import unittest
from datetime import date, timedelta
from types import SimpleNamespace

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.congress_signal import (
    compute_congress_aggregate,
    modifier_from_aggregate,
    signal_value,
)

TODAY = date(2026, 6, 11)


def tx(direction="buy", days_ago=5, amount_mid=8000.5, politician="Jane Doe"):
    return SimpleNamespace(
        direction=direction,
        transaction_date=TODAY - timedelta(days=days_ago),
        amount_mid=amount_mid,
        politician_name=politician,
    )


class AggregateTests(unittest.TestCase):
    def test_empty_input(self):
        agg = compute_congress_aggregate([], TODAY)
        self.assertEqual(agg.buy_count, 0)
        self.assertEqual(agg.sell_count, 0)
        self.assertIsNone(agg.net_value)
        self.assertFalse(agg.cluster_buy)

    def test_other_direction_excluded(self):
        agg = compute_congress_aggregate([tx(direction="other")], TODAY)
        self.assertEqual(agg.buy_count, 0)
        self.assertIsNone(agg.net_value)

    def test_outside_window_excluded(self):
        agg = compute_congress_aggregate([tx(days_ago=120)], TODAY)
        self.assertEqual(agg.buy_count, 0)

    def test_null_date_excluded(self):
        t = tx()
        t.transaction_date = None
        agg = compute_congress_aggregate([t], TODAY)
        self.assertEqual(agg.buy_count, 0)

    def test_net_value_buy_minus_sell(self):
        agg = compute_congress_aggregate(
            [tx(direction="buy", amount_mid=10_000.0),
             tx(direction="sell", amount_mid=4_000.0, politician="Bob Roe")],
            TODAY,
        )
        self.assertEqual(agg.net_value, 6_000.0)

    def test_null_amount_counts_but_adds_no_value(self):
        agg = compute_congress_aggregate(
            [tx(direction="buy", amount_mid=None),
             tx(direction="buy", amount_mid=10_000.0, politician="Bob Roe")],
            TODAY,
        )
        self.assertEqual(agg.buy_count, 2)
        self.assertEqual(agg.net_value, 10_000.0)

    def test_all_null_amounts_net_value_none(self):
        agg = compute_congress_aggregate(
            [tx(direction="buy", amount_mid=None)], TODAY
        )
        self.assertEqual(agg.buy_count, 1)
        self.assertIsNone(agg.net_value)

    def test_distinct_counts_dedupe_household_lines(self):
        # Self + Spouse rows share politician_name → one distinct buyer.
        agg = compute_congress_aggregate(
            [tx(politician="Jane Doe"), tx(politician="Jane Doe")], TODAY
        )
        self.assertEqual(agg.buy_count, 2)
        self.assertEqual(agg.distinct_buyers, 1)

    def test_cluster_two_politicians_within_30d(self):
        agg = compute_congress_aggregate(
            [tx(politician="Jane Doe", days_ago=10),
             tx(politician="Bob Roe", days_ago=20)],
            TODAY,
        )
        self.assertTrue(agg.cluster_buy)

    def test_no_cluster_same_politician(self):
        agg = compute_congress_aggregate(
            [tx(politician="Jane Doe", days_ago=10),
             tx(politician="Jane Doe", days_ago=20)],
            TODAY,
        )
        self.assertFalse(agg.cluster_buy)

    def test_no_cluster_when_buys_span_beyond_30d(self):
        agg = compute_congress_aggregate(
            [tx(politician="Jane Doe", days_ago=5),
             tx(politician="Bob Roe", days_ago=80)],
            TODAY,
        )
        self.assertFalse(agg.cluster_buy)


class ModifierTests(unittest.TestCase):
    def _agg(self, **kw):
        base = dict(buy_count=0, sell_count=0, distinct_buyers=0,
                    distinct_sellers=0, net_value=None, cluster_buy=False)
        base.update(kw)
        from backend.app.services.congress_signal import CongressAggregate
        return CongressAggregate(**base)

    def test_cluster_is_plus_3(self):
        self.assertEqual(modifier_from_aggregate(
            self._agg(buy_count=2, distinct_buyers=2, cluster_buy=True)), 3)

    def test_net_buying_is_plus_1(self):
        self.assertEqual(modifier_from_aggregate(
            self._agg(buy_count=1, distinct_buyers=1, net_value=10_000.0)), 1)

    def test_buying_with_unknown_net_is_plus_1(self):
        self.assertEqual(modifier_from_aggregate(
            self._agg(buy_count=1, distinct_buyers=1, net_value=None)), 1)

    def test_pronounced_selling_is_minus_2(self):
        self.assertEqual(modifier_from_aggregate(
            self._agg(sell_count=4, distinct_sellers=3,
                      net_value=-1_500_000.0)), -2)

    def test_mild_selling_is_zero(self):
        self.assertEqual(modifier_from_aggregate(
            self._agg(sell_count=1, distinct_sellers=1,
                      net_value=-50_000.0)), 0)

    def test_quiet_is_zero(self):
        self.assertEqual(modifier_from_aggregate(self._agg()), 0)


class SignalValueTests(unittest.TestCase):
    def test_payload_carries_aggregate_and_modifier(self):
        agg = compute_congress_aggregate(
            [tx(politician="Jane Doe", days_ago=10),
             tx(politician="Bob Roe", days_ago=20)],
            TODAY,
        )
        payload = signal_value(agg)
        self.assertEqual(payload["modifier"], 3)
        self.assertEqual(payload["buy_count"], 2)
        self.assertTrue(payload["cluster_buy"])
        self.assertEqual(payload["window_days"], 90)


if __name__ == "__main__":
    unittest.main()
