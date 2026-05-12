# Tier 3 v2 — Fan-out Orchestration + Relationship Prompt Routing

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** `docs/superpowers/specs/2026-04-20-tier-3-v2-fanout-prompt-routing-design.md`

**Goal:** Populate the relationships graph across whole themes on demand, and feed resolved counterparties into the Business Quality / Risk Assessment / Future Durability deep-dive prompts as structured anchors. Also ship a small Item 1A heading-regex fix that affects the source material for risk relationships.

**Architecture:** One new service (`FanoutService`) with in-memory status, one new query layer (`relationship_context.py`), one new router (`/api/fanouts/...`), one new prompt slot (`{counterparty_context}` in `DEEP_DIVE_USER`). No schema changes, no migrations. Backend sequences ingest → extract → resolve serially per ticker; frontend adds a "Fan out" button per theme/ticker with 3s-interval status polling.

**Tech Stack:** FastAPI, async SQLAlchemy, LangGraph (existing), Next.js 16 App Router, React 19, TypeScript.

**Test strategy note:** The backend has no test framework (per CLAUDE.md); the frontend ships without Jest/Vitest wired. Verification steps in this plan are manual — curl + DB inspection for backend, browser interaction + backend log watch for frontend. This matches how Tier 3 v1, Phase A, and Phases B-D were validated.

**Branch:** `feat/relationships-fanout-prompt-routing` off `main`.

---

## Phase 0 — Item 1A heading regex fix

### Task 1: Tolerate mid-word `\n` splits in Item 1A regex

**Files:**
- Modify: `backend/app/services/edgar_html.py:53` and `edgar_html.py:90`

Both lines currently contain the same literal pattern:

```python
("item_1a_risk_factors", [r"\bITEM\s*1A\.?\s*RISK\s+FACTORS\b"]),
```

The literal `RISK` and `FACTORS` miss mid-word `\n` splits (e.g. ORCL 10-K renders `R\nisk` at an XBRL/markup boundary). Mirror the `O\s*F` tolerance already used for MD&A patterns in the same file.

- [ ] **Step 1: Make the fix — replace the pattern at both lines**

Replace the pattern string in both `edgar_html.py:53` (10-K) and `edgar_html.py:90` (10-Q) with:

```python
("item_1a_risk_factors", [r"\bITEM\s*1A\.?\s*R\s*I\s*S\s*K\s+F\s*A\s*C\s*T\s*O\s*R\s*S\b"]),
```

Rationale: `\s*` between every letter tolerates HTML-unwrap splits inside the word; the `\s+` between `K` and `F` preserves the required space between `RISK` and `FACTORS`. `\b` boundaries at the ends remain sound because `R` and `S` are both word characters.

- [ ] **Step 2: Start the backend dev server**

From project root, with `backend/venv` activated:

```bash
uvicorn backend.app.main:app --reload
```

Wait for `Application startup complete.` in the logs. Keep this server running for Steps 3-5.

- [ ] **Step 3: Force-re-ingest ORCL filings (the known-bad case)**

Open a second terminal and run:

```bash
curl -s -X POST http://localhost:8000/api/filings/ingest/ORCL | jq
```

Expected: `200` with a `FilingIngestSummary`-like payload listing 10-K, 10-Q, DEF 14A. If the current ORCL accessions are already in `filings`, ingestion is idempotent at the accession level but the section extractor re-runs on the stored HTML — we need the extractor output from the *fixed* regex to land, so if nothing looks different in the response, proceed to Step 4 and check the DB directly.

- [ ] **Step 4: Inspect the extracted Item 1A text in the DB**

```bash
psql "$DATABASE_URL_SYNC" -c "
  SELECT f.ticker, f.form_type, LENGTH(fs.text_content) AS chars,
         LEFT(fs.text_content, 120) AS head
  FROM filing_sections fs
  JOIN filings f ON f.id = fs.filing_id
  WHERE f.ticker = 'ORCL'
    AND fs.section_key = 'item_1a_risk_factors'
  ORDER BY f.period_of_report DESC NULLS LAST
  LIMIT 3;
"
```

Expected AFTER fix (10-K row): `chars` in the tens of thousands (the real Item 1A runs long), `head` starts with actual risk-factor prose (e.g. something like "Risks Related to Our Business" or "The following risk factors…"), NOT a brief cross-reference fragment.

If `chars` is still ~2K and `head` looks like a table of contents entry, the regex still isn't matching — verify the exact pattern at lines 53 and 90, and confirm the file was saved and the reload picked it up.

- [ ] **Step 5: Commit**

```bash
git checkout -b feat/relationships-fanout-prompt-routing
git add backend/app/services/edgar_html.py
git commit -m "fix(edgar): tolerate mid-word whitespace in Item 1A regex

The literal 'RISK' and 'FACTORS' tokens missed ORCL-class 10-Ks where
XBRL/markup boundaries split characters with '\\n' mid-word. Expands
each letter with '\\s*' around it — same treatment already applied to
the 'O\\s*F' tolerance in MD&A patterns."
```

---

## Phase 1 — Fan-out orchestration

### Task 2: Add `FanoutStatus` dataclass + `FanoutService` skeleton (single-ticker flow)

**Files:**
- Create: `backend/app/services/fanout.py`

This task creates the service with support for the per-ticker flow. Theme-scoped fan-out is added in Task 3.

- [ ] **Step 1: Create `backend/app/services/fanout.py`**

```python
"""Fan-out orchestrator for relationship extraction.

On-demand service that walks a ticker list and runs ingest → extract →
resolve for each one. Results are tombstoned in the DB at the section
and row level, so re-runs are cheap unless `force=True`.

Status is tracked in memory per-process (no persistence across server
restarts). Mirrors the pattern of `PipelineService`'s in-memory SSE
queues. If the server restarts mid-run, the client polling the status
endpoint will see a 404 — acceptable for a personal tool.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import async_session
from backend.app.models.theme import Theme
from backend.app.services import (
    counterparty_resolver,
    edgar_relationships,
    edgar_sections_ingest,
)

logger = logging.getLogger(__name__)

FanoutStatusLiteral = Literal["running", "completed", "failed"]
FanoutStageLiteral = Literal["ingest", "extract", "resolve"]


@dataclass
class FanoutError:
    ticker: str
    stage: FanoutStageLiteral
    message: str


@dataclass
class FanoutScope:
    kind: Literal["theme", "ticker"]
    theme_id: str | None = None
    ticker: str | None = None

    def to_dict(self) -> dict:
        if self.kind == "theme":
            return {"kind": "theme", "theme_id": self.theme_id}
        return {"kind": "ticker", "ticker": self.ticker}


@dataclass
class FanoutStatus:
    fanout_id: str
    status: FanoutStatusLiteral
    scope: FanoutScope
    total_tickers: int
    completed_tickers: int = 0
    current_ticker: str | None = None
    current_stage: FanoutStageLiteral | None = None
    errors: list[FanoutError] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "fanout_id": self.fanout_id,
            "status": self.status,
            "scope": self.scope.to_dict(),
            "total_tickers": self.total_tickers,
            "completed_tickers": self.completed_tickers,
            "current_ticker": self.current_ticker,
            "current_stage": self.current_stage,
            "errors": [
                {"ticker": e.ticker, "stage": e.stage, "message": e.message}
                for e in self.errors
            ],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class FanoutService:
    """In-memory fan-out orchestrator. Singleton-per-process."""

    def __init__(self) -> None:
        self._statuses: dict[str, FanoutStatus] = {}

    @staticmethod
    def _new_id() -> str:
        return f"fo_{secrets.token_hex(6)}"

    def get(self, fanout_id: str) -> FanoutStatus | None:
        return self._statuses.get(fanout_id)

    def start_ticker(self, ticker: str, force: bool = False) -> FanoutStatus:
        """Begin a single-ticker fan-out. Returns the status immediately;
        work runs under asyncio.create_task."""
        status = FanoutStatus(
            fanout_id=self._new_id(),
            status="running",
            scope=FanoutScope(kind="ticker", ticker=ticker.upper()),
            total_tickers=1,
        )
        self._statuses[status.fanout_id] = status
        asyncio.create_task(self._run([ticker.upper()], status, force=force))
        return status

    async def _run(
        self,
        tickers: list[str],
        status: FanoutStatus,
        *,
        force: bool,
    ) -> None:
        try:
            for ticker in tickers:
                status.current_ticker = ticker
                await self._run_one_ticker(ticker, status, force=force)
                status.completed_tickers += 1
            status.status = "completed"
        except Exception as exc:  # orchestrator-level crash only
            logger.exception("Fanout orchestrator failed (id=%s)", status.fanout_id)
            status.status = "failed"
            status.errors.append(
                FanoutError(
                    ticker=status.current_ticker or "?",
                    stage=status.current_stage or "ingest",
                    message=f"orchestrator crash: {exc!r}",
                )
            )
        finally:
            status.current_ticker = None
            status.current_stage = None
            status.finished_at = datetime.now(timezone.utc)

    async def _run_one_ticker(
        self,
        ticker: str,
        status: FanoutStatus,
        *,
        force: bool,
    ) -> None:
        """Run ingest → extract → resolve for one ticker. Per-stage errors
        are captured and do not abort the outer loop."""
        # Stage 1: ingest
        status.current_stage = "ingest"
        try:
            async with async_session() as db:
                await edgar_sections_ingest.ingest_ticker_sections(db=db, ticker=ticker)
        except Exception as exc:
            logger.warning("Fanout ingest failed for %s: %r", ticker, exc)
            status.errors.append(
                FanoutError(ticker=ticker, stage="ingest", message=str(exc))
            )
            return  # no point extracting what we couldn't ingest

        # Stage 2: extract
        status.current_stage = "extract"
        try:
            async with async_session() as db:
                await edgar_relationships.extract_ticker_relationships(
                    db=db, ticker=ticker, force=force
                )
        except Exception as exc:
            logger.warning("Fanout extract failed for %s: %r", ticker, exc)
            status.errors.append(
                FanoutError(ticker=ticker, stage="extract", message=str(exc))
            )
            return  # no point resolving empty rows

        # Stage 3: resolve
        status.current_stage = "resolve"
        try:
            async with async_session() as db:
                await counterparty_resolver.resolve_ticker_relationships(
                    db=db, ticker=ticker, force=force
                )
        except Exception as exc:
            logger.warning("Fanout resolve failed for %s: %r", ticker, exc)
            status.errors.append(
                FanoutError(ticker=ticker, stage="resolve", message=str(exc))
            )


# Module-level singleton wired in at router setup.
_service: FanoutService | None = None


def get_service() -> FanoutService:
    global _service
    if _service is None:
        _service = FanoutService()
    return _service
```

**Important:** the exact signatures of `ingest_ticker_sections`, `extract_ticker_relationships`, and `resolve_ticker_relationships` must be verified before running. If any of the three functions takes different kwargs (e.g. no `force=`, or a different DB-session pattern), adjust the call sites in `_run_one_ticker` to match — do NOT invent signatures. Read each function's `def` line if uncertain.

- [ ] **Step 2: Verify service-layer signatures match what's called above**

From project root:

```bash
grep -n "^async def ingest_ticker_sections\|^async def extract_ticker_relationships\|^async def resolve_ticker_relationships" \
  backend/app/services/edgar_sections_ingest.py \
  backend/app/services/edgar_relationships.py \
  backend/app/services/counterparty_resolver.py
```

Expected: three `async def` lines. For each, inspect the full signature (just read the following ~5 lines to see parameters). If any accepts different parameter names — e.g. `session` instead of `db`, or lacks a `force` kwarg — update Step 1's `_run_one_ticker` call sites to pass the correct names. If `extract_ticker_relationships` or `resolve_ticker_relationships` doesn't yet accept `force`, carry the argument through the existing service (they're expected to, per Phase B/C spec docs, but verify).

- [ ] **Step 3: Syntax check**

```bash
source backend/venv/bin/activate
python -c "from backend.app.services.fanout import FanoutService, get_service; s = get_service(); print(s)"
```

Expected: prints a `<backend.app.services.fanout.FanoutService object at 0x...>` with no errors. If you see an `ImportError`, the import line for one of the three services is wrong — check the spelling.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/fanout.py
git commit -m "feat(fanout): FanoutService skeleton with single-ticker flow

Adds in-memory status tracker mirroring the PipelineService SSE-queue
pattern. Per-ticker flow: ingest → extract → resolve, with per-stage
error capture that does not abort the outer loop. Theme scope added
in a follow-up commit."
```

### Task 3: Extend `FanoutService` with theme-scoped fan-out

**Files:**
- Modify: `backend/app/services/fanout.py`

- [ ] **Step 1: Add `start_theme` method to `FanoutService`**

Insert this method into `FanoutService`, after `start_ticker`:

```python
    async def start_theme(
        self, theme_id: str, db: AsyncSession, force: bool = False
    ) -> FanoutStatus:
        """Begin a theme-scoped fan-out. Reads seed_tickers from the theme
        row up-front so the returned total_tickers is accurate; raises if
        the theme doesn't exist."""
        result = await db.execute(select(Theme).where(Theme.id == theme_id))
        theme = result.scalar_one_or_none()
        if theme is None:
            raise ValueError(f"theme {theme_id!r} not found")

        raw_tickers = theme.seed_tickers or []
        # Theme.seed_tickers is JSONB; tolerate list-of-strings or list-of-
        # dicts with a "ticker" key (the discovery pipeline stores either,
        # historically).
        tickers: list[str] = []
        for entry in raw_tickers:
            if isinstance(entry, str):
                tickers.append(entry.upper())
            elif isinstance(entry, dict) and entry.get("ticker"):
                tickers.append(str(entry["ticker"]).upper())
        tickers = sorted(set(tickers))

        status = FanoutStatus(
            fanout_id=self._new_id(),
            status="running",
            scope=FanoutScope(kind="theme", theme_id=theme_id),
            total_tickers=len(tickers),
        )
        self._statuses[status.fanout_id] = status

        if not tickers:
            # Nothing to do. Mark completed immediately.
            status.status = "completed"
            status.finished_at = datetime.now(timezone.utc)
            return status

        asyncio.create_task(self._run(tickers, status, force=force))
        return status
```

- [ ] **Step 2: Verify `Theme.seed_tickers` shape at runtime**

Check the actual data stored in the DB for a populated theme:

```bash
psql "$DATABASE_URL_SYNC" -c "
  SELECT id, name, jsonb_typeof(seed_tickers) AS outer_type,
         jsonb_array_length(seed_tickers) AS n,
         seed_tickers->0 AS first_elem
  FROM themes
  WHERE seed_tickers IS NOT NULL
  LIMIT 3;
"
```

Expected: `outer_type = array`, `first_elem` is either a JSON string (e.g. `"ORCL"`) or a JSON object with a `"ticker"` key. The parser in Step 1 handles both. If you see a third shape, extend the parser.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/fanout.py
git commit -m "feat(fanout): theme-scoped fan-out using Theme.seed_tickers"
```

### Task 4: Add fan-out API router + wire into `main.py`

**Files:**
- Create: `backend/app/api/fanouts.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create `backend/app/api/fanouts.py`**

```python
"""Fan-out endpoints — theme-scoped and ticker-scoped relationship population."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.services.fanout import get_service

router = APIRouter(tags=["fanouts"])


@router.post("/themes/{theme_id}/relationships/fanout", status_code=202)
async def start_theme_fanout(
    theme_id: str,
    force: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Kick off a theme-scoped fan-out. Returns the initial status payload
    (including fanout_id) so the client can start polling immediately."""
    try:
        status = await get_service().start_theme(theme_id, db=db, force=force)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return status.to_dict()


@router.post("/tickers/{ticker}/relationships/fanout", status_code=202)
async def start_ticker_fanout(
    ticker: str,
    force: bool = Query(default=False),
) -> dict:
    """Kick off a single-ticker fan-out."""
    status = get_service().start_ticker(ticker, force=force)
    return status.to_dict()


@router.get("/fanouts/{fanout_id}")
async def get_fanout(fanout_id: str) -> dict:
    status = get_service().get(fanout_id)
    if status is None:
        raise HTTPException(status_code=404, detail="fanout not found")
    return status.to_dict()
```

- [ ] **Step 2: Confirm `get_db` exists and matches the import**

```bash
grep -n "^async def get_db\|^def get_db" backend/app/db.py
```

Expected: one match. If the function is named differently (`get_session`, etc.), update the import and the `Depends(...)` in Step 1 accordingly.

- [ ] **Step 3: Mount the router in `main.py`**

In `backend/app/main.py`, after the existing `from backend.app.api.filings import router as filings_router` import, add:

```python
from backend.app.api.fanouts import router as fanouts_router
```

Near line 98 where existing routers are mounted:

```python
app.include_router(fanouts_router, prefix="/api")
```

Place it after the `filings_router` line so the router order mirrors feature order.

- [ ] **Step 4: Smoke-test the endpoints (dev server must be running)**

Restart `uvicorn` if it wasn't auto-reloading. Then:

```bash
# Kick off a single-ticker fan-out. Use any ticker already in your DB.
curl -s -X POST "http://localhost:8000/api/tickers/ORCL/relationships/fanout" | jq
```

Expected: `202` with JSON like `{"fanout_id": "fo_abc...", "status": "running", "scope": {"kind": "ticker", "ticker": "ORCL"}, "total_tickers": 1, ...}`. Copy the `fanout_id`.

```bash
# Poll until done.
curl -s "http://localhost:8000/api/fanouts/fo_abc..." | jq
```

Expected progression: `status: "running"` with `current_stage` transitioning through `ingest` → `extract` → `resolve`, then `status: "completed"` with `completed_tickers: 1`. For ORCL, the entire run should complete in ~30-60s (ingest is the slow part; extract/resolve skip tombstoned sections).

Error expectation: if ingest fails due to a rate-limit or 404, `errors[]` will contain one entry and `status` will still be `"completed"` (the orchestrator only reports `"failed"` on its own crash, not per-ticker errors).

- [ ] **Step 5: Smoke-test the theme endpoint**

Pick a theme with ≥1 seed ticker:

```bash
psql "$DATABASE_URL_SYNC" -c "SELECT id, name, jsonb_array_length(seed_tickers) FROM themes LIMIT 3;"
```

```bash
curl -s -X POST "http://localhost:8000/api/themes/<id>/relationships/fanout" | jq
```

Expected: `total_tickers` equals the count from the psql query. Poll the status endpoint and watch `current_ticker` advance.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/fanouts.py backend/app/main.py
git commit -m "feat(fanouts): POST theme/ticker fan-out + GET status endpoints"
```

### Task 5: Frontend — add fan-out API client types + functions

**Files:**
- Modify: `frontend/lib/api.ts`

The existing `api.ts` exposes a `filings` object (search it in the file; it's roughly at lines 148-253) plus top-level function exports for formatters. Mirror the `filings` object pattern for `fanouts`.

- [ ] **Step 1: Add `FanoutStatus` TypeScript types**

At a location near the other filing-related types (search for `FilingIngestSummary` in the file and place this nearby):

```ts
export type FanoutStatusLiteral = "running" | "completed" | "failed";
export type FanoutStage = "ingest" | "extract" | "resolve";

export type FanoutScope =
  | { kind: "theme"; theme_id: string }
  | { kind: "ticker"; ticker: string };

export interface FanoutError {
  ticker: string;
  stage: FanoutStage;
  message: string;
}

export interface FanoutStatus {
  fanout_id: string;
  status: FanoutStatusLiteral;
  scope: FanoutScope;
  total_tickers: number;
  completed_tickers: number;
  current_ticker: string | null;
  current_stage: FanoutStage | null;
  errors: FanoutError[];
  started_at: string;
  finished_at: string | null;
}
```

- [ ] **Step 2: Add the `fanouts` client object**

After the existing `filings` / `relationships` client objects, add:

```ts
export const fanouts = {
  startTheme: (themeId: string, force: boolean = false) =>
    apiFetch<FanoutStatus>(
      `/api/themes/${encodeURIComponent(themeId)}/relationships/fanout${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  startTicker: (ticker: string, force: boolean = false) =>
    apiFetch<FanoutStatus>(
      `/api/tickers/${encodeURIComponent(ticker)}/relationships/fanout${force ? "?force=true" : ""}`,
      { method: "POST" }
    ),
  get: (fanoutId: string) =>
    apiFetch<FanoutStatus>(`/api/fanouts/${encodeURIComponent(fanoutId)}`),
};
```

- [ ] **Step 3: Verify the file still type-checks**

```bash
cd frontend
npm run lint
```

Expected: no new lint errors. If the existing codebase has a lint baseline, the count should match what `main` was at before this task.

Also, run `npx tsc --noEmit` if the project supports it (check `package.json` for a `typecheck` script first — use that if present). A clean TS compile is the goal.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api): fanouts client + FanoutStatus types"
```

### Task 6: Frontend — "Fan out" button + inline progress on `TickerFilingsCard`

**Files:**
- Modify: `frontend/components/filings/TickerFilingsCard.tsx`

- [ ] **Step 1: Read the existing component to locate the header/action area**

Open `frontend/components/filings/TickerFilingsCard.tsx` and identify:
1. The ticker card's header / action row where the existing "Ingest latest" button lives.
2. The component's state hooks (look for `useState` imports and existing state like `ingesting`).

The new "Fan out" button sits next to "Ingest latest". The key behavioral difference: ingest is synchronous; fan-out kicks off a background job and polls.

- [ ] **Step 2: Add fan-out state + polling hook to the component**

Near the existing state declarations inside the component function body, add:

```tsx
import { fanouts, type FanoutStatus } from "@/lib/api";
import { useEffect, useRef, useState } from "react";

// inside the component:
const [fanoutStatus, setFanoutStatus] = useState<FanoutStatus | null>(null);
const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

useEffect(() => {
  return () => {
    if (pollRef.current) clearInterval(pollRef.current);
  };
}, []);

const startFanout = async () => {
  try {
    const initial = await fanouts.startTicker(ticker);
    setFanoutStatus(initial);
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const next = await fanouts.get(initial.fanout_id);
        setFanoutStatus(next);
        if (next.status !== "running" && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (err) {
        console.error("fanout poll failed", err);
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 3000);
  } catch (err) {
    console.error("fanout start failed", err);
    setFanoutStatus(null);
  }
};
```

If `useState`, `useEffect`, or `useRef` are already imported, don't duplicate the import — just add the missing ones.

- [ ] **Step 3: Render the button + inline progress next to "Ingest latest"**

Adjacent to the existing "Ingest latest" button in the header action row, add:

```tsx
<button
  type="button"
  onClick={startFanout}
  disabled={fanoutStatus?.status === "running"}
  className="rounded border border-zinc-700 px-2 py-1 text-meta-xs hover:bg-zinc-800 disabled:opacity-50"
>
  {fanoutStatus?.status === "running" ? "Running…" : "Fan out"}
</button>
{fanoutStatus && (
  <span className="ml-2 text-meta-xs text-zinc-400">
    {fanoutStatus.status === "running"
      ? `${fanoutStatus.current_stage ?? "…"} · ${fanoutStatus.current_ticker ?? ""}`
      : fanoutStatus.status === "completed"
      ? fanoutStatus.errors.length > 0
        ? `done · ${fanoutStatus.errors.length} error(s)`
        : "done"
      : "failed"}
  </span>
)}
```

Match the existing button's Tailwind classes where reasonable — the button snippet above uses `text-meta-xs` (present per CLAUDE.md) and standard zinc utility classes, adjust to whatever the existing "Ingest latest" button uses if that's different.

- [ ] **Step 4: Verify in the browser**

With both dev servers running (`uvicorn` on 8000, `npm run dev` on 3000):
1. Open `http://localhost:3000/filings`.
2. Find any ticker card (use ORCL or any ticker already shown).
3. Click "Fan out".
4. Button label switches to "Running…", status text appears: `ingest · ORCL` → `extract · ORCL` → `resolve · ORCL` → `done`.
5. Open DevTools Network tab to confirm the POST + 3-second GETs to `/api/fanouts/...`.

If the button doesn't render, the button JSX was inserted in the wrong part of the component (e.g. outside the header row). Use browser React DevTools to inspect the component tree.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/filings/TickerFilingsCard.tsx
git commit -m "feat(filings): ticker-level fan-out button with polled progress"
```

### Task 7: Frontend — theme-level "Fan out theme" button on `ThemeFilingsPanel`

**Files:**
- Modify: `frontend/components/filings/ThemeFilingsPanel.tsx`

- [ ] **Step 1: Read the component structure**

`ThemeFilingsPanel.tsx` is ~98 lines. Identify:
1. The theme-level header (likely a `<div>` or `<section>` wrapping the theme name + existing batch-ingest controls).
2. Any existing batch-ingest button ("Ingest all" or similar) — the fan-out button goes next to it. If there isn't one, place the fan-out button in the theme's header row alongside the theme name.
3. Where the theme's `id` (the one accepted by the backend endpoint) is available in props/state.

- [ ] **Step 2: Add fan-out state + polling (same pattern as Task 6)**

At the top of the component body, add the same state + effect + `startFanout` block used in Task 6, but calling `fanouts.startTheme(themeId)` instead of `startTicker`. The status type and polling interval are identical — DRY this by factoring into a shared hook IF both consumers would benefit, but it's fine to duplicate across two call sites for now (the hook refactor is cheap to do later if a third caller emerges).

```tsx
const startFanout = async () => {
  try {
    const initial = await fanouts.startTheme(themeId);
    setFanoutStatus(initial);
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const next = await fanouts.get(initial.fanout_id);
        setFanoutStatus(next);
        if (next.status !== "running" && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (err) {
        console.error("fanout poll failed", err);
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }, 3000);
  } catch (err) {
    console.error("fanout start failed", err);
    setFanoutStatus(null);
  }
};
```

- [ ] **Step 3: Render theme-scoped button + progress**

In the theme header area, add:

```tsx
<button
  type="button"
  onClick={startFanout}
  disabled={fanoutStatus?.status === "running"}
  className="rounded border border-zinc-700 px-2 py-1 text-meta-xs hover:bg-zinc-800 disabled:opacity-50"
>
  {fanoutStatus?.status === "running" ? "Running…" : "Fan out theme"}
</button>
{fanoutStatus && (
  <span className="ml-2 text-meta-xs text-zinc-400">
    {fanoutStatus.status === "running"
      ? `${fanoutStatus.completed_tickers}/${fanoutStatus.total_tickers} · ${fanoutStatus.current_stage ?? "…"} ${fanoutStatus.current_ticker ? `· $${fanoutStatus.current_ticker}` : ""}`
      : fanoutStatus.status === "completed"
      ? fanoutStatus.errors.length > 0
        ? `done · ${fanoutStatus.errors.length} error(s)`
        : "done"
      : "failed"}
  </span>
)}
```

- [ ] **Step 4: Verify in the browser**

Reload `/filings`. For a theme with ≥3 tickers, click "Fan out theme". Expected: progress ticks `0/5 · ingest · $NVDA` → `1/5 · extract · $NVDA` → `1/5 · resolve · $NVDA` → `2/5 · ingest · $ORCL` → … → `done`. For 5 tickers expect a ~3-minute runtime; for 15 tickers, ~10 minutes. If an error occurs, the count appears after "done".

- [ ] **Step 5: Commit**

```bash
git add frontend/components/filings/ThemeFilingsPanel.tsx
git commit -m "feat(filings): theme-level fan-out button with per-ticker progress"
```

### Task 8: Phase 1 end-to-end validation

**Files:** none modified.

- [ ] **Step 1: Pick a realistic theme**

Choose a theme with 5-8 seed tickers that hasn't had fan-out run before, OR pick one you just ran and plan to verify idempotency (`force=false` second run should be fast).

- [ ] **Step 2: Run theme fan-out from the UI**

Click "Fan out theme" on `/filings`. Wait for completion.

- [ ] **Step 3: Spot-check DB state for 2 of the tickers**

```bash
psql "$DATABASE_URL_SYNC" -c "
  SELECT ticker, form_type, accession_number, period_of_report
  FROM filings
  WHERE ticker IN ('<T1>', '<T2>')
  ORDER BY ticker, period_of_report DESC;
"
```

Expected: at least one 10-K and one 10-Q per ticker (DEF 14A is variable; often present for large caps).

```bash
psql "$DATABASE_URL_SYNC" -c "
  SELECT ticker, relationship_type, COUNT(*) AS rows,
         COUNT(resolved_to_ticker) AS resolved,
         COUNT(*) FILTER (WHERE unnamed) AS unnamed
  FROM relationships
  WHERE ticker IN ('<T1>', '<T2>')
  GROUP BY ticker, relationship_type
  ORDER BY ticker, rows DESC;
"
```

Expected: at least one row per ticker with `resolved > 0` for mega-cap counterparties (MSFT, AMZN, GOOGL, NVDA if the tickers do business with any of them).

- [ ] **Step 4: Confirm idempotency**

Re-click "Fan out theme" on the same theme. Expected runtime: much shorter (ingest still checks EDGAR but finds existing accessions; extract skips tombstoned sections; resolve skips already-resolved rows). Errors array should be empty or unchanged.

- [ ] **Step 5: No commit — Phase 1 validation only.**

---

## Phase 2 — Relationship prompt routing

### Task 9: Build the `relationship_context.py` query layer

**Files:**
- Create: `backend/app/services/relationship_context.py`

- [ ] **Step 1: Create the file**

```python
"""Query layer that converts persisted `relationships` rows into the
structured counterparty payload the deep-dive prompt consumes.

Kept separate from `edgar_relationships.py` (the extractor) because
this is read-path-only: it assembles outbound + inbound views of the
graph for a single ticker, grouped by relationship_type.

The prompt renderer (`_build_counterparty_context` in graph/nodes.py)
consumes the dataclasses below.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filing import Filing, Relationship

# Cap per (direction, relationship_type) bucket. Realistic counts are
# far lower than this; this is a safety valve for mega-caps with very
# long supplier/customer disclosures.
MAX_ENTRIES_PER_BUCKET = 20


@dataclass
class CounterpartyEntry:
    name: str
    resolved_ticker: str | None
    relationship_type: str
    magnitude_pct: float | None
    unnamed: bool


@dataclass
class CounterpartyContext:
    outbound: dict[str, list[CounterpartyEntry]] = field(default_factory=dict)
    inbound: dict[str, list[CounterpartyEntry]] = field(default_factory=dict)

    @property
    def has_data(self) -> bool:
        return bool(self.outbound) or bool(self.inbound)


async def get_counterparty_context(
    ticker: str, db: AsyncSession
) -> CounterpartyContext:
    """Pull outbound (ticker says X about Y) and inbound (Z named ticker)
    relationship rows, group by `relationship_type`, apply per-bucket cap."""
    ticker_upper = ticker.upper()

    # Outbound: relationships whose filing.ticker matches.
    outbound_rows = (
        await db.execute(
            select(Relationship)
            .join(Filing, Filing.id == Relationship.filing_id)
            .where(Filing.ticker == ticker_upper)
        )
    ).scalars().all()

    # Inbound: relationships where resolved_to_ticker matches. The
    # filing-side ticker (the ROW author) is the one that named us.
    inbound_rows = (
        await db.execute(
            select(Relationship, Filing.ticker.label("author_ticker"))
            .join(Filing, Filing.id == Relationship.filing_id)
            .where(Relationship.resolved_to_ticker == ticker_upper)
        )
    ).all()

    ctx = CounterpartyContext()

    # Outbound — group by relationship_type.
    for row in outbound_rows:
        entry = CounterpartyEntry(
            name=row.counterparty_name,
            resolved_ticker=row.resolved_to_ticker,
            relationship_type=row.relationship_type,
            magnitude_pct=float(row.magnitude_pct) if row.magnitude_pct is not None else None,
            unnamed=bool(row.unnamed),
        )
        ctx.outbound.setdefault(entry.relationship_type, []).append(entry)

    # Inbound — group by relationship_type, but the author ticker is the
    # relevant identity, not the resolved_to_ticker (which is us).
    for r, author_ticker in inbound_rows:
        entry = CounterpartyEntry(
            name=f"${author_ticker}" if author_ticker else "(unknown author)",
            resolved_ticker=author_ticker,
            relationship_type=r.relationship_type,
            magnitude_pct=float(r.magnitude_pct) if r.magnitude_pct is not None else None,
            unnamed=False,
        )
        ctx.inbound.setdefault(entry.relationship_type, []).append(entry)

    # Sort + cap each bucket. Prefer entries with magnitude_pct set (as
    # a disclosure-salience proxy), then alphabetical by name.
    for bucket in (ctx.outbound, ctx.inbound):
        for key, entries in bucket.items():
            entries.sort(
                key=lambda e: (
                    0 if e.magnitude_pct is not None else 1,
                    -(e.magnitude_pct or 0.0),
                    e.name.lower(),
                )
            )
            bucket[key] = entries[:MAX_ENTRIES_PER_BUCKET]

    return ctx
```

- [ ] **Step 2: Syntax-check the module**

```bash
source backend/venv/bin/activate
python -c "
from backend.app.services.relationship_context import (
    CounterpartyContext, CounterpartyEntry, get_counterparty_context, MAX_ENTRIES_PER_BUCKET
)
print('ok', MAX_ENTRIES_PER_BUCKET)
"
```

Expected: prints `ok 20`.

- [ ] **Step 3: Smoke-query against a ticker with known relationship data**

Pick ORCL (which should have outbound rows from Phase B validation). Run:

```bash
python -c "
import asyncio
from backend.app.db import async_session
from backend.app.services.relationship_context import get_counterparty_context

async def main():
    async with async_session() as db:
        ctx = await get_counterparty_context('ORCL', db)
    print('has_data:', ctx.has_data)
    print('outbound types:', list(ctx.outbound.keys()))
    print('inbound types:', list(ctx.inbound.keys()))
    for t, entries in ctx.outbound.items():
        for e in entries[:3]:
            print(f'  OUT {t}: {e.name!r} ({e.resolved_ticker})')

asyncio.run(main())
"
```

Expected: `has_data: True` with outbound types including at least `competitor`, `joint_venture`, or `partner`. Inbound may be empty for ORCL if no other tracked ticker has named ORCL.

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/relationship_context.py
git commit -m "feat(relationships): counterparty_context query layer

New read-path module that assembles outbound + inbound relationship
views grouped by type, for prompt injection. Caps each bucket at 20
entries, preferring rows with magnitude_pct populated."
```

### Task 10: Wire `_fetch_counterparty_context` into `PipelineService`

**Files:**
- Modify: `backend/app/services/pipeline.py`

- [ ] **Step 1: Add the fetcher method**

Mirror the existing `_fetch_filing_sections` method (near line 259 of `pipeline.py`). Add the following method to `PipelineService`, immediately after `_fetch_filing_sections`:

```python
    async def _fetch_counterparty_context(self, ticker: str):
        """Pull outbound + inbound counterparty relationships for this
        ticker. Uses a dedicated session (see `_fetch_edgar_facts` for
        why). Returns an empty CounterpartyContext if nothing has been
        extracted yet — the prompt renderer no-ops cleanly on that."""
        from backend.app.services.relationship_context import (
            CounterpartyContext,
            get_counterparty_context,
        )
        try:
            async with async_session() as s:
                return await get_counterparty_context(ticker, s)
        except Exception:
            logger.exception("counterparty_context fetch failed for %s", ticker)
            return CounterpartyContext()
```

If `logger` isn't imported in `pipeline.py`, import it at the top of the file: `import logging` → `logger = logging.getLogger(__name__)`. Check first (there's very likely already one).

- [ ] **Step 2: Thread the call into the deep-dive runner**

Find the lines in `pipeline.py` where filing sections are fetched and passed into the deep-dive runner. Based on the grep earlier:

- Line 346-347:
  ```python
  edgar_facts, edgar_citations = await self._fetch_edgar_facts(state.ticker)
  filing_sections = await self._fetch_filing_sections(state.ticker)
  ```

Immediately after line 347 (and before the `_emit` call at line 358), add:

```python
counterparty_context = await self._fetch_counterparty_context(state.ticker)
```

Then find the kwargs passed to `node_deep_dive` inside this function (look for `await node_deep_dive(` — the grep at line 805 showed `node_deep_dive` is the function definition; its caller should live near here). Add `counterparty_context=counterparty_context` to the call site.

**If the structure of `_run_deep_dive_with_streaming` doesn't match this assumption**, re-read the function: the contract is "fetch all supplementary data, then invoke `node_deep_dive` with them as kwargs." Follow that contract; don't force the fit.

- [ ] **Step 3: Also thread it into the `deep_dive_start` SSE event payload (optional but parallel to filing_sections)**

`filing_sections` is included in the `deep_dive_start` SSE event per CLAUDE.md (search the file for `deep_dive_start`). Counterparty context is larger per-row but the event firing once per run is fine. Decision: only include it if the frontend actually uses it for live display. For this plan, SKIP this — the frontend's existing `SupplyChainEcosystem` card fetches via the report API after completion, not via SSE. Leaving it out keeps the SSE payload smaller.

- [ ] **Step 4: Syntax-check + server start**

```bash
# restart uvicorn and watch logs
source backend/venv/bin/activate
uvicorn backend.app.main:app --reload
```

Expected: clean startup, no import errors. The wiring change doesn't yet affect prompt output (that's Task 11), so running a pipeline phase here would still produce unchanged deep-dive text — don't worry about that yet.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/pipeline.py
git commit -m "feat(pipeline): fetch counterparty_context alongside filing_sections

Threads into node_deep_dive as a kwarg using the same dedicated-session
pattern as _fetch_filing_sections and _fetch_edgar_facts."
```

### Task 11: Add `RELATIONSHIP_ROUTING` + `_build_counterparty_context` + prompt slot

**Files:**
- Modify: `backend/app/graph/prompts.py`
- Modify: `backend/app/graph/nodes.py`

- [ ] **Step 1: Add `{counterparty_context}` slot to the `DEEP_DIVE_USER` template**

Open `backend/app/graph/prompts.py`. Find `DEEP_DIVE_USER` (grep confirmed line 83). The slot `{filing_excerpts}` is at line 100. Insert a new line after it containing `{counterparty_context}` followed by a blank line. The relative positioning matters — `filing_excerpts` first, then counterparties underneath, so the "anchors not re-quotes" language reads in sequence with the filing text.

Exact change — before:

```
...
{filing_excerpts}

<next section of template>
```

After:

```
...
{filing_excerpts}

{counterparty_context}

<next section of template>
```

Two blank-line separations match the existing template formatting between slots — verify by inspecting the surrounding lines (there should be blank lines between `{macro_data}`, `{technical_data}`, etc.).

- [ ] **Step 2: Add `RELATIONSHIP_ROUTING` and `_build_counterparty_context` to `nodes.py`**

In `backend/app/graph/nodes.py`, near the existing `FILING_EXCERPT_ROUTING` (line 98) and `FILING_EXCERPT_BUDGET_CHARS` (line 109), add:

```python
# Categories that receive the counterparty (supply-chain) context in
# their deep-dive prompt. Structured as a set (no per-section sub-list
# needed — relationship data is already aggregated per-ticker, not
# per-filing-section).
RELATIONSHIP_ROUTING: set[str] = {
    "business_quality",
    "risk_assessment",
    "future_durability",
}
```

Then, in `_run_one_category` or wherever the other `_build_*_context` helpers are defined (the grep showed `_build_filing_excerpt_context` at line 1081, adjacent to the other builders), add the builder:

```python
def _build_counterparty_context(
    category: str,
    ctx,  # CounterpartyContext — imported inline to avoid top-level cycle risk
) -> str:
    if category not in RELATIONSHIP_ROUTING:
        return ""
    if not getattr(ctx, "has_data", False):
        return ""

    lines: list[str] = [
        "RESOLVED COUNTERPARTIES",
        "(pre-extracted from the filing excerpts above; use these as anchors when",
        "referring to named customers, suppliers, partners, or competitors.",
        "Do NOT re-quote verbatim text from the filings for these entities — cite",
        "them by name. Resolved tickers in $ notation indicate companies tracked",
        "elsewhere in this research platform.)",
        "",
    ]

    def _fmt_entry(e) -> str:
        # e: CounterpartyEntry
        ticker_suffix = f" (${e.resolved_ticker})" if e.resolved_ticker else ""
        parts = [f"{e.name}{ticker_suffix}", e.relationship_type]
        if e.magnitude_pct is not None:
            parts.append(f"{e.magnitude_pct:.1f}%")
        return "    - " + " — ".join(parts)

    if ctx.outbound:
        lines.append("Outbound — disclosed relationships:")
        # Stable type order — show concentration-relevant buckets first.
        type_order = [
            "customer", "supplier", "partner", "joint_venture",
            "licensor", "licensee", "distributor", "reseller",
            "competitor", "other",
        ]
        for t in type_order:
            entries = ctx.outbound.get(t)
            if not entries:
                continue
            lines.append(f"  {t.replace('_', ' ').title()}s:")
            for e in entries:
                lines.append(_fmt_entry(e))
        lines.append("")

    if ctx.inbound:
        lines.append("Mentioned by others — who named this ticker in their own filings:")
        for t, entries in sorted(ctx.inbound.items()):
            if not entries:
                continue
            lines.append(f"  As a {t.replace('_', ' ')} ({len(entries)} mention(s)):")
            for e in entries:
                lines.append(f"    - ${e.resolved_ticker} — {e.relationship_type}")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
```

The `ctx` parameter is typed loosely (no top-level import of `CounterpartyContext`) to keep the import graph cheap; runtime duck-typing is sufficient and mirrors how other builders in this file handle their payloads.

- [ ] **Step 3: Pass `counterparty_context` as a kwarg to `node_deep_dive` + into `DEEP_DIVE_USER.format`**

In `nodes.py`, update the `node_deep_dive` signature to accept the new kwarg (mirror `filing_sections`):

```python
async def node_deep_dive(
    state: ResearchState,
    ...,
    filing_sections: dict | None = None,
    counterparty_context=None,  # CounterpartyContext | None
) -> ResearchState:
```

Inside `node_deep_dive`, where `_build_filing_excerpt_context(cat)` is called to assemble the per-category context (line ~1116 per the earlier grep), add a sibling:

```python
counterparty_ctx_text = _build_counterparty_context(cat, counterparty_context) if counterparty_context else ""
```

Pass it into `_run_one_category` by whatever mechanism filing_excerpts_context is currently passed (locals block / kwargs — read the surrounding code). The destination is the `DEEP_DIVE_USER.format(...)` call at line 530, which becomes:

```python
DEEP_DIVE_USER.format(
    ticker=ticker,
    theme=theme_id,
    category=category,
    data=data,
    transcript_data=transcript_context,
    macro_data=macro_context,
    technical_data=technical_context,
    sentiment_data=sentiment_context,
    edgar_data=edgar_context,
    filing_excerpts=filing_excerpts_context,
    counterparty_context=counterparty_ctx_text,
    loop_context=loop_context,
),
```

**Important:** the `.format(...)` call MUST include every slot in the template. After adding `{counterparty_context}` to `prompts.py` in Step 1, any `.format` call that doesn't include `counterparty_context=` will fail with `KeyError` at runtime. If there's a second `.format(DEEP_DIVE_USER, ...)` call elsewhere, update it too. Grep to confirm:

```bash
grep -n "DEEP_DIVE_USER\.format\|DEEP_DIVE_USER %\|DEEP_DIVE_USER," backend/app/graph/
```

Expected: a small number of matches (most likely just the one at nodes.py:530). Update every one.

- [ ] **Step 4: Start the backend + run a deep-dive (end-to-end smoke)**

Restart `uvicorn`. Pick a ticker that already has relationship data (e.g. ORCL after Phase 1 validation). Run a fresh pipeline via the UI (`/pipeline/new`) — or, faster, trigger the deep-dive node directly with curl:

```bash
# Find an existing ORCL run with a completed quick_screen phase, then:
curl -s "http://localhost:8000/api/runs" | jq 'first(.[] | select(.ticker == "ORCL"))'
# then start a new one:
curl -s -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"ticker": "ORCL", "theme_id": "<any valid theme id>"}' | jq
```

Tail the uvicorn logs for the deep-dive phase. Expected: no `KeyError: 'counterparty_context'` in logs, categories run through Haiku/Sonnet normally.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/prompts.py backend/app/graph/nodes.py
git commit -m "feat(prompts): route counterparty graph into deep-dive prompts

Adds RELATIONSHIP_ROUTING = {business_quality, risk_assessment,
future_durability} and a {counterparty_context} slot in DEEP_DIVE_USER
immediately below {filing_excerpts}. The slot is empty when a category
isn't routed or when no relationship data exists for the ticker.
Renderer uses 'anchors not re-quotes' framing to discourage the LLM
from restating filing text already provided upstream."
```

### Task 12: Phase 2 end-to-end validation

**Files:** none modified.

- [ ] **Step 1: Run a deep-dive on ORCL and capture the output**

With both servers running, open `/pipeline/new`, start an ORCL run on a theme you know ORCL is in. Wait for the full pipeline (quick screen → deep dive → thesis → risk) to complete. Open the report page.

- [ ] **Step 2: Inspect Business Quality / Risk Assessment / Future Durability sections**

For each of the three routed categories, look at the analysis prose. Check for:

- ✅ Named counterparties are cited BY NAME — e.g. "Ampere Computing", "$MSFT" — not described only by role ("a hyperscaler customer").
- ✅ Ticker notation appears for resolved counterparties (`$MSFT`, `$AMZN`).
- ✅ No verbatim quote blocks re-quoting Item 1/1A text for entities already in the counterparty list.
- ✅ If any ticker in the theme has named ORCL (inbound mentions), at least one of the three categories should reference it (e.g. "cited as a supplier by $FOO").

Compare quickly against the Business Quality / Risk Assessment output from before Phase 2 (git-stash-restore onto `main`, or look at an existing ORCL run in the DB before this PR's merge). The prompt change should produce qualitatively different, more grounded prose — NOT identical text.

- [ ] **Step 3: If the LLM is still re-quoting, iterate on the slot wording**

If the output still contains large verbatim blocks from Item 1/1A for entities that are in the counterparty list, the "do not re-quote" instruction isn't strong enough. Tweak the slot header in `_build_counterparty_context` (Task 11 Step 2) to be more prescriptive. Example stronger wording:

```
IMPORTANT — HOW TO USE THIS LIST:
- When referring to any entity below, cite them by name only.
- Do NOT quote verbatim passages from the filing excerpts above if the
  passage is about an entity in this list.
- Use this list as your canonical roster of named customers, suppliers,
  partners, and competitors for this ticker.
```

Re-run one deep-dive and re-check. Commit the iteration separately so the history shows the tuning step.

- [ ] **Step 4: Inspect the `SupplyChainEcosystem` card on the deep-dive dashboard**

The card reads from the same `relationships` / `counterparty_aliases` tables, unchanged by this PR. After Phase 1 fan-out + Phase 2 deep-dive, the card should be populated for any fanned-out ticker — verify visually.

- [ ] **Step 5: No commit — Phase 2 validation only.**

---

## Phase 3 — Open PR

### Task 13: Open the PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/relationships-fanout-prompt-routing
```

- [ ] **Step 2: Create the PR**

```bash
gh pr create --title "feat: relationship fan-out + prompt routing (Tier 3 v2 completion)" --body "$(cat <<'EOF'
## Summary
- Fan-out service + endpoints populate the relationships graph across a whole theme (or a single ticker) on demand.
- Resolved counterparties route into Business Quality / Risk Assessment / Future Durability deep-dive prompts as structured anchors.
- Item 1A heading regex tolerates mid-word whitespace splits (fixes ORCL-class 10-Ks).

Spec: \`docs/superpowers/specs/2026-04-20-tier-3-v2-fanout-prompt-routing-design.md\`
Plan: \`docs/superpowers/plans/2026-04-20-tier-3-v2-fanout-prompt-routing.md\`

## Test plan
- [ ] Phase 0: ORCL 10-K Item 1A extracted text goes from ~2KB cross-refs to multi-KB real prose.
- [ ] Phase 1: theme-level fan-out button on \`/filings\` populates relationships for a 5-8 ticker theme; status endpoint ticks through \`ingest/extract/resolve\` stages.
- [ ] Phase 1 idempotency: second fan-out on the same theme completes much faster with no new rows.
- [ ] Phase 2: ORCL deep-dive re-run cites named counterparties by name + \`$TICKER\` notation in BQ / RA / FD sections; no verbatim re-quotes for listed entities.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL in output.

---

## Self-review

**Spec coverage check:**

| Spec section | Task |
| --- | --- |
| Item 1A regex fix | Task 1 |
| `FanoutService` + `FanoutStatus` | Task 2 |
| Theme-scoped fan-out | Task 3 |
| 3 endpoints + router mount | Task 4 |
| Frontend api.ts types + client | Task 5 |
| Ticker-card button + polling | Task 6 |
| Theme-panel button + polling | Task 7 |
| Phase 1 validation gate | Task 8 |
| `relationship_context.py` query layer | Task 9 |
| `PipelineService._fetch_counterparty_context` wiring | Task 10 |
| `RELATIONSHIP_ROUTING` + `_build_counterparty_context` + prompt slot | Task 11 |
| Phase 2 validation gate | Task 12 |
| PR | Task 13 |

**Placeholder scan:** No `TBD` / `TODO` / "implement later". Task 10 Step 3 explicitly chooses NOT to include counterparty_context in the `deep_dive_start` SSE event, with reasoning — not a deferral. Task 12 Step 3 includes a concrete prompt-tuning fallback with actual wording, not just "tune if needed".

**Type consistency:** `FanoutStatus` fields match between the backend dataclass (Task 2), the router's `.to_dict()` output (Task 2), and the TypeScript `FanoutStatus` interface (Task 5). `CounterpartyContext` and `CounterpartyEntry` fields match between `relationship_context.py` (Task 9) and the consumer in `_build_counterparty_context` (Task 11). `RELATIONSHIP_ROUTING` is a `set[str]` in both declaration and usage (`cat in RELATIONSHIP_ROUTING`).

**One known blind spot:** service function signatures (`ingest_ticker_sections`, `extract_ticker_relationships`, `resolve_ticker_relationships`). The plan's Task 2 Step 2 explicitly verifies these before first use rather than assuming them. If any don't accept `force=`, Task 2 Step 2 instructs to carry the argument through rather than silently drop it.
