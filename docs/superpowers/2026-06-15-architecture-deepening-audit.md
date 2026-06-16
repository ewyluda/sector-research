# Architecture deepening audit — 2026-06-15

> Cross-session reference. Produced via the `improve-codebase-architecture` skill: read
> `CONTEXT.md` + `docs/adr/*`, then fanned out four read-only `Explore` agents across the four
> major subsystems (graph / services / api+models+clients / frontend) hunting for the same
> friction signals. Findings that surfaced in **multiple independent audits** are flagged —
> those are the strongest signals.

The lens is **depth**, not bug-hunting: turn shallow modules (interface nearly as complex as
implementation) into deep ones (a lot of behaviour behind a small interface), create real
**seams** where there's leaky copy-paste, and improve testability + locality.

- **Deletion test** — imagine deleting the module. If complexity *concentrates back* across N
  callers, it earns its keep. If it just *moves*, it was shallow.
- **One adapter = hypothetical seam. Two+ adapters = real seam.**

## Settled decisions — do NOT re-litigate

These are recorded in `docs/adr/` and were excluded from the candidate list:

- **ADR-0001** — workspace runs have no human interrupts (no LangGraph StateGraph / checkpoints
  for the workspace loop). Don't suggest re-adding interrupts.
- **ADR-0002** — Step 2 (Research) runs without new source text in v1; the real fix
  (Step 1 persists section text into `filing_sections`, Step 2 queries rows newer than the prior
  run) is already scoped in the ADR. This is a known, documented gap, not a finding.
- **ADR-0003** — `signal_history` is the append-only source of truth; `signals` is a denormalized
  read-cache. Don't suggest collapsing them. The `is_stale`-not-replicated asymmetry is deliberate.

---

## Validation pass — 2026-06-16

Codex re-checked the ranked findings against the current codebase. Overall: the audit is
legitimate, especially the **Universe** and **discovery card serializer** opportunities. A few
details were stale or overstated and are called out inline below.

- **Strongly confirmed:** #2 Universe, #3 discovery card serializer, #4 model cell vocabulary.
- **Confirmed with nuance:** #1 SSE fan-out. The duplication is real, but pipeline's no-replay
  behaviour is documented and currently paired with REST hydration, not an obviously accidental bug.
- **Partially confirmed / adjust before implementing:** #5 bounded modifiers and #6 ticker
  normalization. #5 shares a modifier/snapshot shape more than a single identical algorithm; #6's
  file list was stale because `transcripts_delta.py` already uses `TickerPath`.

Priority after validation: **#2 → #3 → #4 / #6**, with #1 as a dedicated streaming-refactor effort.
#5 is worth doing when already touching discovery scoring, but it is less clean than the original
wording implied.

---

## Candidate deepening opportunities (ranked)

### 1. The SSE stream is implemented three times, not once  ⬅ highest leverage
**Cross-validated: services + frontend audits.**

- **Files:** `backend/app/services/pipeline.py`, `backend/app/services/workspace.py`,
  `backend/app/services/prospectus_service.py` (producers);
  `frontend/components/workspace/WorkspaceReport.tsx`,
  `frontend/components/prospectus/ProspectusReport.tsx` (dual-hydrating consumers).
- **Problem:** Three orchestrators each hand-roll SSE fan-out: subscriber queues, `_emit()` with
  `QueueFull` handling, cleanup on disconnect, and terminal-event close logic. They have **drifted**:
  workspace/prospectus maintain per-run replay buffers and replay-then-tail streams, while pipeline
  uses `_streams` and explicitly drops pre-subscription events because `/pipeline/[runId]` also REST-
  hydrates persisted state. Deletion test: delete any one and the queue/replay/terminal-event
  complexity reappears in the next service. A **real seam** (three adapters) with no module sitting
  on it.
- **Solution:** One deep streaming-fan-out module owning subscribe / emit / replay / terminal-close.
  Each service becomes a thin adapter supplying its own event types + terminal predicate. Workspace's
  `_ticker_locks` stays service-specific.
- **Benefits:** Replay/disconnect-cleanup tested **once** through one interface instead of three
  partial copies; the pipeline replay gap closes in one place. High leverage — lots of concurrency
  behaviour behind a small interface.
- **Risk:** Medium — touches three live streaming services. Biggest commit of the set.
- **Validation note:** Real module opportunity, but do not frame pipeline's current no-replay mode as
  a proven production bug without first deciding whether pipeline should adopt replay semantics.

### 2. The Universe is a domain concept with no module — reached by private import
**Cross-validated: services audit + already a `CONTEXT.md` term.**

- **Files:** `backend/app/services/status_board.py::_build_latest_runs_sql` (de-facto source of
  truth), `backend/app/services/calendar_events.py`,
  `backend/app/services/material_events_scheduler.py`.
- **Problem:** `CONTEXT.md` defines **Universe** ("theme `seed_tickers` ∪ active-thesis tickers")
  as first-class, but no module owns it. The calendar and the material-events scan both reach
  *through a private function* (`_build_latest_runs_sql`) in another module to reconstruct it. The
  "active thesis" semantics (`status IN ('completed','watchlist')`, `DISTINCT ON`, latest-by-
  `completed_at`) hide inside a status-board SQL helper two schedulers secretly depend on.
- **Solution:** A `Universe` module with a public interface (resolve the universe, optionally
  per-theme) consumed by both schedulers and the status board. The latest-runs SQL becomes its
  implementation detail.
- **Benefits:** The `CONTEXT.md` term gets a real seam. Change "what counts as an active thesis" in
  one place; both daily surfaces inherit it *by contract*, not via a private import nobody should
  use. Testable directly instead of only through a scheduler run.
- **Risk:** Low — read-path extraction with clear tests. **Recommended first win.**

### 3. The discovery card crosses the wire through a hand-written serializer that drops fields
**Cross-validated: api + services + frontend audits (all three).**

- **Files:** `backend/app/api/discovery.py::_card_to_dict`,
  `backend/app/services/discovery.py::CompanySignalCard`, `frontend/lib/api/themes.ts`.
- **Problem:** `_card_to_dict` manually enumerates ~20 fields, decoupling the wire shape (the JSON
  the frontend sees) from the dataclass by hand. This has **already bitten twice** — the congress
  chip and centrality chip shipped invisible because their keys were missing. A regression test
  (`test_discovery_card_serialization.py`) exists, but the seam still leaks by default.
- **Solution:** Make the **discovery card** a deep serializing module — its dict form derived from
  the dataclass (single `to_dict`, or a Pydantic shape) so a new field reaches the wire unless you
  *opt it out*, inverting today's "silently dropped unless you opt in."
- **Benefits:** Locality — the wire shape lives with the card, not in a router. Eliminates a whole
  recurring class of "shipped but invisible" bugs; the test becomes redundant rather than a tripwire.
- **Risk:** Low. **Recommended first win.**

### 4. The model's cell vocabulary is duplicated across the backend↔frontend wire as plain arrays
**Cross-validated: frontend audit + flagged in `TODO.md` done-log as "separate friction, out of scope."**

- **Files:** `frontend/components/model/DriverPanel.tsx` (`GROUPS`),
  `frontend/components/model/ForecastGrid.tsx` (`PNL_LINES`/`BS_LINES`/`CF_LINES`) vs backend
  `backend/app/models/model_state.py` (`DRIVER_KEYS`, `LINE_ITEMS_*`).
- **Problem:** ~18 driver keys and ~50 line items are hardcoded as verbatim string arrays on the
  frontend, mirroring the canonical backend registries. The backend asserts its glosses against
  `DRIVER_KEYS` (`graph/model_baseline_node.py:60`) — no parallel guard exists on the frontend. A
  renamed/added driver silently produces an empty column until a `PUT /draft` 422s at runtime.
- **Solution:** One source of truth for the cell vocabulary that both `frontend/lib/cellPath.ts` and
  the model grid read — an exported/generated registry, or one shared frontend constant with a
  parity check.
- **Benefits:** Kills a silent drift surface; the grid can no longer disagree with the model state
  shape.
- **Risk:** Low–medium. This is **consolidation**, not a new deep module — lower leverage than 1–3
  but a known, named friction.

### 5. Three bounded-modifier signals, one shared shape, copy-pasted
**Cross-validated: services audit (two findings).**

- **Files:** `backend/app/services/insider_signal.py`,
  `backend/app/services/congress_signal.py`, `backend/app/services/graph_centrality.py`, applied in
  `backend/app/services/discovery.py` (`_apply_cached_modifier`, `apply_*_modifier`).
- **Problem:** Insider and congress computation share the same skeleton (90-day window, cluster =
  ≥2 distinct actors within 30d, net value, buy/sell counts, then thresholds), but are not literally
  one algorithm: insider net value is `shares * price`, while congress net value is disclosed
  `amount_mid`. Their modifier thresholds differ (+5/+2/−3 vs +3/+1/−2). Discovery applies insider,
  congress, and centrality through near-identical bounded-cache calls. Per `CONTEXT.md`, the
  `InsiderSnapshot.is_stale` overloading (true for fresh-but-zero-modifier too) is **deliberate** —
  any consolidation must preserve it.
- **Solution:** A **bounded signal modifier** module capturing the shared shape (aggregate →
  modifier → clamped [0,100] score → snapshot with documented `is_stale` semantics), with per-signal
  thresholds as explicit configuration.
- **Benefits:** Intent ("congress half-weighted because disclosures lag ≤45 days") becomes a named
  parameter, not a comment next to duplicated code. A fourth signal becomes config, not copy-paste.
- **Risk:** Medium — touches the discovery scoring path; must preserve `is_stale` semantics and the
  `test_discovery_*` pins.
- **Validation note:** Keep this as a consolidation pass, not a first-win deep module. Centrality
  shares the bounded-modifier application shape, not the insider/congress aggregate algorithm.

### 6. Ticker normalization leaks past the `TickerPath` seam
**Cross-validated: api audit (two findings) + services audit.**

- **Files:** `backend/app/api/company.py` (6 handlers), `backend/app/api/journal.py` (reinvents
  `_normalized_or_400`), `backend/app/api/discovery.py` signal-history route, and theme ticker
  mutation routes. Seam is `backend/app/models/ticker.py::TickerPath`.
- **Problem:** `TickerPath` exists and 30 routes use it, but 7 routes take raw `ticker: str` and
  re-normalize in the service layer, and `journal.py` reinvents the dependency locally. The seam
  exists but isn't the only door; the "tickers are uppercase at the boundary" invariant is enforced
  in N places.
- **Solution:** Make `TickerPath` the single entry; retire the local reinvention; drop the redundant
  service-layer `.upper()` where the boundary already guarantees it.
- **Benefits:** One validation seam instead of a convention; removes a silent wrong-lookup footgun.
- **Risk:** Low. Tidying an existing seam, not creating one — lower architectural value than 1–3 but
  cheap.
- **Validation note:** The original file list was stale: `backend/app/api/transcripts_delta.py`
  already uses `TickerPath`. Also, `backend/app/models/ticker.py` explicitly allows defensive
  service-layer `.upper()` for internal callers, so remove only redundant normalization behind a
  `TickerPath`-guarded route.

---

## Noted but not leading (higher risk / lower leverage)

- **`_run_one_category` takes 14 positional context strings** (graph audit) —
  `backend/app/graph/nodes.py` (~lines 209–245). Implicit ordering contract: the `DeepDiveContext`
  must be built *after* the FRED block mutates `state.curated_financials`. Real friction, but it
  sits on the central LangGraph node (riskier), and `graph/deep_dive_context.py` already did most of
  the deepening. Candidate: pass a single `contexts: dict[str,str]` instead of 14 args.
- **`ResearchState.to_dict` / `from_dict`** (graph audit) — `backend/app/graph/state.py`. Permissive
  hand-rolled round-trip (`from_dict` filters to known fields; extra keys drop, missing keys default)
  with schema-drift risk on every new state field. Highest blast radius, lowest "anything broken
  today." Treat as a **watch item**, not a volunteered refactor.

## Smaller duplications observed (low priority)

- **`_first` vs `_first_metric`** — same fallback-key helper in
  `backend/app/services/peer_comp.py` and `backend/app/graph/formatters.py`, kept separate to avoid
  a graph→service import. Candidate: a neutral `utils/` home.
- **Four visibility-gated pollers** in `frontend/app/status/page.tsx` (~130 lines, 60s interval +
  throttle + cancellation × 4). Candidate: a `useVisibilityGatedPoller()` hook.
- **`unwrap_gather_result` vs `unwrap_gather_citation`** in
  `backend/app/graph/deep_dive_helpers.py` — near-identical tuple-or-default extraction.
- **FMPClient boilerplate** — `backend/app/clients/fmp.py` (~30 methods, ~70% params-build +
  `_request` + `_make_citation` ceremony). Deep-client opportunity but large surface; only worth it
  if adding endpoints becomes frequent.
- **Route-ordering landmines** — documented `/compare` before `/{ticker}` (peers),
  `/relationships/dismissed` before `/{param}` (filings), `/catalysts/calendar` before
  `/{catalyst_id}` (catalysts). Test-enforced, not structural. Low value to "fix."
- **FRED citation contract** — `clients/fred.py::get_all_macro` returns `list[Citation]` while every
  FMP method returns a single `Citation`; the one violation of the `tuple[data, Citation]` convention.

---

## Recommendation

Cleanest **deep-module wins with real seams and low blast radius**: **#2 (Universe)** and **#3
(discovery card serializer)** — read-path / boundary changes with obvious tests and no orchestration
risk. **#4 (model cell vocabulary)** is a valid drift-killer but more of a consolidation than a deep
module. **#1 (SSE)** is still the highest *leverage* (three adapters → one) but is the bigger commit
and should first decide whether pipeline should adopt replay semantics.

Suggested order if picking up autonomously: **#2 → #3 → #4 / #6** (all low-risk), then **#1** as a
dedicated effort, then **#5** only when already touching discovery scoring.

Next step per the skill: pick a candidate and drop into a grilling/design conversation before
writing any interface, OR implement one of the low-risk items directly.
