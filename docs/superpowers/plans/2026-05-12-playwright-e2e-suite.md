# Playwright End-to-End Test + Findings Suite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated, re-runnable Playwright suite that drives the sector-research frontend end-to-end across every workspace (Themes/Discovery, Pipeline, Filings/Graph, Catalysts, Status, Workspace-loop, Questions, Library, Financial Model + Reverse-DCF, Performance), captures screenshots and console/network errors, and emits a structured findings report so the user can review issues, formatting/refinement opportunities, and improvement ideas in one place.

**Architecture:** Standalone `@playwright/test` project under `e2e/` (sibling to `backend/` and `frontend/`), no auth required. A `globalSetup` health-checks both servers before any test runs. A `findings` test fixture writes structured markdown into `e2e/findings/<surface>.md` on every observation; an aggregator script merges them into `e2e/reports/summary-<timestamp>.md`. Tests split into two cost tiers — **fixture-mode** tests walk existing data (cheap, always-on) and an opt-in **full-analysis** test kicks off a real pipeline run via `E2E_RUN_FULL_PIPELINE=1` (expensive, ~$1-3 in Claude calls per run). Each test traces, screenshots, captures `console`/`pageerror`/`requestfailed`, and writes findings as it walks.

**Tech Stack:** `@playwright/test` (test runner, not raw playwright), TypeScript, Chromium-only (single-browser is fine for a personal tool). Pinned to `http://127.0.0.1:3000` per project memory (Docker dashboard-api-1 steals IPv6 localhost:8000 from uvicorn). No CI integration — local-only.

**Cost & runtime expectations:**
- Fixture-mode full suite: ~3-5 min, $0
- With `E2E_RUN_FULL_PIPELINE=1`: ~12-20 min, ~$1-3 (one Sonnet pipeline run for a fixture ticker)
- With `E2E_RUN_WORKSPACE_LOOP=1`: +~5 min, ~$0.30

**Branch hygiene:** Current branch is `feat/transcript-delta-analysis` with uncommitted changes. Create this suite on a new branch `feat/e2e-playwright-suite` so it doesn't tangle with in-flight work — `git switch -c feat/e2e-playwright-suite main` before Task 1.

---

## File Structure

```
e2e/
├── package.json                       # @playwright/test + tsx
├── playwright.config.ts               # baseURL=127.0.0.1:3000, traces, screenshots
├── tsconfig.json                      # ESM, strict, Node types
├── global-setup.ts                    # health-check backend+frontend; abort fast
├── fixtures/
│   ├── app.ts                         # `test` fixture: wires console/error/network
│   │                                  # listeners → findings, returns enriched `page`
│   ├── findings.ts                    # `finding()` helper writes structured md
│   └── data.ts                        # pickFixtureTheme(), pickFixtureRunId(),
│                                      # pickFixtureTicker() — read from backend API
├── helpers/
│   ├── api.ts                         # typed thin wrapper over backend REST
│   ├── screenshot.ts                  # naming convention + per-test dir
│   └── waitForPipeline.ts             # poll /api/runs/{id} until status=completed
├── tests/
│   ├── 01-global-shell.spec.ts        # nav, ⌘K palette, print view, 404
│   ├── 02-themes-discovery.spec.ts    # /, /theme/[id], rankings, signals
│   ├── 03-pipeline-existing-run.spec.ts  # walk a completed run end-to-end
│   ├── 04-pipeline-full-analysis.spec.ts # OPT-IN: create + watch a real run
│   ├── 05-deep-dive-sections.spec.ts  # 9 categories + supply-chain card +
│   │                                  # read-through CTA + WhatChangedPanel
│   ├── 06-filings-graph.spec.ts       # /filings, ingest, curation, /filings/graph
│   ├── 07-secondary-surfaces.spec.ts  # catalysts, status board+drawers,
│   │                                  # questions, library, performance
│   ├── 08-workspace-loop.spec.ts      # OPT-IN: kick off a workspace run + SSE
│   ├── 09-financial-model.spec.ts     # /model/[ticker], cell edits, save,
│   │                                  # history/diff
│   └── 10-reverse-dcf.spec.ts         # reverse-DCF tab, sensitivity, what-if
├── scripts/
│   └── aggregate-findings.ts          # merges findings/*.md → reports/summary-*.md
├── findings/
│   └── .gitkeep
├── reports/
│   └── .gitkeep
└── README.md                          # how to run, env vars, where findings land
```

**Modify:**
- `/.gitignore` — add `e2e/findings/*.md`, `e2e/reports/`, `e2e/test-results/`, `e2e/playwright-report/`, `!e2e/findings/.gitkeep`, `!e2e/reports/.gitkeep`

---

## TDD-style note for this plan

Unlike feature work, the test code IS the deliverable here — we are not implementing app code, we are exercising existing app code and documenting what we observe. So each task's loop is:

1. Write the spec file (or one `test()` block within it)
2. Run it against the live app
3. Review the screenshots + findings markdown that landed
4. Fix the test if it fundamentally mis-asserts; otherwise commit the test AS-IS and let the findings speak for the app

A test "passing" means it walked the surface without crashing — it does **not** mean the app is bug-free. The findings file is where the truth lives.

---

## Task 1: Scaffold the e2e/ project

**Files:**
- Create: `e2e/package.json`
- Create: `e2e/tsconfig.json`
- Create: `e2e/playwright.config.ts`
- Create: `e2e/global-setup.ts`
- Create: `e2e/README.md`
- Create: `e2e/.gitkeep` files for `findings/` and `reports/`
- Modify: `/.gitignore`

- [ ] **Step 1: Create `e2e/package.json`**

```json
{
  "name": "sector-research-e2e",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "test": "playwright test",
    "test:headed": "playwright test --headed",
    "test:debug": "playwright test --debug",
    "test:fixture": "playwright test --grep-invert @full-analysis",
    "test:full": "E2E_RUN_FULL_PIPELINE=1 E2E_RUN_WORKSPACE_LOOP=1 playwright test",
    "report": "tsx scripts/aggregate-findings.ts",
    "open-report": "open reports/$(ls -t reports | head -1)"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.0",
    "@types/node": "^20.0.0",
    "tsx": "^4.19.0",
    "typescript": "^5.6.0"
  }
}
```

- [ ] **Step 2: Create `e2e/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "esModuleInterop": true,
    "strict": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "types": ["node"]
  },
  "include": ["**/*.ts"]
}
```

- [ ] **Step 3: Create `e2e/playwright.config.ts`**

```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,                // serial — easier to read findings + no rate-limit thrash
  workers: 1,
  reporter: [['list'], ['html', { outputFolder: 'playwright-report', open: 'never' }]],
  use: {
    baseURL: 'http://127.0.0.1:3000',  // pin IPv4 — IPv6 collides with Docker dashboard-api-1
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
    viewport: { width: 1440, height: 900 },
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
  },
  globalSetup: './global-setup.ts',
  projects: [
    { name: 'chromium', use: { channel: 'chromium' } },
  ],
});
```

- [ ] **Step 4: Create `e2e/global-setup.ts`** — health-checks both servers, fails fast with a useful message

```ts
async function pingOrThrow(url: string, name: string) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(5000) });
    if (!res.ok) throw new Error(`${name} responded ${res.status}`);
  } catch (err) {
    throw new Error(
      `${name} is not reachable at ${url}. Start it before running the suite.\n` +
      `  backend: source backend/venv/bin/activate && uvicorn backend.app.main:app --reload\n` +
      `  frontend: cd frontend && npm run dev\n` +
      `Original error: ${err instanceof Error ? err.message : String(err)}`
    );
  }
}

export default async function globalSetup() {
  await pingOrThrow('http://127.0.0.1:8000/health', 'backend');
  await pingOrThrow('http://127.0.0.1:3000/', 'frontend');
  // eslint-disable-next-line no-console
  console.log('[global-setup] backend + frontend healthy');
}
```

- [ ] **Step 5: Create `e2e/README.md`** — concise run instructions

````markdown
# E2E suite

Walks the frontend end-to-end with Playwright and emits structured findings.

## One-time

```bash
cd e2e
npm install
npx playwright install chromium
```

## Run

Servers must be up: backend on `127.0.0.1:8000`, frontend on `127.0.0.1:3000`.

```bash
# Fixture-mode only (cheap, ~3-5 min, $0)
npm test

# Include the full-analysis pipeline test (~$1-3, ~15 min)
E2E_RUN_FULL_PIPELINE=1 npm test

# Include the workspace-loop test (~$0.30, ~5 min)
E2E_RUN_WORKSPACE_LOOP=1 npm test

# Everything
npm run test:full
```

## Where things land

- `findings/<surface>.md` — structured observations per surface (issues, polish, ideas)
- `reports/summary-<timestamp>.md` — aggregated report (run `npm run report` after tests)
- `test-results/` — Playwright traces, screenshots, videos
- `playwright-report/` — HTML report (`npx playwright show-report`)
````

- [ ] **Step 6: Create the placeholder dirs and update `.gitignore`**

Add the two `.gitkeep` files. Then append to `/.gitignore`:

```gitignore

# e2e
e2e/node_modules/
e2e/test-results/
e2e/playwright-report/
e2e/findings/*.md
e2e/reports/*.md
!e2e/findings/.gitkeep
!e2e/reports/.gitkeep
```

- [ ] **Step 7: Install + smoke-verify config**

```bash
cd e2e && npm install && npx playwright install chromium
npx playwright test --list
```

Expected: `Error: No tests found` (no tests yet — but config + globalSetup loaded cleanly).

- [ ] **Step 8: Commit**

```bash
git add e2e/package.json e2e/package-lock.json e2e/tsconfig.json e2e/playwright.config.ts \
        e2e/global-setup.ts e2e/README.md e2e/findings/.gitkeep e2e/reports/.gitkeep .gitignore
git commit -m "chore(e2e): scaffold playwright project with health-check global setup"
```

---

## Task 2: Findings + app fixtures

**Files:**
- Create: `e2e/fixtures/findings.ts`
- Create: `e2e/fixtures/app.ts`
- Create: `e2e/fixtures/data.ts`
- Create: `e2e/helpers/api.ts`
- Create: `e2e/helpers/screenshot.ts`
- Create: `e2e/helpers/waitForPipeline.ts`

- [ ] **Step 1: Create `e2e/helpers/api.ts`** — thin typed wrapper

```ts
const BASE = 'http://127.0.0.1:8000';

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) throw new Error(`API ${path} → ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export const api = {
  listThemes: () => j<Array<{ id: number; name: string; seed_tickers: string[] }>>('/api/themes'),
  listRuns: () => j<Array<{ run_id: string; ticker: string; status: string; theme_id: number | null }>>('/api/runs'),
  getRun: (id: string) => j<any>(`/api/runs/${id}`),
  getReport: (id: string) => j<any>(`/api/runs/${id}/report`),
  createRun: (body: { ticker: string; theme_id: number }) =>
    j<{ run_id: string }>('/api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  getModel: (ticker: string) => j<any>(`/api/models/${ticker}`),
  listCatalysts: () => j<any[]>('/api/catalysts'),
  statusBoard: () => j<{ entries: any[] }>('/api/status/board'),
  listQuestions: () => j<any[]>('/api/questions'),
};
```

- [ ] **Step 2: Create `e2e/fixtures/findings.ts`** — markdown writer

```ts
import { promises as fs } from 'node:fs';
import path from 'node:path';

export type FindingCategory = 'bug' | 'polish' | 'improvement' | 'note';
export type FindingSeverity = 'low' | 'med' | 'high';

export interface Finding {
  surface: string;                  // e.g. 'pipeline-existing-run'
  category: FindingCategory;
  severity?: FindingSeverity;
  title: string;
  details?: string;
  screenshot?: string;              // relative path
  url?: string;                     // page URL where observed
}

const FINDINGS_DIR = path.resolve(import.meta.dirname, '..', 'findings');

export async function finding(f: Finding) {
  await fs.mkdir(FINDINGS_DIR, { recursive: true });
  const file = path.join(FINDINGS_DIR, `${f.surface}.md`);
  const exists = await fs.stat(file).then(() => true, () => false);
  if (!exists) {
    await fs.writeFile(file, `# Findings: ${f.surface}\n\n`);
  }
  const sev = f.severity ? ` [${f.severity}]` : '';
  const cat = f.category.toUpperCase();
  const url = f.url ? `\n  - URL: \`${f.url}\`` : '';
  const shot = f.screenshot ? `\n  - Screenshot: \`${f.screenshot}\`` : '';
  const det = f.details ? `\n  - ${f.details.replace(/\n/g, '\n    ')}` : '';
  await fs.appendFile(file, `- **${cat}${sev}** — ${f.title}${url}${shot}${det}\n`);
}

export async function resetSurface(surface: string) {
  const file = path.join(FINDINGS_DIR, `${surface}.md`);
  await fs.rm(file, { force: true });
}
```

- [ ] **Step 3: Create `e2e/helpers/screenshot.ts`**

```ts
import type { Page, TestInfo } from '@playwright/test';
import path from 'node:path';

export async function shot(page: Page, info: TestInfo, label: string): Promise<string> {
  const safe = label.replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
  const file = path.join(info.outputDir, `${safe}.png`);
  await page.screenshot({ path: file, fullPage: true });
  // store relative to e2e/ root for cleaner findings paths
  return path.relative(path.resolve(import.meta.dirname, '..'), file);
}
```

- [ ] **Step 4: Create `e2e/fixtures/app.ts`** — extended `test` with auto console/network capture

```ts
import { test as base, expect } from '@playwright/test';
import { finding } from './findings.js';
import { shot } from '../helpers/screenshot.js';

type Fixtures = {
  surface: string;                                 // one per spec file
  capturedErrors: () => string[];                  // pull-on-demand
  snap: (label: string) => Promise<string>;        // screenshot + return rel path
};

export const test = base.extend<Fixtures>({
  surface: ['unknown', { option: true }],
  capturedErrors: async ({ page, surface }, use, info) => {
    const errors: string[] = [];
    page.on('pageerror', async (err) => {
      errors.push(`pageerror: ${err.message}`);
      const s = await shot(page, info, `pageerror-${errors.length}`);
      await finding({
        surface, category: 'bug', severity: 'high',
        title: `Uncaught page error: ${err.message.slice(0, 120)}`,
        details: err.stack?.slice(0, 800),
        url: page.url(), screenshot: s,
      });
    });
    page.on('console', async (msg) => {
      if (msg.type() !== 'error') return;
      const text = msg.text();
      if (text.includes('Download the React DevTools')) return;
      errors.push(`console: ${text}`);
      await finding({
        surface, category: 'bug', severity: 'med',
        title: `Console error: ${text.slice(0, 200)}`,
        url: page.url(),
      });
    });
    page.on('requestfailed', async (req) => {
      if (/favicon|analytics|telemetry/.test(req.url())) return;
      errors.push(`requestfailed: ${req.url()}`);
      await finding({
        surface, category: 'bug', severity: 'high',
        title: `Network request failed: ${req.method()} ${new URL(req.url()).pathname}`,
        details: `Failure: ${req.failure()?.errorText ?? 'unknown'}\nFull URL: ${req.url()}`,
        url: page.url(),
      });
    });
    await use(() => errors.slice());
  },
  snap: async ({ page }, use, info) => {
    await use((label) => shot(page, info, label));
  },
});

export { expect };
```

- [ ] **Step 5: Create `e2e/fixtures/data.ts`** — pick fixture data from the live backend

```ts
import { api } from '../helpers/api.js';

export async function pickFixtureTheme() {
  const themes = await api.listThemes();
  if (!themes.length) throw new Error('No themes in DB — seed one before running e2e tests.');
  const runs = await api.listRuns();
  const themesWithCompletedRun = themes.filter(t =>
    t.seed_tickers.length > 0 &&
    runs.some(r => r.theme_id === t.id && r.status === 'completed')
  );
  return themesWithCompletedRun[0] ?? themes[0];
}

export async function pickFixtureCompletedRun() {
  const runs = await api.listRuns();
  const completed = runs.filter(r => r.status === 'completed');
  if (!completed.length) {
    throw new Error('No completed runs in DB — run a pipeline once before e2e, or set E2E_RUN_FULL_PIPELINE=1.');
  }
  const preferred = ['AAPL', 'MSFT', 'NVDA', 'GOOGL'];
  for (const t of preferred) {
    const m = completed.find(r => r.ticker.toUpperCase() === t);
    if (m) return m;
  }
  return completed[0];
}

export async function pickFixtureTicker() {
  const run = await pickFixtureCompletedRun().catch(() => null);
  return run?.ticker.toUpperCase() ?? 'AAPL';
}
```

- [ ] **Step 6: Create `e2e/helpers/waitForPipeline.ts`**

```ts
import { api } from './api.js';

export async function waitForPipeline(runId: string, opts: { timeoutMs?: number; pollMs?: number } = {}) {
  const timeout = opts.timeoutMs ?? 20 * 60 * 1000;
  const poll = opts.pollMs ?? 5_000;
  const start = Date.now();
  let last = '';
  while (Date.now() - start < timeout) {
    const run = await api.getRun(runId);
    if (run.status !== last) {
      // eslint-disable-next-line no-console
      console.log(`[waitForPipeline] ${runId} → ${run.status} @ ${new Date().toISOString()}`);
      last = run.status;
    }
    if (run.status === 'completed' || run.status === 'watchlist') return run;
    if (run.status === 'failed') throw new Error(`Pipeline failed: ${JSON.stringify(run.error ?? {})}`);
    await new Promise(r => setTimeout(r, poll));
  }
  throw new Error(`Pipeline timed out after ${timeout}ms (last status: ${last})`);
}
```

- [ ] **Step 7: Commit**

```bash
git add e2e/fixtures e2e/helpers
git commit -m "chore(e2e): findings/app/data fixtures + api/screenshot/pipeline helpers"
```

---

## Task 3: 01-global-shell.spec.ts — Nav, ⌘K palette, print view, 404

**Files:**
- Create: `e2e/tests/01-global-shell.spec.ts`

Surface scope: top nav links + their routes load; ⌘K command palette opens & jumps; print stylesheet hides `data-print-hide="true"` elements; 404 page is sane.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';

const SURFACE = 'global-shell';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

const NAV_ROUTES = [
  { label: 'Themes',    path: '/' },
  { label: 'Filings',   path: '/filings' },
  { label: 'Catalysts', path: '/catalysts' },
  { label: 'Status',    path: '/status' },
  { label: 'Workspace', path: '/workspace' },
  { label: 'Questions', path: '/questions' },
  { label: 'Library',   path: '/library' },
];

test('nav links land on the right route', async ({ page, snap, capturedErrors }) => {
  await page.goto('/');
  for (const { label, path } of NAV_ROUTES) {
    const link = page.getByRole('navigation').getByRole('link', { name: new RegExp(`^${label}$`, 'i') });
    if (!(await link.count())) {
      await finding({
        surface: SURFACE, category: 'bug', severity: 'med',
        title: `Nav link missing: "${label}"`,
        details: `Expected a nav link to ${path}. Check frontend/components/Nav.tsx.`,
        url: page.url(),
      });
      continue;
    }
    await link.first().click();
    await page.waitForURL((u) => u.pathname === path, { timeout: 10_000 });
    await snap(`nav-${label.toLowerCase()}`);
  }
  expect(capturedErrors()).toEqual([]);
});

test('command palette opens with ⌘K and jumps to a section', async ({ page, snap }) => {
  const { pickFixtureCompletedRun } = await import('../fixtures/data.js');
  const run = await pickFixtureCompletedRun().catch(() => null);
  if (!run) {
    await finding({ surface: SURFACE, category: 'note', title: 'Skipping ⌘K test — no completed run available' });
    test.skip();
    return;
  }
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');

  await page.keyboard.press('Meta+K');
  const palette = page.getByRole('dialog').or(page.locator('[data-palette="command"]'));
  let opened = await palette.first().isVisible().catch(() => false);
  if (!opened) {
    await page.keyboard.press('Control+K');
    opened = await palette.first().isVisible().catch(() => false);
  }
  if (!opened) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'med',
      title: '⌘K command palette did not open on the deep-dive page',
      details: 'Check frontend/components/deep-dive/CommandPalette.tsx wiring.',
      url: page.url(), screenshot: await snap('palette-not-open'),
    });
    return;
  }
  await snap('palette-open');
  await page.keyboard.type('management');
  await snap('palette-filtered');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  await snap('palette-jumped');
});

test('print stylesheet hides data-print-hide elements', async ({ page, snap }) => {
  await page.goto('/');
  await page.emulateMedia({ media: 'print' });
  await snap('home-print');
  const stillVisible = await page.locator('[data-print-hide="true"]:visible').count();
  if (stillVisible > 0) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'low',
      title: `${stillVisible} elements tagged data-print-hide are still visible under print media`,
      details: 'Check app/globals.css @media print block.',
      url: page.url(),
    });
  }
  await page.emulateMedia({ media: 'screen' });
});

test('404 page renders cleanly', async ({ page, snap, capturedErrors }) => {
  const res = await page.goto('/this-route-does-not-exist');
  await snap('404');
  if (res && res.status() !== 404) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'low',
      title: `Unknown route returned ${res.status()} instead of 404`,
      url: page.url(),
    });
  }
  expect(capturedErrors()).toEqual([]);
});
```

- [ ] **Step 2: Run it**

```bash
cd e2e && npx playwright test tests/01-global-shell.spec.ts
```

Expected: 4 tests run. Findings file appears at `e2e/findings/global-shell.md` if anything was noted.

- [ ] **Step 3: Review findings + commit**

```bash
cat e2e/findings/global-shell.md
git add e2e/tests/01-global-shell.spec.ts
git commit -m "test(e2e): global shell — nav, ⌘K palette, print, 404"
```

---

## Task 4: 02-themes-discovery.spec.ts — Home + theme detail

**Files:**
- Create: `e2e/tests/02-themes-discovery.spec.ts`

Surface scope: home page lists themes; each `/theme/[id]` renders ranked company cards merging FMP + X signal; velocity badges + source badges render; signal-refresh button (if shown) responds.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureTheme } from '../fixtures/data.js';

const SURFACE = 'themes-discovery';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

test('home lists themes with rankings', async ({ page, snap, capturedErrors }) => {
  await page.goto('/');
  await page.waitForLoadState('networkidle');
  await snap('home');
  const cards = page.locator('[data-theme-card], a[href^="/theme/"]');
  if ((await cards.count()) === 0) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'high',
      title: 'No theme cards rendered on /',
      details: 'Expected at least one theme from GET /api/themes.',
      url: page.url(), screenshot: await snap('home-empty'),
    });
  }
  expect(capturedErrors()).toEqual([]);
});

test('theme detail page shows ranked companies, signals, fundamentals', async ({ page, snap, capturedErrors }) => {
  const theme = await pickFixtureTheme();
  await page.goto(`/theme/${theme.id}`);
  await page.waitForLoadState('networkidle');
  await snap(`theme-${theme.id}`);

  const rows = page.locator('[data-company-card], [data-ticker]');
  if ((await rows.count()) === 0) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'high',
      title: `Theme "${theme.name}" rendered no company cards`,
      details: 'DiscoveryEngine may not have produced results — check signals table + FMP screener.',
      url: page.url(),
    });
    return;
  }

  const hasVelocity = await page.locator('[data-velocity], text=/velocity/i').count();
  const hasSources = await page.locator('[data-source-badge], a[title*="FMP"], a[title*="X"]').count();
  if (!hasVelocity) await finding({
    surface: SURFACE, category: 'polish', severity: 'low',
    title: 'No velocity badge visible on theme page',
    details: 'X signal velocity may be stale/missing.',
    url: page.url(),
  });
  if (!hasSources) await finding({
    surface: SURFACE, category: 'polish', severity: 'low',
    title: 'No source citation badges visible on theme page',
    url: page.url(),
  });

  const firstLink = page.locator('a[href*="/pipeline/"], a[href*="/model/"]').first();
  if (await firstLink.count()) {
    await firstLink.click();
    await page.waitForLoadState('networkidle');
    await snap(`theme-${theme.id}-first-company`);
  } else {
    await finding({
      surface: SURFACE, category: 'improvement', severity: 'low',
      title: 'Company cards don\'t expose a primary CTA into research/model',
      details: 'Consider adding a "Research →" or "Open model →" button per company card.',
      url: page.url(),
    });
  }

  expect(capturedErrors()).toEqual([]);
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && npx playwright test tests/02-themes-discovery.spec.ts
cat e2e/findings/themes-discovery.md
git add e2e/tests/02-themes-discovery.spec.ts && git commit -m "test(e2e): themes/discovery — home + theme detail"
```

---

## Task 5: 03-pipeline-existing-run.spec.ts — Walk a completed run

**Files:**
- Create: `e2e/tests/03-pipeline-existing-run.spec.ts`

Surface scope: load a completed run at `/pipeline/[runId]`, verify ReportHeader (ticker), score chips aren't all em-dashes, the 9 deep-dive section headings render, SectionNav scroll-spy highlights.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureCompletedRun } from '../fixtures/data.js';

const SURFACE = 'pipeline-existing-run';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

const DEEP_DIVE_SECTIONS = [
  'Macro & Regime', 'Business Quality', 'Growth & Earnings',
  'Financial Health', 'Risk Assessment', 'Future Durability',
  'Management & Governance', 'Sentiment & Narrative', 'Competition',
];

test('completed run renders header + overview + score bar', async ({ page, snap, capturedErrors }) => {
  const run = await pickFixtureCompletedRun();
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');
  await snap('report-top');

  await expect(page.locator('h1, [data-report-ticker]').first()).toContainText(run.ticker);

  const scoreBarText = await page.locator('[data-score-bar], section').first().innerText().catch(() => '');
  const emDashes = (scoreBarText.match(/—/g) ?? []).length;
  if (emDashes > 9) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'high',
      title: 'Score bar appears to be all em-dashes',
      details: `Found ${emDashes} em-dashes near top of report. Likely scoreKeys.ts normalize regression — check DISPLAY_TO_KEY mapping.`,
      url: page.url(), screenshot: await snap('emdash-blackhole'),
    });
  }

  expect(capturedErrors()).toEqual([]);
});

test('all 9 deep-dive sections render', async ({ page, snap }) => {
  const run = await pickFixtureCompletedRun();
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');

  for (const name of DEEP_DIVE_SECTIONS) {
    const heading = page.getByRole('heading', { name: new RegExp(name, 'i') }).first();
    if (!(await heading.isVisible().catch(() => false))) {
      await finding({
        surface: SURFACE, category: 'bug', severity: 'med',
        title: `Section "${name}" missing from report`,
        details: 'Check graph/nodes.py deep-dive categories and frontend sections.ts registry.',
        url: page.url(), screenshot: await snap(`missing-${name}`),
      });
      continue;
    }
    await heading.scrollIntoViewIfNeeded();
    await page.waitForTimeout(200);
    await snap(`section-${name.replace(/\W+/g, '-').toLowerCase()}`);
  }
});

test('SectionNav scroll-spy highlights as we scroll', async ({ page, snap }) => {
  const run = await pickFixtureCompletedRun();
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');

  const navPill = page.locator('[data-section-nav] a, nav a').filter({ hasText: /Growth & Earnings/i }).first();
  const target = page.getByRole('heading', { name: /Growth & Earnings/i }).first();
  if (!(await target.isVisible().catch(() => false))) {
    await finding({ surface: SURFACE, category: 'note', title: 'Growth & Earnings heading not present — skipping scroll-spy', url: page.url() });
    return;
  }
  await target.scrollIntoViewIfNeeded();
  await page.waitForTimeout(600);
  await snap('scrollspy-growth');

  const aria = await navPill.getAttribute('aria-current').catch(() => null);
  const className = await navPill.getAttribute('class').catch(() => '');
  const looksActive = aria === 'page' || /active|current|bg-/.test(className ?? '');
  if (!looksActive) {
    await finding({
      surface: SURFACE, category: 'polish', severity: 'low',
      title: 'SectionNav pill did not appear active for the scrolled-to section',
      details: 'Verify IntersectionObserver thresholds in SectionNav.tsx.',
      url: page.url(),
    });
  }
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && npx playwright test tests/03-pipeline-existing-run.spec.ts
cat e2e/findings/pipeline-existing-run.md
git add e2e/tests/03-pipeline-existing-run.spec.ts && git commit -m "test(e2e): walk a completed pipeline run end-to-end"
```

---

## Task 6: 04-pipeline-full-analysis.spec.ts — Real run (opt-in)

**Files:**
- Create: `e2e/tests/04-pipeline-full-analysis.spec.ts`

The headline test. Create a real run via `/pipeline/new`, watch SSE, walk the completed report. Default-skipped unless `E2E_RUN_FULL_PIPELINE=1`.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureTheme } from '../fixtures/data.js';
import { waitForPipeline } from '../helpers/waitForPipeline.js';

const SURFACE = 'pipeline-full-analysis';
const ENABLED = process.env.E2E_RUN_FULL_PIPELINE === '1';
const TICKER = process.env.E2E_FIXTURE_TICKER ?? 'AAPL';

test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

test.skip(!ENABLED, 'Set E2E_RUN_FULL_PIPELINE=1 to run this (~$1-3, ~15 min).');

test('full analysis: create run, watch SSE, walk completed report', async ({ page, snap, capturedErrors }) => {
  test.setTimeout(25 * 60 * 1000);
  const theme = await pickFixtureTheme();

  await page.goto('/pipeline/new');
  await page.waitForLoadState('networkidle');
  await snap('new-run-form');

  await page.locator('input[name="ticker"], input[placeholder*="ticker" i]').first().fill(TICKER);
  const themeSelect = page.locator(`select[name="theme"], select[name="theme_id"]`).first();
  if (await themeSelect.count()) {
    await themeSelect.selectOption(String(theme.id));
  } else {
    const combo = page.getByRole('combobox').first();
    if (await combo.count()) {
      await combo.click();
      await page.getByRole('option', { name: new RegExp(theme.name, 'i') }).first().click();
    } else {
      await finding({
        surface: SURFACE, category: 'bug', severity: 'high',
        title: 'No theme selector found on /pipeline/new',
        url: page.url(), screenshot: await snap('no-theme-selector'),
      });
      return;
    }
  }
  await snap('new-run-filled');
  await page.getByRole('button', { name: /start|run|create/i }).first().click();

  await page.waitForURL(/\/pipeline\/[a-f0-9-]+$/i, { timeout: 30_000 });
  const runId = page.url().split('/').pop()!;
  await snap('run-streaming-start');

  let sawStream = false;
  page.on('response', (res) => {
    if (res.url().includes('/stream') && res.status() === 200) sawStream = true;
  });

  await waitForPipeline(runId, { timeoutMs: 20 * 60 * 1000 });
  await page.reload();
  await page.waitForLoadState('networkidle');
  await snap('run-completed');

  if (!sawStream) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'med',
      title: 'No SSE stream connection was observed during the run',
      details: 'Frontend may have polled instead of subscribed. Check usePipelineStream / EventSource wiring.',
      url: page.url(),
    });
  }

  await expect(page.locator('h1, [data-report-ticker]').first()).toContainText(TICKER);
  expect(capturedErrors().filter(e => !/AbortError/.test(e))).toEqual([]);
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && E2E_RUN_FULL_PIPELINE=1 npx playwright test tests/04-pipeline-full-analysis.spec.ts
cat e2e/findings/pipeline-full-analysis.md
git add e2e/tests/04-pipeline-full-analysis.spec.ts && git commit -m "test(e2e): full-analysis end-to-end (opt-in via env var)"
```

---

## Task 7: 05-deep-dive-sections.spec.ts — Per-section deep walk

**Files:**
- Create: `e2e/tests/05-deep-dive-sections.spec.ts`

Surface scope: score chip values, AICompanionPanel double-render (summary+analysis) on data-rich sections, SupplyChainEcosystem card with explore link, WhatChangedPanel.

- [ ] **Step 1: Write the spec**

```ts
import { test } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureCompletedRun } from '../fixtures/data.js';

const SURFACE = 'deep-dive-sections';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

test('score chips show numeric scores, not all em-dashes', async ({ page, snap }) => {
  const run = await pickFixtureCompletedRun();
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');

  const chips = page.locator('[data-score-chip], [data-category-score]');
  const total = await chips.count();
  if (total === 0) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'med',
      title: 'No score chips found on report',
      details: 'Check OverviewBanner / DataRichSection rendering. May be a scoreKeys.ts normalize issue.',
      url: page.url(), screenshot: await snap('no-chips'),
    });
    return;
  }
  let blanks = 0;
  for (let i = 0; i < total; i++) {
    const t = (await chips.nth(i).innerText()).trim();
    if (t === '—' || t === '' || t === 'N/A') blanks++;
  }
  if (blanks / total > 0.5) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'high',
      title: `${blanks}/${total} score chips are blank/em-dash`,
      details: 'Strong signal of scoreKeys.ts DISPLAY_TO_KEY drift after a backend rename.',
      url: page.url(), screenshot: await snap('chips-blank'),
    });
  }
});

test('AICompanionPanel renders twice per data-rich section', async ({ page }) => {
  const run = await pickFixtureCompletedRun();
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');

  const sections = await page.locator('section[id], [data-section]').all();
  for (const section of sections) {
    const id = await section.getAttribute('id') ?? await section.getAttribute('data-section') ?? 'unknown';
    if (id === 'unknown') continue;
    const panels = section.locator('[data-ai-companion], [data-section="summary"], [data-section="analysis"]');
    const n = await panels.count();
    const charts = await section.locator('svg.recharts-surface, canvas').count();
    if (charts > 0 && n < 2) {
      await finding({
        surface: SURFACE, category: 'polish', severity: 'med',
        title: `Section "${id}" has charts but only ${n} AICompanionPanel — expect 2 (summary + analysis)`,
        details: 'Per CLAUDE.md DataRichSection shell contract: summary inside chart grid + analysis full-width below.',
        url: page.url(),
      });
    }
  }
});

test('SupplyChainEcosystem card renders with explore link', async ({ page, snap }) => {
  const run = await pickFixtureCompletedRun();
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');
  const card = page.locator('[data-supply-chain], section').filter({ hasText: /Supply Chain|Ecosystem|Counterparty/i }).first();
  if (!(await card.isVisible().catch(() => false))) {
    await finding({
      surface: SURFACE, category: 'note',
      title: 'No SupplyChainEcosystem card rendered for this run',
      details: 'May be expected if no relationships have been fanned out. Try POST /api/tickers/<t>/relationships/fanout.',
      url: page.url(),
    });
    return;
  }
  await card.scrollIntoViewIfNeeded();
  await snap('supply-chain-card');
  const explore = card.getByRole('link', { name: /2-hop|graph|explore/i });
  if (!(await explore.count())) {
    await finding({
      surface: SURFACE, category: 'improvement', severity: 'low',
      title: 'SupplyChainEcosystem card has no "Explore 2-hop graph" link',
      url: page.url(),
    });
  }
});

test('WhatChangedPanel renders (or is intentionally absent)', async ({ page, snap }) => {
  const run = await pickFixtureCompletedRun();
  await page.goto(`/pipeline/${run.run_id}`);
  await page.waitForLoadState('networkidle');
  const panel = page.locator('#what-changed, [data-what-changed]').first();
  if (await panel.isVisible().catch(() => false)) {
    await panel.scrollIntoViewIfNeeded();
    await snap('what-changed');
  } else {
    await finding({
      surface: SURFACE, category: 'note',
      title: 'WhatChangedPanel not on this run (likely no transcript delta yet)',
      details: 'New feature on feat/transcript-delta-analysis branch — confirm transcript_delta service ran.',
      url: page.url(),
    });
  }
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && npx playwright test tests/05-deep-dive-sections.spec.ts
cat e2e/findings/deep-dive-sections.md
git add e2e/tests/05-deep-dive-sections.spec.ts && git commit -m "test(e2e): deep-dive sections — chips, panels, supply-chain, WhatChanged"
```

---

## Task 8: 06-filings-graph.spec.ts — Filings page + multi-hop graph

**Files:**
- Create: `e2e/tests/06-filings-graph.spec.ts`

Surface scope: `/filings` (TickerFilingsCard, "Fan out" button, SectionReader modal text quality, CurationPanel), then `/filings/graph?root=<ticker>` (RootHeader, depth toggle, HopGroup disclosures, dedup badges).

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureTicker } from '../fixtures/data.js';

const SURFACE = 'filings-graph';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

test('/filings shows ticker filing cards', async ({ page, snap }) => {
  await page.goto('/filings');
  await page.waitForLoadState('networkidle');
  await snap('filings-index');
  const cards = page.locator('[data-ticker-card], [data-ticker]');
  if ((await cards.count()) === 0) {
    await finding({
      surface: SURFACE, category: 'note',
      title: 'No ticker filing cards present',
      details: 'Run POST /api/filings/ingest/<TICKER> for at least one ticker before this test.',
      url: page.url(),
    });
  }
});

test('SectionReader modal opens and shows extracted section text', async ({ page, snap }) => {
  await page.goto('/filings');
  await page.waitForLoadState('networkidle');
  const sectionLink = page.locator('button, a').filter({ hasText: /risk factors|MD&A|business|governance/i }).first();
  if (!(await sectionLink.count())) {
    await finding({
      surface: SURFACE, category: 'note',
      title: 'No section-reader CTA found on /filings — skipping modal test',
      url: page.url(),
    });
    return;
  }
  await sectionLink.click();
  const modal = page.getByRole('dialog').or(page.locator('[data-section-reader]'));
  await modal.first().waitFor({ state: 'visible', timeout: 10_000 });
  await snap('section-reader-open');
  const body = await modal.first().innerText();
  if (body.length < 500) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'med',
      title: 'SectionReader body looks truncated',
      details: `Body is only ${body.length} chars. Check edgar_html extraction.`,
      url: page.url(), screenshot: await snap('section-reader-short'),
    });
  }
});

test('/filings/graph renders root header + hop groups for fixture ticker', async ({ page, snap }) => {
  const ticker = await pickFixtureTicker();
  await page.goto(`/filings/graph?root=${ticker}`);
  await page.waitForLoadState('networkidle');
  await snap(`graph-${ticker}`);

  const root = page.locator('[data-root-header], h1').first();
  await expect(root).toContainText(ticker);

  const depthToggle = page.getByRole('button', { name: /2.?hop|depth.?2|expand/i }).first();
  if (await depthToggle.count()) {
    await depthToggle.click();
    await page.waitForLoadState('networkidle');
    await snap(`graph-${ticker}-hop2`);
  } else {
    await finding({
      surface: SURFACE, category: 'note',
      title: 'No depth-2 toggle found on /filings/graph',
      url: page.url(),
    });
  }

  const dedupBadge = page.locator('text=/\\d+ disclosure/i').first();
  if (await dedupBadge.count()) {
    await dedupBadge.scrollIntoViewIfNeeded();
    await snap(`graph-${ticker}-dedup-badge`);
  }
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && npx playwright test tests/06-filings-graph.spec.ts
cat e2e/findings/filings-graph.md
git add e2e/tests/06-filings-graph.spec.ts && git commit -m "test(e2e): filings index, section reader, multi-hop graph"
```

---

## Task 9: 07-secondary-surfaces.spec.ts — Catalysts, Status, Questions, Library, Performance

**Files:**
- Create: `e2e/tests/07-secondary-surfaces.spec.ts`

Surface scope: smoke-walk each remaining workspace. Surface placeholder/TODO leftovers. Trigger the two status-board drawers.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';

const SURFACE = 'secondary-surfaces';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

const surfaces: Array<{ path: string; label: string; expect?: RegExp }> = [
  { path: '/catalysts',   label: 'catalysts',   expect: /catalyst|earnings|FDA|investor/i },
  { path: '/status',      label: 'status',      expect: /healthy|imminent|stale|triggered|broken/i },
  { path: '/questions',   label: 'questions',   expect: /question|dismiss|resolve|open/i },
  { path: '/library',     label: 'library',     expect: /library|archive|saved/i },
  { path: '/workspace',   label: 'workspace',   expect: /workspace|refresh|verdict/i },
  { path: '/performance', label: 'performance', expect: /performance|track|outcome|verdict/i },
];

for (const s of surfaces) {
  test(`${s.label} page loads cleanly`, async ({ page, snap, capturedErrors }) => {
    await page.goto(s.path);
    await page.waitForLoadState('networkidle');
    await snap(s.label);
    if (s.expect) {
      const text = await page.locator('body').innerText();
      if (!s.expect.test(text)) {
        await finding({
          surface: SURFACE, category: 'polish', severity: 'low',
          title: `${s.label}: expected content matching ${s.expect} not found on the page`,
          url: page.url(), screenshot: await snap(`${s.label}-content-miss`),
        });
      }
    }
    const hits = await page.getByText(/TODO|coming soon|placeholder|lorem ipsum/i).count();
    if (hits) {
      await finding({
        surface: SURFACE, category: 'polish', severity: 'med',
        title: `${s.label}: ${hits} placeholder/TODO strings visible to user`,
        url: page.url(), screenshot: await snap(`${s.label}-placeholder`),
      });
    }
    expect(capturedErrors()).toEqual([]);
  });
}

test('status board: open a ReadThroughDrawer', async ({ page, snap }) => {
  await page.goto('/status');
  await page.waitForLoadState('networkidle');
  const readThroughLink = page.getByRole('button', { name: /read.?through/i }).or(page.getByText(/read.?through/i)).first();
  if (!(await readThroughLink.count())) {
    await finding({
      surface: SURFACE, category: 'note',
      title: 'No read-through CTA found on status board (may be expected if none queued)',
      url: page.url(),
    });
    return;
  }
  await readThroughLink.click();
  await page.waitForTimeout(500);
  await snap('status-readthrough-drawer');
});

test('status board: open an EarningsDrawer', async ({ page, snap }) => {
  await page.goto('/status');
  await page.waitForLoadState('networkidle');
  const earningsLink = page.getByRole('button', { name: /earnings/i }).or(page.getByText(/earnings/i)).first();
  if (!(await earningsLink.count())) {
    await finding({
      surface: SURFACE, category: 'note',
      title: 'No earnings CTA found on status board',
      url: page.url(),
    });
    return;
  }
  await earningsLink.click();
  await page.waitForTimeout(500);
  await snap('status-earnings-drawer');
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && npx playwright test tests/07-secondary-surfaces.spec.ts
cat e2e/findings/secondary-surfaces.md
git add e2e/tests/07-secondary-surfaces.spec.ts && git commit -m "test(e2e): secondary surfaces + status drawers"
```

---

## Task 10: 08-workspace-loop.spec.ts — Workspace refresh (opt-in)

**Files:**
- Create: `e2e/tests/08-workspace-loop.spec.ts`

Surface scope: kick off a workspace run, watch the 5-step SSE stream (update_refresh → research → challenge → differentiate → validate), verify each StepCard + final VerdictBadge. Default-skipped unless `E2E_RUN_WORKSPACE_LOOP=1`.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureCompletedRun } from '../fixtures/data.js';

const SURFACE = 'workspace-loop';
const ENABLED = process.env.E2E_RUN_WORKSPACE_LOOP === '1';

test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

test.skip(!ENABLED, 'Set E2E_RUN_WORKSPACE_LOOP=1 to run this (~$0.30, ~5 min).');

test('kick off workspace loop and observe 5 step cards + verdict', async ({ page, snap, capturedErrors }) => {
  test.setTimeout(10 * 60 * 1000);
  await pickFixtureCompletedRun(); // ensures DB has at least one run to refresh

  await page.goto('/workspace');
  await page.waitForLoadState('networkidle');
  await snap('workspace-index');

  const trigger = page.getByRole('button', { name: /refresh|run|kick/i }).first();
  if (!(await trigger.count())) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'high',
      title: 'No workspace-refresh CTA visible on /workspace',
      details: 'Cannot start a workspace loop from the UI.',
      url: page.url(),
    });
    return;
  }
  await trigger.click();

  await page.waitForURL(/\/workspace\/[a-f0-9-]+$/i, { timeout: 30_000 });
  await snap('workspace-run-streaming');

  const STEPS = ['update_refresh', 'research', 'challenge', 'differentiate', 'validate'];
  for (const step of STEPS) {
    const card = page.locator(`[data-step="${step}"], [data-workspace-step="${step}"]`).first();
    await card.waitFor({ state: 'visible', timeout: 5 * 60 * 1000 });
    await card.scrollIntoViewIfNeeded();
    await snap(`workspace-step-${step}`);
  }

  const verdict = page.locator('[data-verdict-badge]').first();
  await expect(verdict).toBeVisible({ timeout: 60_000 });
  await snap('workspace-verdict');
  expect(capturedErrors().filter(e => !/AbortError/.test(e))).toEqual([]);
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && E2E_RUN_WORKSPACE_LOOP=1 npx playwright test tests/08-workspace-loop.spec.ts
cat e2e/findings/workspace-loop.md
git add e2e/tests/08-workspace-loop.spec.ts && git commit -m "test(e2e): workspace loop end-to-end (opt-in)"
```

---

## Task 11: 09-financial-model.spec.ts — Model, cell edits, history/diff

**Files:**
- Create: `e2e/tests/09-financial-model.spec.ts`

Surface scope: `/model/[ticker]#forecast` ForecastGrid, edit a driver cell → recompute, save → version appears in History tab.

- [ ] **Step 1: Write the spec**

```ts
import { test, expect } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureTicker } from '../fixtures/data.js';
import { api } from '../helpers/api.js';

const SURFACE = 'financial-model';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

test('financial model loads or shows create-model CTA', async ({ page, snap }) => {
  const ticker = await pickFixtureTicker();
  const initial = await api.getModel(ticker).catch(() => null);
  if (!initial?.latest && !initial?.draft) {
    await fetch(`http://127.0.0.1:8000/api/models/${ticker}/initialize`, { method: 'POST' });
  }

  await page.goto(`/model/${ticker}#forecast`);
  await page.waitForLoadState('networkidle');
  await snap('model-forecast');

  const grid = page.locator('[data-forecast-grid], table').first();
  if (!(await grid.isVisible().catch(() => false))) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'high',
      title: `ForecastGrid not visible for ${ticker}`,
      url: page.url(), screenshot: await snap('no-grid'),
    });
    return;
  }

  await page.mouse.wheel(0, 1500);
  await page.waitForTimeout(300);
  await snap('model-scrolled');
});

test('edit a driver cell, save, verify version appears in history', async ({ page, snap, capturedErrors }) => {
  const ticker = await pickFixtureTicker();
  await page.goto(`/model/${ticker}#forecast`);
  await page.waitForLoadState('networkidle');

  const driverCell = page.locator('[data-cell-path^="drivers."]').first();
  if (!(await driverCell.count())) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'high',
      title: 'No driver cells found on ForecastGrid',
      details: 'Check DriverPanel + ForecastGrid wiring of data-cell-path attributes.',
      url: page.url(),
    });
    return;
  }
  await driverCell.click();
  await page.waitForTimeout(200);
  const input = page.locator('input:focus, [data-active-cell-input]').first();
  if (!(await input.count())) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'med',
      title: 'Clicking a driver cell did not surface an editable input',
      url: page.url(), screenshot: await snap('cell-no-edit'),
    });
    return;
  }
  await input.fill('0.42');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(500);
  await snap('cell-edited');

  const save = page.getByRole('button', { name: /save/i }).first();
  if (await save.count()) {
    await save.click();
    await page.waitForTimeout(800);
    await snap('after-save');
  }

  await page.goto(`/model/${ticker}#history`);
  await page.waitForLoadState('networkidle');
  await snap('model-history');
  const versions = page.locator('[data-version], li');
  if ((await versions.count()) === 0) {
    await finding({
      surface: SURFACE, category: 'bug', severity: 'med',
      title: 'No versions listed in History tab after save',
      url: page.url(),
    });
  }

  expect(capturedErrors()).toEqual([]);
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && npx playwright test tests/09-financial-model.spec.ts
cat e2e/findings/financial-model.md
git add e2e/tests/09-financial-model.spec.ts && git commit -m "test(e2e): financial model — grid, cell edit, save, history"
```

---

## Task 12: 10-reverse-dcf.spec.ts — Reverse-DCF tab

**Files:**
- Create: `e2e/tests/10-reverse-dcf.spec.ts`

Surface scope: `/model/[ticker]#reverse-dcf` — ReverseDcfPanel, SensitivityHeatmap, ThesisVsPricedTable, WhatIfScratchPanel; price override re-fetches payload.

- [ ] **Step 1: Write the spec**

```ts
import { test } from '../fixtures/app.js';
import { finding, resetSurface } from '../fixtures/findings.js';
import { pickFixtureTicker } from '../fixtures/data.js';

const SURFACE = 'reverse-dcf';
test.use({ surface: SURFACE });
test.beforeAll(async () => { await resetSurface(SURFACE); });

test('reverse-DCF tab renders all four sub-panels', async ({ page, snap }) => {
  const ticker = await pickFixtureTicker();
  await page.goto(`/model/${ticker}#reverse-dcf`);
  await page.waitForLoadState('networkidle');
  await snap('reverse-dcf');

  const expected = [
    { sel: '[data-reverse-dcf-panel], h2:has-text("Implied")',           name: 'ReverseDcfPanel' },
    { sel: '[data-sensitivity-heatmap], svg.recharts-surface, canvas',   name: 'SensitivityHeatmap' },
    { sel: '[data-thesis-vs-priced], h2:has-text("Thesis")',             name: 'ThesisVsPricedTable' },
    { sel: '[data-whatif-scratch], h2:has-text("What-If")',              name: 'WhatIfScratchPanel' },
  ];
  for (const e of expected) {
    const found = await page.locator(e.sel).first().isVisible().catch(() => false);
    if (!found) {
      await finding({
        surface: SURFACE, category: 'bug', severity: 'med',
        title: `${e.name} not visible on /model/${ticker}#reverse-dcf`,
        url: page.url(), screenshot: await snap(`missing-${e.name}`),
      });
    }
  }
});

test('price override re-fetches reverse-DCF payload', async ({ page, snap }) => {
  const ticker = await pickFixtureTicker();
  await page.goto(`/model/${ticker}#reverse-dcf`);
  await page.waitForLoadState('networkidle');

  const priceInput = page.locator('input[name="price"], input[type="number"]').first();
  if (!(await priceInput.count())) {
    await finding({
      surface: SURFACE, category: 'improvement', severity: 'low',
      title: 'No price-override input visible on reverse-DCF tab',
      details: 'Backend supports ?price=. Consider exposing in WhatIfScratchPanel.',
      url: page.url(),
    });
    return;
  }
  await priceInput.fill('100');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(1500);
  await snap('reverse-dcf-price-100');
});
```

- [ ] **Step 2: Run + review + commit**

```bash
cd e2e && npx playwright test tests/10-reverse-dcf.spec.ts
cat e2e/findings/reverse-dcf.md
git add e2e/tests/10-reverse-dcf.spec.ts && git commit -m "test(e2e): reverse-DCF tab sub-panels + price override"
```

---

## Task 13: Findings aggregator + summary report

**Files:**
- Create: `e2e/scripts/aggregate-findings.ts`

Goal: walk `e2e/findings/*.md`, merge into `e2e/reports/summary-<ISO>.md` with severity counts, all bugs at the top, then improvements/polish, then per-surface detail.

- [ ] **Step 1: Write the aggregator**

```ts
#!/usr/bin/env tsx
import { promises as fs } from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(import.meta.dirname, '..');
const FINDINGS = path.join(ROOT, 'findings');
const REPORTS = path.join(ROOT, 'reports');

async function main() {
  const files = (await fs.readdir(FINDINGS).catch(() => []))
    .filter(f => f.endsWith('.md'))
    .sort();
  await fs.mkdir(REPORTS, { recursive: true });
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  const out = path.join(REPORTS, `summary-${ts}.md`);

  const sections: string[] = [];
  const counts = { bug: 0, polish: 0, improvement: 0, note: 0 };
  const byCat: Record<string, string[]> = { bug: [], polish: [], improvement: [], note: [] };

  for (const f of files) {
    const body = await fs.readFile(path.join(FINDINGS, f), 'utf8');
    const surface = path.basename(f, '.md');
    sections.push(`\n## ${surface}\n\n${body.replace(/^# Findings:.*\n+/, '')}`);

    for (const m of body.matchAll(/\*\*(BUG|POLISH|IMPROVEMENT|NOTE)(?: \[(low|med|high)\])?\*\* — (.+)/g)) {
      const cat = m[1].toLowerCase() as keyof typeof counts;
      counts[cat]++;
      byCat[cat].push(`- (${surface}) ${m[3]}`);
    }
  }

  const toc = files.map(f => `- [${path.basename(f, '.md')}](#${path.basename(f, '.md').toLowerCase()})`).join('\n');

  const summary = [
    `# E2E Findings — ${new Date().toISOString()}`,
    '',
    '## Counts',
    `- bugs: ${counts.bug}`,
    `- polish: ${counts.polish}`,
    `- improvements: ${counts.improvement}`,
    `- notes: ${counts.note}`,
    '',
    '## All bugs',
    byCat.bug.length ? byCat.bug.join('\n') : '_(none)_',
    '',
    '## All improvement opportunities',
    byCat.improvement.length ? byCat.improvement.join('\n') : '_(none)_',
    '',
    '## All polish notes',
    byCat.polish.length ? byCat.polish.join('\n') : '_(none)_',
    '',
    '## Surfaces',
    toc,
    '',
    '---',
    sections.join('\n'),
  ].join('\n');

  await fs.writeFile(out, summary);
  // eslint-disable-next-line no-console
  console.log(`wrote ${out}`);
}

main().catch((e) => { console.error(e); process.exit(1); });
```

- [ ] **Step 2: Run after a full suite**

```bash
cd e2e && npm test && npm run report && npm run open-report
```

Expected: a summary markdown opens with counts, all bugs at the top, then improvements/polish, then per-surface detail.

- [ ] **Step 3: Commit**

```bash
git add e2e/scripts/aggregate-findings.ts
git commit -m "chore(e2e): findings aggregator → reports/summary-<ts>.md"
```

---

## Task 14: End-to-end shakedown + final commit

- [ ] **Step 1: Start both servers** (in two terminals)

```bash
# T1: backend
source backend/venv/bin/activate
uvicorn backend.app.main:app --reload

# T2: frontend
cd frontend && npm run dev
```

- [ ] **Step 2: Run the fixture-mode suite**

```bash
cd e2e && npm test
```

- [ ] **Step 3: Aggregate + open the report**

```bash
npm run report && npm run open-report
```

- [ ] **Step 4: Triage the summary**

Skim `e2e/reports/summary-*.md`. For each bug, decide:
- File a TODO entry in `TODO.md` if it's a real issue
- Open a GitHub issue via `gh issue create` for anything substantial

- [ ] **Step 5: (Optional) Run the cost-tier full suite**

```bash
cd e2e && npm run test:full
```

Use sparingly — after major changes to `backend/app/graph/` or `services/workspace*.py`.

- [ ] **Step 6: Push branch**

```bash
git push -u origin feat/e2e-playwright-suite
```

Then either merge to main or open a PR via `gh pr create`.

---

## Self-Review

**Spec coverage check** — surfaces from CLAUDE.md and route inventory:

| Surface                            | Task |
|------------------------------------|------|
| `/` (Themes/Discovery)             | 4    |
| `/theme/[id]`                      | 4    |
| `/filings`                         | 8    |
| `/filings/graph`                   | 8    |
| `/catalysts`                       | 9    |
| `/status` + drawers                | 9    |
| `/workspace` + `/workspace/[runId]`| 10   |
| `/questions`                       | 9    |
| `/library`                         | 9    |
| `/performance`                     | 9    |
| `/pipeline/new`                    | 6    |
| `/pipeline/[runId]` — streaming    | 6    |
| `/pipeline/[runId]` — completed    | 5, 7 |
| `/report/[runId]` (redirect)       | (implicit — same component as pipeline) |
| `/model/[ticker]#forecast`         | 11   |
| `/model/[ticker]#reverse-dcf`      | 12   |
| `/model/[ticker]#history`          | 11   |
| Global: nav, ⌘K, print, 404        | 3    |
| Deep-dive sections × 9             | 5, 7 |
| SupplyChainEcosystem card          | 7    |
| WhatChangedPanel                   | 7    |
| Findings aggregator                | 13   |
| End-to-end shakedown               | 14   |

`/report/[runId]` is a redirect to `/pipeline/[runId]` — covered transitively. All other surfaces have a task.

**Placeholder scan** — no "TODO" / "fill in details" / "similar to Task N" left in any task body. Code blocks present at every step that changes code. Commands have expected output where useful.

**Type consistency** — `finding()`, `shot()`, `api.*`, `pickFixture*()`, `waitForPipeline()` signatures match across tasks. Surface name strings used in `test.use({ surface })` and in `finding({ surface })` match the file basename convention.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-12-playwright-e2e-suite.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for catching findings drift early — after Task 5 you'll already have real screenshots of your live app.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Good if you want me to narrate findings out loud as they land.

Which approach?
