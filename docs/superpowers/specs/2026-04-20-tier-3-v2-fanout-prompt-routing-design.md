# Tier 3 v2 — Fan-out orchestration + relationship prompt routing

**Date:** 2026-04-20
**Status:** Approved — ready for implementation plan
**Scope:** Close the supply-chain loop end-to-end. Populate the `relationships` graph across whole themes on demand, and feed resolved relationships into deep-dive prompts so the LLM cites named counterparties.

## Motivation

The Tier 3 v2 pipeline (ingest → extract → resolve → graph) works per-ticker but only for tickers that have been manually touched on `/filings`. The result: `SupplyChainEcosystem` card is empty for most tickers, and the deep-dive LLM has no visibility into named counterparties even when the data *does* exist. This spec closes both gaps:

1. **Fan-out orchestration** — populate relationships for every ticker in a theme (or one ticker at a time) with a single click.
2. **Prompt routing** — route the resolved relationship list into `business_quality`, `risk_assessment`, and `future_durability` deep-dive prompts as structured anchors (not verbatim re-quotes of filing text the prompt already carries).

A small Item 1A heading-regex fix rides along because it directly affects the source material for risk relationships.

## Architecture overview

Two thin additions on top of existing services — no new tables, no schema changes.

**Backend:**
- `backend/app/services/fanout.py` — new orchestrator. Walks a ticker list; for each ticker calls existing `edgar_sections_ingest.ingest_latest`, `edgar_relationships.extract_for_ticker`, `counterparty_resolver.resolve_for_ticker` in sequence.
- `backend/app/services/relationship_context.py` — new query layer. Returns outbound + inbound counterparty lists for prompt injection.
- `FanoutService` — in-memory status tracker (`dict[fanout_id, FanoutStatus]`), mirroring the `PipelineService` SSE-queue pattern. No persistence across server restarts (personal tool; acceptable trade).
- New `RELATIONSHIP_ROUTING` set in `graph/nodes.py`, parallel to `FILING_EXCERPT_ROUTING`.
- New `{counterparty_context}` slot in the `DEEP_DIVE_USER` prompt template, positioned immediately after `{filing_excerpts}`.

**Frontend:**
- `/filings` page gets a **"Fan out this theme"** button per theme group and a **"Fan out"** button per ticker card. Clicks `POST` the fan-out endpoint, stores `fanout_id`, polls `GET /api/fanouts/{id}` every 3s, renders inline progress (`3/8 tickers · current: $NVDA`).
- Extensions to existing `ThemeFilingsPanel` + `TickerFilingsCard`. No new pages, no new component modules.

**What stays unchanged:**
- The `SupplyChainEcosystem` deep-dive card — already reads from `relationships` + `counterparty_aliases`; it'll just have more data.
- The LangGraph pipeline edges — no new node, just a new data kwarg threaded into existing deep-dive prompts.

## Fan-out service

### Endpoints

```
POST /api/themes/{theme_id}/relationships/fanout?force=false   → 202 { fanout_id }
POST /api/tickers/{ticker}/relationships/fanout?force=false    → 202 { fanout_id }
GET  /api/fanouts/{fanout_id}                                   → 200 FanoutStatus
```

`FanoutStatus` shape:

```json
{
  "fanout_id": "fo_abc123",
  "status": "running" | "completed" | "failed",
  "scope": { "kind": "theme", "theme_id": 7 } | { "kind": "ticker", "ticker": "ORCL" },
  "total_tickers": 12,
  "completed_tickers": 5,
  "current_ticker": "NVDA",
  "current_stage": "ingest" | "extract" | "resolve" | null,
  "errors": [{ "ticker": "XYZ", "stage": "ingest", "message": "EDGAR 404" }],
  "started_at": "2026-04-20T12:34:56Z",
  "finished_at": null
}
```

### Per-ticker flow

Sequential within a ticker, sequential across tickers.

```
1. ingest_latest(ticker)
     - Always runs. EDGAR call is cheap; picks up new filings since last ingest.
     - filings idempotent on accession_number (existing).
     - filing_sections idempotent on (filing_id, section_key) (existing).
2. extract_for_ticker(ticker, force=force)
     - Skips sections with relationships_extracted_at IS NOT NULL (existing tombstone).
     - force=true clears tombstones + deletes relationship rows for the ticker first.
3. resolve_for_ticker(ticker, force=force)
     - Skips rows where resolved_to_cik IS NOT NULL (existing).
     - force=true re-runs matcher on all rows; may update resolutions.
```

### Concurrency

Serial across tickers. Rationale: EDGAR rate limit (10 req/s) is per-process and easy to violate with parallelism; Haiku cost is proportional to work regardless of parallelism; counterparty resolution loads `company_tickers.json` in memory and is parallel-safe but gains nothing. A 15-ticker theme runs in ~3-5 minutes serial, acceptable for "click and come back."

### Error handling

Per-ticker `try/except`. On error, append `{ticker, stage, message}` to `status.errors[]` and continue. Final `status = "completed"` even with partial errors; `status = "failed"` only if the orchestrator itself crashes. Frontend surfaces the error count inline.

### Sessions

Fresh `async_session()` per ticker (not per stage), matching the pattern in `PipelineService._fetch_filing_sections`. Avoids holding a transaction open for minutes.

### Force flag

- `force=false` (default): every stage skips already-done work.
- `force=true`: `extract` re-runs all sections, `resolve` re-runs all rows. Does NOT re-ingest filings (accession_number is the natural key; re-ingest is an idempotent no-op anyway).

Curl only. No UI surface — it's a dev escape hatch for "my prompts changed, wipe and re-run."

### Non-feature: no cancel endpoint

If a fan-out is running and you regret it, restart the server. Personal tool; YAGNI.

## Relationship prompt routing

### Query layer — `services/relationship_context.py`

```python
@dataclass
class CounterpartyEntry:
    name: str
    resolved_ticker: str | None
    relationship_type: str
    magnitude_pct: float | None
    unnamed: bool

@dataclass
class CounterpartyContext:
    outbound: dict[str, list[CounterpartyEntry]]  # grouped by type
    inbound: dict[str, list[CounterpartyEntry]]   # others who named me, by what they called me
    has_data: bool
```

`get_counterparty_context(ticker, session) -> CounterpartyContext`:

- **Outbound:** `relationships` rows whose underlying filing belongs to `ticker`.
- **Inbound:** `relationships` rows where `resolved_to_ticker = ticker` (cross-refs everyone who named us).
- Both grouped server-side by `relationship_type`.
- `has_data = True` iff either outbound or inbound has at least one entry.

### Pipeline wiring

`PipelineService._fetch_counterparty_context(ticker)` — mirror of `_fetch_filing_sections`. Opens dedicated `async_session`, returns `CounterpartyContext`, threaded into `node_deep_dive` as a kwarg alongside filing sections + edgar_facts.

### Routing + template

```python
# graph/nodes.py
RELATIONSHIP_ROUTING: set[str] = {
    "business_quality",
    "risk_assessment",
    "future_durability",
}
```

`_build_counterparty_context(category, context) -> str`:
- Returns `""` if `category not in RELATIONSHIP_ROUTING` or `not context.has_data`.
- Otherwise renders the payload below (grouped by type; `$TICKER` notation for resolved rows; no verbatim quotes).
- Outbound renders first, then inbound under `MENTIONED BY OTHERS`.
- Empty sub-buckets are omitted. If both outbound and inbound are empty, the slot fills with `""` — header never appears.

New slot `{counterparty_context}` in `DEEP_DIVE_USER`, positioned immediately after `{filing_excerpts}`.

### Exact slot wording

```
RESOLVED COUNTERPARTIES
(pre-extracted from the filing excerpts above; use these as anchors when
referring to named customers, suppliers, partners, or competitors.
Do NOT re-quote verbatim text from the filings for these entities — cite
them by name. Resolved tickers in $ notation indicate companies tracked
elsewhere in this research platform.)

Outbound — {ticker}'s disclosed relationships:
  Customers:
    - Microsoft Corp ($MSFT) — customer
    - [unnamed] — customer, 22.0% of FY2025 revenue
  Partners / JVs:
    - Ampere Computing — joint_venture, 29.0% stake
  Competitors:
    - Amazon Web Services ($AMZN)
    - Google Cloud ($GOOGL)

Mentioned by others — who named {ticker} in their own filings:
  As a supplier (2 mentions):
    - $FOO — supplier
    - $BAR — supplier
```

### Budget

The relationship list is tiny — typical <1K chars. No truncation needed for normal cases. Cap at 20 entries per type-bucket, preferring entries with `magnitude_pct` populated, then by `len(verbatim_quote)` as a disclosure-salience proxy. Tunable later.

## Item 1A heading regex fix

`backend/app/services/edgar_html.py`. The `\bITEM 1A RISK FACTORS\b` pattern misses mid-word `\n` splits (e.g., ORCL 10-K renders `R\nisk` at an XBRL/markup boundary). Mirror the `O\s*F` tolerance already used in MD&A patterns:

- `RISK` → `R\s*I\s*S\s*K`
- `FACTORS` → `F\s*A\s*C\s*T\s*O\s*R\s*S`

Phase 0 of the plan. After the fix, re-ingest any ORCL-like 10-K with `POST /api/filings/ingest/{ticker}` as validation.

## Validation gates

1. **Phase 0 (regex).** Re-ingest ORCL 10-K. Before = Item 1A is ~2KB of cross-references. After = multi-KB real risk factor text starting with a known sentence. If that transition doesn't happen, the regex is wrong.
2. **Phase 1 (fan-out).** Trigger theme fan-out on one theme with 5-8 tickers. Poll the status endpoint through completion. Spot-check 2 tickers: `filings` has latest accessions, `relationships` has rows, `counterparty_aliases` shows auto-resolutions for obvious names (MSFT, AMZN), errors array empty or one plausible miss.
3. **Phase 2 (prompt routing).** Re-run deep-dive on ORCL. Compare Business Quality / Risk Assessment / Future Durability outputs before vs. after. Expect: named counterparties cited by name with `$TICKER` notation; no re-quoted verbatim text from Item 1/1A for those entities; inbound mentions appearing in at least one category. If the LLM keeps re-quoting despite the "do not re-quote" instruction, iterate on slot wording rather than redesigning.

## Sequencing

One PR, one feature branch, three phases:

- **Phase 0** — Item 1A regex fix + re-ingest validation (~30 min).
- **Phase 1** — `FanoutService` + 3 endpoints + frontend button & progress UI (~half day).
- **Phase 2** — `relationship_context.py` + `RELATIONSHIP_ROUTING` + prompt template + `PipelineService` wiring (~half day).

Phases 1 and 2 ship together so Phase 2's validation gate has data to exercise the prompt routing.

## Explicit non-goals

- No cancel endpoint.
- No fan-out persistence across server restarts.
- No `force` toggle in the UI — curl only.
- No new migration, no schema changes.
- No changes to existing extraction, resolution, or graph logic — only new orchestration + query layer on top.
- No changes to the other 6 deep-dive categories' prompts.
- No parallel cross-ticker fan-out.
- No automated / scheduled fan-out. On-demand only.

## Files touched

**New:**
- `backend/app/services/fanout.py`
- `backend/app/services/relationship_context.py`
- `backend/app/api/fanouts.py` (or added to existing relationships router — finalize during implementation)

**Edited:**
- `backend/app/services/edgar_html.py` (Item 1A regex)
- `backend/app/graph/nodes.py` (`RELATIONSHIP_ROUTING`, `_build_counterparty_context`, prompt template, kwarg wiring)
- `backend/app/services/pipeline.py` (`_fetch_counterparty_context`, thread kwarg into deep-dive)
- `backend/app/main.py` (mount new router if standalone)
- `frontend/lib/api.ts` (new fan-out types + endpoints)
- `frontend/components/filings/ThemeFilingsPanel.tsx` (theme-level button + progress)
- `frontend/components/filings/TickerFilingsCard.tsx` (ticker-level button + progress)
