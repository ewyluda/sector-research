# Fix: `/api/outcomes` 500 — `signals_row` Pydantic schema mismatch

**Source:** e2e finding 2026-05-12 (secondary-surfaces, BUG [high]).
**Status:** Validated against live backend. Reproduces 100%.

## Problem

`GET /api/outcomes?limit=N` returns HTTP 500 with `ResponseValidationError: 18 validation errors`. The `/performance` page calls `outcomesApi.list()` on every visit, so the page is fully broken for the user. `/api/outcomes/summary` is unaffected — only the list endpoint surfaces the mismatch.

## Root cause

`backend/app/models/outcome_schemas.py:32-39` declares:

```python
class SignalSnapshot(BaseModel):
    signals_row: dict[str, float | None] | None = None
    deep_dive_scores: dict[str, float | None] | None = None
    workspace_step_verdicts: dict[str, str | None] | None = None
    kill_criterion_state: list[dict[str, Any]] | None = None
    model_assumptions: dict[str, float | None] | None = None
```

But the actual `signal_snapshot` JSONB stored at outcome-emit time carries nested dicts for `velocity`, `discovery`, `narrative`, `fundamental`. Excerpt from a live failing row:

```
signals_row.velocity   = {'ratio': 1.0, 'count_7d': 99, 'direction': 'stable', 'count_30d_approx': 396}
signals_row.discovery  = {'score': 1.0206, 'is_seed': True, 'raw_score': 1.0206, 'boost_applied': 1.0, ...}
signals_row.narrative  = {'summary': None, 'post_count': 50, 'post_texts': [...50 strings...]}
```

Each is a `CompanySignalCard` sub-snapshot, not a scalar. Pydantic rejects every row because the declared inner type is `float | None`. All 18 rows in the DB fail validation.

## Fix

Loosen the inner types to match the persisted shape in `backend/app/models/outcome_schemas.py:32`:

```python
class SignalSnapshot(BaseModel):
    signals_row: dict[str, Any] | None = None
    deep_dive_scores: dict[str, Any] | None = None
    workspace_step_verdicts: dict[str, str | None] | None = None  # leave — actually scalar
    kill_criterion_state: list[dict[str, Any]] | None = None      # already correct
    model_assumptions: dict[str, Any] | None = None
```

Reasoning:
- `signals_row` holds full `CompanySignalCard` velocity/discovery/narrative/fundamental sub-dicts. `Any` matches persisted shape.
- `deep_dive_scores` is *probably* scalar-typed today but the schema rejects all 18 rows before we ever reach it, so we don't know for sure — defensive `Any` survives if future writes nest rationale.
- `model_assumptions`: same defensiveness; reverse-DCF assumptions block could nest in the future.

Frontend `frontend/lib/api.ts` `SignalSnapshot` type needs the matching shape — change inner types to `unknown`. The `/performance` page does not currently render `signal_snapshot.signals_row.narrative` directly, so widening doesn't lose anything; future panels that want to display velocity/post-count will narrow at the consumption site.

## Verification

1. Add a regression test in `backend/tests/` that round-trips a row whose `signals_row` is the nested-dict shape captured above. Test must fail on `main` before the fix.
2. `curl http://127.0.0.1:8000/api/outcomes?limit=10` returns 200 with non-empty list.
3. Browser-load `http://localhost:3000/performance`, confirm no console error and the outcomes table renders.

## Out of scope

- The *upstream* question — should `outcome_materialization` flatten `signals_row` to scalars before persisting? — is a separate decision. Schemas describe what's there now; flattening would be a data-model change with backfill implications.
- `OutcomeSummary` / `/api/outcomes/summary` is already working, no change.
