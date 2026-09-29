import assert from "node:assert/strict";
import test from "node:test";

import { PHASE_ETA_SECONDS, PHASE_LABELS, PHASE_ORDER } from "./pipeline-progress.ts";

test("live progress metadata matches the pipeline phases (targeted follow-up removed, ADR-0005)", () => {
  assert.deepEqual(PHASE_ORDER, [
    "quick_screen",
    "deep_dive",
    "thesis_construction",
    "risk_stress_test",
    "position_monitor",
  ]);
  for (const phase of PHASE_ORDER) {
    assert.equal(typeof PHASE_LABELS[phase], "string");
    assert.equal(typeof PHASE_ETA_SECONDS[phase], "number");
  }
});
