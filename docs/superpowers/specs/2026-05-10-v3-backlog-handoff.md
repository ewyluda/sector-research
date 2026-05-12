# v3 backlog — session-pickup handoff

**Date:** 2026-05-10
**Status:** Backlog reference. Each section is independently pick-up-able in a fresh session.
**Source:** `TODO.md` "Backlog / v3" section.

These are not sequenced — pick whichever matches your appetite for that session. Each entry is self-contained: motivation, what to build, where it touches existing code, and the main constraint.

---

## 1. Persist FMP citations on ResearchState

**Effort:** Small. ~½ day if no surprises.

**Motivation.** Library citation panel currently lists transcript + FRED sources but not the primary FMP fundamentals fetch — the citations from `node_deep_dive`'s 10-endpoint asyncio.gather are returned by each FMP method (`tuple[data, Citation]`) and immediately discarded by the unpacking pattern `(income, _), (balance, _), ...` at `backend/app/graph/nodes.py:831`.

**What to build.**
1. Replace each `_` discard with a named citation variable.
2. Dedupe by source URL (FMP rotates the same `/stable/` endpoint per fetch — collapse to one citation per endpoint kind, not 10).
3. Wrap each in `StateCitation.from_citation(cit)` and call `state.add_citation(...)` (mirror the pattern at `nodes.py:906` and `nodes.py:919`).
4. Verify the report API `phases.deep_dive` payload exposes them and the Library citations panel renders them. Frontend type is already `Citation[]` in `frontend/lib/api.ts`.

**Constraint.** FMP citations are URL-bearing but not unique-per-record — the same `/stable/income-statement?symbol=ORCL` URL covers all 8 quarters. Don't emit 80 near-duplicate citations; emit one per (endpoint, ticker, fiscal-window) tuple at most. Prefer one per endpoint per run.

**Out of scope.** Cell-level cite-back from the model page (handled separately by `StateCitation.cell_path` from the model migration). Tier-2 secondary fetch (analyst grades / insider) — same pattern but lower priority.

---

## 2. Cross-theme supply-chain traversal

**Effort:** Medium. ~1–2 days.

**Motivation.** The existing graph endpoint `GET /api/relationships/graph/{ticker}?direction=out|in|both` (in `backend/app/api/filings.py`, surfaced in `frontend/lib/api.ts:372`) is 1-hop only. Real research questions are multi-hop and theme-scoped: "from NVDA, 2 hops, filtered to AI-infra theme" — i.e. find tickers that NVDA touches, then who those tickers touch, but only counterparties that are tracked under a given `Theme.seed_tickers`.

**What to build.**
1. New endpoint `GET /api/relationships/graph/{ticker}?depth=N&theme_id=X&direction=out|in|both`. Cap depth at 2 (no real value beyond that for the personal tool; combinatorial blow-up).
2. Service layer in `backend/app/services/supply_chain.py` (already hosts the 1-hop builder). Add `build_multi_hop_graph(ticker, depth, theme_id, direction)`. Each hop is a SELECT against `relationships` filtered by `resolved_to_ticker IN <theme.seed_tickers>` for theme scoping.
3. Frontend: extend the existing `SupplyChainEcosystem` component (`frontend/components/deep-dive/sections/SupplyChainEcosystem.tsx`) with a hop-depth toggle and a theme-filter dropdown. Or — better, since the deep-dive page is per-ticker — surface this on a new view linked from `/filings`.

**Constraint.** Cycles are real (A → B → A is allowed in the data model). Track visited node-set per traversal. Bilateral pairs (`confirmed_bilateral=true`) should render once, not twice. Unresolved counterparties (no `resolved_to_cik`) cannot be hops — they're terminal name-only nodes.

**Open question.** Should "hop" cross relationship-type boundaries (customer → supplier of that customer)? Default: yes, they're directional traversals; type filtering is orthogonal.

---

## 3. Interactive D3 force-directed full-graph viewer

**Effort:** Medium-large. ~2–3 days plus polish.

**Motivation.** The supply-chain graph is currently rendered as bucketed lists in `SupplyChainEcosystem.tsx`. Useful for one ticker, useless for seeing density patterns across a theme. A force-directed view of `relationships` rows (filtered by theme) makes hubs and brokers visible — which the current UI hides.

**What to build.**
1. New page `/graph` (or `/filings/graph`). Server fetches a graph payload for a chosen `theme_id`: every resolved counterparty pair where at least one side is in `theme.seed_tickers`.
2. Use `d3-force` directly — no heavyweight viz framework. The frontend already pulls Recharts and lightweight-charts; D3 force is a peer in weight.
3. Node = ticker (or unresolved name); edge = relationship row; edge colour = relationship_type; edge width = magnitude_pct when populated; bilateral edges drawn doubled.
4. Click node → pin + open side panel with outbound/inbound buckets (mirror existing `SupplyChainEcosystem` layout).
5. Don't render >300 nodes — degrade to a "too dense, narrow your filters" message. Real datasets shouldn't hit this; surface it as a hard rail.

**Constraint.** Server-side, the existing graph builder in `services/supply_chain.py` returns `{nodes, edges, summary}` for one ticker. A theme-wide builder is new — write it as a separate function rather than overloading the single-ticker one.

**Out of scope for v1.** Editing nodes from the viewer. Persisting layout. Time-axis (showing how the graph evolved). All deferable.

---

## 4. Sankey revenue-flow visualisation for supply chain

**Effort:** Medium. ~1–2 days.

**Motivation.** When `relationships.magnitude_pct` is populated (Phase B narrative extraction sometimes captures "X is 20% of revenue" — e.g. NVDA's hyperscaler concentration), a Sankey diagram makes concentration immediately visible in a way the bucketed list doesn't.

**What to build.**
1. New section in the deep-dive page (or a new tab on `/filings/{ticker}`) — only renders when ≥2 outbound relationships have non-null `magnitude_pct`.
2. Sankey via `d3-sankey` plugin or Recharts has no native; lean toward the d3-sankey route for fidelity.
3. Source-side = the ticker. Target-side = grouped by `relationship_type` then by counterparty. Value = `magnitude_pct`. The "Other" bucket sums to (100 − sum of named).

**Constraint.** Most filings disclose concentration only in aggregate ("two customers each represented >10%") — magnitude_pct is sparse. The Sankey should hide itself when fewer than ~2 entries have it set, rather than render an empty fan. Prior-art: the existing `RPOTrend` component does the same self-hide on stale data.

**Out of scope.** Backwards across time. Only the latest filing snapshot.

---

## 5. Graph centrality as discovery-ranking input

**Effort:** Medium. ~1 day for v1, more if you go deeper.

**Motivation.** Discovery scoring (`services/discovery.py::DiscoveryEngine`) currently weights X velocity 40% / fundamental quality 40% / discovery score 20%. A ticker that sits at the centre of a theme's supply graph (high betweenness) is a structurally interesting hold even when its X buzz is low — but the current ranking can't see it.

**What to build.**
1. Compute betweenness + eigenvector centrality once per theme as a periodic job (or on-demand, gated behind a refresh button). NetworkX is the natural choice; add to `requirements.txt`.
2. Persist as a new column or a new `theme_centrality_scores` table keyed `(theme_id, ticker, computed_at)`.
3. Surface as a new signal in the `signals` table OR as a separate input weight in `DiscoveryEngine._combined_score` — pick one, don't double-route.
4. UI: a small badge on the discovery card ("hub" / "broker" / nothing) plus a column in the discovery list.

**Constraint.** Centrality is meaningful only when the graph has reasonable density. A theme with 5 tickers and 3 relationships gets noisy centrality scores — gate the badge behind a minimum edge count.

**Open question.** Recompute cadence. Probably daily as part of `signal_scheduler`, but the relationships graph is far slower-changing than X velocity, so weekly may be enough.

---

## 6. Options IV / put-call ratio / short interest

**Effort:** Variable, vendor-dependent.

**Motivation.** Risk Assessment and Sentiment & Narrative both ask the LLM to reason about market positioning that isn't visible in fundamentals. Options IV term structure and short interest would give a real signal here.

**What to build / decide first.**
1. **Vendor decision.** FMP's current tier doesn't expose these. Candidates: ORATS (options IV), MarketCetera or finnhub (short interest), Polygon (both at higher tier). Each adds a monthly bill — defer until there's a clear gap a real research run hit.
2. New client(s) under `backend/app/clients/`. Match the `tuple[data, Citation]` convention.
3. New deep-dive routing entries in `deep_dive_routing.py` (likely Risk Assessment + Sentiment & Narrative).

**Constraint.** Personal tool — don't pay for a vendor until a concrete research run benefits. Lower priority than items 1–5.

---

## 7. Credit ratings vendor

**Effort:** Like options — vendor-bound.

**Motivation.** Financial Health currently relies on FMP fundamentals + EDGAR debt-maturity ladder. Real credit ratings (S&P / Moody's / Fitch) would tighten the leverage analysis.

**What to build.** Same shape as options — pick a vendor, write a client, route into Financial Health.

**Constraint.** Same — vendor cost. Most credit-ratings APIs are expensive. Alternative: scrape from rating-agency public press releases (fragile). Defer.

---

## 8. Institutional ownership (13F) via FMP

**Effort:** Medium, with a gotcha.

**Motivation.** 13F holdings would feed Risk Assessment ("crowded long" detection) and Sentiment & Narrative.

**Why this is in v3, not v2.** FMP's ticker-side endpoints for institutional ownership currently return 404 on the active plan — confirmed during a prior investigation. The path that does work is `institutional-ownership/latest` (filer-side, returns whatever 13F was most recently filed).

**What to build.**
1. Daily polling job in `signal_scheduler` that ingests `institutional-ownership/latest` and aggregates locally into a `ticker_holders` table keyed `(ticker, holder_cik, filing_date)`.
2. New service `services/institutional_ownership.py` to expose "top 10 holders for $TICKER" + change-since-prior-quarter.
3. Route into `_fmt_fundamentals` (it's a fundamentals-adjacent fact) so every category sees it once.

**Constraint.** 13F data is quarterly + delayed — by the time it's filed it's at least 45 days stale. Don't oversell its freshness in the prompt. Frame as "as of [filing date]" with explicit citation.

**Alternative path.** Drop into the v3 freezer until FMP exposes the ticker-side endpoint, since the filer-side aggregation is a substantial build.

---

## Picking from this list

Suggested ordering for fastest payoff:

1. **#1 (FMP citations)** — half a day; clear win for the citations panel; near-zero risk.
2. **#2 (cross-theme traversal)** — builds on existing infra; unlocks real research questions.
3. **#5 (centrality)** — pairs with #2.
4. **#3 (D3 viewer)** + **#4 (Sankey)** — visual polish; do these once #2 has produced enough graph data to actually make pretty pictures.
5. **#6, #7, #8** — vendor/cost decisions; defer until a real research need surfaces.

None of these block each other. Pick by appetite, not dependencies.
