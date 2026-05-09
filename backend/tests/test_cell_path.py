"""Pins the wire format for cell_path strings + round-trip property.

If you change the wire format, the frontend (frontend/lib/cellPath.ts) must
change in lockstep — that contract is what this test guards.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.models.cell_path import (
    AssumptionPath,
    DriverPath,
    Statement,
    StatementCellPath,
    parse,
)


class WireFormatTests(unittest.TestCase):
    def test_driver_to_str(self):
        self.assertEqual(
            str(DriverPath("2026Y", "gross_margin_pct")),
            "drivers.2026Y.gross_margin_pct",
        )

    def test_statement_cell_to_str(self):
        self.assertEqual(
            str(StatementCellPath(Statement.INCOME, "revenue", "2026Q1")),
            "income_statement.revenue.2026Q1",
        )

    def test_assumption_to_str(self):
        self.assertEqual(str(AssumptionPath("discount_rate")), "assumptions.discount_rate")


class ParseTests(unittest.TestCase):
    def test_driver(self):
        p = parse("drivers.2026Y.gross_margin_pct")
        self.assertEqual(p, DriverPath("2026Y", "gross_margin_pct"))

    def test_statement_cell(self):
        p = parse("balance_sheet.cash_and_equivalents.2024Q1")
        self.assertEqual(
            p, StatementCellPath(Statement.BALANCE, "cash_and_equivalents", "2024Q1")
        )

    def test_assumption(self):
        self.assertEqual(parse("assumptions.tax_rate"), AssumptionPath("tax_rate"))

    def test_unknown_shape(self):
        with self.assertRaises(ValueError):
            parse("nonsense")
        with self.assertRaises(ValueError):
            parse("drivers.too.many.parts")
        with self.assertRaises(ValueError):
            parse("assumptions")

    def test_unknown_driver_key(self):
        with self.assertRaises(ValueError):
            parse("drivers.2026Y.not_a_real_driver")

    def test_unknown_line_item(self):
        with self.assertRaises(ValueError):
            parse("income_statement.not_a_line.2026Q1")

    def test_unknown_assumption_key(self):
        # terminal_method is a non-cell assumption — not editable via this path
        with self.assertRaises(ValueError):
            parse("assumptions.terminal_method")
        with self.assertRaises(ValueError):
            parse("assumptions.plug_priority")

    def test_invalid_period(self):
        with self.assertRaises(ValueError):
            parse("drivers.2026Q5.gross_margin_pct")
        with self.assertRaises(ValueError):
            parse("drivers.20XX.gross_margin_pct")


class RoundTripTests(unittest.TestCase):
    def test_round_trip(self):
        cases = [
            "drivers.2026Y.gross_margin_pct",
            "drivers.2024Q1.revenue_growth_pct",
            "income_statement.revenue.2026Q1",
            "balance_sheet.long_term_debt.2024Q4",
            "cash_flow.free_cash_flow.2026Y",
            "assumptions.discount_rate",
            "assumptions.terminal_multiple",
            "assumptions.perpetuity_growth",
            "assumptions.tax_rate",
        ]
        for s in cases:
            with self.subTest(s=s):
                self.assertEqual(str(parse(s)), s)


if __name__ == "__main__":
    unittest.main()
