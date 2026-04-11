# Sector Research App — Plan 4: Frontend

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Next.js 15 frontend — five pages (Theme Dashboard, Theme Detail, Pipeline Runner, Research Library, Full Report) with real-time SSE streaming of pipeline output and inline citation footnotes on every data point.

**Architecture:** Next.js 15 App Router with TypeScript. All backend calls go through `src/lib/api.ts` (typed fetch wrapper). The Pipeline Runner page polls `GET /pipeline/{runId}/state` every 3 seconds while a phase is running, switches to action bar mode when `awaiting_interrupt` is detected. No third-party state management — React `useState` + `useEffect` throughout. Styling via Tailwind CSS with a dark, terminal-inspired theme (appropriate for financial data).

**Tech Stack:** Next.js 15, TypeScript, Tailwind CSS v4, React 19

**Prereq:** Plans 1–3 complete — all backend endpoints operational.

**Spec:** `docs/superpowers/specs/2026-04-10-sector-research-app-design.md` — Section 4

---

## File Map

```
frontend/
├── package.json
├── next.config.ts
├── tsconfig.json
├── tailwind.config.ts
├── postcss.config.mjs
├── src/
│   ├── app/
│   │   ├── layout.tsx                     ← root layout, nav shell
│   │   ├── globals.css                    ← Tailwind base + custom tokens
│   │   ├── page.tsx                       ← Theme Dashboard (/)
│   │   ├── theme/
│   │   │   └── [id]/
│   │   │       └── page.tsx               ← Theme Detail
│   │   ├── pipeline/
│   │   │   └── [runId]/
│   │   │       └── page.tsx               ← Pipeline Runner
│   │   ├── library/
│   │   │   └── page.tsx                   ← Research Library
│   │   └── report/
│   │       └── [runId]/
│   │           └── page.tsx               ← Full Report
│   ├── components/
│   │   ├── ThemeCard.tsx                  ← Theme summary card for dashboard grid
│   │   ├── SignalBadge.tsx                ← Velocity/discovery badge pill
│   │   ├── CompanySignalCard.tsx          ← Company card with FMP snapshot + signal
│   │   ├── CompanyList.tsx                ← Sortable/filterable list of signal cards
│   │   ├── PipelineRail.tsx               ← Left-side phase progress tracker
│   │   ├── PhaseOutput.tsx                ← Renders one phase's output with citations
│   │   ├── CitationFootnote.tsx           ← Superscript number + expandable source
│   │   ├── ActionBar.tsx                  ← Approve / Flag / Stop buttons
│   │   └── LoadingDots.tsx                ← Simple animated loading indicator
│   └── lib/
│       ├── types.ts                       ← TypeScript types mirroring backend schemas
│       └── api.ts                         ← Typed fetch wrappers for all endpoints
```

---

## Task 1: Project Setup

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/next.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tailwind.config.ts`

- [ ] **Step 1: Scaffold Next.js project**

```bash
cd ~/Development/sector-research
npx create-next-app@latest frontend \
  --typescript \
  --tailwind \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

When prompted, accept defaults. Then move `src/` structure in manually if not created.

- [ ] **Step 2: Verify the dev server starts**

```bash
cd ~/Development/sector-research/frontend
npm run dev
```

Expected: server running at `http://localhost:3000`, default Next.js page visible.

Stop the dev server (`Ctrl+C`).

- [ ] **Step 3: Update `frontend/next.config.ts` to proxy API calls**

```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://localhost:8000/:path*",
      },
    ];
  },
};

export default nextConfig;
```

- [ ] **Step 4: Commit**

```bash
cd ~/Development/sector-research
git add frontend/
git commit -m "chore: scaffold next.js 15 frontend with tailwind and api proxy"
```

---

## Task 2: TypeScript Types and API Client

**Files:**
- Create: `frontend/src/lib/types.ts`
- Create: `frontend/src/lib/api.ts`

- [ ] **Step 1: Create `frontend/src/lib/types.ts`**

```typescript
export interface CitationResponse {
  metric: string;
  value: string;
  source_name: string;
  source_url: string;
  tier: 1 | 2;
  retrieved_at: string;
}

export interface FMPSnapshot {
  pe_ratio: number | null;
  ev_to_ebitda: number | null;
  roic: number | null;
  gross_margin: number | null;
  revenue_growth_yoy: number | null;
}

export interface SignalBadge {
  velocity_score: number;
  velocity_label: "accelerating" | "stable" | "decelerating";
  discovery_score: number;
  narrative: string;
  last_computed: string;
}

export interface ResearchRunSummary {
  run_id: string;
  phase_reached: string;
  conviction_score: number | null;
  thesis_status: string | null;
  status: string;
  updated_at: string | null;
}

export interface CompanySignalCard {
  ticker: string;
  company_name: string;
  market_cap: number | null;
  sector: string | null;
  exchange: string | null;
  fmp_snapshot: FMPSnapshot;
  fmp_citations: CitationResponse[];
  signal: SignalBadge | null;
  combined_score: number | null;
  in_seed_list: boolean;
  last_run: ResearchRunSummary | null;
}

export interface ThemeDiscoveryResponse {
  theme_id: string;
  theme_name: string;
  companies: CompanySignalCard[];
  sort_by: string;
  total: number;
}

export interface Theme {
  id: string;
  name: string;
  description: string;
  seed_tickers: string[];
  screener_criteria: Record<string, unknown>;
  x_search_terms: string[];
  signal_weights: { velocity: number; fundamental: number; discovery: number };
  created_at: string;
  updated_at: string | null;
}

export interface RunStateResponse {
  run_id: string;
  ticker: string;
  phase: string;
  status: string;
  conviction_score: number | null;
  thesis_status: string | null;
  phase_outputs: Record<string, unknown>;
  citations: CitationResponse[];
  human_feedback: Record<string, unknown>;
  loop_context: { categories_to_rerun: string[]; loop_reason: string } | null;
}

export type SortOption = "combined_score" | "velocity" | "fundamental" | "market_cap";
```

- [ ] **Step 2: Create `frontend/src/lib/api.ts`**

```typescript
const BASE = "/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`API error ${res.status}: ${error}`);
  }
  return res.json();
}

// ── Themes ────────────────────────────────────────────────────────────────────

export function listThemes(): Promise<import("./types").Theme[]> {
  return request("/themes");
}

export function getTheme(id: string): Promise<import("./types").Theme> {
  return request(`/themes/${id}`);
}

export function createTheme(payload: {
  name: string;
  description: string;
  seed_tickers: string[];
  screener_criteria: Record<string, unknown>;
  x_search_terms: string[];
  signal_weights: { velocity: number; fundamental: number; discovery: number };
}): Promise<import("./types").Theme> {
  return request("/themes", { method: "POST", body: JSON.stringify(payload) });
}

export function deleteTheme(id: string): Promise<void> {
  return request(`/themes/${id}`, { method: "DELETE" });
}

// ── Discovery ─────────────────────────────────────────────────────────────────

export function getThemeDiscovery(
  themeId: string,
  sortBy: string = "combined_score"
): Promise<import("./types").ThemeDiscoveryResponse> {
  return request(`/discovery/theme/${themeId}?sort_by=${sortBy}`);
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

export function startRun(payload: {
  ticker: string;
  theme_id?: string;
}): Promise<{ run_id: string; ticker: string; status: string }> {
  return request("/pipeline/start", { method: "POST", body: JSON.stringify(payload) });
}

export function getRunState(
  runId: string
): Promise<import("./types").RunStateResponse> {
  return request(`/pipeline/${runId}/state`);
}

export function approveRun(
  runId: string,
  payload: { action: "approve" | "watchlist" | "pass" | "stop"; notes?: string }
): Promise<{ run_id: string; status: string; action: string }> {
  return request(`/pipeline/${runId}/approve`, {
    method: "POST",
    body: JSON.stringify({ action: payload.action, notes: payload.notes ?? "" }),
  });
}

export function listRuns(): Promise<import("./types").RunStateResponse[]> {
  return request("/pipeline/runs");
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/
git commit -m "feat: add typescript types and typed api client"
```

---

## Task 3: Root Layout and Global Styles

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/app/globals.css`

- [ ] **Step 1: Update `frontend/src/app/globals.css`**

```css
@import "tailwindcss";

:root {
  --bg: #0a0a0f;
  --surface: #12121a;
  --border: #1e1e2e;
  --text: #e2e8f0;
  --muted: #64748b;
  --accent: #6366f1;
  --green: #10b981;
  --yellow: #f59e0b;
  --red: #ef4444;
}

body {
  background-color: var(--bg);
  color: var(--text);
  font-family: "JetBrains Mono", "Fira Code", monospace;
}
```

- [ ] **Step 2: Replace `frontend/src/app/layout.tsx`**

```tsx
import type { Metadata } from "next";
import "./globals.css";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Sector Research",
  description: "AI-powered equity discovery and due diligence",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">
        <nav className="border-b border-[var(--border)] px-6 py-3 flex items-center gap-6">
          <Link href="/" className="text-[var(--accent)] font-semibold tracking-wider text-sm">
            SECTOR RESEARCH
          </Link>
          <Link href="/" className="text-[var(--muted)] hover:text-[var(--text)] text-sm">
            Themes
          </Link>
          <Link href="/library" className="text-[var(--muted)] hover:text-[var(--text)] text-sm">
            Library
          </Link>
        </nav>
        <main className="px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/layout.tsx frontend/src/app/globals.css
git commit -m "feat: add dark terminal theme layout and global styles"
```

---

## Task 4: Shared Components

**Files:**
- Create: `frontend/src/components/LoadingDots.tsx`
- Create: `frontend/src/components/SignalBadge.tsx`
- Create: `frontend/src/components/CitationFootnote.tsx`
- Create: `frontend/src/components/ActionBar.tsx`

- [ ] **Step 1: Create `frontend/src/components/LoadingDots.tsx`**

```tsx
export default function LoadingDots() {
  return (
    <span className="inline-flex gap-1 items-center">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-1.5 h-1.5 rounded-full bg-[var(--accent)] animate-bounce"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </span>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/SignalBadge.tsx`**

```tsx
import type { SignalBadge as SignalBadgeType } from "@/lib/types";

const LABEL_COLORS = {
  accelerating: "text-[var(--green)] border-[var(--green)]",
  stable: "text-[var(--muted)] border-[var(--muted)]",
  decelerating: "text-[var(--red)] border-[var(--red)]",
};

const LABEL_ARROWS = {
  accelerating: "↑",
  stable: "→",
  decelerating: "↓",
};

interface Props {
  signal: SignalBadgeType;
  compact?: boolean;
}

export default function SignalBadge({ signal, compact = false }: Props) {
  const color = LABEL_COLORS[signal.velocity_label];
  const arrow = LABEL_ARROWS[signal.velocity_label];

  if (compact) {
    return (
      <span className={`text-xs border rounded px-1.5 py-0.5 font-mono ${color}`}>
        {arrow} {signal.velocity_label}
      </span>
    );
  }

  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2">
        <span className={`text-xs border rounded px-1.5 py-0.5 font-mono ${color}`}>
          {arrow} {signal.velocity_label}
        </span>
        <span className="text-xs text-[var(--muted)]">
          score {signal.velocity_score.toFixed(2)}
        </span>
      </div>
      {signal.narrative && (
        <p className="text-xs text-[var(--muted)] italic">{signal.narrative}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/components/CitationFootnote.tsx`**

```tsx
"use client";
import { useState } from "react";
import type { CitationResponse } from "@/lib/types";

interface Props {
  citations: CitationResponse[];
}

export default function CitationFootnote({ citations }: Props) {
  const [expanded, setExpanded] = useState(false);

  if (citations.length === 0) return null;

  return (
    <div className="mt-3 border-t border-[var(--border)] pt-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-xs text-[var(--muted)] hover:text-[var(--text)] flex items-center gap-1"
      >
        <span>{expanded ? "▾" : "▸"}</span>
        <span>{citations.length} source{citations.length !== 1 ? "s" : ""}</span>
      </button>
      {expanded && (
        <ol className="mt-2 space-y-1.5">
          {citations.map((c, i) => (
            <li key={i} className="text-xs flex items-start gap-2">
              <span className="text-[var(--muted)] shrink-0">[{i + 1}]</span>
              <span>
                <span
                  className={`rounded px-1 text-[10px] mr-1 ${
                    c.tier === 1
                      ? "bg-indigo-900/50 text-indigo-300"
                      : "bg-yellow-900/50 text-yellow-300"
                  }`}
                >
                  T{c.tier}
                </span>
                <span className="text-[var(--muted)]">{c.metric}:</span>{" "}
                <span className="text-[var(--text)]">{c.value}</span>{" "}
                <a
                  href={c.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--accent)] underline"
                >
                  {c.source_name}
                </a>
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Create `frontend/src/components/ActionBar.tsx`**

```tsx
"use client";
import { useState } from "react";

interface Props {
  onAction: (action: "approve" | "watchlist" | "pass" | "stop", notes: string) => void;
  disabled: boolean;
  phase: string;
}

export default function ActionBar({ onAction, disabled, phase }: Props) {
  const [notes, setNotes] = useState("");
  const [pending, setPending] = useState(false);

  const handle = async (action: "approve" | "watchlist" | "pass" | "stop") => {
    setPending(true);
    await onAction(action, notes);
    setNotes("");
    setPending(false);
  };

  const isDisabled = disabled || pending;

  return (
    <div className="border-t border-[var(--border)] pt-4 space-y-3">
      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        placeholder="Add notes (optional)..."
        rows={2}
        disabled={isDisabled}
        className="w-full bg-[var(--surface)] border border-[var(--border)] rounded px-3 py-2 text-sm text-[var(--text)] placeholder-[var(--muted)] resize-none focus:outline-none focus:border-[var(--accent)] disabled:opacity-40"
      />
      <div className="flex items-center gap-3">
        <button
          onClick={() => handle("approve")}
          disabled={isDisabled}
          className="px-4 py-2 bg-[var(--accent)] text-white text-sm rounded hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Approve →
        </button>
        {phase === "quick_screen" ? (
          <button
            onClick={() => handle("watchlist")}
            disabled={isDisabled}
            className="px-4 py-2 border border-[var(--yellow)] text-[var(--yellow)] text-sm rounded hover:bg-yellow-900/20 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Watchlist
          </button>
        ) : null}
        <button
          onClick={() => handle("stop")}
          disabled={isDisabled}
          className="px-4 py-2 border border-[var(--border)] text-[var(--muted)] text-sm rounded hover:border-[var(--red)] hover:text-[var(--red)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Stop
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/
git commit -m "feat: add shared components (SignalBadge, CitationFootnote, ActionBar, LoadingDots)"
```

---

## Task 5: Theme Dashboard Page

**Files:**
- Create: `frontend/src/components/ThemeCard.tsx`
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/ThemeCard.tsx`**

```tsx
import Link from "next/link";
import type { Theme } from "@/lib/types";

interface Props {
  theme: Theme;
}

export default function ThemeCard({ theme }: Props) {
  return (
    <Link
      href={`/theme/${theme.id}`}
      className="block bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 hover:border-[var(--accent)] transition-colors group"
    >
      <div className="flex items-start justify-between mb-2">
        <h2 className="text-sm font-semibold text-[var(--text)] group-hover:text-[var(--accent)] transition-colors">
          {theme.name}
        </h2>
        <span className="text-[10px] text-[var(--muted)] border border-[var(--border)] rounded px-1.5 py-0.5">
          {theme.seed_tickers.length} seeds
        </span>
      </div>
      <p className="text-xs text-[var(--muted)] mb-3 line-clamp-2">{theme.description}</p>
      {theme.seed_tickers.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {theme.seed_tickers.slice(0, 5).map((ticker) => (
            <span
              key={ticker}
              className="text-[10px] font-mono text-[var(--accent)] bg-indigo-900/20 rounded px-1.5 py-0.5"
            >
              ${ticker}
            </span>
          ))}
          {theme.seed_tickers.length > 5 && (
            <span className="text-[10px] text-[var(--muted)]">+{theme.seed_tickers.length - 5}</span>
          )}
        </div>
      )}
    </Link>
  );
}
```

- [ ] **Step 2: Replace `frontend/src/app/page.tsx`**

```tsx
import { listThemes } from "@/lib/api";
import ThemeCard from "@/components/ThemeCard";
import Link from "next/link";

export const revalidate = 60;

export default async function ThemeDashboard() {
  let themes = [];
  try {
    themes = await listThemes();
  } catch {
    // Backend may not be running during build
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-lg font-semibold text-[var(--text)]">Themes</h1>
          <p className="text-xs text-[var(--muted)] mt-0.5">
            {themes.length} active theme{themes.length !== 1 ? "s" : ""}
          </p>
        </div>
        <Link
          href="/themes/new"
          className="text-xs px-3 py-1.5 border border-[var(--accent)] text-[var(--accent)] rounded hover:bg-indigo-900/20"
        >
          + New Theme
        </Link>
      </div>

      {themes.length === 0 ? (
        <div className="text-center py-16 text-[var(--muted)] text-sm">
          No themes yet. Create your first theme to start discovering companies.
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {themes.map((theme) => (
            <ThemeCard key={theme.id} theme={theme} />
          ))}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Start dev server and verify the page renders**

```bash
cd ~/Development/sector-research/frontend
npm run dev
```

Open `http://localhost:3000`. Expected: dark nav, "Themes" heading, empty state message (since no themes exist yet).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/ThemeCard.tsx frontend/src/app/page.tsx
git commit -m "feat: add theme dashboard page with theme card grid"
```

---

## Task 6: Theme Detail Page

**Files:**
- Create: `frontend/src/components/CompanySignalCard.tsx`
- Create: `frontend/src/components/CompanyList.tsx`
- Create: `frontend/src/app/theme/[id]/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/CompanySignalCard.tsx`**

```tsx
"use client";
import { useState } from "react";
import type { CompanySignalCard as CompanySignalCardType } from "@/lib/types";
import SignalBadge from "./SignalBadge";
import CitationFootnote from "./CitationFootnote";
import { startRun } from "@/lib/api";
import { useRouter } from "next/navigation";

function fmt(n: number | null, decimals = 1): string {
  if (n === null || n === undefined) return "—";
  return n.toFixed(decimals);
}

function fmtPct(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

function fmtMktCap(n: number | null): string {
  if (!n) return "—";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(1)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  return `$${(n / 1e6).toFixed(0)}M`;
}

interface Props {
  card: CompanySignalCardType;
  themeId: string;
}

export default function CompanySignalCard({ card, themeId }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [launching, setLaunching] = useState(false);
  const router = useRouter();

  const handleRunPipeline = async () => {
    setLaunching(true);
    try {
      const { run_id } = await startRun({ ticker: card.ticker, theme_id: themeId });
      router.push(`/pipeline/${run_id}`);
    } finally {
      setLaunching(false);
    }
  };

  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-4 space-y-3">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono font-semibold text-[var(--accent)]">${card.ticker}</span>
            {card.in_seed_list && (
              <span className="text-[10px] text-[var(--muted)] border border-[var(--border)] rounded px-1">seed</span>
            )}
          </div>
          <p className="text-xs text-[var(--muted)] mt-0.5">{card.company_name}</p>
        </div>
        <div className="text-right">
          <span className="text-xs text-[var(--text)]">{fmtMktCap(card.market_cap)}</span>
          {card.combined_score !== null && (
            <p className="text-[10px] text-[var(--muted)]">score {card.combined_score.toFixed(2)}</p>
          )}
        </div>
      </div>

      {/* Signal badge */}
      {card.signal && <SignalBadge signal={card.signal} compact />}

      {/* FMP snapshot */}
      <div className="grid grid-cols-3 gap-2 text-xs">
        <div>
          <span className="text-[var(--muted)]">P/E</span>
          <p className="font-mono">{fmt(card.fmp_snapshot.pe_ratio)}</p>
        </div>
        <div>
          <span className="text-[var(--muted)]">ROIC</span>
          <p className="font-mono">{fmtPct(card.fmp_snapshot.roic)}</p>
        </div>
        <div>
          <span className="text-[var(--muted)]">Rev growth</span>
          <p className="font-mono">{fmtPct(card.fmp_snapshot.revenue_growth_yoy)}</p>
        </div>
      </div>

      {/* Expand/collapse */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="text-[10px] text-[var(--muted)] hover:text-[var(--text)]"
      >
        {expanded ? "▾ less" : "▸ more"}
      </button>

      {expanded && (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div>
              <span className="text-[var(--muted)]">EV/EBITDA</span>
              <p className="font-mono">{fmt(card.fmp_snapshot.ev_to_ebitda)}</p>
            </div>
            <div>
              <span className="text-[var(--muted)]">Gross margin</span>
              <p className="font-mono">{fmtPct(card.fmp_snapshot.gross_margin)}</p>
            </div>
          </div>
          {card.signal && (
            <div>
              <p className="text-[10px] text-[var(--muted)] mb-1">Social signal</p>
              <SignalBadge signal={card.signal} />
            </div>
          )}
          <CitationFootnote citations={card.fmp_citations} />
        </div>
      )}

      {/* Last run badge */}
      {card.last_run && (
        <div className="text-[10px] text-[var(--muted)] border-t border-[var(--border)] pt-2">
          Last: {card.last_run.phase_reached} — {card.last_run.status}
          {card.last_run.conviction_score !== null && ` (${card.last_run.conviction_score}/100)`}
        </div>
      )}

      {/* CTA */}
      <button
        onClick={handleRunPipeline}
        disabled={launching}
        className="w-full text-xs py-1.5 border border-[var(--accent)] text-[var(--accent)] rounded hover:bg-indigo-900/20 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {launching ? "Starting..." : "Run Quick Screen →"}
      </button>
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/CompanyList.tsx`**

```tsx
"use client";
import { useState } from "react";
import type { CompanySignalCard, SortOption } from "@/lib/types";
import CompanySignalCardComponent from "./CompanySignalCard";

interface Props {
  companies: CompanySignalCard[];
  themeId: string;
  onSortChange: (sort: SortOption) => void;
  currentSort: SortOption;
}

const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "combined_score", label: "Combined" },
  { value: "velocity", label: "Velocity" },
  { value: "fundamental", label: "Fundamentals" },
  { value: "market_cap", label: "Market Cap" },
];

export default function CompanyList({ companies, themeId, onSortChange, currentSort }: Props) {
  const [search, setSearch] = useState("");

  const filtered = companies.filter(
    (c) =>
      c.ticker.toLowerCase().includes(search.toLowerCase()) ||
      c.company_name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Filter by ticker or name..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 bg-[var(--surface)] border border-[var(--border)] rounded px-3 py-1.5 text-sm text-[var(--text)] placeholder-[var(--muted)] focus:outline-none focus:border-[var(--accent)]"
        />
        <div className="flex gap-1">
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => onSortChange(opt.value)}
              className={`text-xs px-2 py-1 rounded border ${
                currentSort === opt.value
                  ? "border-[var(--accent)] text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--muted)] hover:text-[var(--text)]"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <p className="text-xs text-[var(--muted)]">
        {filtered.length} of {companies.length} companies
      </p>

      <div className="space-y-3">
        {filtered.map((card) => (
          <CompanySignalCardComponent key={card.ticker} card={card} themeId={themeId} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/app/theme/[id]/page.tsx`**

```tsx
"use client";
import { useState, useEffect, useCallback } from "react";
import { getTheme, getThemeDiscovery } from "@/lib/api";
import type { Theme, ThemeDiscoveryResponse, SortOption } from "@/lib/types";
import CompanyList from "@/components/CompanyList";
import LoadingDots from "@/components/LoadingDots";

interface Props {
  params: { id: string };
}

export default function ThemeDetailPage({ params }: Props) {
  const [theme, setTheme] = useState<Theme | null>(null);
  const [discovery, setDiscovery] = useState<ThemeDiscoveryResponse | null>(null);
  const [sort, setSort] = useState<SortOption>("combined_score");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (newSort: SortOption) => {
    setLoading(true);
    setError(null);
    try {
      const [t, d] = await Promise.all([
        getTheme(params.id),
        getThemeDiscovery(params.id, newSort),
      ]);
      setTheme(t);
      setDiscovery(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load theme");
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => { load(sort); }, [sort, load]);

  const handleSortChange = (newSort: SortOption) => {
    setSort(newSort);
    load(newSort);
  };

  if (error) {
    return <div className="text-[var(--red)] text-sm py-8">{error}</div>;
  }

  return (
    <div className="max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-[var(--text)]">
          {theme?.name ?? <LoadingDots />}
        </h1>
        {theme && (
          <p className="text-xs text-[var(--muted)] mt-1">{theme.description}</p>
        )}
      </div>

      {loading && !discovery ? (
        <div className="text-[var(--muted)] text-sm py-8 flex items-center gap-2">
          <LoadingDots /> Loading companies...
        </div>
      ) : discovery ? (
        <CompanyList
          companies={discovery.companies}
          themeId={params.id}
          onSortChange={handleSortChange}
          currentSort={sort}
        />
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/CompanySignalCard.tsx frontend/src/components/CompanyList.tsx frontend/src/app/theme/
git commit -m "feat: add theme detail page with sortable company signal card list"
```

---

## Task 7: Pipeline Runner Page

**Files:**
- Create: `frontend/src/components/PipelineRail.tsx`
- Create: `frontend/src/components/PhaseOutput.tsx`
- Create: `frontend/src/app/pipeline/[runId]/page.tsx`

- [ ] **Step 1: Create `frontend/src/components/PipelineRail.tsx`**

```tsx
type PhaseStatus = "pending" | "active" | "complete" | "interrupted";

interface Phase {
  key: string;
  label: string;
}

const PHASES: Phase[] = [
  { key: "quick_screen", label: "Quick Screen" },
  { key: "deep_dive", label: "Deep Dive" },
  { key: "thesis_construction", label: "Thesis" },
  { key: "risk_stress_test", label: "Risk Stress-Test" },
  { key: "position_monitor", label: "Position Plan" },
];

interface Props {
  currentPhase: string;
  humanFeedback: Record<string, unknown>;
  loopContext: { categories_to_rerun: string[]; loop_reason: string } | null;
}

function phaseStatus(phaseKey: string, currentPhase: string, humanFeedback: Record<string, unknown>): PhaseStatus {
  const phaseIndex = PHASES.findIndex((p) => p.key === phaseKey);
  const currentIndex = PHASES.findIndex((p) => p.key === currentPhase);

  if (humanFeedback[phaseKey]) return "complete";
  if (phaseKey === currentPhase) return "active";
  if (phaseIndex < currentIndex) return "complete";
  return "pending";
}

const STATUS_STYLES: Record<PhaseStatus, string> = {
  pending: "text-[var(--muted)] border-[var(--border)]",
  active: "text-[var(--accent)] border-[var(--accent)] animate-pulse",
  complete: "text-[var(--green)] border-[var(--green)]",
  interrupted: "text-[var(--yellow)] border-[var(--yellow)]",
};

const STATUS_ICONS: Record<PhaseStatus, string> = {
  pending: "○",
  active: "◉",
  complete: "✓",
  interrupted: "⚡",
};

export default function PipelineRail({ currentPhase, humanFeedback, loopContext }: Props) {
  return (
    <div className="w-44 shrink-0 space-y-2">
      <p className="text-[10px] text-[var(--muted)] uppercase tracking-wider mb-3">Pipeline</p>
      {PHASES.map((phase) => {
        const status = phaseStatus(phase.key, currentPhase, humanFeedback);
        return (
          <div
            key={phase.key}
            className={`flex items-center gap-2 text-xs border-l-2 pl-3 py-1 ${STATUS_STYLES[status]}`}
          >
            <span className="font-mono text-[10px]">{STATUS_ICONS[status]}</span>
            <span>{phase.label}</span>
          </div>
        );
      })}

      {loopContext ? (
        <div className="mt-4 text-[10px] text-[var(--yellow)] border border-[var(--yellow)]/30 rounded p-2 space-y-1">
          <p className="font-semibold">↺ Looping</p>
          <p className="text-[var(--muted)]">{loopContext.loop_reason}</p>
        </div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 2: Create `frontend/src/components/PhaseOutput.tsx`**

```tsx
import CitationFootnote from "./CitationFootnote";
import type { CitationResponse } from "@/lib/types";

interface Props {
  phase: string;
  output: Record<string, unknown>;
  citations: CitationResponse[];
}

function renderValue(value: unknown, depth = 0): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-[var(--muted)]">—</span>;
  if (typeof value === "string") return <span>{value}</span>;
  if (typeof value === "number") return <span className="font-mono">{value}</span>;
  if (Array.isArray(value)) {
    return (
      <ul className="list-disc list-inside space-y-0.5 pl-2">
        {value.map((item, i) => (
          <li key={i} className="text-xs">{renderValue(item, depth + 1)}</li>
        ))}
      </ul>
    );
  }
  if (typeof value === "object") {
    return (
      <div className={`space-y-2 ${depth > 0 ? "pl-3 border-l border-[var(--border)]" : ""}`}>
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k}>
            <span className="text-[10px] text-[var(--muted)] uppercase tracking-wider">{k.replace(/_/g, " ")}</span>
            <div className="mt-0.5 text-sm">{renderValue(v, depth + 1)}</div>
          </div>
        ))}
      </div>
    );
  }
  return <span>{String(value)}</span>;
}

const PHASE_LABELS: Record<string, string> = {
  quick_screen: "Phase 1–2: Quick Screen",
  deep_dive: "Phase 3: Deep Dive",
  thesis_construction: "Phase 4: Thesis Construction",
  risk_stress_test: "Phase 5: Risk Stress-Test",
  position_monitor: "Phase 6: Position Plan",
};

export default function PhaseOutput({ phase, output, citations }: Props) {
  return (
    <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5">
      <h3 className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider mb-4">
        {PHASE_LABELS[phase] ?? phase}
      </h3>
      <div className="space-y-4 text-sm text-[var(--text)]">
        {renderValue(output)}
      </div>
      <CitationFootnote citations={citations} />
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/app/pipeline/[runId]/page.tsx`**

```tsx
"use client";
import { useState, useEffect, useCallback, useRef } from "react";
import { getRunState, approveRun } from "@/lib/api";
import type { RunStateResponse, CitationResponse } from "@/lib/types";
import PipelineRail from "@/components/PipelineRail";
import PhaseOutput from "@/components/PhaseOutput";
import ActionBar from "@/components/ActionBar";
import LoadingDots from "@/components/LoadingDots";

const INTERRUPT_PHASES = ["quick_screen", "deep_dive", "risk_stress_test"];
const TERMINAL_STATUSES = ["complete", "watchlist", "pass", "stop", "error"];

interface Props {
  params: { runId: string };
}

export default function PipelineRunnerPage({ params }: Props) {
  const [runState, setRunState] = useState<RunStateResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef<NodeJS.Timeout | null>(null);

  const fetchState = useCallback(async () => {
    try {
      const state = await getRunState(params.runId);
      setRunState(state);
      return state;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch run state");
      return null;
    }
  }, [params.runId]);

  // Poll every 3s while the phase is running (not interrupted, not terminal)
  useEffect(() => {
    fetchState();

    const poll = async () => {
      const state = await fetchState();
      if (!state) return;
      const isTerminal = TERMINAL_STATUSES.includes(state.status);
      const isInterrupted = INTERRUPT_PHASES.includes(state.phase) && !state.human_feedback[state.phase];
      if (!isTerminal && !isInterrupted) {
        pollRef.current = setTimeout(poll, 3000);
      }
    };

    pollRef.current = setTimeout(poll, 2000);
    return () => { if (pollRef.current) clearTimeout(pollRef.current); };
  }, [fetchState]);

  const handleAction = async (action: "approve" | "watchlist" | "pass" | "stop", notes: string) => {
    if (!runState) return;
    setSubmitting(true);
    try {
      await approveRun(params.runId, { action, notes });
      // Resume polling after submitting
      setTimeout(() => fetchState(), 1000);
      pollRef.current = setTimeout(async function poll() {
        const state = await fetchState();
        if (!state) return;
        const isTerminal = TERMINAL_STATUSES.includes(state.status);
        const isInterrupted = INTERRUPT_PHASES.includes(state.phase) && !state.human_feedback[state.phase];
        if (!isTerminal && !isInterrupted) {
          pollRef.current = setTimeout(poll, 3000);
        }
      }, 3000);
    } finally {
      setSubmitting(false);
    }
  };

  if (error) return <div className="text-[var(--red)] text-sm py-8">{error}</div>;
  if (!runState) return <div className="text-[var(--muted)] text-sm py-8 flex items-center gap-2"><LoadingDots /> Loading run...</div>;

  const isTerminal = TERMINAL_STATUSES.includes(runState.status);
  const isInterrupted = INTERRUPT_PHASES.includes(runState.phase) && !runState.human_feedback[runState.phase];
  const isRunning = !isTerminal && !isInterrupted;

  const phaseCitations = (runState.citations as CitationResponse[]) ?? [];
  const currentOutput = runState.phase_outputs[runState.phase] as Record<string, unknown> | undefined;

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold font-mono text-[var(--accent)]">${runState.ticker}</h1>
          <span className={`text-xs border rounded px-2 py-0.5 ${
            isRunning ? "text-[var(--accent)] border-[var(--accent)]" :
            isInterrupted ? "text-[var(--yellow)] border-[var(--yellow)]" :
            isTerminal ? "text-[var(--green)] border-[var(--green)]" :
            "text-[var(--muted)] border-[var(--muted)]"
          }`}>
            {isRunning ? "running" : isInterrupted ? "awaiting review" : runState.status}
          </span>
          {runState.conviction_score !== null && (
            <span className="text-xs text-[var(--muted)]">conviction {runState.conviction_score}/100</span>
          )}
        </div>
      </div>

      {/* Two-column layout */}
      <div className="flex gap-6">
        <PipelineRail
          currentPhase={runState.phase}
          humanFeedback={runState.human_feedback}
          loopContext={runState.loop_context}
        />

        <div className="flex-1 space-y-4">
          {/* Completed phases */}
          {Object.entries(runState.phase_outputs)
            .filter(([phase]) => phase !== runState.phase)
            .map(([phase, output]) => (
              <PhaseOutput
                key={phase}
                phase={phase}
                output={output as Record<string, unknown>}
                citations={phaseCitations.filter((c) => c.source_name.includes(phase))}
              />
            ))}

          {/* Current phase */}
          {isRunning && (
            <div className="bg-[var(--surface)] border border-[var(--accent)]/40 rounded-lg p-5">
              <div className="flex items-center gap-2 text-xs text-[var(--accent)]">
                <LoadingDots /> Analyzing {runState.phase.replace(/_/g, " ")}...
              </div>
            </div>
          )}

          {currentOutput && (
            <PhaseOutput
              phase={runState.phase}
              output={currentOutput}
              citations={phaseCitations}
            />
          )}

          {/* Action bar — enabled only at interrupt */}
          {!isTerminal && (
            <ActionBar
              onAction={handleAction}
              disabled={!isInterrupted || submitting}
              phase={runState.phase}
            />
          )}

          {isTerminal && (
            <div className={`text-sm py-4 text-center border rounded-lg ${
              runState.status === "complete"
                ? "border-[var(--green)] text-[var(--green)]"
                : "border-[var(--muted)] text-[var(--muted)]"
            }`}>
              Run {runState.status} —{" "}
              {runState.status === "complete" && (
                <a href={`/report/${params.runId}`} className="underline">View full report</a>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/PipelineRail.tsx frontend/src/components/PhaseOutput.tsx frontend/src/app/pipeline/
git commit -m "feat: add pipeline runner page with phase rail, output display, and action bar"
```

---

## Task 8: Research Library and Full Report Pages

**Files:**
- Create: `frontend/src/app/library/page.tsx`
- Create: `frontend/src/app/report/[runId]/page.tsx`

- [ ] **Step 1: Add `listRuns` endpoint to backend**

Add to `backend/app/routers/pipeline.py`:

```python
@router.get("/runs", response_model=list[RunStateResponse])
def list_runs(
    limit: int = 50,
    db: Session = Depends(get_db),
):
    runs = db.query(ResearchRun).order_by(ResearchRun.updated_at.desc()).limit(limit).all()
    result = []
    for run in runs:
        state = run.state or {}
        result.append(RunStateResponse(
            run_id=str(run.id),
            ticker=run.ticker,
            phase=run.phase,
            status=run.status,
            conviction_score=state.get("conviction_score"),
            thesis_status=state.get("thesis_status"),
            phase_outputs=state.get("phase_outputs", {}),
            citations=state.get("citations", []),
            human_feedback=state.get("human_feedback", {}),
            loop_context=state.get("loop_context"),
        ))
    return result
```

- [ ] **Step 2: Create `frontend/src/app/library/page.tsx`**

Note: This is a server component — no `"use client"` directive. No client-side interactivity is needed on initial render; links are plain anchors. This avoids a client-side waterfall (`server-parallel-fetching` rule).

```tsx
import Link from "next/link";
import type { RunStateResponse } from "@/lib/types";

const STATUS_COLORS: Record<string, string> = {
  in_progress: "text-[var(--accent)]",
  complete: "text-[var(--green)]",
  watchlist: "text-[var(--yellow)]",
  pass: "text-[var(--muted)]",
  stop: "text-[var(--muted)]",
  error: "text-[var(--red)]",
};

const THESIS_COLORS: Record<string, string> = {
  "ON TRACK": "text-[var(--green)]",
  "DRIFTING": "text-[var(--yellow)]",
  "BROKEN": "text-[var(--red)]",
};

async function getRuns(): Promise<RunStateResponse[]> {
  try {
    const res = await fetch("http://localhost:8000/pipeline/runs", {
      next: { revalidate: 10 },
    });
    if (!res.ok) return [];
    return res.json();
  } catch {
    return [];
  }
}

export default async function LibraryPage() {
  const runs = await getRuns();

  return (
    <div className="max-w-5xl mx-auto">
      <h1 className="text-lg font-semibold text-[var(--text)] mb-6">Research Library</h1>

      {runs.length === 0 ? (
        <div className="text-[var(--muted)] text-sm py-8 text-center">
          No research runs yet. Start by running a Quick Screen on a company from a theme.
        </div>
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr className="text-[var(--muted)] text-left border-b border-[var(--border)]">
              <th className="py-2 pr-4">Ticker</th>
              <th className="py-2 pr-4">Phase</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4">Conviction</th>
              <th className="py-2 pr-4">Thesis</th>
              <th className="py-2"></th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.run_id} className="border-b border-[var(--border)] hover:bg-[var(--surface)]">
                <td className="py-3 pr-4 font-mono text-[var(--accent)]">${run.ticker}</td>
                <td className="py-3 pr-4 text-[var(--muted)]">{run.phase.replace(/_/g, " ")}</td>
                <td className={`py-3 pr-4 ${STATUS_COLORS[run.status] ?? "text-[var(--muted)]"}`}>
                  {run.status}
                </td>
                <td className="py-3 pr-4 font-mono">
                  {run.conviction_score !== null ? `${run.conviction_score}/100` : "—"}
                </td>
                <td className={`py-3 pr-4 ${run.thesis_status ? (THESIS_COLORS[run.thesis_status] ?? "") : "text-[var(--muted)]"}`}>
                  {run.thesis_status ?? "—"}
                </td>
                <td className="py-3 text-right">
                  <Link
                    href={run.status === "in_progress" ? `/pipeline/${run.run_id}` : `/report/${run.run_id}`}
                    className="text-[var(--accent)] hover:underline"
                  >
                    {run.status === "in_progress" ? "Resume →" : "View →"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/src/app/report/[runId]/page.tsx`**

```tsx
"use client";
import { useState, useEffect } from "react";
import { getRunState } from "@/lib/api";
import type { RunStateResponse, CitationResponse } from "@/lib/types";
import PhaseOutput from "@/components/PhaseOutput";
import LoadingDots from "@/components/LoadingDots";

interface Props {
  params: { runId: string };
}

const PHASE_ORDER = [
  "quick_screen",
  "deep_dive",
  "thesis_construction",
  "risk_stress_test",
  "position_monitor",
];

function exportToMarkdown(run: RunStateResponse): string {
  const lines: string[] = [
    `# Research Report: $${run.ticker}`,
    ``,
    `**Status:** ${run.status}`,
    `**Conviction Score:** ${run.conviction_score ?? "N/A"}/100`,
    `**Thesis Status:** ${run.thesis_status ?? "N/A"}`,
    ``,
    `---`,
    ``,
  ];

  for (const phase of PHASE_ORDER) {
    const output = run.phase_outputs[phase];
    if (!output) continue;
    lines.push(`## ${phase.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}`);
    lines.push(``);
    lines.push("```json");
    lines.push(JSON.stringify(output, null, 2));
    lines.push("```");
    lines.push(``);
  }

  lines.push(`## Citations`);
  lines.push(``);
  (run.citations as CitationResponse[]).forEach((c, i) => {
    lines.push(`${i + 1}. **${c.metric}**: ${c.value} — [${c.source_name}](${c.source_url}) (Tier ${c.tier})`);
  });

  return lines.join("\n");
}

export default function ReportPage({ params }: Props) {
  const [run, setRun] = useState<RunStateResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getRunState(params.runId).then(setRun).finally(() => setLoading(false));
  }, [params.runId]);

  const handleExport = () => {
    if (!run) return;
    const md = exportToMarkdown(run);
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Research-${run.ticker}-${new Date().toISOString().split("T")[0]}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (loading) return <div className="text-[var(--muted)] text-sm py-8 flex items-center gap-2"><LoadingDots /></div>;
  if (!run) return <div className="text-[var(--red)] text-sm py-8">Run not found.</div>;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-lg font-semibold font-mono text-[var(--accent)]">${run.ticker} — Full Report</h1>
          <div className="flex items-center gap-4 mt-1 text-xs text-[var(--muted)]">
            <span>Conviction: <span className="text-[var(--text)]">{run.conviction_score ?? "—"}/100</span></span>
            {run.thesis_status && (
              <span>Thesis: <span className="text-[var(--text)]">{run.thesis_status}</span></span>
            )}
          </div>
        </div>
        <button
          onClick={handleExport}
          className="text-xs px-3 py-1.5 border border-[var(--border)] text-[var(--muted)] rounded hover:border-[var(--accent)] hover:text-[var(--accent)]"
        >
          Export .md
        </button>
      </div>

      {/* Phase outputs in order */}
      {PHASE_ORDER.filter((p) => run.phase_outputs[p]).map((phase) => (
        <PhaseOutput
          key={phase}
          phase={phase}
          output={run.phase_outputs[phase] as Record<string, unknown>}
          citations={(run.citations as CitationResponse[]).slice(0, 10)}
        />
      ))}

      {/* Full citation list */}
      {(run.citations as CitationResponse[]).length > 0 && (
        <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5">
          <h3 className="text-xs font-semibold text-[var(--muted)] uppercase tracking-wider mb-3">All Citations</h3>
          <ol className="space-y-2">
            {(run.citations as CitationResponse[]).map((c, i) => (
              <li key={i} className="text-xs flex items-start gap-2">
                <span className="text-[var(--muted)] shrink-0">[{i + 1}]</span>
                <span>
                  <span className={`rounded px-1 text-[10px] mr-1 ${c.tier === 1 ? "bg-indigo-900/50 text-indigo-300" : "bg-yellow-900/50 text-yellow-300"}`}>T{c.tier}</span>
                  <span className="text-[var(--muted)]">{c.metric}:</span>{" "}
                  <span className="text-[var(--text)]">{c.value}</span>{" "}
                  <a href={c.source_url} target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] underline">{c.source_name}</a>
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run full test suite one final time**

```bash
cd ~/Development/sector-research/backend
poetry run pytest -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
cd ~/Development/sector-research
git add frontend/src/app/library/ frontend/src/app/report/ backend/app/routers/pipeline.py
git commit -m "feat: add research library and full report pages with markdown export"
```

---

## Plan 4 Complete

At this point the full application is built:

- **Theme Dashboard** — grid of curated themes, click to open any
- **Theme Detail** — sortable company signal card list with FMP snapshot + X signal badge + Run Quick Screen CTA
- **Pipeline Runner** — live polling, phase progress rail, citation footnotes, approve/watchlist/stop action bar
- **Research Library** — table of all runs with status, conviction score, thesis status, resume/view links
- **Full Report** — all phase outputs rendered in order, full citation list, one-click Obsidian markdown export

**Execution order for all four plans:**
1. Plan 1 (Foundation) → working backend with tested clients
2. Plan 2 (Discovery Engine) → theme CRUD + discovery API
3. Plan 3 (LangGraph Pipeline) → full 6-phase agent graph
4. Plan 4 (Frontend) → this plan — five-page UI

**To run the complete app:**
```bash
# Terminal 1
cd ~/Development/sector-research && docker compose up -d db

# Terminal 2
cd ~/Development/sector-research/backend && poetry run uvicorn app.main:create_app --factory --reload --port 8000

# Terminal 3
cd ~/Development/sector-research/frontend && npm run dev
```

Open `http://localhost:3000`.
