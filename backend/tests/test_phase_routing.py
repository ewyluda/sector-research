"""Pins single-source phase routing.

Guards against divergence between:
  - PHASE_SEQUENCE / next_phase() in graph/routing.py  (the canonical table)
  - PipelineService._next_phase() in services/pipeline.py

If any side drifts — e.g. a hardcoded string is reintroduced — at least one
assertion below will fail.
"""

import os
import types
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.graph.routing import PHASE_SEQUENCE, next_phase
from backend.app.services.pipeline import PipelineService


# ── Helpers ───────────────────────────────────────────────────────────────────

def _state_obj(phase: str, loop_context=None, loop_count: int = 0):
    """Build a minimal object with the attributes PipelineService._next_phase reads."""
    obj = types.SimpleNamespace(
        phase=phase,
        loop_context=loop_context,
        loop_count=loop_count,
    )
    return obj


class TestPhaseSequenceTable(unittest.TestCase):
    """PHASE_SEQUENCE covers the four linear successors."""

    def test_linear_successors_present(self):
        expected = {
            "quick_screen": "deep_dive",
            "deep_dive": "targeted_followup",
            "targeted_followup": "thesis_construction",
            "thesis_construction": "risk_stress_test",
        }
        self.assertEqual(PHASE_SEQUENCE, expected)

    def test_risk_not_in_table(self):
        # risk_stress_test has branching logic — must NOT be a simple table entry
        self.assertNotIn("risk_stress_test", PHASE_SEQUENCE)


class TestNextPhase(unittest.TestCase):
    """next_phase() — the single source of routing truth."""

    def test_linear_phases(self):
        for phase, expected in PHASE_SEQUENCE.items():
            with self.subTest(phase=phase):
                result = next_phase(phase, loop_context=None, loop_count=0)
                self.assertEqual(result, expected)

    def test_risk_loop_back_truthy_context_count_0(self):
        result = next_phase("risk_stress_test", loop_context={"reason": "x"}, loop_count=0)
        self.assertEqual(result, "deep_dive")

    def test_risk_loop_back_truthy_context_count_2(self):
        result = next_phase("risk_stress_test", loop_context={"reason": "x"}, loop_count=2)
        self.assertEqual(result, "deep_dive")

    def test_risk_completed_count_3(self):
        result = next_phase("risk_stress_test", loop_context={"reason": "x"}, loop_count=3)
        self.assertEqual(result, "completed")

    def test_risk_completed_no_loop_context(self):
        result = next_phase("risk_stress_test", loop_context=None, loop_count=0)
        self.assertEqual(result, "completed")

    def test_unknown_phase_returns_completed(self):
        result = next_phase("nonexistent_phase", loop_context=None, loop_count=0)
        self.assertEqual(result, "completed")


class TestPipelineServiceNextPhase(unittest.TestCase):
    """PipelineService._next_phase must agree with next_phase() on every input."""

    def _call(self, phase: str, loop_context=None, loop_count: int = 0) -> str:
        state = _state_obj(phase, loop_context=loop_context, loop_count=loop_count)
        # Call unbound — _next_phase only uses `state`, not `self`
        dummy_self = object.__new__(PipelineService)
        return PipelineService._next_phase(dummy_self, state)

    def test_linear_phases_parity(self):
        for phase in PHASE_SEQUENCE:
            with self.subTest(phase=phase):
                svc_result = self._call(phase)
                fn_result = next_phase(phase, loop_context=None, loop_count=0)
                self.assertEqual(svc_result, fn_result)

    def test_risk_loop_back_parity(self):
        ctx = {"reason": "needs_recheck"}
        for count in (0, 1, 2):
            with self.subTest(loop_count=count):
                self.assertEqual(
                    self._call("risk_stress_test", loop_context=ctx, loop_count=count),
                    next_phase("risk_stress_test", loop_context=ctx, loop_count=count),
                )

    def test_risk_completed_parity(self):
        # loop_count > 2
        self.assertEqual(
            self._call("risk_stress_test", loop_context={"reason": "x"}, loop_count=3),
            next_phase("risk_stress_test", loop_context={"reason": "x"}, loop_count=3),
        )
        # no loop_context
        self.assertEqual(
            self._call("risk_stress_test", loop_context=None, loop_count=0),
            next_phase("risk_stress_test", loop_context=None, loop_count=0),
        )

    def test_unknown_phase_parity(self):
        self.assertEqual(
            self._call("unknown_phase"),
            next_phase("unknown_phase", loop_context=None, loop_count=0),
        )


if __name__ == "__main__":
    unittest.main()
