# Context

The shared language for this codebase. If a term you need isn't here, propose it.

## Glossary

### Workspace
The persistent per-ticker analytical surface: the latest completed `research_run` for the ticker, the latest `ticker_models` row, and the history of `workspace_runs` against it. A workspace is **not** a row in the database — it's the projection you get by joining those three things on `ticker`. The `/workspace` page lists recent activity across workspaces; `/workspace/{runId}` shows a single run inside one workspace.

A workspace exists for a ticker iff there is at least one completed `research_run` AND at least one `ticker_models` row for that ticker. Both prerequisites are checked in `WorkspaceService._preflight`.

Workspace runs require a clean saved model state. If a ticker has an unsaved model draft, the run is rejected until the user either saves or discards the draft. This prevents a later draft save from overwriting freshly promoted actuals from the workspace refresh.

**At most one workspace run with status `running` per ticker.** Kicking off a second run while one is in flight returns HTTP 409 with the in-flight run's id; the frontend navigates to that run instead. This invariant prevents two parallel runs from racing on the `ticker_models.(ticker, version)` unique constraint and silently producing a verdict against stale state.

### Workspace run
One execution of the 5-step refresh loop against a workspace. Persisted as one row in `workspace_runs`. Carries `ticker_model_version_before` and `ticker_model_version_after` so a reader can tell whether Step 1 produced a new model version. Carries one denormalized `verdict` (sourced from Step 4's `proposed_verdict`).

**Run status vocabulary:**
- `running` — orchestrator task is alive.
- `completed` — orchestrator finished AND every step produced its Pydantic output without recording an error. This is the only status where the verdict is fully trusted.
- `partial` — orchestrator finished but at least one step's `step_outputs[name]` carries an `error` key. The run is readable but the verdict (if present) was derived from incomplete inputs. The index page renders these with a warning treatment.
- `failed` — the orchestrator itself crashed (uncaught exception or cancellation). `step_outputs` may be empty.

### Theme membership
A theme's `seed_tickers` (JSONB list on the `themes` row) is the curated tracked-ticker list. It is **not** the full set of companies that appear in discovery — discovery additionally surfaces FMP screener matches and flags seeds with `is_seed=true`. Seeds are also the iteration set for daily signal refresh and theme-level fanout, with the scheduler taking the union of `seed_tickers` and any ticker that already has a row in `signals` for the theme.

Membership is mutated through three endpoints in `api/themes.py`: full-payload `PUT /api/themes/{id}` (replaces the list) and the atomic `POST /api/themes/{id}/tickers` / `DELETE /api/themes/{id}/tickers/{ticker}` sub-routes. All three normalize tickers (uppercase, strip, dedupe order-preserving) via the shared `_normalize_tickers` helper, which also tolerates the legacy list-of-dicts shape (entries with a `"ticker"` key) — mirroring `services/fanout.py`'s defensive read.

Removing a ticker from `seed_tickers` does **not** cascade-delete its `signals` or `signal_history` rows: historical readings are preserved, and the scheduler's union-with-previously-signalled rule means an ex-seed ticker keeps refreshing until its `signals` row is manually cleared.

### Signal
A computed reading of one of three X-derived metrics — `velocity`, `narrative`, `discovery` — for a `(ticker, theme_id)` pair at a point in time. Written by the daily `signal_scheduler`.

Persisted in two shapes:
- **`signal_history`** is the append-only source of truth — one row per refresh per `(ticker, theme_id, signal_type)`.
- **`signals`** is a denormalized read-cache holding only the latest reading per `(ticker, theme_id, signal_type)` (last-write-wins via delete-then-insert inside `_persist_signal_set`). It also carries the `is_stale` flag, which is a property of the *current* reading and intentionally not replicated into `signal_history`.

Read paths follow the asymmetry:
- Discovery scoring (`services/discovery._load_cached_signals`), surprise-alert prior-ratio lookup in the scheduler, deep-dive `XSignalVelocity` payload (`api/pipeline.py`, `services/pipeline.py`) — all read from `signals`.
- Multi-period analytics — sparklines, regression checks, surprise-threshold tuning — read from `signal_history` via `services/signal_history.list_signal_history`.

Either both rows land or neither does: `_persist_signal_set` adds the `Signal` and `SignalHistory` rows in the same scheduler transaction before `db.commit()`.

### The 5 steps
The fixed sequence inside one workspace run, run continuously without human gates:

1. **Update / Refresh** — pull latest FMP quarterly actuals + EDGAR filing index, patch into the prior `ticker_models.state`, recompute, diff. If anything actually changed, write a new `ticker_models` row (version + 1). Diff `added` and `changed` populate `changed_cells`. Diff `removed` is surfaced separately as `removed_cells` (a source field disappearing should never look like a user edit) — silent data loss is treated as a first-class warning.
2. **Research** — Haiku triage of new sources against prior thesis; surfaces highlights and new open questions.
3. **Validation** — re-run the reverse-DCF (implied drivers, IRR, sensitivity grids, thesis-vs-priced-in) against the *post-Step-1* ticker_models version, using a live FMP price.
4. **Challenge** — Sonnet pass that stress-tests the prior thesis against Step 1's deltas. Emits `kill_criterion_writes` (applied to `kill_criterion_state`), `catalyst_updates` (deferred — surfaced for UI only until `Catalyst.status` exists), and a `proposed_verdict`.
5. **Differentiation** — peer-comp table (resolved competitor tickers from `competitor_landscape`) plus read-throughs from the existing read-through service.
