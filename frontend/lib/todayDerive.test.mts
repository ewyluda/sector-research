import assert from "node:assert/strict";
import test from "node:test";

import { deriveAttention, deriveSummary } from "./todayDerive.ts";
import type { MaterialEvent, QuestionTickerRollup, StatusBoardEntry } from "./api.ts";

function entry(over: Partial<StatusBoardEntry>): StatusBoardEntry {
  return {
    ticker: "TEST",
    theme_id: "th-1",
    theme_name: "Test Theme",
    run_id: "run-1",
    thesis_status: "BUY",
    conviction_score: 70,
    completed_at: "2026-05-01T00:00:00Z",
    days_since_update: 10,
    health: "healthy",
    health_reasons: [],
    next_catalyst: null,
    kill_criteria_summary: { total: 0, triggered: 0 },
    material_events: null,
    archived_at: null,
    ...over,
  };
}

function rollup(over: Partial<QuestionTickerRollup>): QuestionTickerRollup {
  return { ticker: "TEST", p1_count: 0, p2_count: 0, p3_count: 0, open_count: 0, ...over };
}

test("buckets sort broken → triggered → stale → questions", () => {
  const rows = deriveAttention(
    [
      entry({ ticker: "STALE1", health: "stale", days_since_update: 95 }),
      entry({ ticker: "TRIG", health: "triggered", kill_criteria_summary: { total: 3, triggered: 1 } }),
      entry({ ticker: "BROKE", health: "broken", health_reasons: ["kill criterion triggered"] }),
      entry({ ticker: "FINE", health: "healthy" }),
      entry({ ticker: "SOON", health: "imminent" }),
    ],
    [rollup({ ticker: "QQQ", p1_count: 2, open_count: 4 })],
  );
  assert.deepEqual(
    rows.map((r) => r.ticker),
    ["BROKE", "TRIG", "STALE1", "QQQ"],
  );
});

test("within a health bucket, oldest update first; questions by p1 desc", () => {
  const rows = deriveAttention(
    [
      entry({ ticker: "S-NEW", health: "stale", days_since_update: 91 }),
      entry({ ticker: "S-OLD", health: "stale", days_since_update: 200 }),
    ],
    [
      rollup({ ticker: "Q-LOW", p1_count: 1, open_count: 1 }),
      rollup({ ticker: "Q-HIGH", p1_count: 3, open_count: 5 }),
    ],
  );
  assert.deepEqual(
    rows.map((r) => r.ticker),
    ["S-OLD", "S-NEW", "Q-HIGH", "Q-LOW"],
  );
});

test("healthy/imminent entries and zero-P1 rollups produce no rows", () => {
  assert.deepEqual(
    deriveAttention(
      [entry({ health: "healthy" }), entry({ health: "imminent" })],
      [rollup({ p1_count: 0, p2_count: 4, open_count: 4 })],
    ),
    [],
  );
});

test("a ticker can appear as both a health row and a questions row", () => {
  const rows = deriveAttention(
    [entry({ ticker: "BOTH", health: "triggered" })],
    [rollup({ ticker: "BOTH", p1_count: 1, open_count: 2 })],
  );
  assert.equal(rows.length, 2);
  assert.equal(rows[0].kind, "health");
  assert.equal(rows[1].kind, "questions");
});

test("health row fields map through", () => {
  const [row] = deriveAttention(
    [entry({
      ticker: "NVDA", theme_name: "Semis", run_id: "run-9", health: "triggered",
      health_reasons: ["1 kill criterion triggered"],
      kill_criteria_summary: { total: 5, triggered: 2 }, days_since_update: 12,
    })],
    [],
  );
  assert.equal(row.kind, "health");
  if (row.kind === "health") {
    assert.equal(row.severity, "red");
    assert.equal(row.runId, "run-9");
    assert.equal(row.themeName, "Semis");
    assert.equal(row.triggeredCriteria, 2);
    assert.equal(row.totalCriteria, 5);
    assert.equal(row.daysSinceUpdate, 12);
    assert.deepEqual(row.reasons, ["1 kill criterion triggered"]);
  }
});

test("stale rows are amber, broken/triggered red", () => {
  const rows = deriveAttention(
    [
      entry({ ticker: "B", health: "broken" }),
      entry({ ticker: "S", health: "stale" }),
    ],
    [],
  );
  assert.deepEqual(rows.map((r) => r.severity), ["red", "amber"]);
});

test("deriveSummary counts buckets; all-clear is all zeros", () => {
  assert.deepEqual(
    deriveSummary(
      [
        entry({ health: "broken" }),
        entry({ health: "triggered" }),
        entry({ health: "stale" }),
        entry({ health: "healthy" }),
      ],
      [rollup({ ticker: "A", p1_count: 2 }), rollup({ ticker: "B", p1_count: 0, open_count: 1 })],
    ),
    { alerts: 2, stale: 1, p1Tickers: 1 },
  );
  assert.deepEqual(deriveSummary([], []), { alerts: 0, stale: 0, p1Tickers: 0 });
});

function matEvent(over: Partial<MaterialEvent>): MaterialEvent {
  return {
    id: "ev-1",
    ticker: "NVDA",
    event_type: "guidance",
    materiality: "high",
    headline: "Guidance cut",
    summary: "Cut FY outlook.",
    item_codes: "2.02",
    filing_date: "2026-06-08",
    document_url: null,
    dismissed_at: null,
    ...over,
  };
}

test("event rows slot between health rows and question rows", () => {
  const rows = deriveAttention(
    [entry({ ticker: "BROKE", health: "broken" })],
    [rollup({ ticker: "QQQ", p1_count: 1, open_count: 1 })],
    [matEvent({ ticker: "NVDA" })],
  );
  assert.deepEqual(
    rows.map((r) => r.kind),
    ["health", "event", "questions"],
  );
  const ev = rows[1];
  assert.equal(ev.kind, "event");
  if (ev.kind === "event") {
    assert.equal(ev.ticker, "NVDA");
    assert.equal(ev.severity, "amber");
    assert.equal(ev.headline, "Guidance cut");
  }
});

test("events default arg keeps old call sites working", () => {
  const rows = deriveAttention([], []);
  assert.deepEqual(rows, []);
});

test("event rows sort newest first", () => {
  const rows = deriveAttention(
    [],
    [],
    [
      matEvent({ id: "a", filing_date: "2026-06-05", ticker: "OLD" }),
      matEvent({ id: "b", filing_date: "2026-06-09", ticker: "NEW" }),
    ],
  );
  assert.deepEqual(
    rows.map((r) => (r.kind === "event" ? r.ticker : "")),
    ["NEW", "OLD"],
  );
});
