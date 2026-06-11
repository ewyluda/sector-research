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

### Transcript delta
A Haiku-extracted quarter-over-quarter language shift for one ticker, organized by 9 axes that **overlap with but are not identical to** the deep-dive scoring categories: `business_quality`, `risk_assessment`, `growth_earnings`, `sentiment_narrative`, `management_governance`, `future_durability`, `macro_regime`, `financial_health`, `valuation_stage`. The value of any axis can be `null` — the prompt is instructed to return null when the transcripts don't materially address that axis, and `macro_regime` / `financial_health` / `valuation_stage` are expected to be null on most calls.

**Axis vocabulary diverges by one slot from the scoring vocabulary:** the deep-dive *scoring* set uses `technical_market_structure` (chart/RSI/momentum) where the transcript delta set uses `valuation_stage`. Management never discusses chart structure on earnings calls, so the substitution is intentional. The frontend keeps both sets co-located in `frontend/components/deep-dive/categories.ts` (`SCORE_CATEGORIES` vs. `DELTA_AXES`).

Not to be confused with the **model delta** that Step 1 of the workspace loop emits (`changed_cells`, `removed_cells`): Step 1's delta is structural and numeric — it tracks specific cells in `ticker_models.state` that changed between versions. A transcript delta is qualitative and narrative — it tracks how management's *language* shifted on a thesis axis, anchored by 1-3 verbatim quotes per axis. They live in different tables (`ticker_models` vs. `transcript_deltas`), have different cadences (per workspace run vs. per new earnings transcript), and feed different consumers (Step 4 Challenge consumes the model delta; the deep-dive `WhatChangedPanel` and Step 2 Research consume the transcript delta).

Each emitted axis carries a `direction` (`softening` / `strengthening` / `stable`) and a `magnitude` (`minor` / `material` / `regime_change`). `regime_change` is a strong claim — "the narrative pillar itself has changed" — and is the only magnitude that should ever justify revisiting the thesis from priors.

Persisted in `transcript_deltas`, keyed by `(ticker, transcripts_fingerprint)` where the fingerprint is a SHA-1 of the sorted `(year, quarter)` tuples of the transcripts the delta was computed from. Re-running on the same window is a cache hit (free idempotency). A new transcript drops → new fingerprint → new row. `force=True` updates the matching row in place rather than inserting (avoids the unique constraint). History capped at 8 rows per ticker via delete-oldest sweep at write time.

**Scope is ticker-only, not `(ticker, theme_id)`** — a CEO's tone shift on growth is theme-agnostic, and the consumer surfaces (the deep-dive page and the workspace loop) are both keyed on ticker.

**Known limitation:** `fetch_recent_transcripts` walks back quarter-by-quarter and skips empty quarters, so for a ticker with an FMP coverage gap the 4-quarter window can be non-consecutive (e.g. `[Q4'25, Q3'25, Q1'25, Q4'24]`). The prompt presents real `=== Qn YYYY ===` labels so Haiku can see the gap, but there's no instruction to downweight `regime_change` magnitude on long jumps. In practice this means an occasional over-confident regime call on small-caps / recent IPOs; not a quote-fabrication or wrong-direction risk.

**Resolved (workspace robustness pack, `18e601f`):** `compute_delta` concurrency is guarded. A module-level `_IN_FLIGHT: dict[(ticker, fingerprint), asyncio.Event]` dedupes concurrent computes within the process (leader runs Haiku, followers wait and read the cached row — best-effort: a cross-session follower can miss the leader's row until its caller commits), and the INSERT runs under a SAVEPOINT so losing a cross-session unique-constraint race returns the winner's committed row instead of raising. `workspace_steps.step_research` also catches any stray IntegrityError so a race can't abort a 30-40s workspace run.

### The 5 steps
The fixed sequence inside one workspace run, run continuously without human gates:

1. **Update / Refresh** — pull latest FMP quarterly actuals + EDGAR filing index, patch into the prior `ticker_models.state`, recompute, diff. If anything actually changed, write a new `ticker_models` row (version + 1). Diff `added` and `changed` populate `changed_cells`. Diff `removed` is surfaced separately as `removed_cells` (a source field disappearing should never look like a user edit) — silent data loss is treated as a first-class warning.
2. **Research** — Haiku triage of new sources against prior thesis; surfaces highlights and new open questions.
3. **Validation** — re-run the reverse-DCF (implied drivers, IRR, sensitivity grids, thesis-vs-priced-in) against the *post-Step-1* ticker_models version, using a live FMP price.
4. **Challenge** — Sonnet pass that stress-tests the prior thesis against Step 1's deltas. Emits `kill_criterion_writes` (applied to `kill_criterion_state`), `catalyst_updates` (deferred — surfaced for UI only until `Catalyst.status` exists), and a `proposed_verdict`.
5. **Differentiation** — peer-comp table (peers from `peers_for_ticker` — the curated peer set first, `competitor_landscape` resolution as fallback) plus read-throughs from the existing read-through service.

### Peer set
The curated list of comparison tickers for a ticker, persisted in `peer_sets` (ticker PK, JSONB peers). Auto-seeded on first read from resolved `competitor_landscape` tickers ∪ `FMPClient.get_stock_peers`, capped at 8; manual edits through `PUT /api/peers/{ticker}` are capped at 12. `services/peer_sets.py` functions write **without committing** — callers own the session (API routes commit). `peers_for_ticker` is the read path every consumer shares: curated set if one exists, landscape-derived fallback otherwise. Three consumers of the resulting comp table (`services/peer_comp.py`): `GET /api/peers/{ticker}/comp`, ad-hoc `GET /api/peers/compare?tickers=` (the `/compare` page — URL is the state), and workspace Step 5 (Differentiation).

**Route-ordering footgun:** in `api/peers.py`, `/compare` must stay declared before `/{ticker}` — "compare" parses as a valid ticker (pinned by test).

### Universe
The set of tickers the daily monitoring surfaces care about: **theme `seed_tickers` ∪ tickers with an active (non-archived, completed) thesis** — the latter derived from the status board's latest-runs SQL. Both the unified calendar (`services/calendar_events.py`) and the material-events scan (`services/material_events_scheduler.py`) use this same derivation; if you change how the board picks latest runs, both inherit the change. Distinct from theme membership: a ticker with an active thesis stays in the universe even after being removed from every theme's seeds.

### Material event
A Haiku-classified 8-K for a universe ticker, persisted in `material_events` (unique per filing; `dismissed_at` mirrors read-through dismissals). The daily 06:30 UTC scan prefilters by item code — filings whose items are a non-empty subset of {7.01, 9.01} are skipped, 2.02 is kept (guidance lives there), and empty item metadata means classify anyway. Classification errors are **not** tombstoned, so failed filings retry on the next run. The 8-K side is fault-isolated from the Form 4 insider ingest: an EDGAR/Haiku failure rolls back and is recorded, but insider processing still runs. Surfaces: status-board badge + `MaterialEventsDrawer` (deep link `/status?expand_events=<ticker>` — only resolves for tickers with a board entry), amber high-materiality rows on Today, `/api/events` list/dismiss/scan.

### Insider signal
A 90-day aggregate over `insider_transactions` (Form 4 rows from FMP, idempotent on a sha256 natural key over **parsed** values so serialization drift can't mint duplicates). Computed by the pure `insider_signal.py`: open-market purchases/sales only, null-price rows count but add no value, a cluster is ≥2 distinct buyers within 30 days. Written as a `signals` row with `signal_type="insider"` per (ticker, theme) with the usual `signal_history` dual-write. Discovery applies it as a **bounded modifier** (+5 cluster / +2 net buying / −3 pronounced selling, clamped [0,100], 48h staleness) — deliberately not a fourth combined-score weight. **`InsiderSnapshot.is_stale` is overloaded**: it is also true for fresh-but-zero-modifier snapshots — read its docstring before adding consumers.

### Quant fingerprint
The deterministic quant layer: Piotroski F, Altman Z, Beneish M, accruals, FCF conversion, SBC dilution, and margin OLS slopes, computed in pure Python (`services/quant_fingerprint.py`) from the same 8 quarters of FMP statements the deep dive already fetches — TTM (quarters 0–3) vs prior-TTM (quarters 4–7). Attached to `CuratedFinancials.quant_fingerprint` (zero new API surface) and routed into 5 deep-dive category prompts via `QUANT_ROUTING` + the `{quant_data}` slot, framed as "established facts — don't recompute". Every metric is independently nullable; Altman and Beneish are marked not-applicable for Financial Services. Frontend card hidden for runs predating the feature.

### Trade journal
The manual record of actual trades, one row per entry+exit pair in `journal_trades` (null `exit_date` = open; explicit `exit_date: null` on PATCH reopens and clears exit fields). Optionally linked to a `verdict_outcomes` row (nullable FK, SET NULL) — the link is what enables the **decision-vs-paper comparison** (`services/journal_comparison.py`, pure math): the trade's realized return vs the outcome snapshot whose offset is *nearest* the holding period (midpoint thresholds 4/18/60/136 days — labeled, never interpolated), direction-aware (short = −long), SPY excess = trade − SPY over the holding period. Entry/exit fills auto-populate from FMP adjusted close (on-or-before, 7-day lookback) but stay editable — `*_price_source` distinguishes `manual` from `fmp_eod_adjusted`, and a date move refreshes only FMP-sourced fills (manual prices are sticky). `services/journal.py` is commit-free; FMP failures degrade (null SPY columns, 404 preview) rather than 500.
