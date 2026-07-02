# UX/IA Overhaul Implementation Plan (campaign B3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved UX/IA overhaul spec — dark theme everywhere, 6-entry nav + global ⌘K, earnings-day unblock, curation-queue dismiss, questions/Library/Performance overhauls, and the small-fix bundle.

**Architecture:** Four phases, each a branch + PR that ships working software: (1) top-value fixes (preflight relaxation, curation tombstones, FMP scaling, Performance), (2) IA restructure (nav, global ⌘K, Today+Catalysts merge, demotions), (3) list management (questions snooze/bulk, Library rebuild + abandon, 8-K grouping), (4) small fixes + theme token sweep. Backend changes are additive (new endpoints/columns, relaxed preflight); frontend changes ride the existing typed `lib/api.ts` client.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic + stdlib `unittest` (backend); Next.js 16 App Router + React 19 + Tailwind v4 (frontend); Playwright MCP for live verification.

**Spec:** `docs/superpowers/specs/2026-06-10-ux-overhaul-design.md` — read it first. Audit context: `docs/superpowers/2026-06-10-ux-audit.md`.

**Branches:** one per phase, PR to `main`, merge before the next phase: `feat/ux-phase1-unblocks`, `feat/ux-phase2-ia`, `feat/ux-phase3-lists`, `feat/ux-phase4-theme`.

**House rules that apply to every task:**
- Backend imports are absolute (`backend.app.*`); run everything from project root with `backend/venv` active.
- Backend tests: `backend/venv/bin/python -m unittest backend.tests.<module> -v` from project root. Full suite: `python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')`. Lint: `ruff check backend`.
- Frontend gates (run from `frontend/`): `npm run typecheck` && `npm run lint` && `npm test` && `npm run build`. Every task touching frontend ends with all four green.
- Services consumed by routes are **commit-free** — API routes own the session and commit. Background writers use explicit commits.
- Tickers upper-cased at API entry.
- **Next.js 16 warning** (`frontend/AGENTS.md`): read the relevant guide in `node_modules/next/dist/docs/` before using any App Router API you haven't verified in this codebase (redirects, `useSearchParams`, layout-mounted client components).
- Live verification: backend `DATABASE_URL="postgresql+asyncpg://ericwyluda@localhost:5432/sector_research_test" uvicorn backend.app.main:app --reload` from repo root; frontend `npm run dev` with `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` (Docker steals IPv6 localhost:8000). Use Playwright MCP.
- New frontend colors: always token classes (`bg-[var(--surface)]`, `text-[var(--text-muted)]`…), never `bg-slate-*` — don't add to the pile Phase 4 sweeps.

---

# Phase 1 — Top-value fixes (`feat/ux-phase1-unblocks`)

### Task 1: Preflight relaxation — `no_ticker_model` becomes a warning

**Files:**
- Modify: `backend/app/services/workspace.py` (PreflightStatus ~line 92, `check_preflight` ~line 302, `_preflight` ~line 330)
- Modify: `backend/app/services/workspace_context.py` (line 24)
- Modify: `backend/app/api/workspace.py` (preflight route ~line 58 — confirm the response includes the new field)
- Test: `backend/tests/test_workspace_preflight.py` (extend if it exists — check `ls backend/tests/ | grep -i preflight` — otherwise create)

- [ ] **Step 1: Write the failing tests**

Add to the preflight test module (create with the same session-mocking style as the nearest existing workspace test if none exists; the existing tests for `check_preflight` mock `_gather_preflight_facts`):

```python
class TestPreflightModelRelaxation(unittest.IsolatedAsyncioTestCase):
    def _facts(self, **overrides):
        base = {
            "research_run_found": True,
            "research_run_completed": True,
            "research_run_ticker_matches": True,
            "ticker_model_found": False,
            "draft_present": False,
            "in_flight_run_id": None,
            "research_run": object(),
            "ticker_model": None,
        }
        base.update(overrides)
        return base

    async def test_no_model_is_warning_not_blocking(self):
        svc = WorkspaceService(fmp=None, edgar=None, anthropic=None)
        with mock.patch.object(svc, "_gather_preflight_facts", return_value=self._facts()):
            status = await svc.check_preflight(db=None, ticker="CORZ")
        self.assertTrue(status.ok)
        self.assertEqual(status.missing, [])
        self.assertEqual(status.warnings, ["no_ticker_model"])

    async def test_raising_preflight_allows_missing_model(self):
        svc = WorkspaceService(fmp=None, edgar=None, anthropic=None)
        with mock.patch.object(svc, "_gather_preflight_facts", return_value=self._facts()):
            ctx = await svc._preflight(None, "CORZ")
        self.assertIsNone(ctx["ticker_model"])

    async def test_draft_still_blocks(self):
        svc = WorkspaceService(fmp=None, edgar=None, anthropic=None)
        facts = self._facts(draft_present=True)
        with mock.patch.object(svc, "_gather_preflight_facts", return_value=facts):
            status = await svc.check_preflight(db=None, ticker="CORZ")
        self.assertFalse(status.ok)
        self.assertIn("unsaved_model_draft", status.missing)
```

Adapt constructor/mocking to the actual existing test style — `_gather_preflight_facts` returns the facts dict shown at `workspace.py:295-300` plus `research_run`/`ticker_model` entries (read `_gather_preflight_facts` to confirm exact keys before writing).

- [ ] **Step 2: Run tests to verify they fail**

`backend/venv/bin/python -m unittest backend.tests.test_workspace_preflight -v` → new tests FAIL (`PreflightStatus` has no `warnings`; `_preflight` raises on missing model).

- [ ] **Step 3: Implement**

In `backend/app/services/workspace.py`:

`PreflightStatus` — add the field and update the docstring:

```python
@dataclass
class PreflightStatus:
    """...existing docstring...

    `warnings` is a list of non-blocking advisory codes:
      - "no_ticker_model" — refresh will run but skip the model-update work.
    """
    ok: bool
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    in_flight_run_id: str | None = None
```

`check_preflight` — replace the `no_ticker_model` append:

```python
        warnings: list[str] = []
        if not facts["ticker_model_found"]:
            warnings.append("no_ticker_model")
```

and pass `warnings=warnings` to the returned `PreflightStatus`.

`_preflight` — delete the `if not facts["ticker_model_found"]: raise ValueError(...)` block (lines ~351-352). The returned dict already carries `"ticker_model": facts["ticker_model"]` which is now possibly `None`. Keep the draft check.

In `backend/app/services/workspace_context.py` line 24, change the comment to reflect optionality:

```python
    prior_ticker_model: Any  # TickerModel ORM row, or None when no saved model exists
```

In `backend/app/api/workspace.py`, check how the route serializes `PreflightStatus` — if it builds a dict manually, add `"warnings": status.warnings`; if it returns the dataclass, FastAPI picks the field up automatically.

- [ ] **Step 4: Run tests + full preflight module**

`backend/venv/bin/python -m unittest backend.tests.test_workspace_preflight -v` → PASS. Also run any other workspace test modules (`ls backend/tests/ | grep workspace`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workspace.py backend/app/services/workspace_context.py backend/app/api/workspace.py backend/tests/
git commit -m "feat(workspace): no_ticker_model preflight becomes non-blocking warning"
```

### Task 2: `step_update_refresh` model-skip path

**Files:**
- Modify: `backend/app/services/workspace_steps.py` (`step_update_refresh`, lines ~162-300)
- Modify: `backend/app/models/workspace_schemas.py` (`UpdateRefreshOutput`, ~line 75)
- Test: `backend/tests/test_workspace_steps.py` (or the module that currently tests `step_update_refresh` — find with `grep -rln step_update_refresh backend/tests/`)

- [ ] **Step 1: Write the failing test**

```python
    async def test_update_refresh_skips_model_when_none(self):
        ctx = make_ctx(prior_ticker_model=None)  # reuse the module's ctx factory; fmp/edgar mocked
        out = await step_update_refresh(ctx)
        self.assertTrue(out.model_skipped)
        self.assertEqual(out.version_before, 0)
        self.assertIsNone(out.version_after)
        self.assertEqual(out.changed_cells, [])
        self.assertIn("model refresh skipped", out.summary)
        # FMP statement fetches must NOT have been called
        ctx.fmp.get_income_statement.assert_not_called()
```

The EDGAR mock should still return a submissions payload so `new_filings` exercises the shared path.

- [ ] **Step 2: Run to verify it fails**

Expected: `AttributeError: 'NoneType' object has no attribute 'state'` (current line 168) and `UpdateRefreshOutput` has no `model_skipped`.

- [ ] **Step 3: Implement**

In `workspace_schemas.py`, add to `UpdateRefreshOutput` (additive — old persisted `step_outputs` keep validating):

```python
    model_skipped: bool = Field(
        default=False,
        description="True when no saved ticker model existed; model refresh was skipped (spec §6).",
    )
```

In `workspace_steps.py`, extract the existing EDGAR block (lines ~183-206, from `new_filings: list[FilingRef] = []` through the `except Exception: pass`) into a module-level helper:

```python
async def _fetch_new_filings(ctx: WorkspaceContext) -> list[FilingRef]:
    """Latest 10-Q/10-K ref from EDGAR submissions (best-effort, replicates
    the _latest_per_form logic from edgar_sections_ingest)."""
    new_filings: list[FilingRef] = []
    cik, _ = await ctx.edgar.get_ticker_to_cik(ctx.ticker)
    if cik:
        try:
            ...  # body moved verbatim from step_update_refresh
        except Exception:  # noqa: BLE001 — EDGAR is best-effort
            pass
    return new_filings
```

(move the body verbatim; don't re-indent logic). Then at the top of `step_update_refresh`, before the `prior_state = ...` line:

```python
    if ctx.prior_ticker_model is None:
        # No saved financial model — skip the ModelState refresh entirely
        # but still surface any new filing (spec §6 earnings-day unblock).
        new_filings = await _fetch_new_filings(ctx)
        filing_note = (
            f"loaded latest {new_filings[0].form} (filed {new_filings[0].fetched_at}); "
            if new_filings else "no new EDGAR filing detected; "
        )
        return UpdateRefreshOutput(
            version_before=0,
            version_after=None,
            changed_cells=[],
            removed_cells=[],
            new_filings=new_filings,
            consensus_delta=None,
            model_skipped=True,
            summary=filing_note + "no saved financial model — model refresh skipped",
        )
```

and replace the original inline EDGAR block in the normal path with `new_filings = await _fetch_new_filings(ctx)`.

- [ ] **Step 4: Run the step tests + the full backend suite for the workspace modules**

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(workspace): update_refresh skips ModelState work when no saved model"
```

### Task 3: WorkspaceButton visible reasons + UpdateRefreshCard skip note

**Files:**
- Modify: `frontend/lib/api.ts` (`WorkspacePreflight` type — add `warnings: string[]`; `UpdateRefreshOutput`-equivalent step type — add `model_skipped?: boolean`)
- Modify: `frontend/lib/hooks/useWorkspacePreflight.ts`
- Modify: `frontend/components/status/WorkspaceButton.tsx`
- Modify: `frontend/components/workspace/StepCards/UpdateRefreshCard.tsx`

- [ ] **Step 1: Types**

In `lib/api.ts` find `WorkspacePreflight` and add `warnings: string[];`. In the workspace step-output types find the update-refresh output and add `model_skipped?: boolean;`.

In `useWorkspacePreflight.ts`, the optimistic fallback object gains `warnings: []` (line 42). No other change — `missing` no longer contains `no_ticker_model`, so the existing copy map keeps working for the rest.

- [ ] **Step 2: WorkspaceButton — visible reason + CTA**

Replace the `title`-tooltip-only pattern. The button currently renders standalone (`WorkspaceButton.tsx`); render a reason line under it when blocked. Replace the component body with:

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { workspaceApi } from "@/lib/api";
import { useWorkspacePreflight } from "@/lib/hooks/useWorkspacePreflight";

const CTA: Record<string, { label: string; href: (t: string) => string }> = {
  unsaved_model_draft: { label: "Save or discard draft →", href: (t) => `/model/${t}#forecast` },
};

export function WorkspaceButton({ ticker, researchRunId }: { ticker: string; researchRunId: string }) {
  const router = useRouter();
  const { status: preflight, reasons } = useWorkspacePreflight(ticker, researchRunId);
  const inFlightRunId = preflight?.in_flight_run_id ?? null;
  const canKickOff = (preflight?.ok ?? false) || inFlightRunId != null;
  const blockedCode = preflight && !preflight.ok ? preflight.missing[0] : null;
  const cta = blockedCode ? CTA[blockedCode] : null;
  return (
    <span className="inline-flex flex-col items-start gap-0.5">
      <button
        type="button"
        disabled={!canKickOff}
        onClick={async (ev) => {
          ev.stopPropagation();
          if (inFlightRunId) {
            router.push(`/workspace/${inFlightRunId}`);
            return;
          }
          try {
            const { run_id } = await workspaceApi.kickOff(ticker, researchRunId);
            router.push(`/workspace/${run_id}`);
          } catch (err) {
            alert(`Workspace kick-off failed: ${err instanceof Error ? err.message : err}`);
          }
        }}
        className="rounded bg-[var(--surface-alt)] px-2 py-0.5 text-[11px] text-[var(--text-muted)] ring-1 ring-[var(--border)] hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        ↻ Workspace
      </button>
      {!canKickOff && reasons.length > 0 && (
        <span className="text-[10px] text-[var(--text-faint)]" onClick={(e) => e.stopPropagation()}>
          {reasons[0]}{" "}
          {cta && (
            <Link href={cta.href(ticker)} className="text-[var(--primary-dk)] hover:underline">
              {cta.label}
            </Link>
          )}
        </span>
      )}
    </span>
  );
}
```

Note the old `bg-slate-700/40` classes are replaced with tokens (house rule). Check the call sites (`grep -rn WorkspaceButton frontend/`) — the AttentionList also imports it; verify the extra reason line doesn't break either layout, and tighten with a `compact` prop only if a call site actually needs it.

- [ ] **Step 3: UpdateRefreshCard skip note**

In `UpdateRefreshCard.tsx`, where the card renders `version_before → version_after` / changed-cell info, branch on the new flag first:

```tsx
{output.model_skipped ? (
  <p className="text-xs text-[var(--text-muted)]">
    No financial model — model refresh skipped.{" "}
    <Link href={`/model/${ticker}#forecast`} className="text-[var(--primary-dk)] hover:underline">
      Create model →
    </Link>
  </p>
) : ( /* existing version/cells rendering */ )}
```

The card needs the `ticker` — check what props it receives (`grep -n "UpdateRefreshCard" frontend/components/workspace/`); `WorkspaceReport` knows the run's ticker, thread it through if absent.

- [ ] **Step 4: Gates + live verify**

Frontend gates green. Live: pick a board ticker with no model (preflight returns `warnings:["no_ticker_model"]`), click ↻ Workspace → run starts, step 1 card shows the skip note; pick a ticker with an unsaved draft → button disabled with visible "Save or discard…" link.

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(status): visible preflight reasons + model-skip CTA on workspace button"
```

### Task 4: Curation-queue dismiss — backend tombstones

**Files:**
- Modify: `backend/app/models/filing.py` (`CounterpartyAlias` — make `canonical_cik`/`canonical_ticker`/`canonical_name` nullable if not already; check the model first)
- Create: `backend/migrations/versions/<generated>_alias_tombstones.py` (only if nullability changes are needed)
- Modify: `backend/app/services/counterparty_resolver.py`
- Modify: `backend/app/api/filings.py`
- Test: `backend/tests/test_counterparty_dismiss.py` (new; copy session/fixture style from the existing resolver test module — find with `grep -rln counterparty backend/tests/`)

- [ ] **Step 1: Check nullability, write the failing tests**

Read `CounterpartyAlias` in `models/filing.py` (~line 272). If `canonical_cik`/`canonical_name` are `nullable=False`, change to `nullable=True` and generate a migration (`cd backend && alembic revision --autogenerate -m "alias tombstones"`). If already nullable, skip the migration.

Tests (new module, in-memory style consistent with existing resolver tests):

```python
class TestDismissCounterparty(unittest.IsolatedAsyncioTestCase):
    async def test_dismiss_writes_tombstone(self):
        # dismiss_counterparty(db, alias_name="OpenAI", created_by="ui-curator")
        # → CounterpartyAlias row: alias_normalized=normalize_name("OpenAI"),
        #   canonical_cik None, source "curator_private"
        ...

    async def test_resolver_skips_tombstoned_alias(self):
        # a Relationship row whose counterparty normalizes to a tombstoned alias
        # is NOT given resolved_to_cik and is counted under summary["skipped_private"]
        ...

    async def test_unresolved_queue_excludes_tombstoned(self):
        # list_unresolved_counterparties drops names whose normalized form has ANY alias row
        # (this already holds — pin it so the tombstone behavior can't regress)
        ...
```

Write the bodies against the real functions using the same async-session test harness the existing resolver tests use (read one first; don't invent a new harness).

- [ ] **Step 2: Run to verify failures** (`dismiss_counterparty` doesn't exist yet).

- [ ] **Step 3: Implement service functions**

In `counterparty_resolver.py`:

```python
async def dismiss_counterparty(
    db: AsyncSession, *, alias_name: str, created_by: str | None = None,
) -> dict:
    """Tombstone a counterparty as not-resolvable (private company etc).

    Writes a CounterpartyAlias with null canonical fields and
    source="curator_private". The unresolved queue already excludes any
    normalized name that has an alias row, so the tombstone removes it from
    the queue; the resolver skips applying null-cik aliases. Commit-free —
    caller owns the session.
    """
    norm = normalize_name(alias_name)
    existing = await _existing_alias_for(db, norm)
    if existing is not None:
        raise ValueError(f"alias already exists for {norm!r} (source={existing.source})")
    db.add(CounterpartyAlias(
        alias_name=alias_name,
        alias_normalized=norm,
        canonical_cik=None,
        canonical_ticker=None,
        canonical_name=None,
        source="curator_private",
        created_by=created_by,
    ))
    return {"alias_normalized": norm, "dismissed": True}


async def undismiss_counterparty(db: AsyncSession, *, alias_normalized: str) -> dict:
    """Delete a curator_private tombstone (Undo). Only tombstones are deletable."""
    row = await _existing_alias_for(db, alias_normalized)
    if row is None or row.source != "curator_private":
        raise ValueError(f"no curator_private tombstone for {alias_normalized!r}")
    await db.delete(row)
    return {"alias_normalized": alias_normalized, "restored": True}


async def list_dismissed(db: AsyncSession, limit: int = 100) -> list[CounterpartyAlias]:
    result = await db.execute(
        select(CounterpartyAlias)
        .where(CounterpartyAlias.source == "curator_private")
        .order_by(CounterpartyAlias.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())
```

In `resolve_ticker_relationships` (the per-row loop, ~line 311-326): where an existing alias is found and applied, skip tombstones —

```python
            existing = await _existing_alias_for(db, norm)
            if existing is not None:
                if existing.canonical_cik is None:
                    summary["skipped_private"] = summary.get("skipped_private", 0) + 1
                    local_alias_cache[norm] = None
                    continue
                ...  # existing apply path
```

Apply the same guard at the earlier alias-reuse branch (~line 316-321) — both alias lookups must treat null-cik aliases as "decided: do not resolve". Initialize `"skipped_private": 0` in the summary dict (~line 269).

- [ ] **Step 4: API endpoints**

In `api/filings.py`, after the `create_manual_alias` route:

```python
class DismissCounterpartyRequest(BaseModel):
    counterparty_name: str
    created_by: str | None = None


@router.post("/relationships/dismiss")
async def dismiss_counterparty_route(
    body: DismissCounterpartyRequest, db: AsyncSession = Depends(get_db),
) -> dict:
    """Tombstone a counterparty (private company / not resolvable). Spec §9."""
    try:
        result = await dismiss_counterparty(
            db, alias_name=body.counterparty_name, created_by=body.created_by,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return result


@router.delete("/relationships/dismiss/{alias_normalized}")
async def undismiss_counterparty_route(
    alias_normalized: str, db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        result = await undismiss_counterparty(db, alias_normalized=alias_normalized)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    await db.commit()
    return result


@router.get("/relationships/dismissed")
async def list_dismissed_route(
    limit: int = 100, db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = await list_dismissed(db, limit=limit)
    return [
        {"alias_name": r.alias_name, "alias_normalized": r.alias_normalized,
         "created_at": r.created_at.isoformat() if r.created_at else None}
        for r in rows
    ]
```

(import the three service functions at the top with the existing resolver imports).

- [ ] **Step 5: Tests green, migration applied (if any), full suite, commit**

```bash
git commit -am "feat(filings): curation-queue dismiss via curator_private alias tombstones"
```

### Task 5: Curation dismiss — frontend

**Files:**
- Modify: `frontend/lib/api.ts` (`relationships` client: add `dismiss(name)`, `undismiss(aliasNormalized)`, `listDismissed()`)
- Modify: `frontend/components/filings/CurationPanel.tsx`
- Modify: `frontend/app/filings/page.tsx` (queue-count badge in the header)

- [ ] **Step 1: API client methods** — follow the existing `relationships.createAlias` shape in `lib/api.ts`:

```ts
dismiss: (counterparty_name: string) =>
  post<{ alias_normalized: string; dismissed: boolean }>(`/api/relationships/dismiss`, { counterparty_name, created_by: "ui-curator" }),
undismiss: (aliasNormalized: string) =>
  del<{ alias_normalized: string; restored: boolean }>(`/api/relationships/dismiss/${encodeURIComponent(aliasNormalized)}`),
listDismissed: () =>
  get<{ alias_name: string; alias_normalized: string; created_at: string | null }[]>(`/api/relationships/dismissed`),
```

(match the module's actual fetch helpers — it may use a `request()` wrapper rather than `get/post/del`; mirror `createAlias` exactly, including the `/api` prefix convention used there.)

- [ ] **Step 2: CurationPanel** — add per-row dismiss + collapsed Dismissed section:

In the row header `div` (next to the counterparty name block), add:

```tsx
<button
  type="button"
  onClick={() => onDismiss(row)}
  disabled={busy === row.alias_normalized}
  className="shrink-0 text-[11px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--error-bg)] hover:text-[var(--error-text)] disabled:opacity-50 transition"
>
  Not public / dismiss
</button>
```

with handler mirroring `onApplyCandidate`:

```tsx
async function onDismiss(row: UnresolvedCounterparty) {
  setBusy(row.alias_normalized);
  setError(null);
  try {
    await relationships.dismiss(row.counterparty_name);
    setItems((cur) => cur?.filter((r) => r.alias_normalized !== row.alias_normalized) ?? null);
    setDismissed(null); // force reload of the dismissed section next expand
  } catch (e) {
    setError(e instanceof Error ? e.message : "dismiss failed");
  } finally {
    setBusy(null);
  }
}
```

Below the queue list, add a collapsed "Dismissed (private / not public)" disclosure that lazy-loads `relationships.listDismissed()` on first expand and renders each with an "Undo" button calling `relationships.undismiss(alias_normalized)` then reloading both lists. State: `const [dismissed, setDismissed] = useState<DismissedAlias[] | null>(null)` — same lazy pattern as `items`.

- [ ] **Step 3: Queue badge** — in `app/filings/page.tsx`'s header, render the pending count. CurationPanel already shows `{items.length} pending` when loaded; lift a lightweight count by having the page fetch `relationships.listUnresolved(50)` length server-side is wasteful — instead have CurationPanel always load the queue on mount (drop the `expanded && items === null` gate to plain `items === null` on mount) so its own header count shows without expanding. That satisfies the spec's "queue count badge" with no new endpoint.

- [ ] **Step 4: Gates + live verify** — dismiss OpenAI in the live queue → row disappears, appears under Dismissed, Undo restores it; re-run resolve for a ticker mentioning OpenAI → stays unresolved-skipped (check `skipped_private` in the resolve response).

- [ ] **Step 5: Commit**

```bash
git commit -am "feat(filings): dismiss/undo UI for curation queue"
```

### Task 6: FMP ratio scaling fix (StatisticsGrid + peer comp)

**Files:**
- Investigate first: `backend/app/services/company_snapshot.py` (~lines 112-160), `backend/app/services/peer_comp.py` (~lines 104-160)
- Test: `backend/tests/test_metric_scaling.py` (new, recorded payloads)
- Possibly modify: both services + `frontend/components/company/StatisticsGrid.tsx` only if the bug is render-side (unlikely)

- [ ] **Step 1: Dump live payloads (do NOT skip — CLAUDE.md FMP rule)**

With the venv active and `.env` loaded, run a scratch script (delete afterwards):

```bash
backend/venv/bin/python - <<'EOF'
import asyncio, json
from backend.app.clients.fmp_client import FMPClient
async def main():
    fmp = FMPClient()
    for t in ("ORCL", "MSFT", "CORZ"):
        ratios, _ = await fmp.get_ratios_ttm(t)
        km, _ = await fmp.get_key_metrics_ttm(t)
        growth, _ = await fmp.get_financial_growth(t)
        print(t, json.dumps({"ratios": ratios, "km": km, "growth": growth}, default=str)[:4000])
asyncio.run(main())
EOF
```

(adapt method names to `FMPClient`'s actual API — `grep -n "def get_ratios_ttm\|def get_key_metrics_ttm\|def get_financial_growth" backend/app/clients/fmp_client.py`.) Record for each suspect metric whether FMP returns a **fraction** (0.71) or **percent** (71.0): `grossProfitMarginTTM`, `operatingProfitMarginTTM`, `ebitdaMarginTTM`, `returnOnEquityTTM`, `returnOnInvestedCapitalTTM`, `revenueGrowth`, plus whatever key the 5Y CAGR comes from. The audit's observed values (Gross 118.1% true ~71%, FCF −5911.7%, Rev 5Y CAGR 70.3%) imply at least one consumer multiplies an already-percent value by 100, or derives `fcf_margin = p_s / p_fcf` against a near-zero/negative `p_fcf`.

- [ ] **Step 2: Write failing tests with the recorded payloads**

`backend/tests/test_metric_scaling.py` — paste trimmed real payloads as module constants, then assert the **builder outputs** are fractions in sane ranges:

```python
ORCL_RATIOS = {...}  # trimmed real payload from Step 1
ORCL_KM = {...}
ORCL_GROWTH = [...]

class TestStatisticsScaling(unittest.TestCase):
    def test_gross_margin_is_fraction(self):
        # exercise the same code path company_snapshot uses for the Gross stat
        # (extract a pure helper in Step 3 if the logic is inline) and assert
        # 0 < gross < 1 for ORCL (true value ~0.71)
        ...

    def test_fcf_margin_sane_or_none(self):
        # derived fcf_margin must be None or within (-2.0, 1.0); the −5911% case must not escape
        ...
```

Shape the tests around whatever the actual broken transformation turns out to be — the invariant to pin is the output range, with the real payload as input.

- [ ] **Step 3: Fix the builders**

Apply the per-key scaling the live dump showed (likely: keep fractions as fractions end-to-end and fix the frontend `unit="pct"` formatting, or divide by 100 where FMP returns percent-form). Add the sanity guard in both services:

```python
def _sane_margin(value: float | None, *, key: str, ticker: str) -> float | None:
    """Margin-type metrics outside [-2.0, 1.0] (fraction form) are logged and passed
    through — the UI must not render a silently wrong number without a trace."""
    if value is not None and not (-2.0 <= value <= 1.0):
        logger.warning("suspicious %s=%s for %s (scaling bug?)", key, value, ticker)
    return value
```

Check `StatisticsGrid.tsx`'s `pct` formatting (does it multiply by 100?) and `PeerCompTable`'s — the fix must make BOTH consumers correct, since they share the backend values. Trace one value end-to-end (ORCL gross: FMP → builder → API JSON → rendered string) and write down the convention in a comment at the top of each builder.

- [ ] **Step 4: Tests green; live verify** — `/company/ORCL` Overview shows Gross ≈ 71%, `/compare?tickers=ORCL,MSFT` margins sane; no console warnings.

- [ ] **Step 5: Commit**

```bash
git commit -am "fix(metrics): pin FMP ratio scaling with recorded payloads; sanity-guard margins"
```

### Task 7: Performance page — data-first defaults + taxonomy split

**Files:**
- Modify: `backend/app/api/outcomes.py` (summary endpoint — find with `grep -n "summary" backend/app/api/outcomes.py`)
- Modify: `frontend/app/performance/page.tsx` (default offset, line ~24)
- Modify: `frontend/components/performance/PerformanceFilters.tsx`, `HeroBand.tsx`, `ByVerdictTable.tsx`, `OutcomeList.tsx`
- Test: extend the outcomes API test module (`grep -rln outcomes backend/tests/`)

- [ ] **Step 1: Backend `populated_offsets`**

In the summary endpoint's service/query layer, compute which of `["1d","1w","1m","3m","6m"]` have at least one non-null snapshot among the rows in scope, and add `populated_offsets: list[str]` to the summary response model. Test: seed snapshots at 1d+1w only → response lists exactly `["1d","1w"]`.

- [ ] **Step 2: Frontend default offset**

In `performance/page.tsx`: when the URL has no `snapshot_offset` param, pick the **largest** populated offset from the summary response (order `6m > 3m > 1m > 1w > 1d`), falling back to `"1m"` if the list is empty. URL param always wins. When the active offset is NOT in `populated_offsets`, render an annotation in `HeroBand` instead of bare em-dashes:

```tsx
<p className="text-xs text-[var(--text-muted)]">
  No {offset} snapshots yet — outcomes are too young for this horizon.
</p>
```

- [ ] **Step 3: Superseded hidden by default**

`OutcomeList` / the page's outcomes fetch: pass `superseded=false` unless a new "Show superseded" checkbox in `PerformanceFilters` is on (URL param `superseded=1`). The backend filter already exists (`?superseded=` in `api/outcomes.py`).

- [ ] **Step 4: Taxonomy split**

In `ByVerdictTable.tsx`: split the mixed Band column into two columns — **Run verdict** (`completed` / `watchlist` rows) and **Workspace health** (`healthy` / `imminent` / `stale` / `triggered` / `broken`). Look at the rows the API actually returns (the band values are produced backend-side — find the grouping in the outcomes service); if the API mixes them in one `band` field, group rows into two sections client-side by membership in the health-vocabulary set, with a section header row for each.

- [ ] **Step 5: Gates, live verify (page loads with data visible, no em-dash wall), commit**

```bash
git commit -am "feat(performance): data-first default offset, hide superseded, split verdict/health taxonomy"
```

### Task 8: Phase 1 wrap — PR

- [ ] Full backend suite + ruff + all frontend gates green.
- [ ] Live walk: earnings-day journey end-to-end on a no-model ticker (Status → earnings drawer → ↻ Workspace → completed run with skip note) — count the steps, compare to B1's 6-step detour.
- [ ] `git push -u origin feat/ux-phase1-unblocks`, open PR titled "UX overhaul phase 1: earnings unblock, curation dismiss, metric scaling, performance defaults", merge after CI green (gh API may 401 on merge — use git/SSH per memory).

---

# Phase 2 — IA restructure (`feat/ux-phase2-ia`)

### Task 9: `GET /api/tickers` — quick-switcher source

**Files:**
- Create: `backend/app/api/tickers.py`
- Modify: `backend/app/main.py` (register router — copy the pattern of the existing `include_router` lines)
- Test: `backend/tests/test_tickers_api.py`

- [ ] **Step 1: Failing test** — seed a theme with `seed_tickers=["NVDA"]`, a research_run for `ORCL`, a ticker_model for `MSFT`; assert the endpoint returns all three exactly once, upper-case, sorted (no FMP calls — ticker-only payload).

- [ ] **Step 2: Implement**

```python
"""GET /api/tickers — distinct known tickers for the global command palette.

Union of theme seed_tickers ∪ research_runs.ticker ∪ ticker_models.ticker.
Deliberately DB-only (no FMP) so the palette opens instantly.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.research_run import ResearchRun
from backend.app.models.theme import Theme
from backend.app.models.ticker_model import TickerModel

router = APIRouter(prefix="/api", tags=["tickers"])


@router.get("/tickers")
async def list_tickers(db: AsyncSession = Depends(get_db)) -> list[dict]:
    tickers: set[str] = set()
    for theme in (await db.execute(select(Theme))).scalars():
        tickers.update(t.upper() for t in (theme.seed_tickers or []))
    for (t,) in (await db.execute(select(ResearchRun.ticker).distinct())).all():
        if t:
            tickers.add(t.upper())
    for (t,) in (await db.execute(select(TickerModel.ticker).distinct())).all():
        if t:
            tickers.add(t.upper())
    return [{"ticker": t} for t in sorted(tickers)]
```

(verify model/field names — `Theme.seed_tickers` is JSONB; adjust imports to actual module paths with `grep -rn "class Theme" backend/app/models/`.)

- [ ] **Step 3: Tests green, commit** — `git commit -am "feat(api): GET /api/tickers for global command palette"`

### Task 10: Global ⌘K command palette

**Files:**
- Create: `frontend/components/GlobalCommandPalette.tsx`
- Modify: `frontend/app/layout.tsx` (mount it)
- Modify: `frontend/components/deep-dive/DeepDiveDashboard.tsx` (or wherever `<CommandPalette />` is mounted — `grep -rn "CommandPalette" frontend/` — remove the report-local mount)
- Modify: `frontend/lib/api.ts` (add `getTickers()`; reuse existing recent-runs list calls)
- Keep: `frontend/components/deep-dive/sections.ts` (single registry, now consumed by the global palette)

- [ ] **Step 1: Build the component**

Start from a copy of `frontend/components/deep-dive/CommandPalette.tsx` (keep `scoreMatch`, the keyboard plumbing, the modal markup — they're proven). Changes:

1. **Item type** gains an `action: () => void` instead of section-jump-only:

```tsx
interface PaletteItem {
  id: string;
  group: "Ticker" | "Surface" | "Run" | "Action" | "Section";
  title: string;
  searchBlob: string;
  run: (router: ReturnType<typeof useRouter>) => void;
}
```

2. **Static surfaces** (module-level — includes every demoted page):

```tsx
const SURFACES: { title: string; href: string }[] = [
  { title: "Today", href: "/" },
  { title: "Calendar", href: "/?tab=calendar" },
  { title: "Status board", href: "/status" },
  { title: "Themes", href: "/themes" },
  { title: "Filings", href: "/filings" },
  { title: "Filings graph", href: "/filings/graph" },
  { title: "Performance", href: "/performance" },
  { title: "Library", href: "/library" },
  { title: "Questions", href: "/questions" },
  { title: "Workspace runs", href: "/workspace" },
  { title: "Prospectus reports", href: "/prospectus" },
  { title: "Compare peers", href: "/compare" },
  { title: "New research run", href: "/pipeline/new" },
];
```

3. **Dynamic sources, fetched once per open** (in an effect keyed on `open`, results cached in a ref for the session): `getTickers()` → Ticker items (`run: r => r.push(\`/company/${t}\`)`), and the existing recent-runs list call from `lib/api.ts` (whatever `/library` uses — `grep -n "listRuns\|getRuns" frontend/lib/api.ts`) limited to 15 → Run items (`{TICKER} · {date} · {status}` → `/pipeline/{run_id}`).

4. **Actions**: when the query looks like a ticker that matched a Ticker item, append contextual actions for it:

```tsx
{ group: "Action", title: `New run: ${t}`, run: (r) => r.push(`/pipeline/new?ticker=${t}`) },
{ group: "Action", title: `Log trade: ${t}`, run: (r) => r.push(`/performance?log_trade=${t}`) },
```

(check `/pipeline/new` reads a `?ticker=` prefill param — `grep -n "searchParams\|ticker" frontend/app/pipeline/new/page.tsx`; if it doesn't, add that one-line prefill while you're there.)

5. **Sections on report pages**: `usePathname()`; when it matches `/pipeline/[runId]`, append `SECTIONS` (import from `@/components/deep-dive/sections`) as `group: "Section"` items with the original scroll-into-view behavior (`document.getElementById(id)?.scrollIntoView(...)`).

6. **Ranking:** filter+sort with `scoreMatch` as before, but stable-group results in order Ticker → Action → Section → Surface → Run when scores tie.

- [ ] **Step 2: Mount + retire**

In `app/layout.tsx`, render `<GlobalCommandPalette />` (client component inside the body, next to `<Nav />`). Remove the report-local `<CommandPalette />` mount; delete `frontend/components/deep-dive/CommandPalette.tsx` once nothing imports it (`npm run typecheck` will confirm).

- [ ] **Step 3: Gates + live verify** — ⌘K from `/status`: type "orcl" → Ticker + New-run + Log-trade entries; Enter navigates to `/company/ORCL`. From a report page: section entries appear and still smooth-scroll. Esc/arrows work everywhere.

- [ ] **Step 4: Commit** — `git commit -am "feat(nav): global ⌘K command palette (tickers, surfaces, runs, actions)"`

### Task 11: Nav slim-down

**Files:**
- Modify: `frontend/components/Nav.tsx`

- [ ] **Step 1: New links array + ⌘K hint**

```tsx
const links = [
  { href: "/",            label: "Today"       },
  { href: "/status",      label: "Status"      },
  { href: "/themes",      label: "Themes"      },
  { href: "/filings",     label: "Filings"     },
  { href: "/performance", label: "Performance" },
  { href: "/library",     label: "Library"     },
];
```

Active-state: the current `path.startsWith(href.replace("/new", ""))` logic keeps working with the slimmed list (the `.replace` becomes a no-op — simplify to `path.startsWith(href)`); spot-check that `/theme/[id]` still highlights Themes (it starts with `/theme`, not `/themes` — keep the existing behavior, whatever it was, by testing before/after). After the ticker-box form, add the hint chip:

```tsx
<button
  type="button"
  onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
  className="ml-1 text-[10px] font-mono text-[var(--text-faint)] border border-[var(--border)] rounded px-1.5 py-0.5 hover:text-[var(--text-muted)]"
  aria-label="Open command palette"
>
  ⌘K
</button>
```

(If the synthetic-event trick doesn't trigger the palette listener, export a tiny `openPalette()` setter from `GlobalCommandPalette` via a module-level event emitter instead — `window.dispatchEvent(new CustomEvent("open-palette"))` with a matching listener in the palette.)

- [ ] **Step 2: Gates + live verify** — 6 entries render; `/catalysts`, `/prospectus`, `/workspace`, `/questions`, `/pipeline/new` all still load by URL.

- [ ] **Step 3: Commit** — `git commit -am "feat(nav): slim to 6 entries + command-palette hint"`

### Task 12: Today + Catalysts merge

**Files:**
- Modify: `frontend/app/page.tsx` (tab strip)
- Replace: `frontend/app/catalysts/page.tsx` (redirect)
- Modify: `frontend/components/catalysts/CatalystsView.tsx` (only if its props need loosening)
- Modify: `frontend/lib/api.ts` only if `getCatalysts()` isn't callable client-side already (it is — check)

- [ ] **Step 0: Read the Next.js 16 docs for `redirect` and `useSearchParams`** in `node_modules/next/dist/docs/` before writing the redirect or tab-param code. Note `app/page.tsx` is already `"use client"`; `useSearchParams` on a client page may require a `<Suspense>` boundary — the docs say.

- [ ] **Step 1: Tab strip on `/`**

In `app/page.tsx`, add tab state from the URL (`?tab=calendar` ⇒ Calendar, default Briefing):

```tsx
const searchParams = useSearchParams();
const tab = searchParams.get("tab") === "calendar" ? "calendar" : "briefing";
```

Render a tab strip under the page header:

```tsx
<div className="flex gap-1 border-b border-[var(--border)]" data-print-hide="true">
  {(["briefing", "calendar"] as const).map((t) => (
    <Link key={t} href={t === "briefing" ? "/" : "/?tab=calendar"} scroll={false}
      className={clsx("px-3 py-1.5 text-sm rounded-t-md",
        tab === t ? "bg-[var(--surface)] text-[var(--text)] font-medium border border-b-0 border-[var(--border)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text)]")}>
      {t === "briefing" ? "Briefing" : "Calendar"}
    </Link>
  ))}
</div>
```

Briefing tab = the existing page content unchanged. Calendar tab = `<CatalystsView buckets={buckets} />` where `buckets` is client-fetched via `getCatalysts()` lazily when the tab first activates (same `useState<CatalystListResponse | null>(null)` + effect pattern the page already uses for its other sources; error state renders the same inline error note the old `/catalysts` page showed).

- [ ] **Step 2: Redirect `/catalysts`**

Replace `frontend/app/catalysts/page.tsx` body with the server-side redirect (exact API per the Next 16 docs read in Step 0):

```tsx
import { redirect } from "next/navigation";

export default function CatalystsRedirect() {
  redirect("/?tab=calendar");
}
```

- [ ] **Step 3: Gates + live verify** — `/` shows Briefing; `/?tab=calendar` shows week lanes + agenda + List toggle, all features from the old page work (toggle, earnings deep-links to `/status?expand_earnings=`); `/catalysts` lands on the Calendar tab.

- [ ] **Step 4: Commit** — `git commit -am "feat(today): absorb catalysts as Calendar tab; redirect /catalysts"`

### Task 13: Attention ordering, agenda compaction, archived-thesis tag

**Files:**
- Modify: `frontend/lib/todayDerive.ts` + its tests `frontend/lib/todayDerive.test.mts` (severity ordering)
- Modify: `frontend/components/catalysts/AgendaList.tsx` / `AgendaRow.tsx` (compaction + tag — read both first)
- Modify: whatever passes board data to the agenda (the archived tag needs to know which tickers have active board entries — `CatalystsView` receives buckets; the calendar view fetches `/api/catalysts/calendar`; check whether the agenda rows carry a flag already or the Today page's `board` can be threaded in)

- [ ] **Step 1: Severity ordering (TDD — this file has a node test suite)**

In `todayDerive.test.mts`, add a test that `deriveAttention` returns items ordered: high-materiality events, then medium, then question rollups; within a tier, preserve current ordering. Run `npm test` → fails. Implement in `deriveAttention` (a sort with an explicit tier function — read the item-shape union first). Run → passes.

- [ ] **Step 2: Fuzzy-date compaction**

In the agenda components: events whose catalyst has no resolved date (the "Next 1-3 mo" style rows — find the field that distinguishes fuzzy from dated rows by reading `AgendaList`/the calendar-event type in `lib/api.ts`) collapse into one compact group per ticker at the bottom of the agenda: a single row `CORZ — 3 undated catalysts` expandable (`usePersistedCollapse` is for sections; plain `useState` is fine here) to the full sentences. Dated rows keep current rendering.

- [ ] **Step 3: Archived-thesis tag**

Agenda rows whose ticker has no active board entry get a muted chip `archived thesis` after the ticker. Cheapest source of truth: the Today page already fetches the board — thread a `Set<string>` of active board tickers into `CatalystsView → AgendaList` as an optional prop (`activeTickers?: Set<string>`); when provided and `!activeTickers.has(row.ticker)`, render the chip. (Old `/catalysts` consumers are gone after Task 12, so the prop can be required-optional without breakage.)

- [ ] **Step 4: Gates (`npm test` includes the new derive test) + live verify + commit**

```bash
git commit -am "feat(today): attention severity ordering, agenda compaction, archived-thesis tags"
```

### Task 14: Demotion affordances (Prospectus list on Filings, Workspace retry)

**Files:**
- Modify: `frontend/app/filings/page.tsx` (Prospectus reports section)
- Modify: `frontend/app/workspace/page.tsx` (Retry on failed rows)
- Check: `frontend/components/prospectus/ProspectusList.tsx` props (reuse it on Filings if it's self-fetching or takes a list prop)

- [ ] **Step 1: Prospectus section on `/filings`** — under the existing "+ New prospectus report" button's area, render the existing `ProspectusList` (read it: if it's the component `/prospectus` uses and it fetches its own data, drop it in directly inside a collapsed-by-default disclosure titled "Prospectus reports"; if `/prospectus`'s page does the fetching, lift that fetch pattern). `/prospectus` page stays untouched.

- [ ] **Step 2: Workspace retry** — in `app/workspace/page.tsx`, rows with `status === "failed"` get a `Retry` button that calls `workspaceApi.kickOff(row.ticker)` (no pinned research_run_id — preflight revalidates) and routes to the new run. Reuse the kick-off + error-alert pattern from `WorkspaceButton`.

- [ ] **Step 3: Gates + live verify + commit**

```bash
git commit -am "feat(ia): prospectus list on filings, retry for failed workspace runs"
```

### Task 15: Status-board row menu + kill-criteria drawer (spec §6)

**Files:**
- Modify: `frontend/app/status/page.tsx` (row menu — currently "Open report" / "Archive"; find with `grep -n "Archive\|Open report" frontend/app/status/page.tsx`)
- Create: `frontend/components/status/KillCriteriaDrawer.tsx` (model it on `ReadThroughDrawer.tsx` / `EarningsDrawer.tsx` — read both first; same inline-expand pattern)
- Modify: `frontend/lib/api.ts` (kill-criteria toggle method — check whether a client for `PUT /api/runs/{id}/kill-criteria/{ordinal}` already exists with `grep -n "kill" frontend/lib/api.ts`; add if missing)

- [ ] **Step 1: Row menu entries** — add to the ⋯ menu, above Archive:

```tsx
{ label: "Company workspace", href: `/company/${entry.ticker}` },
{ label: "Model",             href: `/model/${entry.ticker}#forecast` },
{ label: "View questions",    href: `/questions?ticker=${entry.ticker}` },
```

(adapt to the menu's actual item shape — it may render plain `<Link>`s; match it.)

- [ ] **Step 2: Kill-criteria drawer** — third drawer beside read-throughs/earnings. The board payload already carries each entry's kill-criteria summary (see `StatusBoardEntry` in `lib/api.ts` — find the field). Drawer rows: criterion text · armed/triggered toggle wired to the PUT endpoint (optimistic update + revert on error), matching the toggle semantics the workspace-run report already renders (`grep -rn "kill" frontend/components/workspace/` for the existing toggle to mirror). Trigger chip on the row (e.g., `KC n/m`) opens it, like the events/earnings chips.
- [ ] **Step 3: Gates + live verify** — toggle a criterion from the board; reload; state persisted. Row menu links land on company/model/questions pages.
- [ ] **Step 4: Commit** — `git commit -am "feat(status): row-menu company/model/questions links + kill-criteria drawer"`

### Task 16: Phase 2 wrap — PR

- [ ] All gates green; live walk: every demoted surface reachable in ≤2 actions (⌘K → entry, or contextual link). `/catalysts` redirect verified.
- [ ] Push `feat/ux-phase2-ia`, PR "UX overhaul phase 2: 6-entry nav, global ⌘K, Today+Catalysts merge", merge after CI.

---

# Phase 3 — List management (`feat/ux-phase3-lists`)

### Task 17: Questions — `snoozed_until` + bulk endpoint (backend)

**Files:**
- Modify: `backend/app/models/question.py` (add column)
- Create: `backend/migrations/versions/<generated>_question_snooze.py`
- Modify: `backend/app/api/questions.py`
- Test: extend the questions API test module (`grep -rln "questions" backend/tests/ | head`)

- [ ] **Step 1: Failing tests**

```python
    async def test_snoozed_questions_excluded_from_open_list(self):
        # question with snoozed_until = now+7d does not appear in GET /questions?status=open
        # and does not count in GET /questions/by-ticker rollups
        ...

    async def test_snooze_expiry_reincludes(self):
        # snoozed_until = now-1h → appears again
        ...

    async def test_bulk_dismiss_by_filter(self):
        # POST /questions/bulk {filter: {ticker: "CORZ", priority: 3}, action: "dismiss"}
        # dismisses exactly the matching open questions, returns {"affected": N}
        ...

    async def test_bulk_snooze_by_ids(self):
        # POST /questions/bulk {ids: [...], action: "snooze", snooze_days: 7}
        # sets snoozed_until ≈ now+7d on those rows only
        ...
```

(write real bodies in the existing module's harness style — it has API tests for dismiss/resolve to copy.)

- [ ] **Step 2: Model + migration**

```python
    snoozed_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

`cd backend && alembic revision --autogenerate -m "question snoozed_until"` then `alembic upgrade head`.

- [ ] **Step 3: Exclusion in list + rollup**

In `api/questions.py`, both `GET /questions` (when `status` is `"open"`, the default) and `GET /questions/by-ticker` add:

```python
from sqlalchemy import or_, func
...
    .where(or_(Question.snoozed_until.is_(None), Question.snoozed_until <= func.now()))
```

(by-ticker builds counts — add the same predicate to its filtered aggregation; read the existing query first.)

- [ ] **Step 4: Bulk endpoint**

```python
class BulkFilter(BaseModel):
    ticker: str | None = None
    theme_id: str | None = None
    priority: int | None = None
    category: str | None = None
    status: str = "open"


class BulkBody(BaseModel):
    ids: list[str] | None = None
    filter: BulkFilter | None = None
    action: Literal["dismiss", "resolve", "snooze"]
    note: str | None = Field(default=None, max_length=2000)
    answer_text: str | None = Field(default=None, max_length=10000)
    snooze_days: int = Field(default=7, ge=1, le=90)


@router.post("/questions/bulk")
async def bulk_action(body: BulkBody, db: AsyncSession = Depends(get_db)) -> dict:
    """Apply dismiss/resolve/snooze to a set of questions (spec §7).
    Exactly one of `ids` / `filter` must be provided. `resolve` requires answer_text."""
    if (body.ids is None) == (body.filter is None):
        raise HTTPException(status_code=422, detail="provide exactly one of ids|filter")
    if body.action == "resolve" and not body.answer_text:
        raise HTTPException(status_code=422, detail="resolve requires answer_text")

    q = select(Question)
    if body.ids is not None:
        q = q.where(Question.id.in_(body.ids))
    else:
        f = body.filter
        q = q.where(Question.status == f.status)
        if f.ticker:
            q = q.where(Question.ticker == f.ticker.upper())
        if f.theme_id:
            q = q.where(Question.theme_id == f.theme_id)
        if f.priority is not None:
            q = q.where(Question.priority == f.priority)
        if f.category:
            q = q.where(Question.category == f.category)

    rows = list((await db.execute(q)).scalars())
    now = datetime.now(timezone.utc)
    for row in rows:
        if body.action == "dismiss":
            row.status = "dismissed"
            row.dismissed_at = now
            row.dismiss_note = body.note
        elif body.action == "resolve":
            row.status = "resolved_manual"
            row.answer_text = body.answer_text
            row.answer_source = "manual"
            row.resolved_at = now
        else:  # snooze
            row.snoozed_until = now + timedelta(days=body.snooze_days)
    await db.commit()
    return {"affected": len(rows)}
```

(match the state transitions exactly to the existing per-row endpoints at lines ~137-195 — copy their field assignments, don't re-derive.)

- [ ] **Step 5: Tests green, full suite, commit**

```bash
git commit -am "feat(questions): snoozed_until column + POST /questions/bulk"
```

### Task 18: Questions — filters, checkboxes, bulk bar (frontend)

**Files:**
- Modify: `frontend/lib/api.ts` (`questions` client: `bulk(body)`; `Question` type gains `snoozed_until: string | null`)
- Modify: `frontend/components/questions/OpenQuestionsPanel.tsx`, `QuestionRow.tsx` (read both first; the page is `frontend/app/questions/page.tsx`, 166 lines)

- [ ] **Step 1:** Filter chips (priority P1/P2/P3, category) in the drilled `?ticker=` view — client-side filtering over the already-fetched list is fine at these sizes; chips toggle in URL params so links are shareable.

- [ ] **Step 2:** Row checkboxes + header "select all matching filter" checkbox + a bulk bar that appears when ≥1 selected:

```
[n selected]  [Dismiss]  [Snooze 7d]  [Snooze 30d]   (Resolve stays per-row)
```

Dismiss/snooze call `questions.bulk({ids, action, snooze_days})`, then refetch. "Select all matching filter" selects the visible filtered ids (not a server-side filter call — keeps semantics obvious).

- [ ] **Step 3:** Gates + live verify on CORZ's 112-question pile: filter to P3 → select all → Snooze 30d → list shrinks, Today rollup count drops next poll. Commit:

```bash
git commit -am "feat(questions): priority/category filters, bulk dismiss/snooze"
```

### Task 19: 8-K near-duplicate grouping (API-layer)

**Files:**
- Modify: `backend/app/api/events.py` (list endpoint, ~line 43; dismiss endpoint, ~line 107)
- Modify: `backend/app/services/status_board.py` (`_summarize_material_events`, ~line 127)
- Test: extend the events/status-board test modules (`grep -rln "material_event" backend/tests/`)

- [ ] **Step 1: Failing tests**

```python
    def test_groups_same_ticker_type_within_4_days(self):
        # two APLD "financing" events 2 days apart → one group, count=2,
        # primary = newest, member_ids contains both
        ...

    def test_does_not_group_across_type_or_window(self):
        # APLD financing + APLD guidance → two groups;
        # two financing events 6 days apart → two groups
        ...

    async def test_dismiss_group_dismisses_members(self):
        # POST /events/{primary_id}/dismiss?group=true sets dismissed_at on both members
        ...
```

- [ ] **Step 2: Pure grouping helper** (new function in `backend/app/services/material_events_grouping.py` so both consumers share it):

```python
"""Group near-duplicate material events: same (ticker, event_type) within a
4-day window collapse into one group (spec §6). Pure — both /api/events and
the status-board summary consume it."""
from datetime import timedelta

GROUP_WINDOW_DAYS = 4


def group_events(events: list) -> list[dict]:
    """events: MaterialEvent rows sorted any order. Returns groups sorted by
    newest filing_date desc; each: {primary, count, member_ids, headlines}."""
    by_key: dict[tuple, list] = {}
    for ev in sorted(events, key=lambda e: e.filing_date, reverse=True):
        placed = False
        for (ticker, etype, anchor_date), members in by_key.items():
            if (
                ticker == ev.ticker and etype == ev.event_type
                and abs((anchor_date - ev.filing_date).days) <= GROUP_WINDOW_DAYS
            ):
                members.append(ev)
                placed = True
                break
        if not placed:
            by_key[(ev.ticker, ev.event_type, ev.filing_date)] = [ev]
    groups = []
    for members in by_key.values():
        primary = members[0]  # newest — input was sorted desc
        groups.append({
            "primary": primary,
            "count": len(members),
            "member_ids": [str(m.id) for m in members],
            "headlines": [m.headline for m in members],
        })
    groups.sort(key=lambda g: g["primary"].filing_date, reverse=True)
    return groups
```

- [ ] **Step 3: Wire both consumers**

`api/events.py` list endpoint: after fetching rows, run `group_events`, and extend the response item model with `group_count: int`, `group_member_ids: list[str]`, `group_headlines: list[str]` (primary's own fields stay top-level, so existing consumers keep rendering). Dismiss endpoint gains `?group=true` (default true): look up the primary's group members via the same `(ticker, event_type, window)` rule and set `dismissed_at` on all.

`status_board.py::_summarize_material_events`: feed each ticker's events through `group_events` so the 14-day summary counts groups, not raw filings.

- [ ] **Step 4: Frontend** — `MaterialEventsDrawer` + Today amber rows + `lib/api.ts` types: render `×{group_count}` badge when >1, expandable to `group_headlines`; dismiss button hits the group default. (`grep -rn "MaterialEvent" frontend/components/` for the consumers.)

- [ ] **Step 5: Tests + gates green; live verify the two APLD cards now render as one with ×2; commit**

```bash
git commit -am "feat(events): group near-duplicate 8-Ks by ticker+type within 4 days"
```

### Task 20: Run abandon — backend

**Files:**
- Modify: `backend/app/api/pipeline.py` (new route next to archive/unarchive — find with `grep -n "archive" backend/app/api/pipeline.py`)
- Test: extend the pipeline API test module

- [ ] **Step 1: Failing tests** — abandon on an `in_progress` run sets `status="abandoned"`; abandon on a `completed` run → 409; abandoned runs excluded from the status board's latest-run selection (check `status_board.py`'s SQL — it keys on latest **completed** runs already, so likely no change; pin it with an assert).

- [ ] **Step 2: Implement**

```python
@router.post("/runs/{run_id}/abandon")
async def abandon_run(run_id: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Mark a stuck run abandoned (spec §8). Only in_progress/paused runs qualify;
    no row deletion — Library renders abandoned runs greyed."""
    run = await db.get(ResearchRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status not in ("in_progress", "paused"):
        raise HTTPException(status_code=409, detail=f"cannot abandon a {run.status} run")
    run.status = "abandoned"
    await db.commit()
    return {"run_id": run_id, "status": "abandoned"}
```

`research_runs.status` is a plain String column (verify — no DB enum ⇒ no migration). Check `services/pipeline.py::_run_phase` never resurrects an abandoned run (it operates on runs it started; a stuck task for a zombie is long dead — note this in the PR description, don't build a guard for it).

- [ ] **Step 3: One-time backfill of the April zombies** — run against the real DB once, after live verification on the test DB:

```sql
UPDATE research_runs SET status='abandoned'
WHERE status IN ('in_progress','paused') AND started_at < NOW() - INTERVAL '7 days';
```

(check the actual timestamp column name first: `grep -n "Mapped" backend/app/models/research_run.py | grep -i "at"`). Record the rowcount in the PR.

- [ ] **Step 4: Tests + suite green, commit**

```bash
git commit -am "feat(runs): POST /runs/{id}/abandon for stuck pipeline runs"
```

### Task 21: Library rebuild (frontend)

**Files:**
- Rewrite: `frontend/app/library/page.tsx` (471 lines — read it fully first; reuse its data fetch + card internals where they fit)
- Modify: `frontend/lib/api.ts` (`abandonRun(runId)`; `Run` status union gains `"abandoned"`)
- Modify: `frontend/components/company/ThesesTab.tsx` (filter abandoned out of default view — find the run-history list)

- [ ] **Step 1: Grouped archive structure**

Group the fetched runs by ticker client-side:

- One **ticker row** per group: ticker (mono, links `/company/[ticker]`), latest run's verdict + status chip + date, run count badge. Default sort: most-recent activity desc.
- Expanding (plain `useState`, chevron like CurationPanel's) shows that ticker's runs newest-first: each row = date · status chip · verdict · link to `/pipeline/{run_id}`.
- Filters above the list: status (`completed | watchlist | abandoned | all-active`), theme, "has thesis" — client-side over the fetched list.
- Status chip vocabulary: render ONLY current statuses (`completed`, `watchlist`, `in_progress`, `paused`, `pass`, `abandoned`); delete the gate-era chip branches ("Awaiting approval", "Gate-Gaps") from the old page code.
- Abandoned runs render greyed (`opacity-60`); `in_progress`/`paused` runs older than ~7 days show an **Abandon** button → `abandonRun(run_id)` + local refetch, with `confirm()` guard.

- [ ] **Step 2: ThesesTab** — exclude `status === "abandoned"` from the default run-history list; show them under a "show abandoned" toggle if the list component already has a filter affordance, otherwise just exclude.

- [ ] **Step 3: Gates + live verify** — ORCL's 7 runs render as one expandable group; April zombies greyed/abandonable; every old card's information is still reachable. Commit:

```bash
git commit -am "feat(library): grouped-by-ticker archive, abandon action, retire gate-era chips"
```

### Task 22: Filings page polish

**Files:**
- Modify: `frontend/components/filings/ThemeFilingsPanel.tsx` and/or `TickerFilingsCard.tsx` (wording — find the literals with `grep -rn "Extract competition\|Re-extract" frontend/components/filings/`)
- Modify: `frontend/app/filings/page.tsx` (chore count header)
- Modify: `frontend/components/filings/MultiHopGraphView.tsx` or the graph page (default depth — `grep -rn "depth" frontend/app/filings/graph/ frontend/components/filings/`)

- [ ] **Step 1:** Unify the extract-button label: always "Extract competition", with a small `(re-run)` state hint when already extracted. Add a one-line caption near the per-theme header: `Fan out = ingest + extract + resolve for every ticker below.`
- [ ] **Step 2:** Chore count in the page header: count tickers whose cards show "no sections yet" (the data driving that state is already in the page's fetch — surface `N tickers ready to ingest` as a muted chip).
- [ ] **Step 3:** `/filings/graph` defaults to `depth=2` (and the UI toggle reflects it).
- [ ] **Step 4:** Gates + live verify + commit:

```bash
git commit -am "feat(filings): wording unification, ingest-chore count, 2-hop graph default"
```

### Task 23: Phase 3 wrap — PR

- [ ] Full suite + gates green; live walk: questions bulk flow, library groups, grouped events on Today/status drawer.
- [ ] Push `feat/ux-phase3-lists`, PR "UX overhaul phase 3: questions bulk/snooze, library rebuild, 8-K grouping", merge after CI.

---

# Phase 4 — Small fixes + theme sweep (`feat/ux-phase4-theme`)

### Task 24: Small-fixes bundle (spec §12)

**Files (one commit per fix is fine; all are independent):**

- [ ] **23.1 EventCard double title** — `frontend/components/catalysts/EventCard.tsx` lines ~53-56: for `kind === "catalyst"` the title row prints `event.title` and the subtitle row prints it again. Change the subtitle line so catalyst rows render `eventSubtitle(event)` (or nothing if that's empty for catalysts — read `eventSubtitle` and pick the non-duplicating branch).
- [ ] **23.2 Question rollup deep links** — wherever Today's attention list links question rollups (`frontend/components/today/AttentionList.tsx`), link `/questions?ticker=${t}` instead of `/questions`.
- [ ] **23.3 Refresh signals button** — theme detail page (`frontend/app/theme/[id]/page.tsx` or its signals banner component — `grep -rn "stale" frontend/components/ frontend/app/theme/`): replace the dead-end staleness banner with the same banner + a `Refresh signals` button → `POST /api/themes/{id}/signals/refresh` (add `themes.refreshSignals(id)` to `lib/api.ts` if missing), spinner while in flight, refetch on completion.
- [ ] **23.4 Ticker-everywhere linking** — ticker strings link to `/company/[ticker]`: theme-detail company cards (detail pane header), status-board ticker cells, report header (also add an explicit `Company →` link beside "Refresh workspace →" in `frontend/components/deep-dive/ReportHeader.tsx`). Keep row-click behaviors working (stopPropagation on the link).
- [ ] **23.5 "X SignalT2" spacing** — find the concatenation (`grep -rn "X Signal" frontend/components/`) and put a space/gap between heading and tier badge.
- [ ] **23.6 `/pipeline/new` copy** — update the stale "Runs 4 due-diligence phases automatically, then waits for approval before sizing" copy to describe the current flow: 5 phases, fully automatic, no approval gate.
- [ ] **23.7 Reverse-DCF em-dash explanations** — `frontend/components/model/ReverseDcfPanel.tsx` + `ThesisVsPricedTable.tsx`: when implied IRR / priced-in cells are null, render `—` with a `title` AND a visible footnote line: `— = no solution at the current price (solver did not converge)`.
- [ ] **23.8 Forecast grid n/a vs missing** — `frontend/components/model/DriverPanel.tsx` / `CellRenderer.tsx`: drivers that are surfaced-but-no-op (`interest_income_yield`, `revolver_rate` — per CLAUDE.md) render `n/a` muted; genuinely missing values keep `—`.
- [ ] **23.9 Researched indicator on theme cards** — discovery company cards (`grep -rn "Run Quick Screen" frontend/components/`) show a small `Researched` chip linking to `/pipeline/{latest_completed_run_id}` when the board/runs data already available to the page knows one exists; if the page has no such data, add the lightest possible source (the existing runs list endpoint filtered by ticker, fetched once per theme page).
- [ ] **Gates + live screenshot pass over Today/theme/status/report/model; commit per fix or one bundle commit:**

```bash
git commit -am "fix(ux): small-fixes bundle — event cards, deep links, signals refresh, copy, em-dash explanations"
```

### Task 25: Theme — diagnose the light-render mechanism (NO sweeping yet)

**Files:** none modified — this is a diagnosis step; its output is a short section appended to this plan (replace the placeholder in Task 26 Step 1).

- [ ] **Step 1: Reproduce live** — run frontend+backend, open `/company/ORCL/peers` and `/workspace/[some-runId]` with Playwright; screenshot. **Note:** the current `frontend/app/globals.css` defines only DARK token values (verified 2026-06-10 during planning — single `:root`, `--color-*` aliases point at the same dark set, the only light override lives inside `@media print`), and `WorkspaceReport`/`PeerCompTable` use `var(--surface)` classes. If those pages now render dark, the audit-era light split may already be partially gone — re-verify each of the three audit-flagged surfaces (workspace report, model Forecast/History tabs, company Peers tab) before assuming work exists.
- [ ] **Step 2: If a surface renders light**, find the winning rule: Playwright `browser_evaluate` → `getComputedStyle(document.body).backgroundColor` and `getComputedStyle($0).backgroundColor` on the light element, then walk `document.styleSheets` for the selector that sets it. Candidates to check: a route-level `<style>`, a component-scoped CSS module, Tailwind `@theme` blocks, `color-scheme` + `light-dark()`, stale `.next` build CSS (do a clean `rm -rf .next && npm run dev` once before concluding anything).
- [ ] **Step 3: Write the findings into Task 26** — which surfaces are light, which rule produces it, and the removal path. Commit the plan-doc update.

### Task 26: Theme — token reconciliation + mechanical sweep

**Files:**
- Modify: `frontend/app/globals.css`
- Modify: every file using hardcoded palette classes — enumerate live:

```bash
grep -rln "slate-[0-9]\|bg-white\|bg-gray-\|text-gray-\|bg-zinc\|bg-neutral" frontend/app frontend/components --include="*.tsx" | grep -v node_modules
```

(planning-time check found at least: `app/status/page.tsx` (26 hits), `app/library/page.tsx`, `components/ThesisCard.tsx`, `components/status/EarningsDrawer.tsx`, `components/status/WorkspaceButton.tsx` (fixed in Task 3), `components/filings/ThemeFilingsPanel.tsx` — the live grep is the source of truth, and Phases 1-3 will have changed the set.)

- [x] **Task 25 DIAGNOSIS (2026-06-11):** all three audit-flagged surfaces render DARK live (workspace report body rgb(15,23,42)/cards rgb(30,41,59); model forecast tab dark with transparent table cells; company peers tab zero light-background elements among 400 sampled). The light-render mechanism is GONE — globals.css's single :root now carries the dark palette for both `--x` and `--color-*` namespaces (light only inside `@media print`). No removal needed; Step 1 reduces to the namespace-reconciliation check only.
- [ ] **Step 1: Apply Task 25's removal** (NO-OP per diagnosis above), and reconcile the two token namespaces: keep the base `--x` set as canonical; keep the `--color-*` aliases as one-line `var()` redirects (they already are — verify nothing defines `--color-*` independently anywhere else: `grep -rn -- "--color-" frontend --include="*.css"`).
- [ ] **Step 2: Sweep, one surface per commit.** Mapping (mechanical, no redesign):
  - `bg-slate-900` → `bg-[var(--bg)]` · `bg-slate-800`, `bg-slate-800/50` → `bg-[var(--surface)]` · `bg-slate-700/40`-style controls → `bg-[var(--surface-alt)]`
  - `border-slate-700`/`600` → `border-[var(--border)]` · `ring-slate-600` → `ring-[var(--border)]`
  - `text-slate-100`/`200` → `text-[var(--text)]` · `text-slate-300`/`400` → `text-[var(--text-muted)]` · `text-slate-500` → `text-[var(--text-faint)]`
  - ambers/emeralds/reds used as status colors → `--warning`/`--success`/`--error` tokens; score colors stay on `scoreColors.ts`.
  - Anything that doesn't fit the mapping: pick the visually-identical token, screenshot before/after.
- [ ] **Step 3: Per-surface verification** — before/after Playwright screenshots ≈ identical for previously-dark surfaces (eyeball; the values map 1:1 so diffs mean a mistake). For the previously-light surfaces (if any remained at Task 25): after-screenshot shows them dark, no theme flash navigating status → workspace report → back.
- [ ] **Step 4: Guard the future** — add a one-line note to `frontend/AGENTS.md`: "Colors: token classes only (`bg-[var(--surface)]` etc.) — no `slate-*`/`gray-*` palette classes." Final repo-wide grep returns zero hits outside `globals.css`/comments.
- [ ] **Step 5: Commit series + gates**

```bash
git commit -m "refactor(theme): <surface> → CSS variable tokens"   # per surface
```

### Task 27: Phase 4 wrap + campaign close-out

- [ ] All gates green; full suite; `npm run build` clean.
- [ ] **Re-walk the four B1 journeys** with Playwright and record step counts vs B1: morning check, new idea, earnings day (must beat the 6-step detour), filings chores (queue reaches zero on dismissible items). Acceptance bar = spec §14, all 9 items.
- [ ] Push `feat/ux-phase4-theme`, PR "UX overhaul phase 4: small fixes + dark token sweep", merge after CI.
- [ ] **Docs:** update `CLAUDE.md` — workspaces list (6 nav entries, Catalysts→Today tab, demotions), frontend-layout section (GlobalCommandPalette, Library/Questions changes), the workspace-loop section (preflight warnings, model-skip), filings section (dismiss tombstones), material-events section (grouping). Update the campaign ledger (check B3), `TODO.md` Done entry, auto-memory.

---

## Execution notes

- **Task order within a phase is dependency order** — don't reorder (Task 2 needs Task 1's Optional model; Task 10 needs Task 9's endpoint; Task 26 needs Task 25's diagnosis).
- **Premise re-verification:** every task names planning-time line numbers — they drift. Re-grep before editing; if a premise is wrong (e.g., a surface already renders dark in Task 25), record it in the PR and skip rather than force.
- **Per-task definition of done:** code + tests + gates green + live Playwright check of the touched surface + commit. No "should work".
