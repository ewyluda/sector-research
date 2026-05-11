"""Tests for backend.app.services.outcome_tracker."""
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal

from backend.app.services.outcome_tracker import (
    all_offset_keys,
    calendar_target,
)


class TestOffsetMath(unittest.TestCase):
    def test_calendar_target_known_offsets(self):
        base = date(2026, 1, 1)
        self.assertEqual(calendar_target(base, "1d"), date(2026, 1, 2))
        self.assertEqual(calendar_target(base, "1w"), date(2026, 1, 8))
        self.assertEqual(calendar_target(base, "1m"), date(2026, 1, 31))
        self.assertEqual(calendar_target(base, "3m"), date(2026, 4, 1))
        self.assertEqual(calendar_target(base, "6m"), date(2026, 6, 30))

    def test_calendar_target_unknown_raises(self):
        with self.assertRaises(ValueError):
            calendar_target(date(2026, 1, 1), "9999")

    def test_all_offset_keys_ordered(self):
        self.assertEqual(all_offset_keys(), ["1d", "1w", "1m", "3m", "6m"])


if __name__ == "__main__":
    unittest.main()
