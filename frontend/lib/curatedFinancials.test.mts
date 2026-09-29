import assert from "node:assert/strict";
import test from "node:test";

import { growthPct, normalizeCuratedFinancials, ttmEpsGrowth, withTrueYoy } from "./curatedFinancials.ts";
import type { CuratedFinancials, QuarterlyMetric } from "./api.ts";

const q = (values: number[], staleYoy = 99): QuarterlyMetric[] =>
  values.map((value, i) => ({ period: `p${i}`, value, yoy_growth: staleYoy }));

// SMCI revenue as stored (newest first). Q3 FY26 $10.24B vs Q3 FY25 $4.60B.
const SMCI_REV = [10.243, 12.682, 5.018, 5.757, 4.6, 5.678, 5.937, 5.355];

test("yoy compares with the same quarter a year earlier, not the previous quarter", () => {
  const out = withTrueYoy(q(SMCI_REV));
  assert.ok(Math.abs((out[0].yoy_growth ?? 0) - 122.67) < 0.1); // not -19.2
  assert.equal(out[4].yoy_growth, null); // no quarter four back
});

test("growth is n/m on a non-positive base or a tiny-base blowup", () => {
  assert.equal(growthPct(-6.7, 0.045), null); // |g| > 1000%
  assert.equal(growthPct(5, -2), null);
  assert.equal(growthPct(5, 0), null);
  assert.equal(growthPct(12, 10), 20);
});

test("normalize recomputes stored QoQ values and hides a meaningless DCF gap", () => {
  const cf = {
    quarterly_revenue: q(SMCI_REV),
    quarterly_free_cf: q([-6.7, 0.045, 1, 1, 1, 1, 1, 1]),
    dcf_intrinsic_value: -60.37,
    dcf_gap_percent: -303,
  } as unknown as CuratedFinancials;
  const out = normalizeCuratedFinancials(cf)!;
  assert.ok((out.quarterly_revenue[0].yoy_growth ?? 0) > 100);
  assert.equal(out.dcf_gap_percent, null);
  assert.equal(normalizeCuratedFinancials(null), null);
});

test("TTM EPS growth is year over year", () => {
  assert.equal(ttmEpsGrowth(q([2, 2, 2, 2, 1, 1, 1, 1])), 100);
  assert.equal(ttmEpsGrowth(q([2, 2, 2, 2, 1])), null);
});
