import assert from "node:assert/strict";
import test from "node:test";

import { buildCategoryWrappers } from "./categoryWrappers.ts";
import type { CategoryState, WrapperCache } from "./categoryWrappers.ts";

function makeState(score: number): CategoryState {
  return { status: "pass", score, key_findings: ["finding"], structured: null };
}

test("same CategoryState reference → same wrapper object returned", () => {
  const cache: WrapperCache = new Map();
  const stateA = makeState(70);
  const stateB = makeState(55);

  const cats1 = { alpha: stateA, beta: stateB };
  const result1 = buildCategoryWrappers(cats1, cache);

  // Simulate a second render where only beta changed
  const stateB2 = makeState(60); // new reference
  const cats2 = { alpha: stateA, beta: stateB2 };
  const result2 = buildCategoryWrappers(cats2, cache);

  // alpha unchanged → same wrapper reference
  assert.strictEqual(result2.alpha, result1.alpha, "unchanged category must return identical wrapper reference");

  // beta changed → new wrapper
  assert.notStrictEqual(result2.beta, result1.beta, "changed category must return a new wrapper");
});

test("fail status yields null wrapper", () => {
  const cache: WrapperCache = new Map();
  const failState: CategoryState = { status: "fail", score: null, key_findings: [], structured: null };
  const result = buildCategoryWrappers({ cat: failState }, cache);
  assert.strictEqual(result.cat, null);
});

test("null wrapper is also cached stably", () => {
  const cache: WrapperCache = new Map();
  const failState: CategoryState = { status: "fail", score: null, key_findings: [], structured: null };
  const cats = { cat: failState };

  const r1 = buildCategoryWrappers(cats, cache);
  const r2 = buildCategoryWrappers(cats, cache);
  assert.strictEqual(r1.cat, r2.cat, "null wrapper must be reference-stable when state unchanged");
});

test("wrapper carries correct score and key_findings", () => {
  const cache: WrapperCache = new Map();
  const state = makeState(82);
  const result = buildCategoryWrappers({ x: state }, cache);
  const w = result.x;
  assert.ok(w !== null);
  assert.equal(w!.score, 82);
  assert.deepEqual(w!.key_findings, ["finding"]);
  assert.deepEqual(w!.citations, []);
  assert.equal(w!.content, "");
});

test("stale keys are evicted from cache when category is removed", () => {
  const cache: WrapperCache = new Map();
  const s = makeState(50);
  buildCategoryWrappers({ alpha: s, beta: s }, cache);
  assert.equal(cache.size, 2);

  // beta removed from next render
  buildCategoryWrappers({ alpha: s }, cache);
  assert.equal(cache.size, 1, "stale key should be evicted");
  assert.ok(cache.has("alpha"));
  assert.ok(!cache.has("beta"));
});

test("all 9 categories: only the updated one gets a new wrapper", () => {
  const cache: WrapperCache = new Map();
  const names = [
    "financial_health", "growth_earnings", "technical_market_structure",
    "business_quality", "macro_regime", "risk_assessment",
    "management_governance", "sentiment_narrative", "future_durability",
  ];

  // Initial build
  const initialStates: Record<string, CategoryState> = {};
  for (const n of names) initialStates[n] = makeState(60);
  const r1 = buildCategoryWrappers(initialStates, cache);

  // One category (risk_assessment) gets a new state
  const updatedStates = { ...initialStates, risk_assessment: makeState(45) };
  const r2 = buildCategoryWrappers(updatedStates, cache);

  for (const n of names) {
    if (n === "risk_assessment") {
      assert.notStrictEqual(r2[n], r1[n], `${n} should have a new wrapper`);
    } else {
      assert.strictEqual(r2[n], r1[n], `${n} should retain its original wrapper`);
    }
  }
});
