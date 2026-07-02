import { strict as assert } from "node:assert";
import { test } from "node:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { PNL_LINES, BS_LINES, CF_LINES, DRIVER_KEYS } from "./modelVocab.ts";

// The backend is the canonical owner of the cell vocabulary. This test reads
// its registries straight from source and pins the frontend mirror against
// them, so a renamed/added driver or line item fails CI here instead of
// silently rendering a blank row in the grid.
const MODEL_STATE_PY = join(
  import.meta.dirname,
  "..",
  "..",
  "backend",
  "app",
  "models",
  "model_state.py",
);

const source = readFileSync(MODEL_STATE_PY, "utf8");

/** Extract the string-literal entries of a `NAME: list[str] = [ ... ]` block. */
function pyStringList(name: string): string[] {
  const re = new RegExp(`${name}\\s*:\\s*list\\[str\\]\\s*=\\s*\\[([\\s\\S]*?)\\]`);
  const m = source.match(re);
  assert.ok(m, `could not find registry ${name} in model_state.py`);
  return [...m![1].matchAll(/"([^"]+)"/g)].map((g) => g[1]);
}

test("PNL line items match backend LINE_ITEMS_PNL", () => {
  assert.deepEqual(PNL_LINES, pyStringList("LINE_ITEMS_PNL"));
});

test("balance-sheet line items match backend LINE_ITEMS_BS", () => {
  assert.deepEqual(BS_LINES, pyStringList("LINE_ITEMS_BS"));
});

test("cash-flow line items match backend LINE_ITEMS_CF", () => {
  assert.deepEqual(CF_LINES, pyStringList("LINE_ITEMS_CF"));
});

test("flattened driver keys match backend DRIVER_KEYS (membership + order)", () => {
  assert.deepEqual(DRIVER_KEYS, pyStringList("DRIVER_KEYS"));
});
