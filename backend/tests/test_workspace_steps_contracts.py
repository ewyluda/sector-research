"""Contract tests for workspace steps:

- _parse_json_lenient must raise on malformed input (not silently return {})
  so the challenge step can't quietly default to a healthy verdict.
- KillCriterionWrite ordinals are 0-based and only `armed | triggered` are
  accepted (matching the existing /api/runs/{run_id}/kill-criteria contract
  and the array index used in ThesisCard).
"""
import unittest

from pydantic import ValidationError

from backend.app.models.workspace_schemas import KillCriterionWrite
from backend.app.services.workspace_steps import _parse_json_lenient


class TestParseJsonLenientFailsLoud(unittest.TestCase):
    def test_raises_on_malformed_json(self):
        with self.assertRaises(ValueError):
            _parse_json_lenient("not json at all")

    def test_raises_on_array_top_level(self):
        with self.assertRaises(ValueError):
            _parse_json_lenient("[1, 2, 3]")

    def test_strips_code_fence_and_parses(self):
        out = _parse_json_lenient('```json\n{"verdict": "healthy"}\n```')
        self.assertEqual(out, {"verdict": "healthy"})


class TestKillCriterionWriteContract(unittest.TestCase):
    def test_accepts_zero_ordinal(self):
        w = KillCriterionWrite(ordinal=0, status="armed")
        self.assertEqual(w.ordinal, 0)

    def test_rejects_resolved_status(self):
        with self.assertRaises(ValidationError):
            KillCriterionWrite(ordinal=0, status="resolved")

    def test_accepts_triggered(self):
        w = KillCriterionWrite(ordinal=2, status="triggered", note="margin compressed below 30%")
        self.assertEqual(w.status, "triggered")


if __name__ == "__main__":
    unittest.main()
