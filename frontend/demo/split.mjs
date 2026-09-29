// Splits demo/api.json into static files the browser fetches one at a time
// (public/demo-data/), so a visitor downloads only the responses a page uses.
// Runs before the demo build; the output is generated, not committed.
import { readFileSync, writeFileSync, mkdirSync, rmSync } from "node:fs";

const store = JSON.parse(readFileSync(new URL("./api.json", import.meta.url)));
const out = new URL("../public/demo-data/", import.meta.url);
rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
const index = {};
Object.entries(store).forEach(([key, { status, body }], i) => {
  writeFileSync(new URL(`${i}.json`, out), body);
  index[key] = { status, file: `${i}.json` };
});
writeFileSync(new URL("index.json", out), JSON.stringify(index));
console.log(`demo-data: ${Object.keys(index).length} responses`);
