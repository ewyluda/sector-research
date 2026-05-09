import assert from "node:assert/strict";
import test from "node:test";

import { assumptionPath, driverPath, statementPath, toWire } from "./cellPath.ts";

test("driverPath wire format", () => {
  assert.equal(
    toWire(driverPath("2026Y", "gross_margin_pct")),
    "drivers.2026Y.gross_margin_pct",
  );
});

test("statementPath wire format", () => {
  assert.equal(
    toWire(statementPath("income_statement", "revenue", "2026Q1")),
    "income_statement.revenue.2026Q1",
  );
  assert.equal(
    toWire(statementPath("balance_sheet", "long_term_debt", "2024Q4")),
    "balance_sheet.long_term_debt.2024Q4",
  );
  assert.equal(
    toWire(statementPath("cash_flow", "free_cash_flow", "2026Y")),
    "cash_flow.free_cash_flow.2026Y",
  );
});

test("assumptionPath wire format", () => {
  assert.equal(toWire(assumptionPath("discount_rate")), "assumptions.discount_rate");
});
