"""Pins the pure near-duplicate grouping helper: same (ticker, event_type)
within GROUP_WINDOW_DAYS collapse into one group; primary = newest member;
groups sorted newest-first."""

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

from backend.app.services.material_events_grouping import (
    GROUP_WINDOW_DAYS,
    group_events,
)


def ev(id="e1", ticker="APLD", etype="financing", day=8, headline="h"):
    return SimpleNamespace(
        id=id, ticker=ticker, event_type=etype,
        filing_date=date(2026, 6, day), headline=headline,
    )


class GroupEventsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(group_events([]), [])

    def test_groups_same_ticker_type_within_4_days(self):
        # two APLD financing events 2 days apart → one group, count=2,
        # primary = newest, member_ids contains both
        groups = group_events([
            ev(id="old", day=6, headline="older"),
            ev(id="new", day=8, headline="newer"),
        ])
        self.assertEqual(len(groups), 1)
        g = groups[0]
        self.assertEqual(g["count"], 2)
        self.assertEqual(g["primary"].id, "new")
        self.assertEqual(set(g["member_ids"]), {"new", "old"})
        self.assertEqual(g["headlines"], ["newer", "older"])

    def test_does_not_group_across_type_or_window(self):
        # APLD financing + APLD guidance → two groups
        groups = group_events([ev(etype="financing"), ev(id="e2", etype="guidance")])
        self.assertEqual(len(groups), 2)
        # two financing events 6 days apart → two groups
        groups = group_events([ev(day=2), ev(id="e2", day=8)])
        self.assertEqual(len(groups), 2)

    def test_does_not_group_across_tickers(self):
        groups = group_events([ev(ticker="APLD"), ev(id="e2", ticker="NVDA")])
        self.assertEqual(len(groups), 2)

    def test_window_anchors_on_newest_member(self):
        # days 8, 5, 4: 4 is within 4d of 8 (the anchor) so all three group;
        # window measured from the newest member, not pairwise.
        groups = group_events([ev(id="a", day=8), ev(id="b", day=5), ev(id="c", day=4)])
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["count"], 3)

    def test_groups_sorted_newest_first(self):
        groups = group_events([
            ev(id="old", ticker="NVDA", day=1),
            ev(id="new", ticker="APLD", day=9),
        ])
        self.assertEqual([g["primary"].id for g in groups], ["new", "old"])

    def test_window_constant(self):
        self.assertEqual(GROUP_WINDOW_DAYS, 4)


if __name__ == "__main__":
    unittest.main()
