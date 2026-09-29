// Recorded backend for the Playwright smoke suite.
//
//   node e2e/mock-api.mjs --record http://127.0.0.1:8000   # proxy + record into e2e/fixtures/api.json
//   node e2e/mock-api.mjs                                  # replay (CI)
//
// Serves GET responses keyed by path + query. In replay, an unrecorded request
// returns 404 and is logged, so a page that starts calling a new endpoint shows
// up as a failing test instead of silently rendering an empty state.
import { createServer } from "node:http";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";

const PORT = Number(process.env.MOCK_API_PORT ?? 8010);
const FIXTURE = process.env.MOCK_API_FIXTURE ?? fileURLToPath(new URL("./fixtures/api.json", import.meta.url));
const recordFrom = process.argv.includes("--record") ? process.argv[process.argv.indexOf("--record") + 1] : null;
const store = recordFrom || !existsSync(FIXTURE) ? {} : JSON.parse(readFileSync(FIXTURE, "utf8"));
const misses = new Set();

const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "*",
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
};

function save() {
  const text = JSON.stringify(store, null, 1);
  if (/apikey=[A-Za-z0-9]{8,}/i.test(text)) throw new Error("refusing to write a fixture containing an API key");
  writeFileSync(FIXTURE, text);
}

createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    res.writeHead(204, cors).end();
    return;
  }
  const key = `${req.method} ${req.url}`;
  if (recordFrom) {
    const upstream = await fetch(recordFrom + req.url, { method: req.method });
    const body = await upstream.text();
    if (req.method === "GET" && !req.url.includes("/stream")) {
      store[key] = { status: upstream.status, body };
      save();
    }
    res.writeHead(upstream.status, { ...cors, "Content-Type": upstream.headers.get("content-type") ?? "application/json" });
    res.end(body);
    return;
  }
  const hit = store[key];
  if (!hit) {
    if (!misses.has(key)) console.error(`[mock-api] unrecorded: ${key}`);
    misses.add(key);
    res.writeHead(404, { ...cors, "Content-Type": "application/json" }).end(JSON.stringify({ detail: "unrecorded" }));
    return;
  }
  res.writeHead(hit.status, { ...cors, "Content-Type": "application/json" }).end(hit.body);
}).listen(PORT, "127.0.0.1", () => {
  console.log(`[mock-api] ${recordFrom ? `recording from ${recordFrom}` : `replaying ${Object.keys(store).length} responses`} on :${PORT}`);
});
