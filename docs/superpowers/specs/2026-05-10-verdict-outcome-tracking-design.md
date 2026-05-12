# Verdict outcome tracking — edge measurement

**Date:** 2026-05-10
**Status:** Refined via brainstorming. Ready for implementation plan.
**Source:** Repo audit on 2026-05-10. v3 alpha-direction priority #1.

The meta-feature. Every other feature synthesizes information into a verdict; nothing closes the loop on whether those verdicts make money. Without that loop, every other feature is faith-based.

---

## The four questions this answers

1. **Do I have any edge at all?** — Aggregate IRR of positive verdicts vs SPY.
2. **Which verdict band actually predicts?** — Per-band rollup of return / excess / win-rate.
3. **Which themes are my alpha source?** — Per-theme rollup, drill-down to outcomes.
4. **Which signals drive my best picks?** — Quartile-bucketed return by signal value at emission.

All four are v1.

---

## What constitutes a "verdict"

Two emission sources are tracked. The status board is a view, not an emission.

| Source             | Where it's emitted                                                                | Verdict values                                       |
| ------------------ | --------------------------------------------------------------------------------- | ---------------------------------------------------- |
| `research_run`     | `research_runs.status` transitions to `completed` / `watchlist` / `pass`          | `completed` (positive), `watchlist` (neutral park), `pass` (rare — explicit no-go) |
| `workspace_run`    | `workspace_runs.verdict` column (extracted from `step_outputs.challenge.proposed_verdict` and persisted on terminal status) | `healthy` / `imminent` / `triggered` / `broken`      |

**Design call.** Each emission is an independent observation. A workspace run on `(NVDA, AI infra)` does NOT replace a prior research run on the same ticker — both are tracked separately. Within the same `(ticker, theme_id, source_type=workspace_run)` pair, however, a new verdict supersedes the prior one (see Supersede stamping).

`watchlist` and `broken` verdicts ARE tracked. They're the control group — "are my broken verdicts actually losing money" is a real validation question, and negative-verdict alpha (avoidance) is also real.

---

## Data model

Single Alembic migration. Three tables.

### `sector_etf_mapping`

Static lookup, ~12 rows seeded in the migration:

```sql
sector_etf_mapping (
  fmp_sector  text PRIMARY KEY,
  etf_ticker  text NOT NULL,
  notes       text
)
```

Seeds:

| FMP sector              | ETF |
| ----------------------- | --- |
| Technology              | XLK |
| Energy                  | XLE |
| Healthcare              | XLV |
| Financial Services      | XLF |
| Industrials             | XLI |
| Consumer Cyclical       | XLY |
| Consumer Defensive      | XLP |
| Basic Materials         | XLB |
| Utilities               | XLU |
| Real Estate             | XLRE |
| Communication Services  | XLC |

Tickers in unmapped sectors get `sector_etf_ticker = NULL`. Sector-excess columns stay null for that outcome. Acceptable.

### `verdict_outcomes`

```sql
verdict_outcomes (
  id                                uuid PRIMARY KEY,
  source_type                       text NOT NULL,         -- 'research_run' | 'workspace_run'
  source_id                         uuid NOT NULL,
  ticker                            text NOT NULL,
  theme_id                          uuid REFERENCES themes(id) ON DELETE SET NULL,
  verdict                           text NOT NULL,
  verdict_emitted_at                timestamptz NOT NULL,

  -- Entry pricing (anchored to first trading day strictly after emission)
  entry_price_at                    date NOT NULL,
  entry_price                       numeric NOT NULL,
  entry_price_source                text NOT NULL DEFAULT 'fmp_historical_eod_adjusted',

  -- Benchmark entry prices, ALL anchored to entry_price_at
  spy_entry_price                   numeric,
  sector_etf_ticker                 text,                  -- nullable
  sector_etf_entry_price            numeric,
  theme_basket_entry_value          numeric,               -- 100.0 (basket starts at par)
  theme_basket_constituents         jsonb,                 -- [{ticker, entry_price}, ...] snapshotted at emission

  -- Signal context at emission (use case #4)
  signal_snapshot                   jsonb,

  -- Supersede stamp (use case #2 — realized return when a new same-source verdict for same (ticker, theme_id) lands)
  superseded_at                     timestamptz,
  superseded_by_outcome_id          uuid REFERENCES verdict_outcomes(id) ON DELETE SET NULL,
  realized_ticker_return_pct        numeric,
  realized_spy_excess_pct           numeric,
  realized_sector_excess_pct        numeric,
  realized_theme_basket_excess_pct  numeric,

  closed_at                         timestamptz,           -- set when 6m snapshot lands; orthogonal to supersede
  created_at                        timestamptz NOT NULL DEFAULT now(),

  UNIQUE (source_type, source_id)
);

CREATE INDEX ix_outcomes_ticker_emitted     ON verdict_outcomes (ticker, verdict_emitted_at DESC);
CREATE INDEX ix_outcomes_theme_emitted      ON verdict_outcomes (theme_id, verdict_emitted_at DESC);
CREATE INDEX ix_outcomes_open               ON verdict_outcomes (closed_at) WHERE closed_at IS NULL;
CREATE INDEX ix_outcomes_open_per_position  ON verdict_outcomes (ticker, theme_id, source_type, superseded_at) WHERE superseded_at IS NULL;
```

### `verdict_return_snapshots`

```sql
verdict_return_snapshots (
  id                       uuid PRIMARY KEY,
  outcome_id               uuid NOT NULL REFERENCES verdict_outcomes(id) ON DELETE CASCADE,
  snapshot_offset          text NOT NULL,           -- '1d' | '1w' | '1m' | '3m' | '6m'
  snapshot_date            date NOT NULL,

  ticker_price             numeric NOT NULL,
  spy_price                numeric,
  sector_etf_price         numeric,
  theme_basket_value       numeric,

  ticker_return_pct        numeric NOT NULL,
  spy_excess_pct           numeric,
  sector_excess_pct        numeric,
  theme_basket_excess_pct  numeric,

  created_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (outcome_id, snapshot_offset)
);
```

### Signal snapshot JSONB shape

Assembled by two builders in `outcome_tracker.py`:

```jsonc
{
  "signals_row": {
    "velocity":    12.3,
    "fundamental": 0.78,
    "discovery":   0.65,
    "surprise":    null
  },
  "deep_dive_scores": {                     // research_run source only
    "Business Quality":      72,
    "Risk Assessment":       58,
    "Growth & Earnings":     81,
    "Macro & Regime":        65,
    "Future Durability":     70,
    "Financial Health":      82,
    "Sentiment & Narrative": 60,
    "Management & Governance": 75,
    "Valuation":             55
  },
  "workspace_step_verdicts": {              // workspace_run source only
    "update_refresh":  "healthy",           // each value is the step's emitted verdict string
    "research":        "healthy",
    "challenge":       "imminent",
    "differentiation": "healthy",
    "validation":      "healthy"
  },
  "kill_criterion_state": [
    { "ordinal": 1, "state": "armed" },
    { "ordinal": 2, "state": "triggered" }
  ],
  "model_assumptions": {                    // null if no model exists for ticker
    "discount_rate":     0.10,
    "terminal_growth":   0.025,
    "terminal_multiple": null
  }
}
```

---

## Snapshot offset definitions

| Offset | Calendar target (from `entry_price_at`)             |
| ------ | --------------------------------------------------- |
| `1d`   | First trading day ≥ entry_price_at + 1 calendar day |
| `1w`   | First trading day ≥ entry_price_at + 7 calendar days |
| `1m`   | First trading day ≥ entry_price_at + 30 calendar days |
| `3m`   | First trading day ≥ entry_price_at + 90 calendar days |
| `6m`   | First trading day ≥ entry_price_at + 180 calendar days. Closes the outcome (`closed_at = now()`). |

FMP returns trading days only — the "first available adjusted-close on or after target" rule resolves cleanly.

---

## Entry price rule

`entry_price_at` = first trading day strictly after `verdict_emitted_at`'s calendar date. `entry_price` = adjusted close on that day.

Rationale: verdicts land off-hours; a real-money replica reacts at next open at earliest. Using same-day close gives a free look-ahead and inflates measured alpha. Using next-day close (vs next-day open) avoids needing a separate intraday endpoint while staying conservative.

All three benchmark entry prices anchor to the **same** `entry_price_at` so excess returns are directly comparable.

---

## Theme basket math

At verdict emission, snapshot `theme.seed_tickers` and each constituent's `entry_price_at` adjusted close into `theme_basket_constituents` JSONB. Basket value starts at 100 by convention.

At each snapshot offset:

```
basket_value_at(date) = mean(
    constituent.adjusted_close(date) / constituent.entry_price
  for constituent in theme_basket_constituents
  if constituent.adjusted_close(date) is not null
) * 100

basket_return_pct_at(date) = basket_value_at(date) / 100 - 1
```

Equal-weighted arithmetic average. Missing constituents (delistings, FMP gaps) drop from that snapshot's average — not back-filled.

---

## Supersede rule

When `record_verdict` runs for `(ticker=X, theme_id=Y, source_type=S)`:

1. Look up the latest non-superseded outcome for the same `(X, Y, S)`. **Same source_type** — workspace verdicts supersede prior workspace verdicts, research-run verdicts supersede prior research-run verdicts. They don't supersede across types.
2. If found, stamp it:
   - `superseded_at = now()`
   - `superseded_by_outcome_id = new.id`
   - `realized_ticker_return_pct`, `realized_spy_excess_pct`, `realized_sector_excess_pct`, `realized_theme_basket_excess_pct` — all computed from the new outcome's `entry_price_at` prices.

Cross-theme verdicts don't supersede each other. Cross-source-type verdicts don't supersede each other. Both directional — `(NVDA, AI infra)` research run and `(NVDA, AI infra)` workspace run are independent positions.

`closed_at` is orthogonal — set only when the 6m snapshot lands. An outcome can be `superseded_at IS NOT NULL` AND `closed_at IS NULL` (the original snapshots keep being filled even after a successor exists).

---

## Services

`backend/app/services/outcome_tracker.py`:

```python
async def record_verdict(
    *,
    source_type: Literal["research_run", "workspace_run"],
    source_id: UUID,
    ticker: str,
    theme_id: int | None,
    verdict: str,
    verdict_emitted_at: datetime,
    signal_snapshot: dict,
    fmp: FMPClient,
    db: AsyncSession,
) -> VerdictOutcome: ...

async def refresh_snapshots(*, fmp: FMPClient, db: AsyncSession) -> RefreshSummary: ...

async def backfill_from_history(*, fmp: FMPClient, db: AsyncSession) -> BackfillSummary: ...

def build_research_run_signal_snapshot(state, signals_row, kill_states) -> dict: ...
def build_workspace_run_signal_snapshot(run, signals_row, kill_states, model_state) -> dict: ...
```

**Helper:**

```python
async def _resolve_entry_prices(
    *, ticker: str, target_date: date, theme_seed_tickers: list[str] | None,
    sector: str | None, fmp: FMPClient,
) -> EntryPriceBundle:
    """One batched range-fetch per unique ticker over [target_date, target_date + 7d]."""
```

**Failure modes:**
- FMP no data on entry date: retry target_date + 1 up to 7 days, then raise. No partial outcome rows.
- FMP no data for a benchmark (sector ETF / theme constituent): null that column, continue. Outcome is still recorded; one benchmark missing.
- Refresh-job per-outcome errors: captured in `summary.errors[]`, never abort the loop.
- **Backfill schema-evolution tolerance.** Older research runs may have `state` JSONB without the deep-dive score keys, or in a different shape than current. Signal-snapshot builders defensively `.get(key, None)` everything from the persisted state, never KeyError. A backfilled outcome with partial `signal_snapshot` is still tracked; missing signals just drop from `by_signal_bucket` aggregations.
- **Re-emission as new outcome.** If a workspace run re-runs and emits the same verdict for the same `(ticker, theme_id)`, the new run has a distinct `source_id` so `record_verdict` creates a new outcome row and supersedes the prior one. That's intentional — each terminal completion is a fresh observation moment, even when the verdict string is unchanged.

---

## Hook points

1. **`backend/app/services/pipeline.py::PipelineService._run_phase`** — after status transitions to `completed` or `watchlist`, assemble snapshot via `build_research_run_signal_snapshot`, call `record_verdict(source_type="research_run", ...)`. Wrap in `unit_of_work()`.

2. **`backend/app/services/workspace.py`** — after final step's verdict persists into `workspace_runs.step_outputs`, assemble snapshot via `build_workspace_run_signal_snapshot`, call `record_verdict(source_type="workspace_run", ...)`. Wrap in `unit_of_work()`.

3. **`backend/app/main.py::lifespan`** — register `AsyncIOScheduler` cron at 03:00 UTC (after the existing 02:00 signal refresh, before US pre-open). Wrapper pulls `app.state.fmp` + a fresh `async_session()`, runs `refresh_snapshots` inside `unit_of_work()`.

---

## API surface

`backend/app/api/outcomes.py`, prefix `/api/outcomes`, registered without secondary prefix.

```
GET  /api/outcomes/summary
       ?theme_id=
       &window=30d|90d|1y|all              (default 90d)
       &snapshot_offset=1d|1w|1m|3m|6m     (default 3m)
       &benchmark=spy|sector|theme_basket  (default spy)
       &source_type=research_run|workspace_run|all  (default all)
     →  {
          window, snapshot_offset, benchmark,
          overall:    { n, mean_return_pct, mean_excess_pct, win_rate, median_excess_pct },
          by_verdict: { healthy: {...}, imminent: {...}, ..., completed: {...}, watchlist: {...} },
          by_theme:   [ { theme_id, theme_name, n, mean_return_pct, mean_excess_pct, win_rate }, ... ],
          by_signal_bucket: {
            "velocity":    [ { bucket: "0-25th", n, mean_excess_pct, win_rate }, ... ],
            "fundamental": [ ... ],
            "discovery":   [ ... ]
          }
        }

GET  /api/outcomes
       ?theme_id=&verdict=&source_type=&superseded=true|false|all&closed=true|false|all
       &limit=&offset=
     →  paginated list, each outcome inlines its snapshot grid + supersede stamp

GET  /api/outcomes/by-source/{source_type}/{source_id}
     →  single outcome + full snapshot grid + signal_snapshot. 404 if not tracked.

POST /api/outcomes/backfill
     →  202 + summary stats. Manual, infrequent.
```

`win_rate` = fraction of outcomes whose `<benchmark>_excess_pct` at `snapshot_offset` is > 0. Quartile cutoffs for `by_signal_bucket` are computed over the window's outcomes (relative, not absolute thresholds).

**Quartile noise caveat.** For small windows (<~20 outcomes), each quartile holds 2–5 outcomes — too few to draw conclusions. Frontend renders quartile rows regardless; signal-attribution interpretation needs ≥40 outcomes in window to be meaningful. Not enforced; user judgment.

---

## Frontend

New top-level page `/performance`, 8th nav link in `frontend/components/Nav.tsx`.

```
┌─ Filters bar (data-print-hide) ─────────────────────────────────────┐
│  [Window: 30d|90d|1y|All] [Offset: 1m|3m|6m] [Benchmark: SPY|Sector│
│   |Theme] [Source: All|Research|Workspace]                          │
└─────────────────────────────────────────────────────────────────────┘

┌─ HeroBand ──────────────────────────────────────────────────────────┐
│  Lifetime IRR — positive verdicts: +14.2% (vs SPY +6.1%, +8.1%)     │
│  N = 42  |  Win rate = 64%  |  Median excess = +5.8%                │
└─────────────────────────────────────────────────────────────────────┘

┌─ ByVerdictTable ────────────────────────────────────────────────────┐
│  Band       N    Mean Return    Excess     Win Rate    Median Excess│
│  healthy   18    +18.4%         +12.3%     78%         +9.4%        │
│  imminent  10    +8.7%          +2.6%      60%         +1.2%        │
│  triggered  8    -3.4%          -9.5%      25%         -7.1%        │
│  broken     6    -12.1%         -18.2%     17%         -15.0%       │
│  completed  ...                                                     │
│  watchlist  ...                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─ ByThemeTable ──────────────────────────────────────────────────────┐
│  Theme            N   Mean Return    Excess    Win Rate              │
│  AI infra        12   +18.4%         +12.3%    75%                   │
│  Nuclear          8   +6.1%          +0.0%     50%                   │
│  ...              Row click → filters OutcomeList below              │
└─────────────────────────────────────────────────────────────────────┘

┌─ BySignalBucketPanel ───────────────────────────────────────────────┐
│  Velocity quartile     N    Mean Excess    Win Rate                  │
│  0–25th               10    -4.2%          30%                       │
│  25–50th               9    +1.5%          55%                       │
│  50–75th              11    +6.8%          68%                       │
│  75–100th             12    +14.3%         82%                       │
│  null                  0    —              —                         │
│  [Switch signal: Velocity | Fundamental | Discovery]                 │
└─────────────────────────────────────────────────────────────────────┘

┌─ OutcomeList ───────────────────────────────────────────────────────┐
│  Ticker | Theme | Verdict | Emitted | Status | +1m Ex | +3m Ex      │
│   | +6m Ex | Realized (if superseded)                                │
│  Row click → /pipeline/[runId] or /workspace/[runId]                 │
└─────────────────────────────────────────────────────────────────────┘
```

**Components** in `frontend/components/performance/`:

- `PerformanceFilters.tsx` — four-control bar; drives URL state via `useSearchParams`.
- `HeroBand.tsx` — three big numbers + N + win rate.
- `ByVerdictTable.tsx` — verdict-band rollup, color-coded by sign of excess.
- `ByThemeTable.tsx` — theme rollup, row click filters OutcomeList.
- `BySignalBucketPanel.tsx` — quartile bucket table + signal switcher.
- `OutcomeList.tsx` — paginated, sortable, links to source run.
- `ReturnCell.tsx` — shared cell formatter (`+12.3%`, sign-colored).

`Status` cell client-derives from `(superseded_at, closed_at)` → `open` / `superseded` / `closed`.

Print hygiene: filter bar carries `data-print-hide="true"`.

**Out of scope for v1:** within-outcome sparkline of excess return, status-board inline excess badge, drawdown stats, per-signal heatmaps. All derivable from the same data later.

---

## Tests

**`backend/tests/test_outcome_tracker.py`** (~12 tests):

- `test_record_verdict_idempotent`
- `test_record_verdict_uses_next_trading_day`
- `test_record_verdict_captures_all_three_benchmarks`
- `test_record_verdict_supersedes_prior_open_outcome_same_source_type`
- `test_record_verdict_does_not_supersede_across_source_types`
- `test_record_verdict_cross_theme_no_supersede`
- `test_record_verdict_unmapped_sector_null_columns`
- `test_refresh_snapshots_fills_due_offsets`
- `test_refresh_snapshots_closes_at_6m`
- `test_refresh_snapshots_theme_basket_drops_missing_constituent`
- `test_refresh_snapshots_per_outcome_errors_isolated`
- `test_backfill_idempotent`
- `test_signal_snapshot_research_run_shape`
- `test_signal_snapshot_workspace_run_shape`

**`backend/tests/test_outcomes_api.py`** (~8 tests):

- Summary filter combinations (theme / window / offset / benchmark / source_type).
- `by_signal_bucket` quartiles compute correctly given fixture data.
- Win rate = fraction of outcomes with `<benchmark>_excess_pct > 0` for active benchmark.
- Empty-window returns zero-filled summary, not 404.
- `superseded` / `closed` filters on list endpoint.

Approx 20 tests. Mocks `FMPClient` at the service boundary per `test_unit_of_work.py` pattern.

---

## Phasing

~3 days end-to-end:

| Phase | Scope | Day |
| ----- | ----- | --- |
| 1 | Migration + ORM + `sector_etf_mapping` seeds + outcome_tracker core (record_verdict, refresh_snapshots, helper) + scheduler wiring | Day 1 |
| 2 | Signal-snapshot assembly builders + hook wiring (pipeline.py + workspace.py) + service-layer tests | Day 1.5 |
| 3 | Backfill + `POST /api/outcomes/backfill` + first manual run against existing data | Day 2 |
| 4 | API surface (summary + list + by-source) + API tests | Day 2.5 |
| 5 | Frontend `/performance` page (6 components + filters + URL state) | Day 3 |

No vendor cost. No new dependencies — FMP historical-EOD already integrated.

---

## Decisions locked

1. **Use cases.** All four — edge / band / themes / signal attribution — in v1.
2. **Verdict transitions.** Both fixed offsets AND supersede stamping; same source_type within same `(ticker, theme_id)` supersedes; cross-type and cross-theme are independent.
3. **Signal attribution.** v1. Signals row + run-internal scores (deep-dive categories, kill-criterion state, model assumptions, workspace step verdicts).
4. **Benchmarks.** SPY + sector ETF + theme basket — all three. Each excess column independent; null if benchmark unavailable.
5. **Schema shape.** Wide normalized (Approach A) — three explicit benchmark columns; JSONB only for theme constituents + signal snapshot.
6. **Negative verdicts.** Tracked (`watchlist`, `broken` included) as control group.
7. **Entry price.** Next trading day adjusted close. Same date anchors all benchmarks.
8. **Closed semantics.** Set only when 6m snapshot lands. Orthogonal to supersede.
9. **Theme basket math.** Equal-weighted arithmetic mean of constituent returns. Constituents snapshotted at emission; missing prices dropped from that snapshot's mean.
10. **Sector mapping.** Static table seeded in migration; null if FMP sector unmapped.

---

## Out of scope for v1

- Position sizing / Kelly fractioning / risk-adjusted (Sharpe / Sortino).
- Drawdown stats.
- Within-outcome sparkline / time-series of excess return.
- Status-board excess-return inline badge.
- Multi-leg / pair-trade tracking.
- Survivorship-bias correction beyond null-on-missing-price.
- Auto-promotion of high-alpha verdict bands as discovery signals (meta-meta-feature).
- Intraday entry pricing (next-day open).

---

## Pre-implementation checklist

- [x] FMP `historical-price-eod/dividend-adjusted` covers SPY + tickers + sector ETFs.
- [x] `research_runs.completed_at` populated on terminal transitions.
- [x] `workspace_runs.completed_at` + final verdict in `step_outputs`.
- [x] FMP `profile.sector` aligns with SPDR ETF mapping vocabulary above.
- [x] Backfill is idempotent and re-runnable as `python -m backend.scripts.backfill_outcomes`.
