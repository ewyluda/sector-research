"""Regression tests for the AI-baseline driver-key vocabulary pin.

Pre-fix, the Sonnet baseline node accepted any driver key the LLM emitted, so a
response like {"drivers": {"2029Y": {"gross_margin": 0.73, "ebit_margin": 0.55}}}
parsed successfully — but `model_balancing.recompute()` reads canonical names
like "gross_margin_pct", so the forecast cells stayed empty and the entire
financial model rendered as em-dashes.

The fix pins BaselineDriversResponse to DRIVER_KEYS via a Pydantic model with
extra="forbid". Non-canonical keys now raise ValidationError at parse time."""
from __future__ import annotations

import json
import unittest

from pydantic import ValidationError

from backend.app.graph.model_baseline_node import BaselineDriversResponse
from backend.app.models.model_state import DRIVER_KEYS


class TestBaselineDriversResponseSchema(unittest.TestCase):
    def test_accepts_canonical_keys(self):
        """Sanity: a response using only DRIVER_KEYS parses cleanly."""
        payload = {
            "drivers": {
                "2029Y": {
                    "revenue_growth_pct": {"value": 0.10, "reason": "consensus", "source_citation_id": None},
                    "gross_margin_pct": {"value": 0.73, "reason": "stable mix", "source_citation_id": None},
                    "sga_pct_revenue": {"value": 0.08, "reason": "scale", "source_citation_id": None},
                }
            }
        }
        parsed = BaselineDriversResponse.model_validate_json(json.dumps(payload))
        # Canonical keys round-trip
        self.assertEqual(parsed.drivers["2029Y"].revenue_growth_pct.value, 0.10)
        self.assertEqual(parsed.drivers["2029Y"].gross_margin_pct.value, 0.73)
        # Unspecified canonical keys default to None
        self.assertIsNone(parsed.drivers["2029Y"].capex_pct_revenue)

    def test_rejects_unknown_driver_key(self):
        """The actual failure mode observed in production: LLM emits
        `gross_margin` instead of `gross_margin_pct`. Must fail loudly."""
        payload = {
            "drivers": {
                "2029Y": {
                    "gross_margin": {"value": 0.73, "reason": "x", "source_citation_id": None},
                }
            }
        }
        with self.assertRaises(ValidationError) as cm:
            BaselineDriversResponse.model_validate_json(json.dumps(payload))
        # The error mentions the extra/forbidden field
        self.assertIn("gross_margin", str(cm.exception))

    def test_rejects_ebit_margin_observed_alias(self):
        """`ebit_margin` was the second-most-frequent invented key. Pin it."""
        payload = {
            "drivers": {
                "2029Y": {
                    "ebit_margin": {"value": 0.55, "reason": "x", "source_citation_id": None},
                }
            }
        }
        with self.assertRaises(ValidationError):
            BaselineDriversResponse.model_validate_json(json.dumps(payload))

    def test_rejects_tax_rate_observed_alias(self):
        """LLM emitted `tax_rate`; canonical name is `effective_tax_rate`."""
        payload = {
            "drivers": {
                "2029Y": {
                    "tax_rate": {"value": 0.13, "reason": "x", "source_citation_id": None},
                }
            }
        }
        with self.assertRaises(ValidationError):
            BaselineDriversResponse.model_validate_json(json.dumps(payload))

    def test_glosses_cover_every_driver_key(self):
        """The system prompt enumerates each canonical key with a one-line gloss.
        If a future PR adds to DRIVER_KEYS without updating the glosses, the
        module-level assertion fires at import — re-assert here so a unit run
        catches it too."""
        from backend.app.graph.model_baseline_node import _DRIVER_GLOSSES
        self.assertEqual(set(_DRIVER_GLOSSES.keys()), set(DRIVER_KEYS))


if __name__ == "__main__":
    unittest.main()
