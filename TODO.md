# TODO

Cross-session task tracker. Context for each item is in `docs/superpowers/specs/2026-04-14-data-gaps-analysis.md` unless noted otherwise.

## In progress

- **Tier 3 v2 — follow-ups**
  - Fan-out orchestration — run extract + resolve across every ticker in a theme's seed list / discovery universe, respecting per-call idempotency.
  - Deep-dive prompt routing — feed resolved relationships into Business Quality / Risk Assessment prompts so the LLM can reference supply-chain context.

## Backlog / polish

- **Item 1A regex misses mid-word `\n` splits** — ORCL 10-K has "Risk" rendered as "R\nisk" because of an XBRL/markup boundary inside the word, so `\bITEM 1A RISK FACTORS\b` doesn't match the real heading and the algorithm falls back to cross-references. Add `R\s*I\s*S\s*K` / `F\s*A\s*C\s*T\s*O\s*R\s*S` tolerance like we did for `O\s*F` in MD&A patterns.

## Next up (sequenced)

- **Tier 3 v2 — Phase B: relationship extraction (inline)**
  - New table `relationships` — see spec for full schema. Unique on `(filing_id, section_key, counterparty_name, relationship_type)`.
  - One Haiku call per section with structured output — counterparty_name, relationship_type, magnitude_pct, unnamed flag, verbatim_quote, source_section.
  - Runs inline during deep-dive (confirmed with user 2026-04-14). Cached by `(accession_number, section_key)` — re-runs only when new filing ingested.
  - Fan-out: every ticker surfaced in quick_screen `competitive_landscape` + every discovery-ranked ticker. Lazy — first time a ticker is touched, extract once; subsequent runs are free.

- **Tier 3 v2 — Phase C: name → ticker resolution**
  - New table `counterparty_aliases(alias_name, canonical_cik, source)` — grows over time.
  - Normalizer (strip "Inc.", "Corporation", etc.) + RapidFuzz `token_set_ratio`.
  - `GET /api/relationships/unresolved` — curation queue sorted by frequency.
  - `POST /api/relationships/alias` — writes resolution + backfills matching rows.

- **Tier 3 v2 — Phase D: graph API + Supply Chain card + bilateral reconciliation**
  - `GET /api/relationships/{ticker}?depth=1&direction=both` — returns `{nodes, edges}` with weights and `confirmed_bilateral` flag.
  - New "Supply Chain" card in deep-dive dashboard — 1-hop named customers + suppliers as a list (not a graph), linked to their own research page if tracked. Separate bucket for "disclosed but unnamed" concentrations.
  - Bilateral reconciliation: when a new row lands, check for a reciprocal row and flip `confirmed_bilateral=true` on both.

## Backlog / v3

- **`signals` table loses velocity history** — currently upsert-overwrite per `(ticker, theme_id, signal_type)`. Daily scheduler replaces yesterday's row. For multi-month velocity charts, either make `signals` append-only or add a sibling `signal_history` table. Not blocking anything today.
- Interactive D3 force-directed full-graph viewer.
- Sankey revenue-flow visualization for supply chain.
- Graph centrality (betweenness, eigenvector) as an input to discovery ranking.
- Cross-theme supply-chain traversal ("from NVDA, 2 hops, filtered to AI-infra theme").
- Relationship extraction from earnings-call transcripts (already ingested) — catches partnership announcements not yet in 10-Ks.
- Customer concentration via XBRL `ConcentrationRiskPercentage1` with dimensional axis handling (v1 skips axes; HTML extraction catches it indirectly via Phase B).
- Options IV / put-call / short interest — new vendor or FMP higher tier.
- Credit ratings — new vendor.
- Institutional ownership (13F) via FMP — current plan returns 404 on ticker-side endpoints; would need daily polling of `institutional-ownership/latest` into a local ticker→holder aggregation.
- Persist FMP citations on state — currently discarded for primary FMP fetches in `node_deep_dive` (only transcript + FRED citations land in state).

## Done (recent)

- Tier 3 v2 Phase D (graph + Supply Chain card + reconciliation): `GET /api/relationships/graph/{ticker}?direction=out|in|both` returns `{root_ticker, nodes[], edges[], summary}` — 1-hop graph with direction, magnitude_pct, bilateral flag. Node identity: resolved via CIK, or normalized name for unresolved counterparties. `tracked` flag annotated from theme seed_tickers. `POST /api/relationships/reconcile` scans all resolved rows for reciprocal pairs (customer↔supplier, partner↔partner, competitor↔competitor, licensor↔licensee, distributor↔reseller, joint_venture↔joint_venture) and flips `confirmed_bilateral=true` on both sides. Frontend: new `SupplyChainEcosystem` component in deep-dive dashboard after Business Quality — shows named counterparties grouped by type, with verbatim quotes, bilateral badges, tracker-link for tracked tickers, and an "Unnamed concentrations" bucket. Verified: ORCL graph returns 6 nodes + 5 edges bucketed by competitor/other/partner
- Tier 3 v2 Phase C (counterparty resolution): new `counterparty_aliases` table + `resolved_to_cik` / `resolved_to_ticker` columns on `relationships`. Normalizer strips corporate suffixes (Inc/Corp/LLC/Holdings/Group/etc) and punctuation. RapidFuzz token_set_ratio against EDGAR's ~10k-entity company_tickers.json — auto-resolves at ≥95, surfaces 80-94 for manual curation. On-demand endpoints `POST /api/relationships/resolve/{ticker}` + `GET /api/relationships/unresolved` + `POST /api/relationships/alias`. Write-through: creating an alias backfills every matching Relationship row. Frontend curation panel on `/filings` shows pending counterparties with top-5 candidates and one-click "Use this" resolution. Verified on ORCL: Microsoft Azure auto-resolved to MSFT, AWS manually resolved to AMZN, AMPR/GOOG/SoftBank correctly surfaced to queue
- Tier 3 v2 Phase B (relationship extraction, on-demand): new `relationships` table + `FilingSection.relationships_extracted_at` tombstone column for idempotency (including zero-relationship sections). Haiku extractor with Pydantic structured output over 15K-char excerpts from `item_1_business`, `item_1a_risk_factors`, `item_7_mda`, `item_2_mda_10q`. On-demand endpoints `POST /api/filings/extract-relationships/{ticker}` (with `?force=true` re-run) + `GET /api/filings/{ticker}/relationships`. Verified end-to-end on ORCL: 5 relationships (Ampere joint-venture 29%, SoftBank partner, AWS/Azure/GCP competitors) with verbatim quotes
- Tier 3 v2 Phase A (heading-trim polish): Item 7 MD&A in 10-Ks now anchors to line-start (MULTILINE) so cross-references like "…see Item 7 Management's Discussion…" no longer out-compete the real heading by body length. Regex tolerates HTML-unwrap "O\s*F" word splits. Added boundary markers for 10-K Items 1B/1C/2/3/4/5/6. Verified on ORCL: Item 7 went from 2K chars of cross-ref fragment → 74K of real MD&A starting with "We begin Management's Discussion…"
- Tier 3 v2 Phase A (prompt routing): `FILING_EXCERPT_ROUTING` map + `_build_filing_excerpt_context` in `node_deep_dive`; filing sections fetched per-ticker in `PipelineService._fetch_filing_sections` and threaded through as kwarg. Section excerpts truncated to 5K chars at prompt-build time. Verified end-to-end on ORCL: Business Quality / Risk Assessment / Growth & Earnings / Management & Governance / Future Durability each receive the relevant 10-K / 10-Q / DEF 14A excerpt; `Financial Health` correctly gets none
- Tier 3 v2 Phase A (frontend): `/filings` page grouped by thesis → ticker → section with modal reader and on-demand "Ingest latest" button
- Tier 3 v2 Phase A (backend): `filing_sections` table + migration; `FilingSection` ORM; `EdgarClient.get_filing_index` + `fetch_document`; BS4 extractor with hybrid boundary-marker regex (capped sections, no bleed); on-demand ingest orchestrator (latest 10-K, 10-Q, DEF 14A per ticker, idempotent); `POST /api/filings/ingest/{ticker}`, `POST /api/filings/ingest/batch`, `GET /api/filings/{ticker}`, `GET /api/filings/{ticker}/{accession}/sections/{section_key}`. Verified end-to-end against AAPL + ORCL
- Tier 1: key-case bug in data_gaps, silent-failure detection, technical/sentiment prompt routing
- Tier 3 v1: EDGAR XBRL ingest — `filings` + `xbrl_facts` tables, whitelist of RPO / debt-maturity / concentration / credit concepts, ticker → CIK → companyfacts → persist
- EDGAR UI surfacing: report API + SSE carry `edgar_facts`; new `DebtMaturityLadder` + `RPOTrend` Recharts components
- SEC citation surfacing: `SEC EDGAR · XBRL filings` appears in Library citations panel
- Chart formatting: shared `formatUSD` (`$X.XXB` / `$X.XM` / `$XK` / `$X,XXX`) applied across all dollar charts; findings/evidence stacked vertically
- Tier 2: FMP analyst grades + grades-historical + grades-consensus + price-target-consensus + ratings-snapshot + insider-trading — routed into `_fmt_fundamentals`
- Prefill-error purge: stale `"does not support assistant message prefill"` CategoryError entries filtered out of aggregation (state JSONB untouched)
- Transaction-collision bug in deep-dive: intra-phase SQL now uses dedicated sessions so `async with db.begin()` persist block stays clean
