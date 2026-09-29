// Records the demo's API responses: crawls the app (a normal build pointed at
// e2e/mock-api.mjs in record mode, proxying a running backend) and writes every
// GET response to demo/api.json. Then build with NEXT_PUBLIC_DEMO=1.
//
//   node demo/record.mjs            # needs the backend on :8000; builds and serves the app itself
import { spawn, execSync } from "node:child_process";
import { chromium } from "@playwright/test";

const API = "http://127.0.0.1:8000";
const APP = "http://127.0.0.1:3100";
const get = async (p) => (await fetch(API + p)).json();
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

const env = { ...process.env, MOCK_API_FIXTURE: new URL("./api.json", import.meta.url).pathname };
const mock = spawn("node", ["e2e/mock-api.mjs", "--record", API], { env, stdio: "inherit" });
execSync("npx next build", { env: { ...process.env, NEXT_PUBLIC_API_URL: "http://127.0.0.1:8010" }, stdio: "inherit" });
const app = spawn("npx", ["next", "start", "-p", "3100", "-H", "127.0.0.1"], { stdio: "ignore" });
await wait(4000);

const runs = (await get("/api/runs?limit=40")).filter((r) => ["completed", "watchlist"].includes(r.status));
const latestByTicker = new Map();
for (const r of runs) if (!latestByTicker.has(r.ticker)) latestByTicker.set(r.ticker, r);
const themes = await get("/api/themes");
const neo = themes.find((t) => t.name === "Neo-clouds") ?? themes[0];
const models = ["NVDA", "ORCL", "CRWV", "CORZ", "NBIS"];
const companies = [...new Set([...latestByTicker.keys()].slice(0, 10))];
const tabs = ["", "/financials", "/peers", "/research", "/theses", "/transcripts", "/filings"];
const workspace = await get("/api/workspace/recent").catch(() => []);

const urls = [
  "/", "/?tab=calendar", "/status", "/themes", "/filings", "/library", "/questions", "/workspace",
  ...themes.map((t) => `/theme/${t.id}`),
  `/filings/graph/theme?theme=${neo.id}`,
  ...["CRWV", "NBIS", "ORCL"].map((t) => `/filings/graph?root=${t}`),
  ...[...latestByTicker.values()].map((r) => `/pipeline/${r.id}`),
  ...companies.flatMap((t) => tabs.map((tab) => `/company/${t}${tab}`)),
  ...models.flatMap((t) => [`/model/${t}#forecast`, `/model/${t}#reverse-dcf`, `/model/${t}#history`]),
  "/compare?tickers=NBIS,CRWV,ORCL,CORZ",
  ...(Array.isArray(workspace) ? workspace.slice(0, 3).map((w) => `/workspace/${w.id}`) : []),
  ...["all", "90d", "1y"].flatMap((w) => ["1m", "3m"].flatMap((o) =>
    ["spy", "spy_beta", "sector", "theme_basket"].map((b) => `/performance?window=${w}&snapshot_offset=${o}&benchmark=${b}`))),
];

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
for (const u of urls) {
  try {
    await page.goto(APP + u, { waitUntil: "networkidle", timeout: 60000 });
    if (u.includes("#")) { await page.reload({ waitUntil: "networkidle" }); }
    await wait(500);
  } catch (e) { console.error("skip", u, e.message.split("\n")[0]); }
}
await page.goto(APP + "/");
await page.keyboard.press("Meta+k");          // the ⌘K palette's tickers + runs
await wait(2000);
await browser.close();
app.kill(); mock.kill();
console.log(`recorded ${urls.length} pages`);
