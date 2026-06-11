"""Pin discovery combined-score weighting, stale collapse, and all-missing behavior.

Tests target compute_combined_score (and its dependencies compute_fundamental_quality_score
and compute_velocity_score) in backend/app/services/discovery.py.

Behaviors being pinned:
  1. Fresh X → 40% velocity + 40% fundamental + 20% discovery
  2. Missing X signal → 80% fundamental + 20% discovery (collapsed weights)
  3. Stale X signal → same 80/20 collapse (caller passes has_x_signal=False)
  4. All-missing (no fundamentals, no X) → 0.0 (characterization: zero fundamental score)
  5. Custom theme signal_weights override honored
"""
import unittest

from backend.app.services.discovery import (
    compute_combined_score,
    compute_fundamental_quality_score,
    compute_velocity_score,
)
from backend.app.clients.x_client import STALE_THRESHOLD_HOURS


# ── Sanity-check the STALE_THRESHOLD_HOURS constant itself ───────────────────

class TestStaleThresholdConstant(unittest.TestCase):
    def test_stale_threshold_is_36_hours(self):
        """Staleness boundary is documented as 36 h; pin it so a config change is
        caught by tests before anything in production silently shifts."""
        self.assertEqual(STALE_THRESHOLD_HOURS, 36)


# ── compute_fundamental_quality_score ────────────────────────────────────────

class TestFundamentalQualityScore(unittest.TestCase):
    """Score decomposition: ROIC (40 pts), Gross Margin (30 pts), Revenue Growth (30 pts)."""

    def test_maximum_score_all_top_tier(self):
        # roic > 20% → 40, gross_margin > 60% → 30, revenue_growth > 30% → 30 = 100
        score = compute_fundamental_quality_score(
            roic=0.25, gross_margin=0.65, revenue_growth=0.35, pe_ratio=None
        )
        self.assertEqual(score, 100.0)

    def test_zero_score_all_none(self):
        score = compute_fundamental_quality_score(
            roic=None, gross_margin=None, revenue_growth=None, pe_ratio=None
        )
        self.assertEqual(score, 0.0)

    def test_partial_score_roic_only(self):
        # roic > 10% → 24; others None → 24
        score = compute_fundamental_quality_score(
            roic=0.12, gross_margin=None, revenue_growth=None, pe_ratio=None
        )
        self.assertEqual(score, 24.0)

    def test_pe_ratio_not_used(self):
        # pe_ratio is accepted but never contributes to score (no rubric for it)
        score_with_pe = compute_fundamental_quality_score(
            roic=0.25, gross_margin=0.65, revenue_growth=0.35, pe_ratio=15.0
        )
        score_without_pe = compute_fundamental_quality_score(
            roic=0.25, gross_margin=0.65, revenue_growth=0.35, pe_ratio=None
        )
        self.assertEqual(score_with_pe, score_without_pe)

    def test_roic_tiers(self):
        self.assertEqual(
            compute_fundamental_quality_score(roic=0.21, gross_margin=None, revenue_growth=None, pe_ratio=None), 40.0
        )
        self.assertEqual(
            compute_fundamental_quality_score(roic=0.16, gross_margin=None, revenue_growth=None, pe_ratio=None), 32.0
        )
        self.assertEqual(
            compute_fundamental_quality_score(roic=0.11, gross_margin=None, revenue_growth=None, pe_ratio=None), 24.0
        )
        self.assertEqual(
            compute_fundamental_quality_score(roic=0.06, gross_margin=None, revenue_growth=None, pe_ratio=None), 16.0
        )
        self.assertEqual(
            compute_fundamental_quality_score(roic=0.04, gross_margin=None, revenue_growth=None, pe_ratio=None), 0.0
        )


# ── compute_velocity_score ───────────────────────────────────────────────────

class TestVelocityScore(unittest.TestCase):
    def test_unknown_direction_yields_zero(self):
        self.assertEqual(compute_velocity_score("unknown", None), 0.0)

    def test_stable_yields_50(self):
        self.assertEqual(compute_velocity_score("stable", None), 50.0)

    def test_accelerating_baseline_ratio_none(self):
        # 60 + 1.0 * 10 = 70
        self.assertEqual(compute_velocity_score("accelerating", None), 70.0)

    def test_accelerating_capped_at_100(self):
        # 60 + 4.0 * 10 = 100 (not 100.0+)
        score = compute_velocity_score("accelerating", 4.0)
        self.assertEqual(score, 100.0)

    def test_decelerating_below_50(self):
        # ratio 0.5 → 50 - abs(1.0 - 0.5) * 20 = 50 - 10 = 40
        self.assertEqual(compute_velocity_score("decelerating", 0.5), 40.0)

    def test_decelerating_floor_zero(self):
        score = compute_velocity_score("decelerating", -10.0)
        self.assertEqual(score, 0.0)


# ── compute_combined_score — fresh X (40/40/20) ──────────────────────────────

class TestCombinedScoreFreshX(unittest.TestCase):
    """When has_x_signal=True: velocity*0.4 + fundamental*0.4 + disc_norm*0.2."""

    def test_exact_weights_fresh_x(self):
        # Hand-computable example:
        # fundamental_score = 80.0
        # velocity: direction=stable → compute_velocity_score = 50.0
        # discovery_score = 0.05 → disc_normalized = min(0.05 * 1000, 100) = 50.0
        # combined = 50.0*0.4 + 80.0*0.4 + 50.0*0.2 = 20 + 32 + 10 = 62.0
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        score = compute_combined_score(
            fundamental_score=80.0,
            velocity_direction="stable",
            velocity_ratio=None,
            discovery_score=0.05,
            weights=weights,
            has_x_signal=True,
        )
        self.assertEqual(score, 62.0)

    def test_fresh_x_accelerating(self):
        # velocity_score = 70.0 (accelerating, ratio=None)
        # fundamental = 40.0, disc_normalized = 0.0 (discovery_score=0)
        # combined = 70*0.4 + 40*0.4 + 0*0.2 = 28 + 16 + 0 = 44.0
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        score = compute_combined_score(
            fundamental_score=40.0,
            velocity_direction="accelerating",
            velocity_ratio=None,
            discovery_score=0.0,
            weights=weights,
            has_x_signal=True,
        )
        self.assertEqual(score, 44.0)

    def test_disc_normalized_caps_at_100(self):
        # discovery_score = 0.2 → disc_normalized = min(200, 100) = 100
        # combined = 50*0.4 + 50*0.4 + 100*0.2 = 20 + 20 + 20 = 60.0
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        score = compute_combined_score(
            fundamental_score=50.0,
            velocity_direction="stable",
            velocity_ratio=None,
            discovery_score=0.2,
            weights=weights,
            has_x_signal=True,
        )
        self.assertEqual(score, 60.0)


# ── compute_combined_score — missing X (80/20 collapse) ─────────────────────

class TestCombinedScoreMissingX(unittest.TestCase):
    """When has_x_signal=False: fundamental*0.80 + discovery_score*100*0.20."""

    def test_exact_80_20_collapse(self):
        # fundamental = 60.0, discovery_score = 0.05
        # combined = 60.0*0.8 + 0.05*100*0.2 = 48.0 + 1.0 = 49.0
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        score = compute_combined_score(
            fundamental_score=60.0,
            velocity_direction="unknown",
            velocity_ratio=None,
            discovery_score=0.05,
            weights=weights,
            has_x_signal=False,
        )
        self.assertEqual(score, 49.0)

    def test_velocity_direction_ignored_when_no_x(self):
        # Even if direction looks like good signal, it should be ignored
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        score_acc = compute_combined_score(
            fundamental_score=60.0,
            velocity_direction="accelerating",
            velocity_ratio=2.0,
            discovery_score=0.0,
            weights=weights,
            has_x_signal=False,
        )
        score_unk = compute_combined_score(
            fundamental_score=60.0,
            velocity_direction="unknown",
            velocity_ratio=None,
            discovery_score=0.0,
            weights=weights,
            has_x_signal=False,
        )
        # Both must ignore velocity and produce identical scores
        self.assertEqual(score_acc, score_unk)
        # Expected: 60*0.8 + 0*0.2 = 48.0
        self.assertEqual(score_acc, 48.0)

    def test_missing_x_zero_discovery(self):
        # fundamental=100, discovery_score=0 → 100*0.8 + 0 = 80.0
        score = compute_combined_score(
            fundamental_score=100.0,
            velocity_direction="unknown",
            velocity_ratio=None,
            discovery_score=0.0,
            weights={},
            has_x_signal=False,
        )
        self.assertEqual(score, 80.0)


# ── Stale X → same 80/20 collapse ───────────────────────────────────────────

class TestCombinedScoreStaleX(unittest.TestCase):
    """Stale X is treated identically to missing X at compute_combined_score level.

    In _merge_results (line ~531 of discovery.py) the call is:
        has_x_signal = has_x_signal and not is_stale
    so a stale signal reaches compute_combined_score with has_x_signal=False.
    These tests pin that the function itself produces the same result either way.
    """

    def test_stale_treated_as_no_x_by_caller(self):
        # Pin: when caller passes has_x_signal=False (stale path), score uses 80/20
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        # Explicitly simulating what _merge_results does for a stale signal:
        is_stale = True
        has_velocity_data = True
        has_x_for_scoring = has_velocity_data and not is_stale  # False
        score = compute_combined_score(
            fundamental_score=70.0,
            velocity_direction="accelerating",
            velocity_ratio=1.5,
            discovery_score=0.0,
            weights=weights,
            has_x_signal=has_x_for_scoring,
        )
        # Expected: 70*0.8 + 0 = 56.0
        self.assertEqual(score, 56.0)

    def test_stale_vs_missing_produce_same_score(self):
        # Any velocity data on a stale signal must produce same score as no signal
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        score_stale = compute_combined_score(
            fundamental_score=50.0,
            velocity_direction="accelerating",
            velocity_ratio=3.0,
            discovery_score=0.0,
            weights=weights,
            has_x_signal=False,  # stale → False
        )
        score_missing = compute_combined_score(
            fundamental_score=50.0,
            velocity_direction="unknown",
            velocity_ratio=None,
            discovery_score=0.0,
            weights=weights,
            has_x_signal=False,
        )
        self.assertEqual(score_stale, score_missing)


# ── All-missing (no fundamentals, no X) ─────────────────────────────────────

class TestCombinedScoreAllMissing(unittest.TestCase):
    """Characterization: what does the code actually do when everything is absent.

    fundamental_quality_score with all-None inputs returns 0.0 (no rubric matches).
    With has_x_signal=False: combined = 0.0 * 0.80 + 0.0 * 0.20 = 0.0.
    Not a designed "minimum floor" — it is literally zero.
    """

    def test_all_none_fundamentals_score_is_zero(self):
        fund = compute_fundamental_quality_score(
            roic=None, gross_margin=None, revenue_growth=None, pe_ratio=None
        )
        self.assertEqual(fund, 0.0)

    def test_combined_all_missing_is_zero(self):
        # discovery_score=0, has_x_signal=False, fundamental_score=0
        # combined = 0*0.8 + 0*100*0.2 = 0.0
        score = compute_combined_score(
            fundamental_score=0.0,
            velocity_direction="unknown",
            velocity_ratio=None,
            discovery_score=0.0,
            weights={},
            has_x_signal=False,
        )
        self.assertEqual(score, 0.0)

    def test_all_missing_with_fresh_x_still_zero_no_velocity(self):
        # Even with has_x_signal=True, if velocity direction is "unknown"
        # (which computes to 0) and fundamentals + discovery are 0, result is 0.
        # Characterization: unknown direction contributes 0 to velocity score.
        weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        score = compute_combined_score(
            fundamental_score=0.0,
            velocity_direction="unknown",
            velocity_ratio=None,
            discovery_score=0.0,
            weights=weights,
            has_x_signal=True,
        )
        self.assertEqual(score, 0.0)


# ── Custom signal_weights override ───────────────────────────────────────────

class TestCombinedScoreCustomWeights(unittest.TestCase):
    """theme.signal_weights can override the default 40/40/20 split."""

    def test_custom_weights_honored(self):
        # Override: velocity=0.6, fundamental=0.3, discovery=0.1
        # velocity_score(stable) = 50, fundamental=80, disc_normalized=50 (disc=0.05)
        # combined = 50*0.6 + 80*0.3 + 50*0.1 = 30 + 24 + 5 = 59.0
        weights = {"x_velocity": 0.60, "fundamental_quality": 0.30, "discovery": 0.10}
        score = compute_combined_score(
            fundamental_score=80.0,
            velocity_direction="stable",
            velocity_ratio=None,
            discovery_score=0.05,
            weights=weights,
            has_x_signal=True,
        )
        self.assertEqual(score, 59.0)

    def test_custom_weights_differ_from_default(self):
        # Same inputs, different weights → different score
        default_weights = {"x_velocity": 0.40, "fundamental_quality": 0.40, "discovery": 0.20}
        custom_weights = {"x_velocity": 0.60, "fundamental_quality": 0.30, "discovery": 0.10}

        default_score = compute_combined_score(
            fundamental_score=80.0,
            velocity_direction="stable",
            velocity_ratio=None,
            discovery_score=0.05,
            weights=default_weights,
            has_x_signal=True,
        )
        custom_score = compute_combined_score(
            fundamental_score=80.0,
            velocity_direction="stable",
            velocity_ratio=None,
            discovery_score=0.05,
            weights=custom_weights,
            has_x_signal=True,
        )
        self.assertNotEqual(default_score, custom_score)

    def test_missing_weight_key_falls_back_to_default(self):
        # If a weight key is absent, .get() returns the default value (0.40, 0.40, 0.20)
        # Passing empty dict should use defaults for all three weights
        # velocity=stable(50), fundamental=50, disc=0
        # combined = 50*0.4 + 50*0.4 + 0*0.2 = 20 + 20 + 0 = 40.0
        score = compute_combined_score(
            fundamental_score=50.0,
            velocity_direction="stable",
            velocity_ratio=None,
            discovery_score=0.0,
            weights={},   # empty → all defaults
            has_x_signal=True,
        )
        self.assertEqual(score, 40.0)


if __name__ == "__main__":
    unittest.main()
