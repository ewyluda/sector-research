# Company Workspace — Slice 1 Implementation Plan (Shell + Re-home)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the persistent `/company/[ticker]` shell (header + tab strip + lens selector) and re-home the existing Research, Model, and Filings surfaces under it, with Overview/Financials/Transcripts as empty-state placeholders.

**Architecture:** A client-rendered Next.js route group `app/company/[ticker]/` whose `layout.tsx` renders a persistent company header, a 7-tab strip, and a `Lens` theme selector (state in a `?lens=<themeId>` search param). The Research tab resolves the latest completed research run for the ticker and renders the existing `DeepDiveDashboard`; Model and Filings tabs reuse existing ticker-scoped components. A new backend `GET /api/company/{ticker}/header` (FastAPI router + `company_snapshot` service over the shared `FMPClient`) feeds the header's live quote + profile.

**Tech Stack:** FastAPI + Pydantic + async SQLAlchemy (backend), `FMPClient` (shared `app.state.fmp` singleton), Next.js 16 App Router + React 19 + Tailwind v4 (frontend), stdlib `unittest` (backend tests).

**Spec:** `docs/superpowers/specs/2026-05-25-company-workspace-design.md`

**Conventions to honor (from CLAUDE.md):**
- Backend uses **absolute imports** rooted at project root (`from backend.app... import ...`); run commands from project root with `backend/venv` active.
- Every backend endpoint normalizes `ticker = ticker.upper()` at entry.
- Frontend pages/components in this app are `"use client"` and read route params via `useParams()` (matches `/model/[ticker]` and `/pipeline/[runId]`). Follow that pattern — do **not** introduce server components with `await params`.
- **Next.js 16 caveat:** before writing frontend routing code, skim `frontend/node_modules/next/dist/docs/` for the current `useParams` / `useSearchParams` / layout conventions (per `frontend/AGENTS.md`).
- Every backend data-client method returns `tuple[data, Citation]` — unpack accordingly.

---

## File Structure

**Backend (create):**
- `backend/app/services/company_snapshot.py` — `CompanyHeader` Pydantic model + `build_company_header(fmp, ticker)` service function. One responsibility: assemble the header payload from FMP quote + profile.
- `backend/app/api/company.py` — `APIRouter(prefix="/company")` exposing `GET /{ticker}/header`. Thin; delegates to the service.
- `backend/tests/test_company_snapshot.py` — unit tests for `build_company_header` with a stub FMP client.

**Backend (modify):**
- `backend/app/main.py` — import and register the company router with `prefix="/api"`.

**Frontend (create):**
- `frontend/lib/reportProps.ts` — pure `reportToDashboardProps(report)` mapping `ReportResponse` → `DeepDiveDashboard` props.
- `frontend/components/company/EmptyState.tsx` — placeholder/empty-state block with optional CTA.
- `frontend/components/company/PricePill.tsx` — price + Δ + %Δ colored pill.
- `frontend/components/company/LensSelector.tsx` — theme lens dropdown bound to `?lens=`.
- `frontend/components/company/TabStrip.tsx` — the 7-tab primary nav, lens-param-preserving.
- `frontend/components/company/CompanyHeader.tsx` — identity + PricePill + LensSelector; fetches `getCompanyHeader`.
- `frontend/components/company/ResearchTab.tsx` — latest-run resolver + run selector + report render.
- `frontend/components/company/ThesesTab.tsx` — status-board rows + run history + open questions for the ticker.
- `frontend/components/model/ModelWorkspace.tsx` — the existing model page body, extracted to take a `ticker` prop.
- `frontend/app/company/[ticker]/layout.tsx` — the shell.
- `frontend/app/company/[ticker]/page.tsx` — Overview placeholder.
- `frontend/app/company/[ticker]/financials/page.tsx` — Financials placeholder.
- `frontend/app/company/[ticker]/transcripts/page.tsx` — Transcripts placeholder.
- `frontend/app/company/[ticker]/research/page.tsx` — renders `ResearchTab`.
- `frontend/app/company/[ticker]/model/page.tsx` — renders `ModelWorkspace`.
- `frontend/app/company/[ticker]/filings/page.tsx` — renders `TickerFilingsCard`.
- `frontend/app/company/[ticker]/theses/page.tsx` — renders `ThesesTab`.

**Frontend (modify):**
- `frontend/lib/api.ts` — add `CompanyHeader` type + `getCompanyHeader(ticker)`.
- `frontend/app/model/[ticker]/page.tsx` — replace body with a thin wrapper rendering `ModelWorkspace`.
- `frontend/components/Nav.tsx` — add a ticker-jump input that routes to `/company/<TICKER>`.

---

## Task 1: Backend — company header service

**Files:**
- Create: `backend/app/services/company_snapshot.py`
- Create: `backend/tests/test_company_snapshot.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_company_snapshot.py`:

```python
"""Unit tests for build_company_header.

The service assembles the company-workspace header from FMP quote + profile.
We stub the FMP client (its methods return tuple[data, Citation]) — no network.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_snapshot import build_company_header


class _StubFMP:
    """Returns canned (data, citation) tuples; citation is irrelevant here."""

    def __init__(self, quote, profile):
        self._quote = quote
        self._profile = profile

    async def get_quote(self, ticker):
        return self._quote, None

    async def get_company_profile(self, ticker):
        return self._profile, None


class BuildCompanyHeaderTest(unittest.IsolatedAsyncioTestCase):
    async def test_maps_quote_and_profile(self):
        fmp = _StubFMP(
            quote={"price": 214.36, "change": -5.57, "changePercentage": -2.53},
            profile={
                "companyName": "Nebius Group N.V.",
                "exchangeShortName": "NasdaqGS",
                "image": "https://logo.example/nbis.png",
                "currency": "USD",
            },
        )
        header = await build_company_header(fmp, "nbis")
        self.assertEqual(header.ticker, "NBIS")
        self.assertEqual(header.name, "Nebius Group N.V.")
        self.assertEqual(header.exchange, "NasdaqGS")
        self.assertEqual(header.logo_url, "https://logo.example/nbis.png")
        self.assertEqual(header.currency, "USD")
        self.assertEqual(header.price, 214.36)
        self.assertEqual(header.change, -5.57)
        self.assertEqual(header.change_pct, -2.53)
        self.assertEqual(header.delay_label, "15 min delay")

    async def test_degrades_when_quote_missing(self):
        fmp = _StubFMP(quote={}, profile={"companyName": "Acme Inc"})
        header = await build_company_header(fmp, "ACME")
        self.assertEqual(header.ticker, "ACME")
        self.assertEqual(header.name, "Acme Inc")
        self.assertIsNone(header.price)
        self.assertIsNone(header.change)
        self.assertIsNone(header.change_pct)

    async def test_handles_non_dict_payloads(self):
        fmp = _StubFMP(quote=[], profile=None)
        header = await build_company_header(fmp, "ZZZ")
        self.assertEqual(header.ticker, "ZZZ")
        self.assertIsNone(header.name)
        self.assertIsNone(header.price)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run (from project root, venv active):
```bash
source backend/venv/bin/activate
python -m unittest backend.tests.test_company_snapshot -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.app.services.company_snapshot'`.

- [ ] **Step 3: Write the service**

Create `backend/app/services/company_snapshot.py`:

```python
"""Company-workspace snapshot service.

Slice 1 surfaces only the header (live quote + identity from FMP). Later slices
add /overview, /financials, /transcripts to this module.
"""
from typing import Optional

from pydantic import BaseModel


class CompanyHeader(BaseModel):
    ticker: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    logo_url: Optional[str] = None
    currency: Optional[str] = None
    price: Optional[float] = None
    change: Optional[float] = None
    change_pct: Optional[float] = None
    delay_label: str = "15 min delay"


def _as_dict(value) -> dict:
    """FMP helpers return dicts, but degrade defensively to {} for [] / None."""
    return value if isinstance(value, dict) else {}


async def build_company_header(fmp, ticker: str) -> CompanyHeader:
    """Assemble the persistent header payload.

    `fmp` is the shared FMPClient (app.state.fmp). Quote feeds price/change;
    profile feeds identity. Missing data degrades to None — the shell never
    needs more than the ticker to render.
    """
    ticker = ticker.upper()

    try:
        quote, _ = await fmp.get_quote(ticker)
    except Exception:
        quote = {}
    try:
        profile, _ = await fmp.get_company_profile(ticker)
    except Exception:
        profile = {}

    quote = _as_dict(quote)
    profile = _as_dict(profile)

    price = quote.get("price")
    if price is None:
        price = profile.get("price")

    return CompanyHeader(
        ticker=ticker,
        name=profile.get("companyName"),
        exchange=profile.get("exchangeShortName"),
        logo_url=profile.get("image"),
        currency=profile.get("currency"),
        price=price,
        change=quote.get("change"),
        change_pct=quote.get("changePercentage"),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python -m unittest backend.tests.test_company_snapshot -v
```
Expected: PASS (3 tests OK).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/company_snapshot.py backend/tests/test_company_snapshot.py
git commit -m "feat(company): company header snapshot service"
```

---

## Task 2: Backend — company router + registration

**Files:**
- Create: `backend/app/api/company.py`
- Modify: `backend/app/main.py` (router imports block ~line 12-30, registration block ~line 167-182)

- [ ] **Step 1: Write the router**

Create `backend/app/api/company.py`:

```python
"""Company workspace API.

Routes:
  GET /api/company/{ticker}/header   → live quote + identity for the shell header
"""
from fastapi import APIRouter, Request

from backend.app.services.company_snapshot import CompanyHeader, build_company_header

router = APIRouter(prefix="/company", tags=["company"])


@router.get("/{ticker}/header", response_model=CompanyHeader)
async def get_company_header(ticker: str, request: Request) -> CompanyHeader:
    return await build_company_header(request.app.state.fmp, ticker)
```

- [ ] **Step 2: Register the router in main.py**

In `backend/app/main.py`, find the router imports (near the other `from backend.app.api.* import router as *_router` lines) and add:

```python
from backend.app.api.company import router as company_router
```

Then in the registration block (alongside the other `app.include_router(..., prefix="/api")` calls, near line 167-182) add:

```python
app.include_router(company_router, prefix="/api")
```

- [ ] **Step 3: Verify the app imports and the route is wired**

Run (project root, venv active):
```bash
python -c "from backend.app.main import app; print([r.path for r in app.routes if 'company' in r.path])"
```
Expected output contains: `['/api/company/{ticker}/header']`

- [ ] **Step 4: Smoke the endpoint (optional, needs a live FMP key + running DB-less import)**

If a dev server is convenient:
```bash
uvicorn backend.app.main:app --reload &
sleep 3
curl -s http://127.0.0.1:8000/api/company/AAPL/header | head -c 400
kill %1
```
Expected: JSON with `"ticker":"AAPL"` and a numeric `price` (or nulls if FMP key absent — still valid shape).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/company.py backend/app/main.py
git commit -m "feat(company): GET /api/company/{ticker}/header endpoint"
```

---

## Task 3: Frontend — API client for header

**Files:**
- Modify: `frontend/lib/api.ts` (add type + fetch fn near the model client fns, ~line 1409+)

- [ ] **Step 1: Add the type and client function**

Append to `frontend/lib/api.ts` (after the model client functions, before any trailing exports):

```ts
// ── Company workspace ─────────────────────────────────────────────────────────

export interface CompanyHeader {
  ticker: string;
  name: string | null;
  exchange: string | null;
  logo_url: string | null;
  currency: string | null;
  price: number | null;
  change: number | null;
  change_pct: number | null;
  delay_label: string;
}

export async function getCompanyHeader(ticker: string): Promise<CompanyHeader> {
  return apiFetch<CompanyHeader>(`/api/company/${encodeURIComponent(ticker)}/header`);
}
```

- [ ] **Step 2: Type-check**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no new errors referencing `api.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(company): typed getCompanyHeader client"
```

---

## Task 4: Frontend — EmptyState + PricePill primitives

**Files:**
- Create: `frontend/components/company/EmptyState.tsx`
- Create: `frontend/components/company/PricePill.tsx`

- [ ] **Step 1: Write EmptyState**

Create `frontend/components/company/EmptyState.tsx`:

```tsx
import Link from "next/link";

export function EmptyState({
  title,
  message,
  cta,
}: {
  title: string;
  message: string;
  cta?: { href: string; label: string };
}) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-10 text-center">
      <p className="text-sm font-semibold text-[var(--text)]">{title}</p>
      <p className="mt-1 text-sm text-[var(--text-muted)]">{message}</p>
      {cta && (
        <Link
          href={cta.href}
          className="mt-4 inline-block rounded-md bg-[var(--primary)] px-3 py-1.5 text-sm text-white hover:bg-[var(--primary-dk)]"
        >
          {cta.label}
        </Link>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Write PricePill**

Create `frontend/components/company/PricePill.tsx`:

```tsx
export function PricePill({
  price,
  change,
  changePct,
  currency,
  delayLabel,
}: {
  price: number | null;
  change: number | null;
  changePct: number | null;
  currency: string | null;
  delayLabel: string;
}) {
  if (price == null) {
    return <span className="text-sm text-[var(--text-muted)]">—</span>;
  }
  const up = (change ?? 0) >= 0;
  const sym = currency === "USD" || currency == null ? "$" : "";
  const tone = up ? "text-[var(--success,#16a34a)]" : "text-[var(--error,#dc2626)]";
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-sm font-semibold text-[var(--text)]">
        {sym}
        {price.toFixed(2)}
      </span>
      {change != null && changePct != null && (
        <span className={`rounded px-1.5 py-0.5 font-mono text-xs ${tone}`}>
          {up ? "+" : ""}
          {change.toFixed(2)} ({up ? "+" : ""}
          {changePct.toFixed(2)}%)
        </span>
      )}
      <span className="text-[10px] text-[var(--text-muted)]">{delayLabel}</span>
    </div>
  );
}
```

- [ ] **Step 3: Type-check**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/company/EmptyState.tsx frontend/components/company/PricePill.tsx
git commit -m "feat(company): EmptyState + PricePill primitives"
```

---

## Task 5: Frontend — LensSelector + TabStrip

**Files:**
- Create: `frontend/components/company/LensSelector.tsx`
- Create: `frontend/components/company/TabStrip.tsx`

- [ ] **Step 1: Write LensSelector**

Create `frontend/components/company/LensSelector.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { themes } from "@/lib/api";
import type { Theme } from "@/lib/api";

export function LensSelector() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const lens = params.get("lens") ?? "";
  const [themeList, setThemeList] = useState<Theme[]>([]);

  useEffect(() => {
    themes.list().then(setThemeList).catch(() => setThemeList([]));
  }, []);

  function onChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const next = new URLSearchParams(Array.from(params.entries()));
    if (e.target.value) next.set("lens", e.target.value);
    else next.delete("lens");
    const qs = next.toString();
    router.push(qs ? `${pathname}?${qs}` : pathname);
  }

  return (
    <label className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
      Lens:
      <select
        value={lens}
        onChange={onChange}
        className="rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-1 text-xs text-[var(--text)]"
      >
        <option value="">All</option>
        {themeList.map((t) => (
          <option key={t.id} value={t.id}>
            {t.name}
          </option>
        ))}
      </select>
    </label>
  );
}
```

- [ ] **Step 2: Write TabStrip**

Create `frontend/components/company/TabStrip.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import clsx from "clsx";

const TABS: { seg: string; label: string }[] = [
  { seg: "", label: "Overview" },
  { seg: "financials", label: "Financials" },
  { seg: "transcripts", label: "Transcripts" },
  { seg: "research", label: "Research" },
  { seg: "model", label: "Model" },
  { seg: "filings", label: "Filings" },
  { seg: "theses", label: "Theses" },
];

export function TabStrip({ ticker }: { ticker: string }) {
  const pathname = usePathname();
  const params = useSearchParams();
  const lens = params.get("lens");
  const base = `/company/${ticker}`;
  const qs = lens ? `?lens=${encodeURIComponent(lens)}` : "";

  return (
    <nav className="flex items-center gap-1 overflow-x-auto border-b border-[var(--border)] px-2">
      {TABS.map(({ seg, label }) => {
        const href = seg ? `${base}/${seg}` : base;
        const active = seg ? pathname === href : pathname === base;
        return (
          <Link
            key={seg || "overview"}
            href={`${href}${qs}`}
            className={clsx(
              "whitespace-nowrap px-3 py-2 text-sm transition-colors",
              active
                ? "border-b-2 border-[var(--primary)] font-medium text-[var(--text)]"
                : "text-[var(--text-muted)] hover:text-[var(--text)]"
            )}
          >
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
```

- [ ] **Step 3: Type-check**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. (`clsx` is already a dependency — used in `Nav.tsx`.)

- [ ] **Step 4: Commit**

```bash
git add frontend/components/company/LensSelector.tsx frontend/components/company/TabStrip.tsx
git commit -m "feat(company): lens selector + primary tab strip"
```

---

## Task 6: Frontend — CompanyHeader component

**Files:**
- Create: `frontend/components/company/CompanyHeader.tsx`

- [ ] **Step 1: Write CompanyHeader**

Create `frontend/components/company/CompanyHeader.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { getCompanyHeader } from "@/lib/api";
import type { CompanyHeader as CompanyHeaderData } from "@/lib/api";
import { PricePill } from "./PricePill";
import { LensSelector } from "./LensSelector";

export function CompanyHeader({ ticker }: { ticker: string }) {
  const [data, setData] = useState<CompanyHeaderData | null>(null);

  useEffect(() => {
    let alive = true;
    getCompanyHeader(ticker)
      .then((d) => alive && setData(d))
      .catch(() => alive && setData(null));
    return () => {
      alive = false;
    };
  }, [ticker]);

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="flex items-center gap-3">
        {data?.logo_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={data.logo_url} alt="" className="h-7 w-7 rounded" />
        )}
        <div>
          <div className="flex items-center gap-2">
            <span className="text-base font-semibold text-[var(--text)]">{ticker}</span>
            {data?.exchange && (
              <span className="text-xs text-[var(--text-muted)]">{data.exchange}</span>
            )}
          </div>
          {data?.name && (
            <div className="text-xs text-[var(--text-muted)]">{data.name}</div>
          )}
        </div>
        <div className="ml-2">
          <PricePill
            price={data?.price ?? null}
            change={data?.change ?? null}
            changePct={data?.change_pct ?? null}
            currency={data?.currency ?? null}
            delayLabel={data?.delay_label ?? "15 min delay"}
          />
        </div>
      </div>
      <LensSelector />
    </div>
  );
}
```

- [ ] **Step 2: Type-check**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/company/CompanyHeader.tsx
git commit -m "feat(company): persistent company header with live price + lens"
```

---

## Task 7: Frontend — shell layout + placeholder pages

**Files:**
- Create: `frontend/app/company/[ticker]/layout.tsx`
- Create: `frontend/app/company/[ticker]/page.tsx`
- Create: `frontend/app/company/[ticker]/financials/page.tsx`
- Create: `frontend/app/company/[ticker]/transcripts/page.tsx`

- [ ] **Step 1: Skim the Next.js 16 routing docs**

Run:
```bash
ls frontend/node_modules/next/dist/docs/ 2>/dev/null | head
```
Confirm `useParams`/`useSearchParams` from `next/navigation` are the client-side accessors (this app already uses them in `app/model/[ticker]/page.tsx`). This task follows that exact pattern — a `"use client"` layout reading `useParams()`.

- [ ] **Step 2: Write the layout (the shell)**

Create `frontend/app/company/[ticker]/layout.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { CompanyHeader } from "@/components/company/CompanyHeader";
import { TabStrip } from "@/components/company/TabStrip";

export default function CompanyLayout({ children }: { children: React.ReactNode }) {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();

  return (
    <div className="mx-auto max-w-[1400px]">
      <div className="sticky top-14 z-30 bg-[var(--surface)]" data-print-hide="true">
        <CompanyHeader ticker={ticker} />
        <TabStrip ticker={ticker} />
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}
```

- [ ] **Step 3: Write the Overview placeholder**

Create `frontend/app/company/[ticker]/page.tsx`:

```tsx
import { EmptyState } from "@/components/company/EmptyState";

export default function OverviewPage() {
  return (
    <EmptyState
      title="Overview"
      message="Coming soon — company statistics grid, price chart, and Bulls/Bears."
    />
  );
}
```

- [ ] **Step 4: Write the Financials placeholder**

Create `frontend/app/company/[ticker]/financials/page.tsx`:

```tsx
import { EmptyState } from "@/components/company/EmptyState";

export default function FinancialsPage() {
  return (
    <EmptyState
      title="Financials"
      message="Coming soon — income statement, balance sheet, and cash flow with period slider and common-size toggles."
    />
  );
}
```

- [ ] **Step 5: Write the Transcripts placeholder**

Create `frontend/app/company/[ticker]/transcripts/page.tsx`:

```tsx
import { EmptyState } from "@/components/company/EmptyState";

export default function TranscriptsPage() {
  return (
    <EmptyState
      title="Transcripts"
      message="Coming soon — earnings-call transcripts with speaker segmentation and AI summary."
    />
  );
}
```

- [ ] **Step 6: Verify the shell renders**

Run the dev server and load a ticker:
```bash
cd frontend && npm run dev
```
Open `http://localhost:3000/company/AAPL`. Expected: global Nav, then a company header (AAPL + price pill or "—"), a 7-tab strip with "Overview" active, and the "Overview — Coming soon" placeholder. Click Financials/Transcripts — placeholders render, tab highlight follows, URL updates.

- [ ] **Step 7: Commit**

```bash
git add frontend/app/company/
git commit -m "feat(company): shell layout + Overview/Financials/Transcripts placeholders"
```

---

## Task 8: Frontend — report→props helper

**Files:**
- Create: `frontend/lib/reportProps.ts`

- [ ] **Step 1: Write the pure mapping**

Create `frontend/lib/reportProps.ts`. This mirrors the report-load mapping in `app/pipeline/[runId]/page.tsx` (`loadReportData` + `dashboardCategories`), as a pure function over a completed `ReportResponse`:

```ts
import type {
  ReportResponse,
  CategoryOutput,
  CuratedFinancials,
  DeepDiveCategoryStructured,
  TranscriptAnalysis,
  XSignalVelocity,
  EdgarFacts,
  QuickScreenStructured,
} from "./api";

export interface DashboardProps {
  financials: CuratedFinancials | null;
  categories: Record<string, CategoryOutput | null>;
  scores: Record<string, number>;
  transcriptAnalysis: TranscriptAnalysis | null;
  xSignalVelocity: XSignalVelocity | null;
  edgarFacts: EdgarFacts;
  convictionScore: number | null;
  quickScreen: QuickScreenStructured | null;
  themeId?: string;
}

export function reportToDashboardProps(report: ReportResponse): DashboardProps {
  const deep = report.phases.deep_dive;
  const rawCats = deep?.categories ?? {};
  const categories: Record<string, CategoryOutput | null> = {};
  for (const [key, val] of Object.entries(rawCats)) {
    const v = val as CategoryOutput & { __type__?: string; structured?: unknown };
    if (v.__type__ === "CategoryError") {
      categories[key] = null;
    } else {
      categories[key] = {
        score: v.score ?? 0,
        content: "",
        key_findings: v.key_findings ?? [],
        citations: [],
        structured: (v.structured as DeepDiveCategoryStructured) ?? undefined,
      };
    }
  }

  return {
    financials: deep?.curated_financials ?? null,
    categories,
    scores: report.scores ?? {},
    transcriptAnalysis: deep?.transcript_analysis ?? null,
    xSignalVelocity: report.x_signal_velocity ?? null,
    edgarFacts: deep?.edgar_facts ?? {},
    convictionScore: report.conviction_score ?? null,
    quickScreen: (report.phases.quick_screen?.structured as QuickScreenStructured) ?? null,
    themeId: report.theme_id ?? undefined,
  };
}
```

- [ ] **Step 2: Type-check (confirms the field names match `ReportResponse`)**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. If `report.theme_id` or `report.x_signal_velocity` are typed differently, adjust the access to match `ReportResponse` in `lib/api.ts` (do not loosen types with `any`).

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/reportProps.ts
git commit -m "feat(company): reportToDashboardProps mapping helper"
```

---

## Task 9: Frontend — Research tab

**Files:**
- Create: `frontend/components/company/ResearchTab.tsx`
- Create: `frontend/app/company/[ticker]/research/page.tsx`

- [ ] **Step 1: Write ResearchTab**

Create `frontend/components/company/ResearchTab.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { pipeline } from "@/lib/api";
import type { RunSummary, ReportResponse } from "@/lib/api";
import { DeepDiveDashboard } from "@/components/deep-dive/DeepDiveDashboard";
import { ReportHeader } from "@/components/deep-dive/ReportHeader";
import { reportToDashboardProps } from "@/lib/reportProps";
import { EmptyState } from "./EmptyState";

export function ResearchTab({ ticker }: { ticker: string }) {
  const lens = useSearchParams().get("lens");
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [report, setReport] = useState<ReportResponse | null>(null);

  useEffect(() => {
    pipeline
      .list({ status: "completed", limit: 50 })
      .then((all) => {
        const mine = all.filter((r) => r.ticker?.toUpperCase() === ticker.toUpperCase());
        setRuns(mine);
        const preferred =
          (lens && mine.find((r) => r.theme_id === lens)) || mine[0];
        setActiveRunId(preferred?.id ?? null);
      })
      .catch(() => setRuns([]));
  }, [ticker, lens]);

  useEffect(() => {
    if (!activeRunId) {
      setReport(null);
      return;
    }
    pipeline
      .report(activeRunId)
      .then(setReport)
      .catch(() => setReport(null));
  }, [activeRunId]);

  if (runs === null) {
    return <div className="p-6 text-[var(--text-muted)]">Loading research…</div>;
  }
  if (runs.length === 0) {
    return (
      <EmptyState
        title="No research yet"
        message="Run the due-diligence pipeline to generate a deep-dive report for this company."
        cta={{ href: `/pipeline/new?ticker=${ticker}`, label: "Run pipeline →" }}
      />
    );
  }

  const props = report ? reportToDashboardProps(report) : null;

  return (
    <div className="space-y-4">
      {runs.length > 1 && (
        <div className="flex items-center gap-2">
          <label className="text-sm text-[var(--text-muted)]">Run:</label>
          <select
            value={activeRunId ?? ""}
            onChange={(e) => setActiveRunId(e.target.value)}
            className="rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-1 text-sm text-[var(--text)]"
          >
            {runs.map((r) => (
              <option key={r.id} value={r.id}>
                {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                {r.theme_name ? ` · ${r.theme_name}` : ""}
                {r.thesis_status ? ` · ${r.thesis_status}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}
      {props && activeRunId && (
        <>
          <ReportHeader
            financials={props.financials}
            quickScreen={props.quickScreen}
            convictionScore={props.convictionScore}
            ticker={ticker}
            runId={activeRunId}
            isLive={false}
            runStatus="completed"
          />
          <DeepDiveDashboard
            ticker={ticker}
            themeId={props.themeId}
            financials={props.financials}
            categories={props.categories}
            scores={props.scores}
            isLive={false}
            transcriptAnalysis={props.transcriptAnalysis}
            xSignalVelocity={props.xSignalVelocity ?? undefined}
            edgarFacts={props.edgarFacts}
          />
        </>
      )}
    </div>
  );
}
```

> Note: `pipeline.list` accepts `{ status?, theme_id?, search?, limit? }` (no `ticker` field), so we filter client-side by ticker after fetching completed runs. This matches the existing `RunSummary` shape (`ticker`, `theme_id`, `theme_name`, `thesis_status`, `created_at`).

- [ ] **Step 2: Write the research page**

Create `frontend/app/company/[ticker]/research/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { ResearchTab } from "@/components/company/ResearchTab";

export default function CompanyResearchPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <ResearchTab ticker={ticker} />;
}
```

- [ ] **Step 3: Type-check**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. If `ReportHeader`'s prop types differ from those passed here, align the call to its actual signature in `components/deep-dive/ReportHeader.tsx` (read it first — do not change the component).

- [ ] **Step 4: Manual smoke**

With the dev server running, open `/company/<TICKER>/research` for a ticker that has a completed run (find one via the Library page). Expected: the deep-dive dashboard renders identically to `/pipeline/[runId]`. For a ticker with no runs: the "No research yet" empty state with a "Run pipeline →" CTA. With `?lens=<themeId>` set, the run selector defaults to the run for that theme when one exists.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/company/ResearchTab.tsx frontend/app/company/[ticker]/research/
git commit -m "feat(company): Research tab — latest run resolver + report render"
```

---

## Task 10: Frontend — extract ModelWorkspace + Model/Filings tabs

**Files:**
- Create: `frontend/components/model/ModelWorkspace.tsx`
- Modify: `frontend/app/model/[ticker]/page.tsx` (replace body with wrapper)
- Create: `frontend/app/company/[ticker]/model/page.tsx`
- Create: `frontend/app/company/[ticker]/filings/page.tsx`

- [ ] **Step 1: Extract ModelWorkspace (verbatim move + signature change)**

Create `frontend/components/model/ModelWorkspace.tsx` by **moving the entire contents** of `frontend/app/model/[ticker]/page.tsx` into it, with exactly these changes:

1. Keep the `"use client";` line and all imports **except** remove `useParams` from the `next/navigation` import (it's no longer used here).
2. Change the default-export component declaration:

   From:
   ```tsx
   export default function ModelPage() {
     const params = useParams<{ ticker: string }>();
     const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker) ?? "";
   ```
   To:
   ```tsx
   export function ModelWorkspace({ ticker: tickerProp }: { ticker: string }) {
     const ticker = (tickerProp || "").toUpperCase();
   ```
3. Move the module-level helper components defined below `ModelPage` (`ForecastTabContent`, `ReverseDcfTabContent`, `HistoryTabContent`) into this new file **verbatim** — they are referenced by the component.

Everything else (state, effects, the `forecast/reverse-dcf/history` sub-tab nav and `<main>` body) moves unchanged.

- [ ] **Step 2: Replace the standalone model page with a thin wrapper**

Replace the entire contents of `frontend/app/model/[ticker]/page.tsx` with:

```tsx
"use client";

import { useParams } from "next/navigation";
import { ModelWorkspace } from "@/components/model/ModelWorkspace";

export default function ModelPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <ModelWorkspace ticker={ticker} />;
}
```

- [ ] **Step 3: Write the company Model tab page**

Create `frontend/app/company/[ticker]/model/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { ModelWorkspace } from "@/components/model/ModelWorkspace";

export default function CompanyModelPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <ModelWorkspace ticker={ticker} />;
}
```

- [ ] **Step 4: Write the company Filings tab page**

Create `frontend/app/company/[ticker]/filings/page.tsx` (reuses the existing self-contained, ticker-scoped `TickerFilingsCard`, default export taking `{ ticker }`):

```tsx
"use client";

import { useParams } from "next/navigation";
import TickerFilingsCard from "@/components/filings/TickerFilingsCard";

export default function CompanyFilingsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <TickerFilingsCard ticker={ticker} />;
}
```

- [ ] **Step 5: Type-check + lint**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no errors. (If lint flags an unused import left in `ModelWorkspace.tsx`, remove only that import.)

- [ ] **Step 6: Manual smoke**

With dev server running:
- `/model/<TICKER>` still works exactly as before (forecast/reverse-dcf/history sub-tabs, draft editing, save).
- `/company/<TICKER>/model` shows the same model under the company shell.
- `/company/<TICKER>/filings` shows the filings card for the ticker.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/model/ModelWorkspace.tsx frontend/app/model/[ticker]/page.tsx frontend/app/company/[ticker]/model/ frontend/app/company/[ticker]/filings/
git commit -m "feat(company): re-home Model + Filings tabs; extract ModelWorkspace"
```

---

## Task 11: Frontend — Theses tab (the lens detail)

**Files:**
- Create: `frontend/components/company/ThesesTab.tsx`
- Create: `frontend/app/company/[ticker]/theses/page.tsx`

- [ ] **Step 1: Write ThesesTab**

Create `frontend/components/company/ThesesTab.tsx`. It surfaces, for the ticker: status-board rows (themes + health + kill-criteria), run/verdict history, and open questions — all from existing endpoints. The active lens (`?lens=`) highlights the matching theme row.

```tsx
"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { status, pipeline, questions } from "@/lib/api";
import type { StatusBoardEntry, RunSummary, Question } from "@/lib/api";

export function ThesesTab({ ticker }: { ticker: string }) {
  const lens = useSearchParams().get("lens");
  const [rows, setRows] = useState<StatusBoardEntry[]>([]);
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [qs, setQs] = useState<Question[]>([]);

  useEffect(() => {
    const up = ticker.toUpperCase();
    status
      .board()
      .then((b) => setRows(b.entries.filter((e) => e.ticker.toUpperCase() === up)))
      .catch(() => setRows([]));
    pipeline
      .list({ limit: 50 })
      .then((all) => setRuns(all.filter((r) => r.ticker?.toUpperCase() === up)))
      .catch(() => setRuns([]));
    questions
      .list({ ticker: up })
      .then((r) => setQs(r.questions))
      .catch(() => setQs([]));
  }, [ticker]);

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-2 text-sm font-semibold text-[var(--text)]">Theses tracking {ticker}</h3>
        {rows.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">Not tracked in any theme yet.</p>
        ) : (
          <div className="space-y-2">
            {rows.map((e) => (
              <div
                key={e.run_id}
                className={`flex items-center justify-between rounded-md border px-3 py-2 ${
                  lens && e.theme_id === lens
                    ? "border-[var(--primary)] bg-[var(--accent-bg)]"
                    : "border-[var(--border)] bg-[var(--surface)]"
                }`}
              >
                <div className="text-sm">
                  <span className="font-medium text-[var(--text)]">{e.theme_name}</span>
                  <span className="ml-2 text-xs text-[var(--text-muted)]">{e.thesis_status}</span>
                </div>
                <div className="flex items-center gap-3 text-xs text-[var(--text-muted)]">
                  <span className="uppercase">{e.health}</span>
                  <span>
                    kill: {e.kill_criteria_summary.triggered}/{e.kill_criteria_summary.total} triggered
                  </span>
                  <Link
                    href={`/pipeline/${e.run_id}`}
                    className="text-[var(--primary)] hover:underline"
                  >
                    run →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-[var(--text)]">Run history</h3>
        {runs.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No runs yet.</p>
        ) : (
          <ul className="space-y-1 text-sm">
            {runs.map((r) => (
              <li key={r.id} className="flex items-center gap-3">
                <span className="text-[var(--text-muted)]">
                  {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                </span>
                <span className="text-[var(--text)]">{r.theme_name ?? "—"}</span>
                <span className="text-xs text-[var(--text-muted)]">{r.thesis_status ?? r.status}</span>
                <Link href={`/pipeline/${r.id}`} className="text-[var(--primary)] hover:underline">
                  open →
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-[var(--text)]">Open questions</h3>
        {qs.length === 0 ? (
          <p className="text-sm text-[var(--text-muted)]">No open questions.</p>
        ) : (
          <ul className="list-disc space-y-1 pl-5 text-sm text-[var(--text)]">
            {qs.map((q) => (
              <li key={q.id}>{q.question_text}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: (Sanity) the referenced types/fields are confirmed present**

These were verified against `frontend/lib/api.ts` while writing this plan: `KillCriteriaSummary { total: number; triggered: number }`, `Question { id; question_text; ... }`, and `export const questions = { list({ ticker, ... }): Promise<{ questions: Question[] }>, ... }`. No changes needed — this step is just a guard against drift. Do **not** add `any` casts.

- [ ] **Step 3: Write the theses page**

Create `frontend/app/company/[ticker]/theses/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { ThesesTab } from "@/components/company/ThesesTab";

export default function CompanyThesesPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <ThesesTab ticker={ticker} />;
}
```

- [ ] **Step 4: Type-check**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors after aligning field names in Step 2.

- [ ] **Step 5: Manual smoke**

Open `/company/<TICKER>/theses` for a tracked ticker. Expected: theme rows with health + kill-criteria, run history, open questions. With `?lens=<themeId>`, the matching theme row is highlighted.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/company/ThesesTab.tsx frontend/app/company/[ticker]/theses/
git commit -m "feat(company): Theses tab — status rows, run history, open questions"
```

---

## Task 12: Frontend — entry point (Nav ticker-jump)

**Files:**
- Modify: `frontend/components/Nav.tsx`

> **Deviation from spec (flagged):** the spec deferred a top-nav entry and proposed linking from theme detail + status board. Slice 1 needs at least one reliable way to reach `/company/[ticker]`; a minimal ticker-jump input in `Nav` is fully self-contained and guarantees reachability. Cross-app ticker links (theme detail, status board) remain a fast-follow.

- [ ] **Step 1: Add a ticker-jump form to Nav**

In `frontend/components/Nav.tsx`, make the component a client component capable of navigation. The file is already `"use client"` (uses `usePathname`). Add `useRouter` and `useState` to the imports:

Change:
```tsx
import { usePathname } from "next/navigation";
```
to:
```tsx
import { usePathname, useRouter } from "next/navigation";
import { useState } from "react";
```

Inside the `Nav` component, after `const path = usePathname();`, add:
```tsx
  const router = useRouter();
  const [tickerInput, setTickerInput] = useState("");

  function goToCompany(e: React.FormEvent) {
    e.preventDefault();
    const t = tickerInput.trim().toUpperCase();
    if (t) router.push(`/company/${encodeURIComponent(t)}`);
  }
```

Then, inside the `<nav className="flex items-center gap-1">` element, after the `{links.map(...)}` block (before `</nav>`), add the jump form:
```tsx
          <form onSubmit={goToCompany} className="ml-2">
            <input
              value={tickerInput}
              onChange={(e) => setTickerInput(e.target.value)}
              placeholder="Ticker…"
              className="w-24 rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-1 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)]"
              aria-label="Go to company workspace"
            />
          </form>
```

- [ ] **Step 2: Type-check + lint**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no errors.

- [ ] **Step 3: Manual smoke**

With dev server running: type `NVDA` into the Nav ticker box, press Enter → navigates to `/company/NVDA`.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/Nav.tsx
git commit -m "feat(company): Nav ticker-jump entry point to /company/[ticker]"
```

---

## Task 13: Full-slice verification

- [ ] **Step 1: Backend tests**

Run (project root, venv active):
```bash
python -m unittest backend.tests.test_company_snapshot -v
```
Expected: OK (3 tests).

- [ ] **Step 2: Frontend type-check + lint**

Run:
```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no errors.

- [ ] **Step 3: End-to-end manual smoke**

With backend (`uvicorn backend.app.main:app --reload` from project root) and frontend (`npm run dev`) running, and `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` (per the IPv6 note in project memory):

1. Nav → type a ticker → lands on `/company/<TICKER>`.
2. Header shows identity + price pill (or "—" if FMP key absent); Lens selector lists themes.
3. All 7 tabs navigate; active highlight + URL update; `?lens=` persists across tab clicks.
4. Research tab: completed-run ticker → dashboard renders; no-run ticker → "Run pipeline" CTA.
5. Model tab matches `/model/<TICKER>`; standalone `/model/<TICKER>` still works.
6. Filings tab shows the filings card.
7. Theses tab shows theme rows / run history / questions; lens highlights the matching row.

- [ ] **Step 4: Final commit (if any verification fixes were needed)**

```bash
git add -A && git commit -m "chore(company): slice 1 verification fixes"
```

---

## Out of scope for slice 1 (do not build here)

- Overview statistics grid, price chart, Bulls/Bears, beat/miss (slice 2).
- Financials tables, period slider, common-size toggles (slice 3).
- Transcripts reader (slice 4).
- Lens reframing of Overview / filings graph / Bulls-Bears (lands with those tabs in slices 2–3).
- Cross-app ticker links from theme detail + status board (fast-follow after slice 1).
- Refactoring `app/pipeline/[runId]/page.tsx` to consume `reportToDashboardProps` (its render path is fed by live SSE state, not a single report object — leave it untouched).
