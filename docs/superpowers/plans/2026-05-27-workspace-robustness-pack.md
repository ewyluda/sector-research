# Workspace Robustness Pack Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the workspace surface against five silent failure modes — preflight gaps, the concurrent `kick_off` race, missing `step_outputs` schema validation, the `compute_delta` race that aborts entire workspace runs, and invisible model drafts that silently block workspace refreshes.

**Architecture:** Most fixes live behind two new seams: a typed preflight endpoint (`GET /api/workspace/{ticker}/preflight`) that the frontend hits before showing a kick-off button, and a per-ticker `asyncio.Lock` registry in `WorkspaceService` that closes the preflight-to-claim race. The remaining fixes are localized: a validate-then-persist pass in `_run_workspace`, an in-flight guard in `transcript_delta`, and a draft-state banner in `ModelWorkspace`.

**Tech Stack:** FastAPI + Pydantic v2, async SQLAlchemy on PostgreSQL, Next.js 16 App Router, React 19, Tailwind v4. Backend tests via stdlib `unittest` (no pytest). Frontend lint via `npm run lint`.

---

## Pre-flight (do once before starting)

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
git checkout -b feat/workspace-robustness-pack
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -5
cd frontend && npm run lint && cd ..
```

Both should be clean before starting Task 1.

---

## Task 1: Backend — typed preflight DTO + endpoint

Today `_preflight` lives on `WorkspaceService` and is called from inside `kick_off()`, where it raises `ValueError` on missing prerequisites. The frontend only learns about the failure via the HTTP 400. We need a separate read-only endpoint that returns a structured DTO ("ok / not-ok, here's why") so the UI can disable the button before the user clicks.

**Files:**
- Modify: `backend/app/services/workspace.py` (add `PreflightStatus` dataclass + `check_preflight()` method, refactor existing `_preflight` to call the same core)
- Modify: `backend/app/api/workspace.py` (add `GET /api/workspace/{ticker}/preflight` route)
- Modify: `frontend/lib/api.ts` (add `WorkspacePreflight` type + `workspaceApi.preflight()` method)
- Create: `backend/tests/test_workspace_preflight.py`

- [ ] **Step 1.1: Write the failing test**

Create `backend/tests/test_workspace_preflight.py`:

```python
"""Tests for WorkspaceService.check_preflight() — non-raising preflight DTO."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.workspace import WorkspaceService, PreflightStatus


class TestCheckPreflight(unittest.TestCase):
    def _make_service(self):
        return WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())

    def test_returns_ok_when_all_prereqs_met(self):
        # Stub the underlying DB-touching helper used by check_preflight().
        # We do this at the service level — replace _gather_preflight_facts to
        # return the shape check_preflight maps from.
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": True,
                "research_run_completed": True,
                "research_run_ticker_matches": True,
                "ticker_model_found": True,
                "draft_present": False,
                "in_flight_run_id": None,
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]

        async def run():
            return await svc.check_preflight(db=MagicMock(), ticker="NVDA")

        result = asyncio.run(run())
        self.assertIsInstance(result, PreflightStatus)
        self.assertTrue(result.ok)
        self.assertEqual(result.missing, [])
        self.assertIsNone(result.in_flight_run_id)

    def test_reports_missing_research_run(self):
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": False,
                "research_run_completed": False,
                "research_run_ticker_matches": False,
                "ticker_model_found": True,
                "draft_present": False,
                "in_flight_run_id": None,
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertFalse(result.ok)
        self.assertIn("no_completed_research_run", result.missing)

    def test_reports_unsaved_draft(self):
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": True,
                "research_run_completed": True,
                "research_run_ticker_matches": True,
                "ticker_model_found": True,
                "draft_present": True,
                "in_flight_run_id": None,
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertFalse(result.ok)
        self.assertIn("unsaved_model_draft", result.missing)

    def test_reports_in_flight_run(self):
        svc = self._make_service()

        async def fake_gather(db, ticker, research_run_id=None):
            return {
                "research_run_found": True,
                "research_run_completed": True,
                "research_run_ticker_matches": True,
                "ticker_model_found": True,
                "draft_present": False,
                "in_flight_run_id": "abc-123",
            }

        svc._gather_preflight_facts = fake_gather  # type: ignore[assignment]
        result = asyncio.run(svc.check_preflight(db=MagicMock(), ticker="NVDA"))
        self.assertFalse(result.ok)
        self.assertIn("workspace_run_in_flight", result.missing)
        self.assertEqual(result.in_flight_run_id, "abc-123")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 1.2: Run the test and verify it fails**

```bash
python -m unittest backend.tests.test_workspace_preflight -v
```

Expected: `ImportError: cannot import name 'PreflightStatus'` or `AttributeError: 'WorkspaceService' object has no attribute 'check_preflight'`.

- [ ] **Step 1.3: Add the dataclass and the two methods**

Edit `backend/app/services/workspace.py`. Add near the top of the file, after the `WorkspaceRunInFlight` class:

```python
from dataclasses import dataclass, field


@dataclass
class PreflightStatus:
    """Read-only DTO describing whether a workspace run can be kicked off.

    `missing` is a list of stable string codes the frontend can map to copy:
      - "no_completed_research_run"
      - "research_run_not_completed"
      - "research_run_ticker_mismatch"
      - "no_ticker_model"
      - "unsaved_model_draft"
      - "workspace_run_in_flight"
    `in_flight_run_id` is populated when "workspace_run_in_flight" is in missing
    so the frontend can deep-link to the running report instead of starting a new one.
    """
    ok: bool
    missing: list[str] = field(default_factory=list)
    in_flight_run_id: str | None = None
```

Replace the existing `_preflight` method with two methods — a low-level facts gatherer and a non-raising `check_preflight` plus a raising shim that keeps the existing `kick_off` semantics intact:

```python
    async def _gather_preflight_facts(
        self,
        db: AsyncSession,
        ticker: str,
        *,
        research_run_id: str | None = None,
    ) -> dict:
        """Single DB pass collecting every fact the preflight needs.

        Returns a dict of booleans + the optional in-flight run id. Callers
        decide whether to raise (kick_off path) or return a DTO (HTTP preflight).
        """
        from backend.app.models import ResearchRun, TickerModel, TickerModelDraft

        if research_run_id is not None:
            rr = (await db.execute(
                select(ResearchRun).where(ResearchRun.id == research_run_id)
            )).scalar_one_or_none()
            rr_found = rr is not None
            rr_completed = bool(rr and rr.status == "completed")
            rr_ticker_matches = bool(rr and rr.ticker == ticker)
        else:
            rr = (await db.execute(
                select(ResearchRun)
                .where(ResearchRun.ticker == ticker, ResearchRun.status == "completed")
                .order_by(ResearchRun.updated_at.desc())
                .limit(1)
            )).scalar_one_or_none()
            rr_found = rr is not None
            rr_completed = rr_found  # filtered in the query
            rr_ticker_matches = rr_found

        tm = (await db.execute(
            select(TickerModel)
            .where(TickerModel.ticker == ticker)
            .order_by(TickerModel.version.desc())
            .limit(1)
        )).scalar_one_or_none()

        draft = (await db.execute(
            select(TickerModelDraft).where(TickerModelDraft.ticker == ticker).limit(1)
        )).scalar_one_or_none()

        in_flight = (await db.execute(
            select(WorkspaceRun)
            .where(WorkspaceRun.ticker == ticker, WorkspaceRun.status == "running")
            .order_by(WorkspaceRun.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()

        return {
            "research_run": rr,
            "ticker_model": tm,
            "research_run_found": rr_found,
            "research_run_completed": rr_completed,
            "research_run_ticker_matches": rr_ticker_matches,
            "ticker_model_found": tm is not None,
            "draft_present": draft is not None,
            "in_flight_run_id": str(in_flight.id) if in_flight is not None else None,
        }

    async def check_preflight(
        self,
        *,
        db: AsyncSession,
        ticker: str,
        research_run_id: str | None = None,
    ) -> PreflightStatus:
        """Non-raising preflight check for UI use."""
        facts = await self._gather_preflight_facts(db, ticker, research_run_id=research_run_id)
        missing: list[str] = []
        if not facts["research_run_found"]:
            missing.append("no_completed_research_run")
        elif not facts["research_run_completed"]:
            missing.append("research_run_not_completed")
        elif not facts["research_run_ticker_matches"]:
            missing.append("research_run_ticker_mismatch")
        if not facts["ticker_model_found"]:
            missing.append("no_ticker_model")
        if facts["draft_present"]:
            missing.append("unsaved_model_draft")
        if facts["in_flight_run_id"] is not None:
            missing.append("workspace_run_in_flight")
        return PreflightStatus(
            ok=len(missing) == 0,
            missing=missing,
            in_flight_run_id=facts["in_flight_run_id"],
        )
```

Then rewrite the existing `_preflight` to delegate to `_gather_preflight_facts` and raise on missing items (preserves the existing `kick_off` and `_build_context` callers exactly):

```python
    async def _preflight(
        self,
        db: AsyncSession,
        ticker: str,
        *,
        research_run_id: str | None = None,
    ) -> dict:
        """Raising preflight used by kick_off / _build_context. Returns {research_run, ticker_model}."""
        facts = await self._gather_preflight_facts(db, ticker, research_run_id=research_run_id)
        if not facts["research_run_found"]:
            if research_run_id is not None:
                raise ValueError(f"research_run {research_run_id} not found")
            raise ValueError(f"no completed research_run for ticker {ticker}")
        if not facts["research_run_ticker_matches"]:
            raise ValueError(
                f"research_run {research_run_id} ticker {facts['research_run'].ticker} != requested ticker {ticker}"
            )
        if not facts["research_run_completed"]:
            raise ValueError(
                f"research_run {research_run_id} status is {facts['research_run'].status}; must be completed"
            )
        if not facts["ticker_model_found"]:
            raise ValueError(f"no ticker_model exists for ticker {ticker}; initialize one first")
        if facts["draft_present"]:
            raise ValueError(
                f"unsaved model draft exists for ticker {ticker}; save or discard it before workspace refresh"
            )
        return {"research_run": facts["research_run"], "ticker_model": facts["ticker_model"]}
```

- [ ] **Step 1.4: Run the test and verify it passes**

```bash
python -m unittest backend.tests.test_workspace_preflight -v
```

Expected: 4 tests pass.

- [ ] **Step 1.5: Run the full backend suite to confirm no regression**

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -3
```

Expected: same pass count as before + 4 new tests, zero failures.

- [ ] **Step 1.6: Add the HTTP endpoint**

Edit `backend/app/api/workspace.py`. Add after `get_run` (around line 56):

```python
@router.get("/{ticker}/preflight")
async def preflight(
    ticker: Ticker = Depends(TickerPath),
    research_run_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    svc: WorkspaceService = Depends(get_workspace_service),
):
    status = await svc.check_preflight(db=db, ticker=ticker, research_run_id=research_run_id)
    return {
        "ok": status.ok,
        "missing": status.missing,
        "in_flight_run_id": status.in_flight_run_id,
    }
```

- [ ] **Step 1.7: Smoke-test the endpoint with the dev server**

In one terminal:
```bash
uvicorn backend.app.main:app --reload --port 8001
```

In another:
```bash
curl -s 'http://127.0.0.1:8001/api/workspace/AAPL/preflight' | python -m json.tool
```

Expected: a JSON object with `ok`, `missing`, `in_flight_run_id`. The exact contents depend on local DB state — verify the shape is right. Stop the server.

- [ ] **Step 1.8: Wire the typed client method**

Edit `frontend/lib/api.ts`. Find the `workspaceApi` object (around line 1580). Add a new method directly above `kickOff`:

```typescript
export interface WorkspacePreflight {
  ok: boolean;
  missing: (
    | "no_completed_research_run"
    | "research_run_not_completed"
    | "research_run_ticker_mismatch"
    | "no_ticker_model"
    | "unsaved_model_draft"
    | "workspace_run_in_flight"
  )[];
  in_flight_run_id: string | null;
}
```

(Place this above the `workspaceApi` object literal — keep it as a top-level export.)

Then inside the `workspaceApi` object, before `kickOff`:

```typescript
  preflight: async (
    ticker: string,
    researchRunId?: string,
  ): Promise<WorkspacePreflight> => {
    const qs = researchRunId
      ? `?research_run_id=${encodeURIComponent(researchRunId)}`
      : "";
    const r = await fetch(
      `${BASE}/api/workspace/${encodeURIComponent(ticker)}/preflight${qs}`,
    );
    if (!r.ok) throw new Error(`preflight ${r.status}`);
    return r.json();
  },
```

- [ ] **Step 1.9: Verify lint passes**

```bash
cd frontend && npm run lint && cd ..
```

Expected: zero errors.

- [ ] **Step 1.10: Commit**

```bash
git add backend/app/services/workspace.py backend/app/api/workspace.py backend/tests/test_workspace_preflight.py frontend/lib/api.ts
git commit -m "$(cat <<'EOF'
feat(workspace): typed preflight DTO + GET /preflight endpoint

Adds PreflightStatus dataclass and check_preflight() — a non-raising
sibling to the existing _preflight() — plus a HTTP endpoint and a
typed frontend client. Frontend can now disable kick-off buttons
with structured reasons (no_ticker_model, unsaved_model_draft, etc.)
instead of relying on 400/409 surprise responses.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Backend — close the preflight-to-claim race

Today `kick_off()` runs `_preflight` then `INSERT WorkspaceRun(status="running")` in the same `unit_of_work()` block, but two concurrent calls can both pass the `WorkspaceRun.status=="running"` SELECT before either INSERT completes. The IntegrityError path partially handles this (it re-queries for the in-flight row), but the **draft-present** check has no DB-level guard at all — two tabs can both pass `draft is None`, both proceed, and the second model write hits the `(ticker, version)` unique constraint with a less recoverable error.

Solution: per-ticker `asyncio.Lock` held through preflight + INSERT. Single-process serialization is sufficient because the FastAPI app is one process (no horizontal scaling for this local-only tool).

**Files:**
- Modify: `backend/app/services/workspace.py` (add `_ticker_locks` registry + acquire in `kick_off`)
- Modify: `backend/tests/test_workspace_preflight.py` (add race test)

- [ ] **Step 2.1: Write the failing test**

Append to `backend/tests/test_workspace_preflight.py`:

```python
class TestKickOffRaceGuard(unittest.TestCase):
    def test_concurrent_kick_offs_serialize_on_ticker_lock(self):
        """Two parallel kick_off() calls for the same ticker must not both pass preflight.

        We stub _preflight to record entry order and sleep, then assert the
        lock forces serial execution.
        """
        from backend.app.services.workspace import WorkspaceService
        svc = WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())
        entries: list[str] = []

        # Replace the run-lifecycle internals so we only test the lock.
        async def fake_kick(ticker: str, tag: str):
            async with svc._acquire_ticker_lock(ticker):
                entries.append(f"enter:{tag}")
                await asyncio.sleep(0.05)
                entries.append(f"exit:{tag}")

        async def run():
            await asyncio.gather(fake_kick("NVDA", "a"), fake_kick("NVDA", "b"))

        asyncio.run(run())
        # Either a fully before b or b fully before a — never interleaved.
        ordering = ",".join(entries)
        self.assertIn(ordering, {"enter:a,exit:a,enter:b,exit:b", "enter:b,exit:b,enter:a,exit:a"})

    def test_different_tickers_do_not_block(self):
        from backend.app.services.workspace import WorkspaceService
        svc = WorkspaceService(fmp=MagicMock(), edgar=MagicMock(), anthropic=MagicMock())
        entries: list[str] = []

        async def fake_kick(ticker: str, tag: str):
            async with svc._acquire_ticker_lock(ticker):
                entries.append(f"enter:{tag}")
                await asyncio.sleep(0.05)
                entries.append(f"exit:{tag}")

        async def run():
            await asyncio.gather(fake_kick("NVDA", "a"), fake_kick("AAPL", "b"))

        asyncio.run(run())
        # Both enters happen before either exit.
        idx_enter_a = entries.index("enter:a")
        idx_enter_b = entries.index("enter:b")
        idx_exit_a = entries.index("exit:a")
        idx_exit_b = entries.index("exit:b")
        self.assertLess(max(idx_enter_a, idx_enter_b), min(idx_exit_a, idx_exit_b))
```

- [ ] **Step 2.2: Run the test and verify it fails**

```bash
python -m unittest backend.tests.test_workspace_preflight.TestKickOffRaceGuard -v
```

Expected: `AttributeError: 'WorkspaceService' object has no attribute '_acquire_ticker_lock'`.

- [ ] **Step 2.3: Add the per-ticker lock registry**

Edit `backend/app/services/workspace.py`. In `WorkspaceService.__init__`, add a new dict after `self._queues`:

```python
        self._queues: dict[str, asyncio.Queue] = {}
        self._ticker_locks: dict[str, asyncio.Lock] = {}
        self._ticker_locks_guard = asyncio.Lock()
```

Then add a context-manager helper right below the SSE plumbing section:

```python
    # ── Per-ticker concurrency guard ───────────────────────────────────────────

    def _acquire_ticker_lock(self, ticker: str):
        """Async context manager that serializes kick_off per ticker.

        Two concurrent kick_off() calls for the same ticker would otherwise both
        pass the draft-absence check before either INSERT lands, allowing the
        second run to race the first model-version write and surface a
        (ticker, version) IntegrityError. The lock pins them to single-file
        execution within this process; horizontal scaling is not a concern
        (single-process local tool).
        """
        svc = self
        ticker = ticker.upper()

        class _LockCtx:
            async def __aenter__(self_inner):
                async with svc._ticker_locks_guard:
                    lock = svc._ticker_locks.get(ticker)
                    if lock is None:
                        lock = asyncio.Lock()
                        svc._ticker_locks[ticker] = lock
                self_inner._lock = lock
                await lock.acquire()
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):
                self_inner._lock.release()

        return _LockCtx()
```

- [ ] **Step 2.4: Run the tests and verify they pass**

```bash
python -m unittest backend.tests.test_workspace_preflight.TestKickOffRaceGuard -v
```

Expected: 2 tests pass.

- [ ] **Step 2.5: Wrap kick_off with the lock**

In `WorkspaceService.kick_off`, wrap the entire body in the lock. Replace the existing method's body (keep the signature). The full new method:

```python
    async def kick_off(self, ticker: str, *, research_run_id: str | None = None) -> str:
        """Create the workspace_runs row and start the background task. Returns run_id.

        Holds a per-ticker asyncio.Lock across preflight + INSERT to prevent
        two parallel callers from both passing the draft-absent check.
        """
        async with self._acquire_ticker_lock(ticker):
            try:
                async with unit_of_work() as db:
                    in_flight = (await db.execute(
                        select(WorkspaceRun)
                        .where(WorkspaceRun.ticker == ticker, WorkspaceRun.status == "running")
                        .order_by(WorkspaceRun.created_at.desc())
                        .limit(1)
                    )).scalar_one_or_none()
                    if in_flight is not None:
                        raise WorkspaceRunInFlight(run_id=str(in_flight.id))

                    ctx_data = await self._preflight(db, ticker, research_run_id=research_run_id)
                    run_id = str(uuid4())
                    row = WorkspaceRun(
                        id=run_id,
                        ticker=ticker,
                        parent_research_run_id=str(ctx_data["research_run"].id),
                        ticker_model_version_before=ctx_data["ticker_model"].version,
                        status="running",
                        step_outputs={},
                        citations=[],
                    )
                    db.add(row)
            except IntegrityError:
                in_flight_id = await self._find_in_flight_run_id(ticker)
                if in_flight_id is not None:
                    raise WorkspaceRunInFlight(run_id=in_flight_id)
                raise

        asyncio.create_task(
            self._run_workspace(
                run_id=run_id,
                ticker=ticker,
                db_factory=unit_of_work,
                research_run_id=str(ctx_data["research_run"].id),
            )
        )
        return run_id
```

(The `asyncio.create_task` call must remain **outside** the lock — releasing as soon as the row is committed is correct, since the long-running `_run_workspace` no longer needs the guard.)

- [ ] **Step 2.6: Re-run full backend suite to confirm no regression**

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 2.7: Commit**

```bash
git add backend/app/services/workspace.py backend/tests/test_workspace_preflight.py
git commit -m "$(cat <<'EOF'
fix(workspace): per-ticker asyncio.Lock closes kick_off race

Two concurrent POST /workspace/{ticker}/runs could both pass the
draft-absent preflight check before either WorkspaceRun INSERT
committed, racing the (ticker, version) unique constraint on the
first model-version write. The new _acquire_ticker_lock() serializes
kick_off per ticker. Different tickers run in parallel (verified).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Backend — validate `step_outputs` against Pydantic schemas before persist

The `workspace_runs.step_outputs` column is free-form JSONB. Step functions return Pydantic models, but `run_steps_in_sequence` calls `.model_dump()` on them — if a step *partially* crashes and returns a raw dict with an `error` key (the existing `partial` status convention), the dict bypasses schema validation entirely. A future schema mismatch (e.g. a missing required field after a refactor) would persist silently and crash the frontend.

Solution: after `run_steps_in_sequence` returns, validate each step's output dict against its declared Pydantic schema. On failure, replace the entry with `{"error": "schema_validation_failed: <detail>"}` and force final status to `partial`.

**Files:**
- Modify: `backend/app/services/workspace.py` (add `_validate_step_outputs` helper, call from `_run_workspace`)
- Create: `backend/tests/test_workspace_step_outputs_validation.py`

- [ ] **Step 3.1: Write the failing test**

Create `backend/tests/test_workspace_step_outputs_validation.py`:

```python
"""Tests for step_outputs schema validation pass in _run_workspace."""
import unittest

from backend.app.services.workspace import _validate_step_outputs


class TestValidateStepOutputs(unittest.TestCase):
    def test_valid_outputs_pass_through_unchanged(self):
        outputs = {
            "update_refresh": {
                "version_before": 1,
                "version_after": 2,
                "changed_cells": [],
                "removed_cells": [],
                "new_filings": [],
                "consensus_delta": None,
                "summary": "loaded latest 10-Q",
            },
        }
        validated, had_error = _validate_step_outputs(outputs)
        self.assertFalse(had_error)
        self.assertEqual(validated["update_refresh"]["summary"], "loaded latest 10-Q")

    def test_existing_error_entry_is_preserved(self):
        """Entries with an `error` key are the existing partial-step contract and pass through."""
        outputs = {"research": {"error": "Haiku timeout"}}
        validated, had_error = _validate_step_outputs(outputs)
        self.assertTrue(had_error)
        self.assertEqual(validated["research"], {"error": "Haiku timeout"})

    def test_schema_mismatch_is_replaced_with_error_entry(self):
        """A dict that fails Pydantic validation becomes {error: ...} and flips had_error."""
        outputs = {
            "update_refresh": {
                # missing required `version_before` and `summary`
                "version_after": 2,
                "changed_cells": "this should be a list",  # wrong type
            },
        }
        validated, had_error = _validate_step_outputs(outputs)
        self.assertTrue(had_error)
        self.assertIn("error", validated["update_refresh"])
        self.assertIn("schema_validation_failed", validated["update_refresh"]["error"])

    def test_unknown_step_name_is_passed_through_untouched(self):
        """Defensive: if a new step name appears that has no registered schema, don't break."""
        outputs = {"future_step": {"hello": "world"}}
        validated, had_error = _validate_step_outputs(outputs)
        self.assertFalse(had_error)
        self.assertEqual(validated["future_step"], {"hello": "world"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3.2: Run the test and verify it fails**

```bash
python -m unittest backend.tests.test_workspace_step_outputs_validation -v
```

Expected: `ImportError: cannot import name '_validate_step_outputs'`.

- [ ] **Step 3.3: Add the validator**

Edit `backend/app/services/workspace.py`. Add at module level, after the imports:

```python
from backend.app.models.workspace_schemas import (
    UpdateRefreshOutput,
    ResearchOutput,
    ValidationOutput,
    ChallengeOutput,
    DifferentiationOutput,
)


_STEP_SCHEMAS = {
    "update_refresh": UpdateRefreshOutput,
    "research": ResearchOutput,
    "validation": ValidationOutput,
    "challenge": ChallengeOutput,
    "differentiation": DifferentiationOutput,
}


def _validate_step_outputs(outputs: dict) -> tuple[dict, bool]:
    """Validate each step's JSONB payload against its Pydantic schema.

    Returns (validated_outputs, had_error). Entries already shaped as
    {"error": "..."} pass through (existing per-step partial contract) and
    flip had_error to True. Entries that fail schema validation are replaced
    with {"error": "schema_validation_failed: <detail>"} so the persisted row
    is always either a valid schema dump or an explicit error sentinel —
    never silent corrupted data the frontend will crash on.

    Unknown step names pass through untouched: this function must not gate
    schema evolution to a hard whitelist that breaks when a new step is added.
    """
    from pydantic import ValidationError

    validated: dict = {}
    had_error = False
    for step_name, payload in outputs.items():
        if isinstance(payload, dict) and "error" in payload:
            validated[step_name] = payload
            had_error = True
            continue
        schema = _STEP_SCHEMAS.get(step_name)
        if schema is None:
            validated[step_name] = payload
            continue
        try:
            validated[step_name] = schema.model_validate(payload).model_dump()
        except ValidationError as e:
            validated[step_name] = {
                "error": f"schema_validation_failed: {e.errors()[0]['msg'] if e.errors() else str(e)}",
            }
            had_error = True
            logger.warning(
                "step_outputs validation failed for step=%s payload_keys=%s",
                step_name, list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__,
            )
    return validated, had_error
```

- [ ] **Step 3.4: Run the test and verify it passes**

```bash
python -m unittest backend.tests.test_workspace_step_outputs_validation -v
```

Expected: 4 tests pass.

- [ ] **Step 3.5: Wire the validator into `_run_workspace`**

In `backend/app/services/workspace.py::_run_workspace`, find the block (around line 256):

```python
            version_after = outputs.get("update_refresh", {}).get("version_after")
            verdict_str = outputs.get("challenge", {}).get("proposed_verdict")
            had_step_error = any(
                isinstance(v, dict) and "error" in v for v in outputs.values()
            )
            final_status = "partial" if had_step_error else "completed"
```

Replace with:

```python
            outputs, had_step_error = _validate_step_outputs(outputs)
            version_after = outputs.get("update_refresh", {}).get("version_after")
            verdict_str = outputs.get("challenge", {}).get("proposed_verdict")
            final_status = "partial" if had_step_error else "completed"
```

(The old `had_step_error` boolean computation is now done inside the validator. Verdict reads stay the same because a valid `ChallengeOutput.model_dump()` keeps `proposed_verdict` at the top level.)

- [ ] **Step 3.6: Full backend suite**

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 3.7: Commit**

```bash
git add backend/app/services/workspace.py backend/tests/test_workspace_step_outputs_validation.py
git commit -m "$(cat <<'EOF'
fix(workspace): validate step_outputs against Pydantic schemas before persist

workspace_runs.step_outputs is free-form JSONB. A schema mismatch
(missing field, wrong type) would persist silently and crash the
frontend report page. _validate_step_outputs now runs each step's
payload through its declared Pydantic schema; failures are replaced
with {"error": "schema_validation_failed: ..."} and force partial
status. Existing {"error": ...} entries pass through; unknown step
names pass through (don't gate schema evolution).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Backend — `compute_delta` in-flight guard (don't abort entire workspace run)

CONTEXT.md documents the race: two concurrent `compute_delta` calls for the same `(ticker, fingerprint)` both pass the cache-check SELECT, both call Haiku, one wins the unique constraint and the other crashes with IntegrityError. The *new* angle from the audit: when the loser is the workspace Step 2 (`research`), the orchestrator marks the **entire** workspace run as `failed` — losing 30-40s of upstream work over a benign secondary read.

Two-part fix:
1. Add a module-level in-flight set + asyncio.Lock so concurrent calls for the same key wait for the first to finish and then re-read the cached row.
2. (Defense in depth) Catch the IntegrityError in the workspace step and degrade to `{transcript_delta: null}` instead of bubbling.

**Files:**
- Modify: `backend/app/services/transcript_delta.py`
- Modify: `backend/app/services/workspace_steps.py` (catch the IntegrityError around the `compute_delta` call inside `step_research`)
- Create: `backend/tests/test_transcript_delta_race.py`

- [ ] **Step 4.1: Write the failing test**

Create `backend/tests/test_transcript_delta_race.py`:

```python
"""Tests for compute_delta in-flight guard — concurrent calls must not race the unique constraint."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services import transcript_delta


class TestComputeDeltaInFlightGuard(unittest.TestCase):
    def test_concurrent_same_key_calls_serialize(self):
        """Two parallel compute_delta() calls for the same (ticker, fingerprint) must
        serialize: Haiku is called exactly once, the second caller returns the cached row."""
        # Fake transcripts so fingerprint is stable
        fake_transcripts = [
            {"year": 2026, "quarter": 1, "content": "q1"},
            {"year": 2025, "quarter": 4, "content": "q4"},
        ]

        haiku_call_count = 0

        async def fake_fetch(*args, **kwargs):
            return (fake_transcripts, None)

        async def fake_complete(**kwargs):
            nonlocal haiku_call_count
            haiku_call_count += 1
            await asyncio.sleep(0.05)  # window for the race
            return '{"axes":{"business_quality":null,"risk_assessment":null,"growth_earnings":null,"sentiment_narrative":null,"management_governance":null,"future_durability":null,"macro_regime":null,"financial_health":null,"valuation_stage":null}}'

        # Stub the DB: first SELECT returns None (no cache), second SELECT (after
        # first compute commits) returns a stub row. We model this by patching
        # the SELECT path to return None always but ensuring the in-flight guard
        # makes the second call await the first.
        from backend.app.models.transcript_delta import TranscriptDelta

        cache: dict = {}

        async def fake_execute(q):
            # Return a result-shaped mock that yields cache.get("row")
            result = MagicMock()
            row = cache.get("row")
            result.scalar_one_or_none = MagicMock(return_value=row)
            result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=list(cache.values()) if cache else [])))
            return result

        async def fake_flush():
            return None

        async def fake_delete(obj):
            return None

        db = MagicMock()
        db.execute = fake_execute
        db.flush = fake_flush
        db.delete = fake_delete

        def add_side_effect(row):
            cache["row"] = row

        db.add = MagicMock(side_effect=add_side_effect)

        with patch.object(transcript_delta, "fetch_recent_transcripts", fake_fetch), \
             patch.object(transcript_delta, "complete", fake_complete):

            async def run_both():
                return await asyncio.gather(
                    transcript_delta.compute_delta(ticker="NVDA", db=db, fmp=MagicMock()),
                    transcript_delta.compute_delta(ticker="NVDA", db=db, fmp=MagicMock()),
                )

            asyncio.run(run_both())

        self.assertEqual(haiku_call_count, 1, "Haiku should be called once; second caller awaits the in-flight result")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4.2: Run the test and verify it fails**

```bash
python -m unittest backend.tests.test_transcript_delta_race -v
```

Expected: `haiku_call_count == 2`, test fails — both callers race.

- [ ] **Step 4.3: Add the in-flight guard**

Edit `backend/app/services/transcript_delta.py`. Add near the top, after the module constants (around line 39):

```python
import asyncio  # noqa: E402

_IN_FLIGHT: dict[tuple[str, str], asyncio.Event] = {}
_IN_FLIGHT_GUARD = asyncio.Lock()
```

Then modify `compute_delta` to acquire the lock for the `(ticker, fingerprint)` key. Replace the body of `compute_delta` (everything after fingerprint is computed):

```python
async def compute_delta(
    *,
    ticker: str,
    db: AsyncSession,
    fmp: FMPClient,
    force: bool = False,
) -> TranscriptDelta:
    """Fetch the latest TRANSCRIPT_WINDOW transcripts, compute or return cached delta.

    Concurrent calls for the same (ticker, fingerprint) coordinate via an
    in-memory asyncio.Event: the second caller waits for the first to land
    its INSERT, then re-reads the cached row. Avoids both racing the
    (ticker, transcripts_fingerprint) unique constraint.
    """
    transcripts, _citation = await fetch_recent_transcripts(
        fmp, ticker, limit=TRANSCRIPT_WINDOW,
    )
    if len(transcripts) < MIN_TRANSCRIPTS_FOR_DELTA:
        raise InsufficientTranscriptsError(
            f"{ticker}: only {len(transcripts)} transcript(s) available — need at least {MIN_TRANSCRIPTS_FOR_DELTA}"
        )

    window = _window_from_transcripts(transcripts)
    fingerprint = compute_fingerprint(window)
    key = (ticker, fingerprint)

    # Try cache first — if a prior call already landed, we're done.
    existing = (await db.execute(
        select(TranscriptDelta).where(
            TranscriptDelta.ticker == ticker,
            TranscriptDelta.transcripts_fingerprint == fingerprint,
        )
    )).scalar_one_or_none()
    if existing is not None and not force:
        return existing

    # Coordinate concurrent computes for the same key.
    async with _IN_FLIGHT_GUARD:
        in_flight_event = _IN_FLIGHT.get(key)
        is_leader = in_flight_event is None
        if is_leader:
            in_flight_event = asyncio.Event()
            _IN_FLIGHT[key] = in_flight_event

    if not is_leader:
        # Follower: wait for the leader to finish, then re-read.
        await in_flight_event.wait()
        cached = (await db.execute(
            select(TranscriptDelta).where(
                TranscriptDelta.ticker == ticker,
                TranscriptDelta.transcripts_fingerprint == fingerprint,
            )
        )).scalar_one_or_none()
        if cached is not None:
            return cached
        # Leader failed; fall through and try again as a new leader.
        return await compute_delta(ticker=ticker, db=db, fmp=fmp, force=force)

    try:
        raw = await complete(
            model=HAIKU,
            system=_SYSTEM_PROMPT,
            user=_build_user_prompt(transcripts),
            assistant_prefill='{"axes":',
            max_tokens=2500,
        )
        parsed, _end = json.JSONDecoder().raw_decode(raw.lstrip())
        axes = AxesDelta.model_validate(parsed["axes"]).model_dump()

        if existing is not None:
            existing.axes = axes
            existing.computed_at = datetime.now(timezone.utc)
            await db.flush()
            return existing

        row = TranscriptDelta(
            id=str(uuid4()),
            ticker=ticker,
            transcripts_window=window,
            transcripts_fingerprint=fingerprint,
            axes=axes,
            computed_at=datetime.now(timezone.utc),
        )
        db.add(row)
        await db.flush()
        await _trim_history(ticker=ticker, db=db)
        return row
    finally:
        async with _IN_FLIGHT_GUARD:
            _IN_FLIGHT.pop(key, None)
        in_flight_event.set()
```

- [ ] **Step 4.4: Run the race test and verify it passes**

```bash
python -m unittest backend.tests.test_transcript_delta_race -v
```

Expected: pass; `haiku_call_count == 1`.

- [ ] **Step 4.5: Re-run full backend suite for regression**

```bash
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -3
```

Expected: all pass.

- [ ] **Step 4.6: Belt-and-suspenders — degrade gracefully in workspace_steps**

Even with the in-flight guard, a stray `IntegrityError` (e.g. another process, or a transient DB error) should not abort the workspace run. Edit `backend/app/services/workspace_steps.py`. Find the call site that invokes `compute_delta` inside `step_research` (search for `compute_delta` in the file). Wrap it like this:

```python
from sqlalchemy.exc import IntegrityError as _IntegrityError
# ... existing imports unchanged ...

# Inside step_research, wherever compute_delta is called:
try:
    delta = await compute_delta(ticker=ctx.ticker, db=ctx.db, fmp=ctx.fmp)
except _IntegrityError as e:
    logger.warning("transcript_delta race in step_research for %s: %s", ctx.ticker, e)
    delta = None
except InsufficientTranscriptsError:
    delta = None
```

(If `compute_delta` is wrapped in a helper inside `workspace_steps.py`, apply the same try/except there. The exact line is project-specific — grep before editing.)

Verify the change:
```bash
grep -n "compute_delta\|IntegrityError" backend/app/services/workspace_steps.py
```

Expected: see the try/except around the call.

- [ ] **Step 4.7: Commit**

```bash
git add backend/app/services/transcript_delta.py backend/app/services/workspace_steps.py backend/tests/test_transcript_delta_race.py
git commit -m "$(cat <<'EOF'
fix(transcript_delta): in-flight guard + workspace step degrades gracefully

Two concurrent compute_delta() calls for the same (ticker, fingerprint)
could both pass the cache SELECT, both call Haiku, and one would surface
IntegrityError — which then aborted the entire workspace run (Step 2
caller). Adds an asyncio.Event-keyed in-flight map: leader runs Haiku,
followers wait and re-read the cached row. Workspace step also catches
IntegrityError defensively so a stray race never aborts a 30-40s run.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Frontend — preflight-gated workspace kick-off buttons

Three call sites today trigger `workspaceApi.kickOff()` and only learn about preflight failures via the 400/409 alert:
- `frontend/app/status/page.tsx:547` (per-row "↻ Workspace" in the status board)
- `frontend/components/deep-dive/ReportHeader.tsx:98` (the badge on the pipeline report header)
- (Verify) `frontend/app/workspace/page.tsx` if it has a kick-off action — grep first.

We'll write one tiny hook (`useWorkspacePreflight`) that takes ticker + optional researchRunId and returns `{loading, status}`, then plumb it into all three sites. Disabled button + tooltip.

**Files:**
- Create: `frontend/lib/hooks/useWorkspacePreflight.ts`
- Modify: `frontend/app/status/page.tsx`
- Modify: `frontend/components/deep-dive/ReportHeader.tsx`
- Modify (if applicable): `frontend/app/workspace/page.tsx`

- [ ] **Step 5.1: Grep for all kick-off call sites**

```bash
grep -rn "workspaceApi.kickOff\|kickOff(" frontend/app frontend/components --include="*.tsx" --include="*.ts"
```

Note every site for Step 5.4.

- [ ] **Step 5.2: Create the hook**

Create `frontend/lib/hooks/useWorkspacePreflight.ts`:

```typescript
"use client";
import { useEffect, useState } from "react";
import { workspaceApi, type WorkspacePreflight } from "@/lib/api";

const MISSING_COPY: Record<WorkspacePreflight["missing"][number], string> = {
  no_completed_research_run: "Needs a completed research run for this ticker.",
  research_run_not_completed: "The pinned research run hasn't completed yet.",
  research_run_ticker_mismatch: "The pinned research run doesn't match this ticker.",
  no_ticker_model: "Initialize a model for this ticker first.",
  unsaved_model_draft: "Save or discard the model draft first.",
  workspace_run_in_flight: "A workspace run is already running.",
};

export interface UsePreflightResult {
  loading: boolean;
  status: WorkspacePreflight | null;
  reasons: string[]; // human-readable copy for each missing code
}

export function useWorkspacePreflight(
  ticker: string | null | undefined,
  researchRunId?: string | null,
): UsePreflightResult {
  const [status, setStatus] = useState<WorkspacePreflight | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) {
      setStatus(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    workspaceApi
      .preflight(ticker, researchRunId ?? undefined)
      .then((r) => {
        if (!cancelled) setStatus(r);
      })
      .catch(() => {
        // If preflight itself errors, fall back to optimistic (let kick_off
        // surface the real error). Don't block the button on transient netfails.
        if (!cancelled) setStatus({ ok: true, missing: [], in_flight_run_id: null });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [ticker, researchRunId]);

  const reasons = (status?.missing ?? []).map((m) => MISSING_COPY[m]);
  return { loading, status, reasons };
}
```

- [ ] **Step 5.3: Verify lint**

```bash
cd frontend && npm run lint && cd ..
```

Expected: zero errors. (The `MISSING_COPY` keyed-by-union-type guarantees TS catches any drift when we add new missing codes.)

- [ ] **Step 5.4: Wire into the status board row**

Edit `frontend/app/status/page.tsx`. The kick-off button is around line 547. The button likely lives inside a per-row component (`ThesisCard` or similar). Find the surrounding component and add at the top:

```tsx
import { useWorkspacePreflight } from "@/lib/hooks/useWorkspacePreflight";
```

Inside the row component (the one that renders the workspace button), add at the top of the function body:

```tsx
const { status: preflight, reasons } = useWorkspacePreflight(e.ticker, e.run_id);
const canKickOff = preflight?.ok ?? false;
const tooltip = reasons.length > 0 ? reasons.join(" • ") : "Run workspace refresh";
```

Then replace the button's `onClick` and add `disabled` + `title`:

```tsx
<button
  type="button"
  disabled={!canKickOff}
  title={tooltip}
  onClick={async () => {
    if (preflight?.in_flight_run_id) {
      router.push(`/workspace/${preflight.in_flight_run_id}`);
      return;
    }
    const { run_id } = await workspaceApi.kickOff(e.ticker, e.run_id);
    router.push(`/workspace/${run_id}`);
  }}
  className="…existing classes… disabled:opacity-40 disabled:cursor-not-allowed"
>
  ↻ Workspace
</button>
```

(Keep the existing class chain — append the `disabled:` modifiers.)

- [ ] **Step 5.5: Wire into ReportHeader**

Edit `frontend/components/deep-dive/ReportHeader.tsx`. Around line 98 (the existing kick-off call site), apply the same pattern: import the hook, call it with `(ticker, runId)`, gate the button with `disabled` + `title`, and route to the in-flight run if `in_flight_run_id` is set.

- [ ] **Step 5.6: Build the frontend to catch type errors**

```bash
cd frontend && npm run build 2>&1 | tail -20 && cd ..
```

Expected: build succeeds. Any TS errors here are the type system catching missing prop wiring — fix them.

- [ ] **Step 5.7: Manual verification in the dev server**

```bash
cd frontend && npm run dev &
DEV_PID=$!
sleep 5
# Open http://127.0.0.1:3000/status in browser
# - Verify: workspace button is disabled with tooltip for a ticker without a model
# - Verify: workspace button is enabled for a fully-prepared ticker
# - Verify: clicking on a ticker with an in-flight run navigates to that run
kill $DEV_PID 2>/dev/null
cd ..
```

- [ ] **Step 5.8: Commit**

```bash
git add frontend/lib/hooks/useWorkspacePreflight.ts frontend/app/status/page.tsx frontend/components/deep-dive/ReportHeader.tsx
git commit -m "$(cat <<'EOF'
feat(workspace): preflight-gated kick-off buttons

useWorkspacePreflight hook calls GET /api/workspace/{ticker}/preflight
and surfaces structured reasons (no_ticker_model, unsaved_model_draft,
etc.) as both a disabled button state and an inline tooltip. When a
run is already in flight, the button still works but routes to the
running report instead of attempting a duplicate kick-off.

Wired into the status board and the deep-dive ReportHeader badge.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Frontend — draft visibility banner on `/model/[ticker]`

Today `ModelWorkspace` has Save/Discard buttons but no visible indicator that a draft exists. The user only finds out their draft is blocking workspace runs from the (now-improved) workspace tooltip — but they may also navigate away from the model page believing their work is saved when in fact it's persisted as a draft, not a version. Add a sticky banner at the top of the page when `draft != null`.

**Files:**
- Modify: `frontend/components/model/ModelWorkspace.tsx`

- [ ] **Step 6.1: Read the current ModelWorkspace shell**

```bash
cat frontend/components/model/ModelWorkspace.tsx | head -90
```

Identify where the `draft` state is rendered (around line 96-99). We'll add a banner above the tabs section when `draft != null`.

- [ ] **Step 6.2: Add the banner**

Edit `frontend/components/model/ModelWorkspace.tsx`. Just above the `<Tabs ...>` or whatever element wraps the three-tab content (search for `tab === "forecast"` or the parent of the tab selector), insert:

```tsx
{draft && (
  <div
    data-print-hide="true"
    className="mb-3 mx-6 flex items-center justify-between gap-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900"
  >
    <div className="flex items-center gap-2">
      <span className="inline-block h-2 w-2 rounded-full bg-amber-500" aria-hidden />
      <span>
        <strong>Unsaved draft</strong> — workspace runs are blocked until you save or discard.
      </span>
    </div>
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={async () => {
          if (!confirm("Discard draft?")) return;
          await discardModelDraft(ticker);
          // Reload the model state
          const r = await getModel(ticker);
          setLatest(r.latest_version);
          setDraft(null);
        }}
        className="text-xs px-2 py-1 rounded border border-amber-400 hover:bg-amber-100"
      >
        Discard
      </button>
      <button
        type="button"
        onClick={async () => {
          const label = prompt("Version label (optional):") ?? null;
          const v = await saveModelVersion(ticker, label);
          setLatest(v);
          setDraft(null);
        }}
        className="text-xs px-2 py-1 rounded bg-amber-500 text-white hover:bg-amber-600"
      >
        Save version
      </button>
    </div>
  </div>
)}
```

You may need to add `getModel` and `saveModelVersion` to the existing import line at the top of the file (search for `import { putModelDraft, saveModelVersion, discardModelDraft` — they may already be there).

- [ ] **Step 6.3: Verify lint and build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -5 && cd ..
```

Expected: zero errors.

- [ ] **Step 6.4: Manual verify**

```bash
cd frontend && npm run dev &
DEV_PID=$!
sleep 5
# In browser:
#   1. Navigate to /model/<ticker-with-existing-model> (or initialize one)
#   2. Edit a cell — banner should appear at the top
#   3. Click Discard — banner should disappear
#   4. Edit again, click Save version — banner should disappear and version increments
kill $DEV_PID 2>/dev/null
cd ..
```

- [ ] **Step 6.5: Commit**

```bash
git add frontend/components/model/ModelWorkspace.tsx
git commit -m "$(cat <<'EOF'
feat(model): sticky banner surfaces unsaved-draft state

Drafts auto-persist to the server on every cell edit, but the user
had no top-level indication that one existed — they'd navigate away
believing work was saved, then later hit the workspace-button block
without context. The amber banner explicitly calls out the unsaved
state and offers Discard / Save Version inline so the resolution is
one click away.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Final verification

- [ ] **Step 7.1: Full backend suite**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -5
```

Expected: all pass, new test count = baseline + 9 (4 preflight + 2 race + 1 ticker-lock variant + 4 step_outputs - any overlap; aim for ≥ 9 new).

- [ ] **Step 7.2: Frontend lint + build**

```bash
cd frontend && npm run lint && npm run build 2>&1 | tail -5 && cd ..
```

Expected: zero errors, build succeeds.

- [ ] **Step 7.3: Update TODO.md "Done (recent)" with a one-paragraph summary**

Edit `/Users/ericwyluda/Development/projects/sector-research/TODO.md`. Add at the top of `## Done (recent)`:

```markdown
- **Workspace robustness pack (2026-05-27)**. Five-issue cluster from the in-conversation audit: (1) typed preflight DTO + GET /api/workspace/{ticker}/preflight endpoint, (2) per-ticker asyncio.Lock closes the kick_off-to-claim race that could let two parallel runs both pass the draft-absent check, (3) workspace_runs.step_outputs validated against Pydantic schemas before persist (schema mismatches become {"error": "schema_validation_failed: ..."} and force partial status), (4) compute_delta in-flight guard via asyncio.Event so concurrent (ticker, fingerprint) calls coalesce on a single Haiku call, plus a defensive IntegrityError catch in workspace_steps.step_research so a stray race no longer aborts the entire workspace run, (5) frontend `useWorkspacePreflight` hook gates the kick-off buttons on /status and the deep-dive ReportHeader with structured tooltip copy, and an amber unsaved-draft banner on /model/[ticker] surfaces the otherwise-invisible draft state. Backend suite green; frontend lint + build clean.
```

- [ ] **Step 7.4: Open the PR**

```bash
git push -u origin feat/workspace-robustness-pack
gh pr create --title "feat(workspace): robustness pack — preflight + race fixes + schema validation" --body "$(cat <<'EOF'
## Summary
- Adds typed preflight DTO + `GET /api/workspace/{ticker}/preflight` endpoint so the UI knows *why* a workspace can't kick off
- Closes the `kick_off`-to-claim race with a per-ticker `asyncio.Lock`
- Validates `workspace_runs.step_outputs` against per-step Pydantic schemas before persist
- Adds an in-flight guard to `compute_delta` so concurrent calls coalesce on a single Haiku run
- Catches `IntegrityError` in `step_research` so a stray transcript-delta race no longer aborts a 30–40s workspace run
- Adds an amber unsaved-draft banner on `/model/[ticker]` and disabled+tooltip state on every workspace kick-off button

## Test plan
- [ ] `python -m unittest discover -s backend/tests -p 'test_*.py'` — all pass
- [ ] `cd frontend && npm run lint && npm run build` — clean
- [ ] Manual: ticker without saved model → workspace button disabled with tooltip
- [ ] Manual: ticker with unsaved draft → banner appears on /model page, workspace button disabled
- [ ] Manual: trigger a second kick-off while one is running → second request routes to in-flight run, no 409 alert

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Self-review checklist (do this before declaring done)

1. **Spec coverage**
   - #1 Preflight: Task 1 (endpoint) + Task 5 (UI gating) ✅
   - #3 Draft visibility: Task 6 (banner) ✅
   - #6 Kick-off race: Task 2 (lock) ✅
   - #7 step_outputs validation: Task 3 ✅
   - #10 compute_delta race aborts workspace: Task 4 ✅

2. **No placeholders**: every step has either code or an exact command; no "TBD", no "implement appropriately".

3. **Type consistency**: `WorkspacePreflight.missing` union codes match `MISSING_COPY` keys in the hook and match the `_STEP_SCHEMAS` keys / `PreflightStatus.missing` codes in the backend. Verify with a grep on `unsaved_model_draft` across both files before declaring done — they should both reference the same string.
