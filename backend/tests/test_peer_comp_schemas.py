"""Pins the schema move (models/peer_comp.py) + backward compatibility:
old persisted DifferentiationOutput JSON (pre-widening, no new fields)
must still validate, and workspace_schemas must re-export the names."""

import unittest


class SchemaMoveTests(unittest.TestCase):
    def test_new_module_exports(self):
        from backend.app.models.peer_comp import (  # noqa: F401
            PeerCompRow,
            PeerCompTable,
            PeerError,
        )

    def test_workspace_schemas_reexports_same_classes(self):
        from backend.app.models import peer_comp, workspace_schemas

        self.assertIs(workspace_schemas.PeerCompRow, peer_comp.PeerCompRow)
        self.assertIs(workspace_schemas.PeerCompTable, peer_comp.PeerCompTable)
        self.assertIs(workspace_schemas.PeerError, peer_comp.PeerError)

    def test_old_persisted_differentiation_output_still_validates(self):
        """A step_outputs payload persisted before the widening (only the
        original 10 metric fields) must round-trip through the schema."""
        from backend.app.models.workspace_schemas import DifferentiationOutput

        old_row = {
            "ticker": "NVDA", "pe": 30.0, "ev_ebitda": 25.0, "p_b": 12.0,
            "p_fcf": 28.0, "p_s": 20.0, "roe": 0.5, "revenue_yoy": 0.6,
            "eps_yoy": 0.8, "gross_margin": None, "ebitda_margin": None,
        }
        old_payload = {
            "peer_comp": {
                "focus_ticker": "NVDA",
                "rows": [old_row],
                "median": {"ticker": "__median__"},
                "delta_vs_median_pct": {"ticker": "__delta__"},
            },
            "read_throughs": [],
            "per_peer_errors": [],
        }
        out = DifferentiationOutput.model_validate(old_payload)
        self.assertEqual(out.peer_comp.focus_ticker, "NVDA")
        # New fields default to None on old data
        self.assertIsNone(out.peer_comp.rows[0].peg)
        self.assertIsNone(out.peer_comp.rows[0].market_cap)

    def test_new_fields_accept_values(self):
        from backend.app.models.peer_comp import PeerCompRow

        row = PeerCompRow(
            ticker="NVDA", peg=1.2, operating_margin=0.35, fcf_margin=0.30,
            roic=0.4, roa=0.3, market_cap=2.5e12,
        )
        self.assertEqual(row.peg, 1.2)
        self.assertEqual(row.market_cap, 2.5e12)


if __name__ == "__main__":
    unittest.main()
