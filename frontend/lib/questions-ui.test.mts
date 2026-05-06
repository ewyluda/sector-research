import assert from "node:assert/strict";
import test from "node:test";

import {
  buildQuestionListPath,
  dismissPromptToAction,
  initialQuestionsTab,
  syncQuestionsTabForTickerFilter,
} from "./questions-ui.ts";

test("buildQuestionListPath sends all status explicitly", () => {
  assert.equal(
    buildQuestionListPath({ status: "all", priority: 1, limit: 200 }),
    "/api/questions?status=all&priority=1&limit=200",
  );
});

test("ticker drilldown forces the by-question tab", () => {
  assert.equal(initialQuestionsTab("MSFT"), "by_question");
  assert.equal(syncQuestionsTabForTickerFilter("by_ticker", "MSFT"), "by_question");
});

test("dismissPromptToAction distinguishes cancel from empty note", () => {
  assert.deepEqual(dismissPromptToAction(null), { cancelled: true });
  assert.deepEqual(dismissPromptToAction(""), { cancelled: false, note: undefined });
  assert.deepEqual(dismissPromptToAction("duplicate"), {
    cancelled: false,
    note: "duplicate",
  });
});
