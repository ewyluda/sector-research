"""Tests for forecast→historical period promotion in step_update_refresh.

The bug: _patch_statement skipped any FMP period not already in
historical_labels, which is exactly the case for a newly reported quarter
(it's still in the model's forecast set when refresh starts). The fix
introduces _promote_forecast_periods which ages those periods into
historical so the patch lands.
"""
import unittest

from backend.app.models.model_state import ModelCell, Period
from backend.app.services.workspace_steps import (
    _patch_statement,
    _promote_forecast_periods,
)


class _StateStub:
    """Minimal stand-in for ModelState; only the bits the helpers touch."""

    def __init__(self, periods, drivers):
        self.periods = periods
        self.drivers = drivers


class TestPromoteForecastPeriods(unittest.TestCase):
    def test_promotes_forecast_period_in_fmp_set(self):
        periods = [
            Period(label="2025Q4", kind="Q", is_historical=True, quarter_index=4),
            Period(label="2026Q1", kind="Q", is_historical=False, quarter_index=1),
        ]
        drivers = {"2026Q1": {"revenue_growth_pct": ModelCell(value=0.1, source="driver")}}
        state = _StateStub(periods, drivers)

        promoted = _promote_forecast_periods(state, {"2026Q1"})

        self.assertEqual(promoted, {"2026Q1"})
        self.assertTrue(periods[1].is_historical)
        self.assertNotIn("2026Q1", state.drivers)

    def test_does_not_touch_already_historical_period(self):
        periods = [
            Period(label="2025Q4", kind="Q", is_historical=True, quarter_index=4),
        ]
        state = _StateStub(periods, {})

        promoted = _promote_forecast_periods(state, {"2025Q4"})

        self.assertEqual(promoted, set())
        self.assertTrue(periods[0].is_historical)

    def test_does_not_promote_forecast_period_not_in_fmp_set(self):
        periods = [
            Period(label="2026Q2", kind="Q", is_historical=False, quarter_index=2),
        ]
        state = _StateStub(periods, {"2026Q2": {}})

        promoted = _promote_forecast_periods(state, {"2026Q1"})

        self.assertEqual(promoted, set())
        self.assertFalse(periods[0].is_historical)
        self.assertIn("2026Q2", state.drivers)


class TestPatchStatementPromoted(unittest.TestCase):
    def test_overwrites_computed_cell_in_promoted_period(self):
        """Promoted periods must allow overwriting non-historical cells.

        Pre-fix _patch_statement gated on `existing.source == 'historical'`,
        which rejected the computed/driver cells that fill a forecast
        quarter — so even after promotion the actuals would not land.
        """
        statement = {
            "revenue": {
                "2026Q1": ModelCell(value=900.0, source="computed"),
            },
        }
        rows = [{"period": "Q1", "calendarYear": "2026", "revenue": 1000.0}]
        field_map = {"revenue": "revenue"}

        _patch_statement(
            statement,
            rows,
            field_map,
            citation_id="cit-1",
            historical_labels=set(),
            promoted_labels={"2026Q1"},
        )

        self.assertEqual(statement["revenue"]["2026Q1"].value, 1000.0)
        self.assertEqual(statement["revenue"]["2026Q1"].source, "historical")

    def test_skips_non_promoted_forecast_period(self):
        statement = {
            "revenue": {"2026Q2": ModelCell(value=900.0, source="computed")},
        }
        rows = [{"period": "Q2", "calendarYear": "2026", "revenue": 1000.0}]
        field_map = {"revenue": "revenue"}

        _patch_statement(
            statement,
            rows,
            field_map,
            citation_id="cit-1",
            historical_labels=set(),
            promoted_labels=set(),
        )

        # Untouched: still a forecast computed cell.
        self.assertEqual(statement["revenue"]["2026Q2"].value, 900.0)
        self.assertEqual(statement["revenue"]["2026Q2"].source, "computed")

    def test_preserves_non_historical_cell_in_already_historical_period(self):
        """When a period was historical from the start, only refresh cells
        whose source is also historical — leave overrides alone."""
        statement = {
            "revenue": {"2025Q4": ModelCell(value=900.0, source="override")},
        }
        rows = [{"period": "Q4", "calendarYear": "2025", "revenue": 1000.0}]
        field_map = {"revenue": "revenue"}

        _patch_statement(
            statement,
            rows,
            field_map,
            citation_id="cit-1",
            historical_labels={"2025Q4"},
            promoted_labels=set(),
        )

        self.assertEqual(statement["revenue"]["2025Q4"].value, 900.0)
        self.assertEqual(statement["revenue"]["2025Q4"].source, "override")


if __name__ == "__main__":
    unittest.main()
