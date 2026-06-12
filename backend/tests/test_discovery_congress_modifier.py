"""Pins apply_congress_modifier: same bounded-adjustment semantics as
apply_insider_modifier (48h staleness gate, [0,100] clamp, absent/garbage
data → unchanged) over the signal_type='congress' cache."""

import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.discovery import apply_congress_modifier

NOW = datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)
FRESH = (NOW - timedelta(hours=6)).isoformat()
STALE = (NOW - timedelta(hours=72)).isoformat()


class ApplyCongressModifierTests(unittest.TestCase):
    def test_fresh_positive_modifier_applied(self):
        score, mod = apply_congress_modifier(60.0, {"modifier": 3, "computed_at": FRESH}, NOW)
        self.assertEqual(score, 63.0)
        self.assertEqual(mod, 3)

    def test_stale_signal_ignored(self):
        score, mod = apply_congress_modifier(60.0, {"modifier": 3, "computed_at": STALE}, NOW)
        self.assertEqual(score, 60.0)
        self.assertEqual(mod, 0)

    def test_absent_data_unchanged(self):
        self.assertEqual(apply_congress_modifier(60.0, {}, NOW), (60.0, 0))

    def test_clamped_at_100(self):
        score, _ = apply_congress_modifier(99.0, {"modifier": 3, "computed_at": FRESH}, NOW)
        self.assertEqual(score, 100.0)

    def test_clamped_at_0(self):
        score, _ = apply_congress_modifier(1.0, {"modifier": -2, "computed_at": FRESH}, NOW)
        self.assertEqual(score, 0.0)

    def test_garbage_computed_at_ignored(self):
        score, mod = apply_congress_modifier(60.0, {"modifier": 3, "computed_at": "garbage"}, NOW)
        self.assertEqual((score, mod), (60.0, 0))


if __name__ == "__main__":
    unittest.main()
