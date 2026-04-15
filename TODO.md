# TODO

Cross-session task tracker. Context for each item is in `docs/superpowers/specs/2026-04-14-data-gaps-analysis.md` unless noted otherwise.

## In progress

- **Tier 3 v2 — Phase A: filing section extraction**
  - New table `filing_sections(filing_id fk, section_key, heading, text, char_count, extracted_at)`. Unique on `(filing_id, section_key)`.
  - `EdgarClient.get_filing_index(accession)` + `fetch_document(url)`.
  - `services/edgar_html.py` — BS4 extractor for `item_1_business`, `item_1a_risk_factors`, `item_7_mda`, `def14a_governance`. Strips inline XBRL, preserves tagged values.
  - Route excerpts into prompts via a new `{filing_excerpts}` slot. Budget ~4–5K chars per section. Feed into Business Quality, Risk Assessment, Growth & Earnings, Management & Governance.

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

- Tier 1: key-case bug in data_gaps, silent-failure detection, technical/sentiment prompt routing
- Tier 3 v1: EDGAR XBRL ingest — `filings` + `xbrl_facts` tables, whitelist of RPO / debt-maturity / concentration / credit concepts, ticker → CIK → companyfacts → persist
- EDGAR UI surfacing: report API + SSE carry `edgar_facts`; new `DebtMaturityLadder` + `RPOTrend` Recharts components
- SEC citation surfacing: `SEC EDGAR · XBRL filings` appears in Library citations panel
- Chart formatting: shared `formatUSD` (`$X.XXB` / `$X.XM` / `$XK` / `$X,XXX`) applied across all dollar charts; findings/evidence stacked vertically
- Tier 2: FMP analyst grades + grades-historical + grades-consensus + price-target-consensus + ratings-snapshot + insider-trading — routed into `_fmt_fundamentals`
- Prefill-error purge: stale `"does not support assistant message prefill"` CategoryError entries filtered out of aggregation (state JSONB untouched)
- Transaction-collision bug in deep-dive: intra-phase SQL now uses dedicated sessions so `async with db.begin()` persist block stays clean
