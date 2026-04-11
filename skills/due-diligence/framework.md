---
name: Investment Due Diligence Framework
description: Master orchestration for equity due diligence — 6 phases with decision gates
type: framework
---

## Purpose

Structured framework for evaluating public equities across 11 analytical dimensions. Designed for both human analysts (use as a phase checklist) and AI agents (follow end-to-end as executable instructions).

This framework enforces analytical discipline through sequential phases and decision gates. Each gate prevents premature conviction — you cannot build a thesis before doing the work, and you cannot size a position before stress-testing the thesis.

## Phases

### Phase 1: Screening (30 min)

Quick-kill filter. Determine if the company warrants deeper analysis.

**Skills invoked:**
- `01-business-quality/moat-analysis` — surface-level pass only. Can you identify the moat in one sentence?
- `02-financial-health/valuation-multiples` — P/E, EV/EBITDA vs. sector. Obviously cheap or expensive?
- `02-financial-health/profitability-analysis` — margins trending up or down? ROIC vs. WACC?
- `05-technical-market-structure/trend-momentum` — with or against the trend?

**Gate:** Score each dimension PASS / NEUTRAL / FAIL.

| Result | Action |
|--------|--------|
| 3+ PASS, 0 FAIL | Proceed to Phase 2 |
| Mixed / 1 FAIL | Park on watchlist, revisit on catalyst |
| 2+ FAIL | Skip — document why for future reference |

### Phase 2: Data Validation (15-20 min)

Verify all quantitative inputs trace to authoritative sources before deep analysis.

**Source Tier System:**

| Tier | Label | Sources | Usage |
|------|-------|---------|-------|
| 1 | Trusted | SEC EDGAR (10-K, 10-Q, 8-K, DEF 14A), company IR (earnings releases, guidance, presentations), licensed data providers (FMP, Bloomberg, FactSet, S&P Capital IQ), FRED (macro), CBOE/exchange data (options, volume) | All quantitative analysis |
| 2 | Conditional | News outlets (Reuters, Bloomberg, WSJ), social media (Reddit, StockTwits, X), analyst reports | Qualitative signal only — never for raw financial metrics |

**Validation Rules:**
1. Every financial metric (revenue, EPS, margins, ratios) must trace to SEC filings or official company reports
2. Price/volume data must come from exchange feeds or licensed aggregators
3. Macro data must come from official government sources (BLS, BEA, Fed)
4. If a claim cites a number, the source must be identified and tier-rated
5. Social/news sources can inform *what* to investigate, never *what is true*

**Gate:** Any metric that cannot be traced to a Tier 1 source gets flagged as "unverified" and excluded from quantitative models. Qualitative insights from Tier 2 sources are tagged as "hypothesis — requires verification."

### Phase 3: Deep Dive (2-3 hrs)

Full analytical sweep across all 9 analytical categories (01-09). Categories run in parallel — no dependencies between them.

| Category | Skills | Approx. Time |
|----------|--------|-------------|
| 01 — Business Quality | moat-analysis, competitive-positioning, tam-market-sizing, industry-lifecycle | 20 min |
| 02 — Financial Health | valuation-multiples, dcf-analysis, profitability-analysis, balance-sheet-strength, cash-flow-quality | 25 min |
| 03 — Growth & Earnings | revenue-driver-decomposition, earnings-quality, guidance-analysis, analyst-expectations | 20 min |
| 04 — Management & Governance | leadership-assessment, capital-allocation, insider-activity, compensation-alignment | 15 min |
| 05 — Technical & Market Structure | trend-momentum, support-resistance, volume-analysis, options-flow | 15 min |
| 06 — Macro & Regime | rate-environment, inflation-cycle, yield-curve, sector-rotation, regime-classification | 10 min |
| 07 — Sentiment & Narrative | news-sentiment, social-signals, market-narrative, institutional-positioning | 10 min |
| 08 — Risk Assessment | sec-risk-factors, thesis-risk-mapping, concentration-risk, tail-risk-scenarios | 20 min |
| 09 — Future Durability | cash-flow-durability, ai-disruption-vulnerability, revenue-defensibility, technology-adoption-curve | 25 min |

**Gate:** If >3 categories show red flags → flag for risk-weighted review before proceeding to thesis construction.

### Phase 4: Thesis Construction (30 min)

Synthesize findings into an actionable investment thesis.

**Skills invoked:**
- `10-thesis-construction/bull-bear-framing` — explicit bull and bear cases with evidence
- `10-thesis-construction/catalyst-identification` — time-bound value catalysts
- `10-thesis-construction/variant-perception` — where you differ from consensus
- `10-thesis-construction/evidence-grounding` — every claim maps to a Phase 3 finding

**Gate:** Thesis must have ≥3 independently verifiable catalysts. Every quantitative claim must trace to Tier 1 data validated in Phase 2.

### Phase 5: Risk Stress-Test (20 min)

Pressure-test the thesis before committing capital.

**Skills invoked:**
- All `08-risk-assessment` sub-skills
- `09-future-durability/ai-disruption-vulnerability` (mandatory for all positions)
- Run bear case to destruction: argue it as strongly as you can

**Gate:** Risk/reward must exceed 2:1 on probability-weighted basis. If it doesn't, the thesis fails regardless of conviction.

### Phase 6: Position & Monitor

Define execution plan and ongoing monitoring triggers.

**Skills invoked:**
- `11-position-management/entry-exit-strategy`
- `11-position-management/position-sizing`
- `11-position-management/stop-loss-invalidation`
- `11-position-management/monitoring-inflections`

Define inflection triggers for thesis revision. Set monitoring cadence (earnings cycle, SEC filing cycle, macro shifts).

## Sequencing Rules

- Phases are sequential: 1 → 2 → 3 → 4 → 5 → 6
- Within Phase 3, categories run in parallel — no dependencies between them
- Phase 4 requires Phase 3 outputs as input
- Phase 5 can loop back to Phase 3 for deeper investigation on specific categories
- Phase 6 is only reached after Phase 5 clearance

## Scoring

Each category produces a composite score (0-100). These roll up into an Overall Conviction Score. See `scoring-methodology.md` for the full weighting math.

Thesis status uses a traffic-light system (ON TRACK / DRIFTING / BROKEN) rather than a numeric score. See `scoring-methodology.md` for details.

## Output

- Phase 1: GO / WATCHLIST / PASS decision with one-paragraph reasoning
- Phase 2: Data quality report with source tier for each metric
- Phase 3: Nine category reports with composite scores
- Phase 4: Investment thesis with bull/bear/base cases and probability weights
- Phase 5: Risk register with severity, likelihood, and monitoring triggers
- Phase 6: Position plan with entry zones, sizing, stops, and review cadence
- Overall: Conviction Score (0-100) and thesis status (traffic light)
