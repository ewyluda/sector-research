import assert from "node:assert/strict";
import test from "node:test";

import { deriveOrphanEvents } from "./orphanEvents.ts";
import type { MaterialEvent } from "./api/status.ts";

function mkEvent(ticker: string, over: Partial<MaterialEvent> = {}): MaterialEvent {
  return {
    id: `${ticker}-1`,
    ticker,
    event_type: "guidance",
    materiality: "high",
    headline: "h",
    summary: "s",
    item_codes: null,
    filing_date: "2026-06-10",
    document_url: null,
    dismissed_at: null,
    group_count: 1,
    group_member_ids: [],
    group_headlines: [],
    ...over,
  };
}

test("board tickers are excluded", () => {
  const out = deriveOrphanEvents(
    { NVDA: [mkEvent("NVDA")], ERIC: [mkEvent("ERIC")] },
    new Set(["NVDA"]),
  );
  assert.deepEqual(out.map((g) => g.ticker), ["ERIC"]);
});

test("empty event lists are dropped", () => {
  assert.deepEqual(deriveOrphanEvents({ ERIC: [] }, new Set()), []);
});

test("groups sort by ticker", () => {
  const out = deriveOrphanEvents(
    { ZS: [mkEvent("ZS")], ANET: [mkEvent("ANET")] },
    new Set(),
  );
  assert.deepEqual(out.map((g) => g.ticker), ["ANET", "ZS"]);
});
