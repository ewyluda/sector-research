---
name: Deep Dive
description: 3-5 hour comprehensive due diligence workflow covering all 9 analytical categories, thesis construction, risk stress-testing, and position planning
type: workflow
estimated_time: 3-5 hours
requires_prior: quick-screen
---

## When to Use

- Quick Screen returned a GO decision
- An existing position needs full re-evaluation (position size change, thesis drift suspected)
- A major corporate event warrants rebuilding the thesis from scratch (merger, spin-off, CEO departure, significant acquisition)
- A thesis has not been formally documented and the position has grown to material size

Do not run a Deep Dive without first completing a Quick Screen. The Quick Screen confirms liquidity, data availability, and basic business quality — assumptions the Deep Dive builds on.

## Process

### Phase 1 — Data Validation (20 min)

Establish a clean data foundation before any analytical work begins. Errors in this phase propagate into every subsequent step.

**Skills used:** `categories/01-business-quality` (orientation), `categories/02-financial-health/balance-sheet-strength`

**Checklist:**
- [ ] Pull latest 10-K and 10-Q from SEC EDGAR. Confirm fiscal year end and most recent reporting period.
- [ ] Verify financials match across sources (FMP, company IR, Bloomberg/FactSet if available) — flag discrepancies > 2%
- [ ] Confirm share count (basic vs. diluted; check for convertible securities, warrants, options outstanding)
- [ ] Review most recent proxy for compensation structure and insider ownership
- [ ] Confirm any restatements, auditor changes, or going-concern language in the past 3 years
- [ ] Document all data source tiers used (Tier 1 = 10-K/10-Q/8-K; Tier 2 = third-party verified; Tier 3 = management guidance only)
- [ ] Note any pending SEC investigations, material litigation, or covenant violations

**Output of this phase:** A one-paragraph data quality statement documenting sources used, discrepancies found, and any flags that require ongoing tracking.

---

### Phase 2 — Parallel Deep Dive Across 9 Analytical Categories (160 min total)

Run each category in sequence or assign to parallel tracks. Each category has a time budget — stay within it. The goal is sufficient depth for thesis construction, not exhaustive coverage of every sub-skill.

| # | Category | Sub-Skills to Run | Time Budget |
|---|----------|-------------------|-------------|
| BQ | Business Quality | `moat-analysis`, `competitive-positioning`, `industry-lifecycle` (run `tam-market-sizing` only if growth is the thesis) | 20 min |
| FH | Financial Health | `profitability-analysis`, `valuation-multiples`, `cash-flow-quality`, `balance-sheet-strength` (run `dcf-analysis` only if terminal value is contested) | 25 min |
| GE | Growth & Earnings | `revenue-driver-decomposition`, `earnings-quality`, `guidance-analysis`, `analyst-expectations` | 20 min |
| MG | Management & Governance | `leadership-assessment`, `capital-allocation`, `compensation-alignment` (run `insider-activity` if significant insider transactions exist) | 15 min |
| TM | Technical & Market Structure | `trend-momentum`, `support-resistance` (run `volume-analysis` and `options-flow` only if position size is large or options are relevant) | 15 min |
| MR | Macro Regime | `regime-classification`, `rate-environment` (run `inflation-cycle`, `yield-curve`, `sector-rotation` only if macro is a primary thesis driver) | 10 min |
| SN | Sentiment & Narrative | `market-narrative`, `news-sentiment` (run `institutional-positioning` and `social-signals` only if narrative shift is the thesis) | 10 min |
| RA | Risk Assessment | `sec-risk-factors`, `thesis-risk-mapping`, `concentration-risk` (run `tail-risk-scenarios` for all positions > 5% of portfolio) | 20 min |
| FD | Future Durability | `ai-disruption-vulnerability`, `cash-flow-durability`, `revenue-defensibility` (run `technology-adoption-curve` if technology disruption is a risk or opportunity) | 25 min |

**For each category, record:**
- 2-3 key findings that are thesis-relevant
- A score from the category's scoring methodology
- Any red flags triggered
- Any data gaps that could not be resolved

---

### Phase 3 — Thesis Construction (30 min)

Synthesize Phase 2 findings into a structured, defensible investment thesis. Do not begin this phase until all 9 category outputs are documented.

**Skills used (all 4 sub-skills):**
- `categories/10-thesis-construction/bull-bear-framing`
- `categories/10-thesis-construction/catalyst-identification`
- `categories/10-thesis-construction/variant-perception`
- `categories/10-thesis-construction/evidence-grounding`

**Sequence:**
1. **Bull-bear framing first (10 min)** — Define the three scenarios with probability estimates that sum to 100%. Assign price targets to each. Do not let the bull case and bear case share the same core argument.
2. **Catalyst identification (8 min)** — For each scenario, identify at least one specific, time-bound event that will prove or disprove it. "Continued strong execution" is not a catalyst.
3. **Variant perception (7 min)** — State explicitly what consensus believes and where this thesis disagrees. If the thesis agrees with consensus on every major point, it is not a thesis — it is a reiteration.
4. **Evidence grounding (5 min)** — Trace every quantitative claim to a specific data point from Phase 2. Claims supported only by management guidance must be flagged Tier 3.

**Quality gates before proceeding to Phase 4:**
- [ ] Bull, base, and bear probabilities sum to ~100%
- [ ] At least one falsifiable catalyst per scenario
- [ ] Variant perception is specific enough to be proven wrong
- [ ] No quantitative claim is floating free without a source

---

### Phase 4 — Risk Stress-Test (20 min)

Challenge the thesis systematically before sizing the position. This phase is adversarial — the goal is to find the thesis's weakest point before the market does.

**Skills used:**
- `categories/08-risk-assessment/thesis-risk-mapping`
- `categories/08-risk-assessment/tail-risk-scenarios`
- `categories/08-risk-assessment/concentration-risk`
- `categories/09-future-durability/ai-disruption-vulnerability` (mandatory for all tickers)

**Stress-test checklist:**
- [ ] What is the single assumption that, if wrong, invalidates the entire bull case?
- [ ] What is the maximum plausible loss in a bear scenario, and is that loss acceptable at the intended position size?
- [ ] Is there a tail risk scenario (regulatory, macro shock, fraud, product failure) that creates a 50%+ drawdown? What is its probability?
- [ ] What is the AI disruption risk rating for this business? Does the moat analysis hold under that pressure?
- [ ] Does concentration in this position (combined with correlated holdings) create unacceptable portfolio-level risk?
- [ ] Are there any macro regime conditions that would impair the thesis even if the company executes perfectly?

**Record:** A risk register with each risk, probability, magnitude, and mitigation. Include one "nightmare scenario" that stress-tests the position at maximum plausible loss.

---

### Phase 5 — Position Plan (10 min)

Convert the completed thesis into a pre-committed execution plan. This is the final phase — do not begin without a completed Phase 3 thesis and Phase 4 risk register.

**Skills used (all 4 sub-skills):**
- `categories/11-position-management/entry-exit-strategy`
- `categories/11-position-management/position-sizing`
- `categories/11-position-management/stop-loss-invalidation`
- `categories/11-position-management/monitoring-inflections`

**Pre-committed decisions to document:**
1. **Entry zone** — price range and market conditions that justify initiating
2. **Initial position size** — percentage of portfolio, with conviction score adjustment applied
3. **Add-on conditions** — at what price or fundamental milestone would you increase exposure?
4. **Stop-loss trigger** — specific price AND/OR fundamental condition that mandates exit regardless of thesis conviction
5. **Thesis invalidation conditions** — the 2-3 events that would force a full exit regardless of price
6. **Monitoring cadence** — quarterly at minimum; monthly for high-conviction positions
7. **Top 5 signals to watch** — specific, trackable data points with defined response protocols

---

## Output

**Complete analysis document with the following sections:**

1. **Executive summary** (3-5 sentences) — company, thesis in one sentence, recommendation, conviction level

2. **Phase 2 category scores** — table of all 9 categories with scores and key finding per category

3. **Investment thesis** — bull case, base case, bear case with probability weights and price targets; full catalyst list; variant perception statement; evidence map

4. **Risk register** — ranked list of risks with probability, magnitude, mitigation, and one nightmare scenario

5. **Position plan** — entry zone, initial size, add-on conditions, stop-loss trigger, invalidation conditions, monitoring cadence, top 5 signals

6. **Data quality statement** (from Phase 1) — sources used, discrepancies, flags

**The analysis is complete when** every section is filled, every quantitative claim has a source tier, and you can answer these four questions without referencing notes:
- What is the core bet?
- What would make you wrong?
- How much would you lose if wrong?
- What are you watching this quarter?
