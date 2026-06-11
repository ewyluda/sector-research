import assert from "node:assert/strict";
import test from "node:test";

import { formatStat } from "../components/company/formatStat.ts";

test("pct multiplies by 100 exactly once (backend emits fractions)", () => {
  assert.equal(formatStat(0.6830928165442874, "pct"), "68.3%");
  assert.equal(formatStat(-3.4292830201444446, "pct"), "-342.9%"); // margins never n/m
});

test("pct_growth renders n/m beyond ±1000% (tiny-base artifacts)", () => {
  assert.equal(formatStat(-59.11675126903553, "pct_growth"), "n/m"); // ORCL FCF growth
  assert.equal(formatStat(10.1, "pct_growth"), "n/m");
  assert.equal(formatStat(-7.657447421492365, "pct_growth"), "-765.7%"); // within threshold
  assert.equal(formatStat(0.11231605175948767, "pct_growth"), "11.2%"); // ORCL 5y CAGR
});

test("null renders em-dash", () => {
  assert.equal(formatStat(null, "pct"), "—");
  assert.equal(formatStat(null, "pct_growth"), "—");
});
