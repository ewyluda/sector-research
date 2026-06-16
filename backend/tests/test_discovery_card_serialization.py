"""Pins _card_to_dict serialization for insider, congress, and centrality snapshots.

Verifies that all three snapshot blocks are present in the serialized dict with
their full field sets — catching the class of bug where a new snapshot was added
to CompanySignalCard but its serialization block was never wired into _card_to_dict.
"""

import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.api.discovery import _card_to_dict
from backend.app.services.discovery import (
    CompanySignalCard,
    FMPSnapshot,
    XSignalSnapshot,
    InsiderSnapshot,
    CongressSnapshot,
    CentralitySnapshot,
)
def _make_card(**overrides) -> CompanySignalCard:
    """Build a minimal CompanySignalCard with default snapshots."""
    defaults = dict(
        ticker="AAPL",
        company_name="Apple Inc.",
        market_cap=3e12,
        sector="Technology",
        industry="Consumer Electronics",
        signal_source_badge="x+fmp",
        is_surprise=False,
        is_seed=True,
        combined_score=72.5,
        fundamental_quality_score=68.0,
        last_run_id=None,
        last_conviction_score=None,
        last_thesis_status=None,
        fmp=FMPSnapshot(
            roic=0.35,
            gross_margin=0.44,
            revenue_growth_yoy=0.06,
            pe_ratio=28.0,
            market_cap=3e12,
        ),
        x_signal=XSignalSnapshot(
            direction="accelerating",
            ratio=1.4,
            narrative_summary="strong momentum",
            discovery_score=80.0,
            is_stale=False,
        ),
        insider=InsiderSnapshot(),
        congress=CongressSnapshot(),
        centrality=CentralitySnapshot(),
        citations=[],
    )
    defaults.update(overrides)
    return CompanySignalCard(**defaults)


class TestCardToDict(unittest.TestCase):

    def test_insider_block_present(self):
        card = _make_card(
            insider=InsiderSnapshot(
                modifier=2,
                buy_count=5,
                sell_count=1,
                cluster_buy=True,
                net_value=250000.0,
                is_stale=False,
            )
        )
        result = _card_to_dict(card)
        self.assertIn("insider", result)
        ins = result["insider"]
        self.assertEqual(ins["modifier"], 2)
        self.assertEqual(ins["buy_count"], 5)
        self.assertEqual(ins["sell_count"], 1)
        self.assertTrue(ins["cluster_buy"])
        self.assertAlmostEqual(ins["net_value"], 250000.0)
        self.assertFalse(ins["is_stale"])

    def test_congress_block_present(self):
        card = _make_card(
            congress=CongressSnapshot(
                modifier=3,
                buy_count=4,
                sell_count=0,
                cluster_buy=True,
                net_value=500000.0,
                is_stale=False,
            )
        )
        result = _card_to_dict(card)
        self.assertIn("congress", result)
        cong = result["congress"]
        self.assertEqual(cong["modifier"], 3)
        self.assertEqual(cong["buy_count"], 4)
        self.assertEqual(cong["sell_count"], 0)
        self.assertTrue(cong["cluster_buy"])
        self.assertAlmostEqual(cong["net_value"], 500000.0)
        self.assertFalse(cong["is_stale"])

    def test_centrality_block_present(self):
        card = _make_card(
            centrality=CentralitySnapshot(
                modifier=1,
                betweenness=0.12,
                eigenvector=0.08,
                degree=7,
                is_hub=True,
                is_broker=False,
                is_stale=False,
            )
        )
        result = _card_to_dict(card)
        self.assertIn("centrality", result)
        cent = result["centrality"]
        self.assertEqual(cent["modifier"], 1)
        self.assertAlmostEqual(cent["betweenness"], 0.12)
        self.assertAlmostEqual(cent["eigenvector"], 0.08)
        self.assertEqual(cent["degree"], 7)
        self.assertTrue(cent["is_hub"])
        self.assertFalse(cent["is_broker"])
        self.assertFalse(cent["is_stale"])

    def test_all_three_snapshot_keys_present_with_defaults(self):
        """Regression: all three snapshot blocks always appear, even with defaults."""
        card = _make_card()
        result = _card_to_dict(card)
        for key in ("insider", "congress", "centrality"):
            self.assertIn(key, result, f"Missing snapshot key: {key}")

    def test_congress_default_fields(self):
        """Default CongressSnapshot produces zero/stale values in the dict."""
        card = _make_card()
        cong = _card_to_dict(card)["congress"]
        self.assertEqual(cong["modifier"], 0)
        self.assertEqual(cong["buy_count"], 0)
        self.assertEqual(cong["sell_count"], 0)
        self.assertFalse(cong["cluster_buy"])
        self.assertIsNone(cong["net_value"])
        self.assertTrue(cong["is_stale"])

    def test_every_card_field_reaches_the_wire(self):
        """Inversion guard: every CompanySignalCard dataclass field is present
        in the serialized dict. A newly-added field (scalar or nested snapshot)
        can no longer ship invisible — the regression that hid the congress and
        centrality chips. Nested snapshot fields are covered the same way by the
        per-snapshot tests above."""
        from dataclasses import fields as dc_fields

        result = _card_to_dict(_make_card())
        for f in dc_fields(CompanySignalCard):
            self.assertIn(f.name, result, f"card field dropped from wire: {f.name}")

    def test_nested_fmp_and_x_signal_serialize(self):
        """The fmp / x_signal snapshots round-trip through the generic
        serializer (not just the insider/congress/centrality blocks)."""
        result = _card_to_dict(_make_card())
        self.assertEqual(result["fmp"]["roic"], 0.35)
        self.assertEqual(result["x_signal"]["direction"], "accelerating")
        self.assertFalse(result["x_signal"]["is_stale"])


if __name__ == "__main__":
    unittest.main()
