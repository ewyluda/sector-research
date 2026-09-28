import assert from "node:assert/strict";
import test from "node:test";

import { formatModelValue } from "./modelFormat.ts";

test("rates render as percentages", () => {
  assert.equal(formatModelValue("revenue_growth_pct", 0.9), "90.0%");
  assert.equal(formatModelValue("sga_pct_revenue", 0.0234), "2.3%");
  assert.equal(formatModelValue("effective_tax_rate", 0.15), "15.0%");
  assert.equal(formatModelValue("dividend_payout_ratio", 0.01), "1.0%");
});

test("amounts and share counts render in millions", () => {
  assert.equal(formatModelValue("revenue", 46_743_000_000), "46,743");
  assert.equal(formatModelValue("shares_diluted", 24_532_000_000), "24,532");
  assert.equal(formatModelValue("buyback_dollars", -12_340_000), "-12.3");
});

test("per-share, days and missing values", () => {
  assert.equal(formatModelValue("eps_diluted", 1.056), "1.06");
  assert.equal(formatModelValue("dso_days", 53.4), "53");
  assert.equal(formatModelValue("revenue", null), "—");
});
