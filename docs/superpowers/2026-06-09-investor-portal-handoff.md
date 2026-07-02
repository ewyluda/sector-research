# Investor Portal Transformation — Session Handoff

Written 2026-06-09 at the end of the session that designed the portal roadmap and shipped sub-project 1. Reference this file when starting any of the remaining sub-projects. Workflow used (and expected for the rest): brainstorm → spec (`docs/superpowers/specs/`) → plan (`docs/superpowers/plans/`) → subagent-driven execution with per-task spec + quality reviews.

## Where things stand

**Done: sub-project 1 — Peer comparison.** PR #34 (`feat/peer-comparison`, 20 commits) open against `main` as of this writing — **check whether it merged before starting anything that touches the same files** (`peer_comp.py`, `peer_sets.py`, `api/peers.py`, `workspace_steps.py`, `lib/api.ts`, company TabStrip). Spec: `docs/superpowers/specs/2026-06-09-peer-comparison-design.md`. Plan: `docs/superpowers/plans/2026-06-09-peer-comparison.md`. Full feature summary in TODO.md "Done (recent)" and the new CLAUDE.md "Peer comparison" section.

**Also relevant:** `feat/workspace-robustness-pack` (PR #33) may still be unmerged — it adds `_validate_step_outputs` to the workspace service. It is semantically compatible with the peer-comp schema move (imports resolve through the `workspace_schemas` re-export) but expect textual conflicts in `workspace_steps.py` / TODO.md if both are open.

## Product decisions already made (don't re-litigate)

- **Lightweight trade journal, not live P&L.** User chose manual entry/exit logging linked to theses (enables decision-vs-outcome review on `/performance`). Not research-only, not a full portfolio cockpit.
- **Roadmap sequencing** (each gets its own spec → plan cycle): calendar → Today dashboard → 8-K/Form 4 → quant layer → journal.
- `/compare` deliberately has **no top-nav link** (nav already has 10 entries); entry is the company Peers tab.
- Peer sets: auto-seed cap 8, manual cap 12; `peer_sets` service layer is **commit-free** (callers own the session) — follow that pattern for new services consumed by routes.

## Next up — the remaining sub-projects

### 2. Unified calendar (recommended next)

FMP economic calendar (CPI, FOMC, NFP…) + watchlist earnings + thesis catalysts in one week/month grid. Extends `/catalysts`.

- Build on: `api/catalysts.py` + `services/catalyst_promotion.py` / `catalyst_dates.py` (existing catalyst rows per run), `FMPClient.get_earnings_calendar` (exists), the `/catalysts` page with proximity buckets.
- New: an FMP economic-calendar client method (follow `tuple[data, Citation]` convention; live-verify the /stable/ endpoint + wire fields — see "FMP gotcha" below), a merged-events read model, week/month grid UI with a "my universe only" filter.
- Scope question to settle in brainstorming: what defines "my universe" — theme seeds ∪ active theses, or does this force the watchlist primitive early?
- Link each upcoming earnings row to the existing `EarningsDrawer` / workspace kick-off.

### 3. "Today" dashboard (new home page)

Aggregates: today's calendar slice (from #2), status-board health *flips* (not state — needs snapshot/transition data the board doesn't persist yet; see the deferred `status_board_snapshots` idea in TODO history), new filings/8-Ks on covered names (from #4), triggered/near kill criteria, transcript deltas on names that just reported, open questions, stale theses due for workspace refresh. Mostly reads over existing tables + one page; sequence after #2 (and ideally #4) so it has events to show.

### 4. 8-K + Form 4 monitoring (already specced loosely in TODO.md "Backlog / v3")

Daily 8-K scan via EDGAR submissions feed → Haiku event classifier (guidance/personnel/M&A + materiality) → new `material_events` table → status-board badge. Form 4 via EDGAR owners feed → `insider_transactions` table → discovery-ranking signal. TODO.md estimates ~3-4 days. Build on: `EdgarClient`, `FanoutService`, alias resolver, APScheduler cron pattern in `main.py::lifespan` (two existing jobs: signals 2 AM, outcomes 3 AM UTC).

### 5. Deterministic quant layer for deep dives

Piotroski F, Altman Z, Beneish M, accruals ratio, FCF conversion, SBC dilution, margin-trend slopes — computed in pure Python from the 8 quarters already fetched in `node_deep_dive`, injected into prompts as established facts ("don't recompute, interpret"), plus a "Quant fingerprint" card on the deep-dive page. Pattern to follow: `model_balancing.py` (pure synchronous functions over fetched data).

**Do the wire-name fix first (see below) — this sub-project consumes the same FMP payloads.**

### 6. Lightweight trade journal

Manual entries/exits linked to theses; `/performance` gains realized-decision vs verdict-outcome comparison. Smallest of the five; design fresh when reached.

## Known follow-ups / quick fixes (independent of roadmap)

1. **Deep-dive valuation ratios likely silently None (pre-existing bug, high value, ~quick).** `graph/nodes.py:145-163, 678-688` and `CuratedFinancials` read P/E, EV/EBITDA, P/B, P/FCF, P/S, PEG (+ `roeTTM`/`roicTTM`) from `key-metrics-ttm` wire names the live FMP /stable/ API no longer serves. Fix the same way `peer_comp._fetch_one` was fixed: ratios-ttm-first fallback chains via a `_first`-style helper (or import it). Verify against a live NVDA payload before and after. Recorded in TODO.md and PR #34 description.
2. **`DifferentiationCard.tsx` still renders its own bespoke 10-column table.** Now that margins populate, its plain `fmt()` shows raw ratios ("0.46" not "46%"). Migrate it to the shared `components/peers/PeerCompTable`.
3. **`fcf_margin` is a permanently empty column** (FMP serves no FCF-margin field; verified 2026-06-09). Either derive it deterministically (FCF/sales = p_s ÷ p_fcf when both present) or drop the column.
4. Minor: stale-comp race on the Peers tab (mount fetch can overwrite a fresher post-edit fetch — tiny window; a fetch-sequence counter closes it).

## FMP gotcha (cost a review cycle this session — don't repeat)

The /stable/ API's field placement does not match older docs or this codebase's assumptions. Before mapping any new endpoint, dump live keys first:

```bash
backend/venv/bin/python -c "import asyncio; from backend.app.clients.fmp import FMPClient; print(sorted(asyncio.run(FMPClient().get_ratios_ttm('NVDA'))[0].keys()))"
```

Known truths (live-verified 2026-06-09): valuation multiples on `ratios-ttm` (`priceToEarningsRatioTTM`, `enterpriseValueMultipleTTM`, `priceToFreeCashFlowRatioTTM`, `priceToEarningsGrowthRatioTTM`…); returns on `key-metrics-ttm` (`returnOnEquityTTM`, `returnOnInvestedCapitalTTM`, `returnOnAssetsTTM` — true ROA, NOT `returnOnTangibleAssetsTTM`); margins on `ratios-ttm`; market cap on `profile.marketCap`.

## Session mechanics worth knowing

- Backend tests: `backend/venv/bin/python -m unittest backend.tests.<module> -v` from repo root. Full suite needs explicit modules (`backend/tests` has no `__init__.py`, so `discover -t .` fails): `backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')` — 323 tests green as of this handoff.
- Dev API URL must be `http://127.0.0.1:8000` (Docker steals IPv6 `localhost:8000` on this machine).
- Alembic head as of this branch: `d9659a472017` (peer_sets).
- Memory file `project_investor_portal_roadmap.md` (auto-memory) mirrors this roadmap's status — update it when a sub-project ships.
- CLAUDE.md's top "Seven top-level workspaces" list is stale (predates `/company`, `/performance`, `/prospectus`, `/compare`) — worth a hygiene pass someday; the architecture sections below it are current.
