import assert from "node:assert/strict";
import test from "node:test";

import { PHASE_ETA_SECONDS, PHASE_LABELS, PHASE_ORDER } from "./pipeline-progress.ts";

test("targeted follow-up appears in live progress metadata", () => {
  assert.deepEqual(PHASE_ORDER, [
    "quick_screen",
    "deep_dive",
    "targeted_followup",
    "thesis_construction",
    "risk_stress_test",
    "position_monitor",
  ]);
  assert.equal(PHASE_LABELS.targeted_followup, "Targeted Follow-up");
  assert.equal(typeof PHASE_ETA_SECONDS.targeted_followup, "number");
});
