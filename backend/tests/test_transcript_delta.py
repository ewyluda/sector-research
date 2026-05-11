"""Tests for backend.app.services.transcript_delta."""
from __future__ import annotations

import unittest


class TestFingerprint(unittest.TestCase):
    def test_fingerprint_is_deterministic(self):
        from backend.app.services.transcript_delta import compute_fingerprint
        window_a = [{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}]
        window_b = [{"year": 2025, "quarter": 3}, {"year": 2025, "quarter": 4}]
        # Order independent
        self.assertEqual(compute_fingerprint(window_a), compute_fingerprint(window_b))

    def test_fingerprint_differs_on_new_quarter(self):
        from backend.app.services.transcript_delta import compute_fingerprint
        a = [{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}]
        b = [{"year": 2026, "quarter": 1}, {"year": 2025, "quarter": 4}]
        self.assertNotEqual(compute_fingerprint(a), compute_fingerprint(b))


if __name__ == "__main__":
    unittest.main()
