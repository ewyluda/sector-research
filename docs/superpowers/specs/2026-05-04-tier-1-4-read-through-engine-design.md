# Tier 1.4 — Read-Through Engine on Supply-Chain Graph

**Date:** 2026-05-04
**Status:** Spec — ready for implementation plan
**Roadmap context:** Tier 1.4 of `docs/superpowers/specs/2026-05-03-framework-improvements-roadmap-design.md`. Independent of Tier 2 but informs the status board (Tier 2.6) when shipped after.

---

## What this is

A read-through engine that surfaces peer events relevant to active theses by joining the existing supply-chain relationship graph against two streams of "peer events": earnings catalysts and recently completed pipeline runs. When a peer ticker has an event in the recent window and there is at least one relationship edge between that peer and a thesis on the status board, the engine surfaces a `ReadThroughItem` against that thesis.

Concretely: when NVDA's earnings catalyst flips to `Imminent` or NVDA's research run completes, every status-board thesis whose ticker has a `relationships` row touching `NVDA` (in either direction) gets an inline badge with the event details and verbatim filing quote. The user can dismiss individual events or trigger a one-shot Haiku impact-summary on demand.

This is "free leverage" from infra already shipped — `relationships`, `catalysts`, and `research_runs` are all in place. The engine is a query-layer feature plus a single new dismissals table.

## Decisions taken

| Topic | Decision | Why |
|---|---|---|
| Trigger sources (v1) | Earnings catalysts + research-run completions | Both have clean event timestamps already. Health-flips need extra schema; deferred. |
| Consumer scope | Status-board rows (most recent non-archived run per ticker) | Single source of truth; matches the existing fleet-management mental model. |
| Edge direction | Both — outbound and inbound | Inbound mentions are the payoff that fan-out infra already produces (e.g., MSFT prompts already see inbound `$ORCL — competitor`). Same payoff applies here. |
| Relationship-type filter | All types, ranked by signal strength | Engine returns everything; UI decides how to display/filter. |
| Edge sources | `relationships` (customer / supplier / partner / licensor / licensee / distributor / reseller / joint_venture / other) **and** `competitor_landscape` (competitor) | Competitor edges live in a separate table with a JSONB shape. Engine unions both into a single edge view so competitor read-through works without new schema. |
| Persistence | Hybrid — compute on demand, persist only dismissals | Avoids a materialized event log while still supporting "I've handled this." Promotable to full persistence later without schema rework on the dismissals table. |
| UI surface | Inline on `/status` (badge + drawer per row) | Status board is the canonical fleet view; a separate `/read-through` page would split attention. |
| LLM impact summary | Lazy — on-demand button per event | Most events are scannable from the verbatim quote alone; pay Haiku cost only for events the user cares about. |
| Default window | Last 30 days | Matches the lookback most users will actually skim; configurable via query param. |
| Testing | Manual smoke (backend) + lint/Playwright (frontend) | No backend test framework configured per CLAUDE.md. |

## Data model

One new table. No changes to existing schemas.

### New table — `read_through_dismissals`

```python
class ReadThroughDismissal(Base):
    __tablename__ = "read_through_dismissals"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    dismissed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("run_id", "event_key", name="uq_read_through_dismissals_run_event"),
        Index("ix_read_through_dismissals_run_id", "run_id"),
    )
```

`event_key` is a deterministic string the engine produces for each peer event:

- Earnings: `earnings:{peer_ticker}:{expected_window_start.isoformat()}` (e.g., `earnings:NVDA:2026-08-15`).
- Run completion: `run_complete:{peer_run_id}` (the UUID of the peer's run).

Deterministic keys mean dismissals survive engine recomputation. If a user dismisses NVDA's 2026-Q3 earnings event from their MSFT thesis row, that dismissal sticks across page reloads, status-board refreshes, and even if the underlying catalyst row is later edited (the `expected_window_start` is the anchor).

### Single Alembic migration

`alembic revision --autogenerate -m "add read_through_dismissals"` then `alembic upgrade head`.

## Backend architecture

Three layers in `backend/app/services/read_through.py` plus an API surface in `backend/app/api/read_through.py`.

### Layer 1 — Peer-event indexer

```python
@dataclass
class PeerEvent:
    event_key: str           # e.g. "earnings:NVDA:2026-08-15"
    peer_ticker: str         # uppercased
    event_type: Literal["earnings", "run_complete"]
    event_date: date         # window_start for earnings, updated_at.date() for runs
    payload: dict            # type-specific extras (catalyst description, run thesis blurb)


async def compute_peer_events(
    db: AsyncSession,
    since: datetime,
    until: datetime,
) -> list[PeerEvent]:
    """Build the unified peer-event stream from catalysts + completed runs."""
```

Two queries:

- `SELECT ticker, expected_window_start, description, type FROM catalysts WHERE expected_window_start BETWEEN since.date() AND until.date()` — earnings filter applied via `WHERE type = 'earnings'`. Catalyst description goes into `payload["description"]`.
- `SELECT id, ticker, theme_id, state->>'thesis_summary' FROM research_runs WHERE status = 'completed' AND updated_at BETWEEN since AND until AND archived_at IS NULL`. Note: `research_runs` does not have an explicit `completed_at` column — `updated_at` is the de-facto completion time once `status='completed'` is set, and the row's `updated_at` does not bump again until a new run is started (which creates a separate row). Caveat documented inline in the function docstring.

Return value is union-merged into a single list, sorted by `event_date DESC`.

### Layer 2 — Read-through resolver

```python
@dataclass
class RelationshipLink:
    relationship_type: str            # customer | supplier | competitor | partner | ...
    direction: Literal["outbound", "inbound"]
    verbatim_quote: str | None
    magnitude_pct: float | None


@dataclass
class ReadThroughItem:
    event_key: str
    peer_ticker: str
    event_type: str
    event_date: date
    payload: dict
    links: list[RelationshipLink]    # never empty (rows with zero links are filtered)


async def resolve_read_throughs(
    db: AsyncSession,
    status_run_ids: list[str],
    peer_events: list[PeerEvent],
) -> dict[str, list[ReadThroughItem]]:
    """For each status-board run, return the read-through items that have at
    least one relationship edge to a peer event in the window."""
```

Implementation:

1. Query the tickers for the status-board runs in one shot:
   `SELECT id, ticker FROM research_runs WHERE id = ANY(:run_ids)`.
2. Pull all candidate edges in two batched queries (thesis-tickers and peer-tickers as sets):
   - **`relationships` (non-competitor types)**: `SELECT ticker, resolved_to_ticker, relationship_type, verbatim_quote, magnitude_pct FROM relationships WHERE (ticker = ANY(:thesis_tickers) AND resolved_to_ticker = ANY(:peer_tickers)) OR (ticker = ANY(:peer_tickers) AND resolved_to_ticker = ANY(:thesis_tickers))`. `direction` is `outbound` when `ticker ∈ thesis_tickers` and `inbound` otherwise.
   - **`competitor_landscape` (competitor edges)**: `SELECT ticker, segment_name, competitors FROM competitor_landscape WHERE ticker = ANY(:thesis_tickers) OR ticker = ANY(:peer_tickers)`. The `competitors` JSONB is a list of `{name, resolved_to_ticker, verbatim_quote, magnitude_pct, ...}`. Walk the list and emit one synthetic edge per `(filer_ticker, competitor.resolved_to_ticker)` pair where `resolved_to_ticker` is non-null and the pair matches one of the (thesis, peer) combinations. Direction follows the same rule as above. `relationship_type` is hard-coded to `"competitor"`. `verbatim_quote` and `magnitude_pct` come from the JSONB element.
   - Bucket all edges in Python by `(thesis_run_id, peer_event_key)`.
3. Within a thesis, sort items by signal-strength rank: `customer` / `supplier` / `partner` / `joint_venture` first, then `competitor`, then `licensor` / `licensee` / `distributor` / `reseller`, then `other`. Secondary sort by `event_date DESC`.
4. Left-join `read_through_dismissals` on `(run_id, event_key)`. Filter out dismissed rows.

Empty `links` list ⇒ item is dropped (no relationship = no read-through).

### Layer 3 — API endpoints

In `backend/app/api/read_through.py`, registered under `/api/status/read-throughs`:

#### `GET /api/status/read-throughs`

Query params: `since` (ISO datetime, optional, default `now - 30d`), `until` (ISO, optional, default `now`).

Implementation:

1. Call the existing status-board aggregator to get the active row set (reuse Tier 2.6's `load_status_rows` or equivalent).
2. Call `compute_peer_events(db, since, until)`.
3. Call `resolve_read_throughs(db, [r.run_id for r in rows], events)`.
4. Return `{run_id: [ReadThroughItem, ...]}` JSON-serialized via Pydantic response models.

Response shape:

```json
{
  "<run_id>": [
    {
      "event_key": "earnings:NVDA:2026-08-15",
      "peer_ticker": "NVDA",
      "event_type": "earnings",
      "event_date": "2026-08-15",
      "payload": {"description": "Q2 2026 print", "type": "earnings"},
      "links": [
        {
          "relationship_type": "supplier",
          "direction": "outbound",
          "verbatim_quote": "We rely on NVIDIA accelerators for...",
          "magnitude_pct": null
        }
      ]
    }
  ]
}
```

#### `POST /api/status/read-throughs/dismiss`

Body: `{run_id: str, event_key: str}`. Inserts into `read_through_dismissals` (idempotent on the unique constraint — `ON CONFLICT DO NOTHING`). Returns 204.

#### `POST /api/status/read-throughs/summary`

Body: `{run_id: str, event_key: str}`. Lazy LLM endpoint:

1. Look up the run (fetch ticker + thesis state).
2. Parse `event_key` and look up the source row directly:
   - `earnings:{ticker}:{date}` → `SELECT * FROM catalysts WHERE ticker = :ticker AND expected_window_start = :date LIMIT 1`.
   - `run_complete:{uuid}` → `SELECT * FROM research_runs WHERE id = :uuid`.
   - Unrecognized prefix → 400.
3. Call `get_counterparty_context(thesis_ticker, db)` from `services/relationship_context.py` — already-built helper.
4. Compose a prompt using the existing Haiku model from `graph/llm.py`:

   ```
   System: You are a sell-side analyst evaluating peer-event read-through. Given
   a thesis on TICKER and a peer event on PEER_TICKER, produce one paragraph (≤120 words)
   answering: how does this peer event affect the thesis? Cite the relationship from the
   counterparty context if relevant. Do not invent quantitative claims.
   ```

   ```
   User: Thesis: {thesis_summary}\nPeer event: {event_payload}\nRelationships from
   filings: {counterparty_context_rendered}
   ```

5. Return `{summary: str}`. On Haiku failure return 502 with `{error: str}` (matches existing pipeline-service pattern; no fallback).

No response caching in v1 — repeat clicks regenerate. If this becomes a cost problem, cache by `(run_id, event_key)` with a 24h TTL.

### Service-locator wiring

Routes registered in `backend/app/main.py` next to the existing `status` router:

```python
from backend.app.api import read_through as read_through_routes
app.include_router(read_through_routes.router)
```

## Frontend architecture

All changes in `frontend/`:

- `lib/api.ts` — add `RelationshipLink`, `ReadThroughItem` types and three client methods (`getReadThroughs`, `dismissReadThrough`, `summarizeReadThrough`). Mirror the backend Pydantic shapes exactly.
- `app/status/page.tsx` — extend to fetch read-throughs in parallel with the board. Add a numeric badge to each row showing `read_throughs[run_id]?.length ?? 0` (hide when zero). Click → inline drawer expansion below the row using the same pattern as the kill-criterion toggle row.
- `components/status/ReadThroughDrawer.tsx` (new) — renders a list of `ReadThroughItem`s. Each item:
  - Header: peer ticker chip + event-type icon + event date
  - Subhead: relationship-type badges (`customer`, `supplier`, etc.) with verbatim quote in title-attribute tooltip
  - Footer: "Dismiss" button (calls `dismissReadThrough`, optimistically removes from drawer), "Generate impact summary" button (calls `summarizeReadThrough`, renders returned text inline beneath the item, button switches to "Regenerate" after first call).
- No new top-level page in v1.

### Data flow on `/status`

1. Page mount → existing `GET /api/status/board` populates rows.
2. After initial board paint, `GET /api/status/read-throughs?since={now-30d}` populates badges.
3. User clicks badge → drawer renders from already-fetched payload (no network call).
4. Dismiss → optimistic remove + POST. On 204, decrement badge count. On non-204, revert UI and toast error.
5. Summary → POST → spinner inline → render returned text.

Polling (Tier 2.6 polls the board every 60s) is extended: each poll cycle also re-fetches read-throughs to pick up newly-completed peer runs without a hard refresh.

### Print view

Read-through drawer carries `data-print-hide="true"` so it drops out of PDFs (per the project-wide `@media print` convention in `app/globals.css`).

## Error handling

- Empty status board (zero rows) → engine short-circuits and returns `{}`. UI hides badges naturally.
- Empty event window → returns `{}`. UI hides badges.
- Relationship table empty for a run's ticker → that run gets no items; badge hidden.
- Haiku summary failure → 502 with error body; UI shows inline retry affordance, no fallback.
- Dismissal of an `event_key` that no longer matches a current event → still inserted (idempotent unique constraint). The dismissal will simply never be matched by a future query, which is fine.
- Concurrent dismissal/summary calls → no locking; each is independent.

## Testing

No backend test framework is configured (per CLAUDE.md).

**Backend manual smoke** — script under `backend/scripts/smoke_read_through.py`:

1. Pick a status-board ticker that's known to have at least one relationship row (e.g., MSFT or any ticker in the existing fan-out set).
2. Insert a synthetic catalyst row with `expected_window_start = now() + 5d` for a peer ticker (e.g., NVDA) on that ticker's run.
3. Call `compute_peer_events(db, now() - 30d, now() + 30d)` and assert the synthetic event appears.
4. Call `resolve_read_throughs(db, [run_id], events)` and assert the result has at least one `ReadThroughItem` for that run with non-empty `links`.
5. Insert a dismissal row, re-call `resolve_read_throughs`, assert the item is filtered out.
6. Clean up synthetic rows.

**Frontend** — `npm run lint`, `npm run build`, then Playwright walkthrough on `/status`:

- Page renders without console errors.
- Badge appears on at least one row when synthetic events exist (re-using the smoke script's seed).
- Drawer expands and shows event details.
- Dismiss button removes the item and decrements the badge.
- Summary button surfaces a Haiku response (or a clean error UI on simulated failure).

## Non-goals

- **Health-flip events.** Tier 2.6 status board computes health on demand and does not persist state transitions. Detecting flips requires either a `status_board_snapshots` table written on every aggregator run or frontend-side localStorage diffing — both out of scope for v1. Revisit in a v1.5 follow-up after the read-through engine has been used in practice.
- **News-driven events.** News ingestion is Tier 4 (deferred). The engine is structured so a future `news` event type slots into `compute_peer_events` without architectural change.
- **Email / Slack / push notifications.** Local-only tool. Read-throughs are a pull experience — the user opens `/status`.
- **Historical backfill.** No reconstruction of read-throughs predating deployment. The engine's only access path is the windowed query; "history" is whatever the window covers.
- **Materialized peer-event log.** Compute-on-demand is the v1 store. Only dismissals are persisted. If query performance becomes a problem (likely never at the project's scale of ≤100 active runs), promote to a `peer_events` cache table without changing the dismissal schema.
- **Per-relationship-type filtering.** The engine returns all types ranked by signal strength. UI filtering can be added later if scanning becomes hard, but v1 just trusts the rank.
- **Standalone `/read-through` inbox page.** Out of scope for v1. The schema supports building it later from the same data.

## Future work captured

- **Health-flip events (v1.5)** — add `status_board_snapshots(run_id, snapshotted_at, health_status, kill_criteria_summary)` written by the existing aggregator with a 1h minimum interval. `compute_peer_events` extends with a third event type that reads diffs between consecutive snapshots.
- **News events (Tier 4 follow-up)** — once a news source exists, `compute_peer_events` gains a `news` type. UI badge already supports the `event_type` discriminator.
- **Summary caching** — if Haiku cost on summaries becomes meaningful, add a `read_through_summaries(run_id, event_key, summary, generated_at)` cache table with 24h TTL.
- **Standalone `/read-through` page** — fleet-wide inbox view sorted by recency; alternative cut of the same data, useful for "scan everything" workflows.
- **Folding into question log (Tier 1.2)** — when Tier 1.2 ships, an opt-in "Add this read-through as an open question" affordance becomes natural.

## Open dependencies

- Tier 1.3 catalyst calendar (shipped) — provides the `catalysts` table and `expected_window_start` column.
- Tier 2.6 status board (shipped) — provides the row set the engine resolves against.
- Existing relationships infra (shipped) — `relationships`, `counterparty_aliases`, `services/relationship_context.py`.
- Existing Haiku client in `graph/llm.py` (shipped) — used unchanged for the summary endpoint.

No external API or new SDK required.
