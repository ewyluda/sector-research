# 3. Sibling `signal_history` table; `signals` becomes a read-cache

Date: 2026-05-10

## Status

Accepted

## Context

The daily X-signal scheduler (`services/signal_scheduler.py`) computes three readings per `(ticker, theme_id)` — `velocity`, `narrative`, `discovery` — and writes them to the `signals` table. The table's keying is upsert-overwrite: one row per `(ticker, theme_id, signal_type)`, last-write-wins via delete-then-insert inside `_persist_signal_set`. Yesterday's reading is replaced by today's; nothing is retained.

Three downstream concerns require a real time series:

1. **Multi-month velocity sparklines.** `VelocitySparkline.tsx` today renders only the latest ratio badge because there is no historical data to plot.
2. **Surprise-threshold tuning.** `VELOCITY_SURPRISE_MULTIPLIER` (currently 2.0×) was picked by guess. Without history, there is nothing to backtest the threshold against.
3. **Regression checks.** Detecting drift in signal computation requires comparing today's reading against the prior distribution.

Four read paths consume the current-value semantics of `signals` and would have to change if the table itself became append-only: `services/discovery._load_cached_signals` (discovery scoring), the surprise-alert prior-ratio lookup inside `signal_scheduler.refresh_theme_signals`, the `XSignalVelocity` payload in `api/pipeline.py:309`, and the same payload in `services/pipeline.py:353`.

## Decision

Add a sibling **`signal_history`** table that is append-only, dual-written by `_persist_signal_set` inside the same transaction as the `signals` upsert. New time-series consumers go through `services/signal_history.list_signal_history()` and `GET /api/themes/{id}/signals/{ticker}/history`. The four existing read paths are not modified.

Document `signals` as a denormalized read-cache over `signal_history` (CONTEXT.md glossary). The framing matters: it names the asymmetry as technical debt with a known shape, rather than as two equally-canonical tables that must be kept in sync forever. A future migration could replace `signals` with a `SELECT DISTINCT ON (ticker, theme_id, signal_type) ... ORDER BY computed_at DESC` view without breaking callers; that work is not committed to here.

## Alternatives considered

- **Append-only on `signals` itself.** Re-key to `(ticker, theme_id, signal_type, computed_at)`, drop the upsert. Forces all four read paths to grow a "latest row" subquery on the same day this ships. Rejected — the read-path migration cost was disproportionate to the goal of "stop discarding history."
- **Generic event store / time-series table.** Build a polymorphic `events` or `metrics` table that any future signal could land in. Rejected — premature abstraction; today there is exactly one producer.
- **Do nothing; rebuild history from external sources.** The X API's historical search is rate-limited and lossy at multi-month windows. Rejected — the data is already being computed daily; not persisting it is the only reason it doesn't exist.

## Consequences

- **Dual-write coupling.** Every future change to `_persist_signal_set` must remember to write both rows. The helper is the single seam, and `test_signal_scheduler_persist.py` pins the contract — both tables get a row per `signal_type` per refresh, with a shared `computed_at`.
- **`is_stale` is intentionally not replicated.** Staleness is a property of the *current* reading ("did today's scheduler run land?"), not of historical readings, which were fresh when written. The flag stays on `signals` only.
- **Retention is deferred.** ~110K rows/year (~25 tickers × 4 themes × 365 days × 3 signal_types) is trivial for Postgres; pruning can be added as a one-line `DELETE FROM signal_history WHERE computed_at < now() - interval 'N days'` if it ever matters.
- **No backfill.** Existing `signals` rows represent only the latest reading per series, not historical data — backfilling them yields one-point histories, which is no better than starting fresh on the next scheduler run.
- **FK on `theme_id` has no `ON DELETE` action**, matching the existing `signals` table convention. Themes are seed data; deletion is not part of the domain.
- **Endpoint payload is intentionally opaque.** `points[].value` is `Record<string, unknown>` on the wire. Per-`signal_type` keys are documented in the endpoint docstring. A typed discriminated union was rejected as over-engineering for a personal tool with one near-term consumer; the docstring + `XSignalVelocity` interface in `frontend/lib/api.ts` are the canonical reference.
- **Future retirement of `signals`** remains possible but is not on a roadmap. The CONTEXT.md framing names the path; whether to walk it is a later decision driven by real maintenance pain, not by aesthetics.
