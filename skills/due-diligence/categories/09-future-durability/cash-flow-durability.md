---
name: Cash Flow Durability
description: Model the sustainability of a company's cash flows at 5, 10, and 15 year horizons by classifying revenue stream durability and scoring sub-factors
category: future-durability
type: technique
requires: [moat-analysis]
---

## Purpose

Evaluate how durable the company's cash flows are across three investment planning horizons: 5 years (near-term), 10 years (medium-term), and 15 years (long-term). This is not a DCF model — it is a structural assessment of whether the revenue foundation is built on durable or fragile ground.

Most DCF models assume revenue grows steadily with terminal value calculations that implicitly assume the business survives in perpetuity. Cash Flow Durability challenges that assumption by asking: **what is the probability this cash flow stream exists at each horizon, and at what magnitude?**

The output feeds directly into the FD Score (20% at 5yr, 30% at 10yr, 20% at 15yr horizons).

## Methodology

### Step 1: Classify Revenue Streams by Durability Type

Break total revenue into constituent streams and classify each by durability archetype. Use the most recent annual report (segment disclosures, management commentary, investor day materials) as the primary source.

**Durability Archetypes (highest to lowest durability):**

**Contractual Recurring** — Revenue locked in by multi-year contracts, subscriptions, or committed arrangements. Customer must actively cancel or not renew to stop paying. Examples: SaaS subscriptions, enterprise license agreements, maintenance contracts, long-term service agreements.
- Durability: Very High. Revenue is visible and sticky by design.
- Key risk: Contract renewal rates and AI substitution at rollover.
- Indicators: Remaining performance obligations (RPO), backlog, net revenue retention (NRR).

**Usage-Based Recurring** — Revenue generated each time a customer uses the product. No long-term commitment, but strong behavioral lock-in through workflow integration. Examples: cloud infrastructure (AWS, Azure), transaction processing (Visa, Stripe), API call volume.
- Durability: High, but volume-dependent. Churn risk is real; downside scenarios require volume assumptions.
- Key risk: Volume could migrate to cheaper AI alternatives as APIs commoditize.
- Indicators: Cohort revenue retention, net dollar retention, usage growth trends.

**Relationship Recurring** — Revenue generated through ongoing relationships without formal contracts. Customers return out of habit, trust, or switching friction rather than legal obligation. Examples: consulting retainers, preferred vendor relationships, wealth management AUM fees.
- Durability: Moderate. Holds in stable competitive environments; vulnerable to AI disruption that reduces switching costs.
- Key risk: AI-native competitors can now replicate relationship value (expertise, advisory, customization) at scale.
- Indicators: Client tenure distribution, repeat revenue %, share of wallet.

**Project-Based** — Revenue from discrete engagements with no guarantee of repeat. Examples: implementation services, M&A advisory, construction contracts, bespoke software development.
- Durability: Low. Entirely dependent on winning new work each cycle.
- Key risk: AI directly attacks this category by reducing per-project cost and timeline — human-hours billing compresses.
- Indicators: Pipeline conversion rates, book-to-bill ratio, customer concentration.

**One-Time / Transactional** — Revenue from a single sale with no expectation of recurrence. Examples: product unit sales, license perpetual sales, media content sales.
- Durability: Very Low. Must constantly acquire new customers or upsell existing ones.
- Key risk: AI-generated substitutes (content, software, products) reduce willingness to pay.
- Indicators: Customer acquisition cost trends, cohort repeat rates.

**For each revenue stream, document:**
- Stream name and description
- % of total revenue
- Durability archetype
- Primary AI disruption risk

### Step 2: Score Sub-Factors

Score each of the five sub-factors on a 0-100 scale for the company overall (not per stream).

**Revenue Stream Diversity (20% weight)**
- Score 80-100: 5+ distinct revenue streams, no single stream >30% of total; disruption to one stream does not threaten the whole
- Score 50-79: 2-4 revenue streams, largest stream 30-50% of total; moderate concentration
- Score 20-49: 1-2 dominant streams at 50-70% of revenue; company is vulnerable to stream-level disruption
- Score 0-19: Single revenue stream or single stream >70%; existential risk from single-point disruption
- Data sources: Segment disclosures, 10-K revenue breakdown, investor presentations

**Recurring Revenue Percentage (25% weight)**
- Calculate: (Contractual Recurring + Usage-Based Recurring) / Total Revenue
- Score 80-100: >70% recurring; highly predictable revenue base
- Score 50-79: 50-70% recurring; solid base with some project/transactional exposure
- Score 20-49: 30-50% recurring; material dependence on new business and repeat transaction rates
- Score 0-19: <30% recurring; revenue is rebuild-from-zero each year — high fragility
- Red flag trigger: <30% recurring is a hard red flag regardless of other factors
- Data sources: 10-K revenue disaggregation (ASC 606), management commentary, analyst models

**Moat Score Pass-Through (20% weight)**
- Use the Moat Strength Score from the moat-analysis skill as input
- Convert moat score directly: Moat Score 0-100 → Cash Flow Durability sub-factor 0-100
- Rationale: A strong moat is the primary mechanism that makes cash flows durable over time. A business with no moat cannot sustain its cash flows as competition intensifies regardless of current revenue mix.
- Adjustment: If the moat-analysis skill identified AI disruption as a primary moat risk, apply a 20-point downward adjustment to this sub-factor to reflect forward-looking vulnerability

**Customer Concentration Inverse (15% weight)**
- Calculate: 100 − concentration_penalty
- Concentration penalty: (largest customer % of revenue × 2) + (top 3 customers % of revenue × 0.5)
- Example: Top customer = 15% of revenue, top 3 = 35% → penalty = 30 + 17.5 = 47.5 → score = 52.5
- Red flag trigger: Single customer >20% of revenue is a hard red flag
- Data sources: 10-K risk factors (customer concentration disclosure), revenue by customer segment

**CapEx Flexibility (20% weight)**
- Assess what percentage of capex is maintenance (survival) vs. growth (discretionary)
- Score 80-100: Low maintenance capex (<5% of revenue); company can cut spending without impairing the core business. Asset-light model.
- Score 50-79: Moderate maintenance capex (5-10% of revenue); some flexibility but material fixed cost base
- Score 20-49: High maintenance capex (10-20% of revenue); company must spend to maintain position; limited flexibility in downturn
- Score 0-19: Very high maintenance capex (>20% of revenue); capital-intensive model with high fixed costs and limited ability to adapt
- Why it matters for durability: In a disruption scenario, companies with high maintenance capex cannot pivot resources to AI adaptation without impairing current operations
- Data sources: Cash flow statement (capex line), management commentary on maintenance vs. growth capex, depreciation vs. capex ratio

### Step 3: Apply Time-Horizon Discount

Calculate the base Durability Score = weighted average of sub-factor scores (using weights above).

Apply time-horizon discounts to reflect increasing uncertainty:

**5-Year Score** = Base Score × 1.0 (no discount; within visible planning horizon)
- Modifier: If recurring revenue % < 30%, apply additional -10 point penalty

**10-Year Score** = Base Score × 0.85 + AI Vulnerability Adjustment
- AI Vulnerability Adjustment: −(AI Vulnerability Score / 10) points
  - Example: AI Vulnerability Score = 60 → subtract 6 points from the 10yr score
- Rationale: At 10 years, AI substitution effects will be at their peak. Revenue streams that are vulnerable today will have been substantially disrupted by Year 10.
- Modifier: If no AI strategy identified in management commentary, apply additional -5 point penalty

**15-Year Score** = Base Score × 0.70 + Moat Widening Adjustment
- Moat Widening Adjustment: +5 if moat is widening, 0 if stable, -5 if narrowing
- Rationale: At 15 years, only companies with genuinely widening moats (compounding advantages, network effects, proprietary data) will sustain high cash flow durability. Everything else reverts toward commodity economics.
- Modifier: If industry is in structural decline (per industry-lifecycle sub-skill), apply additional -15 point penalty

### Step 4: Compute Per-Horizon Score

**5-Year Durability Score** (0-100): Output of Step 3 for 5yr horizon
**10-Year Durability Score** (0-100): Output of Step 3 for 10yr horizon
**15-Year Durability Score** (0-100): Output of Step 3 for 15yr horizon

These three scores feed into the FD Score: (5yr × 20%) + (10yr × 30%) + (15yr × 20%)

## Key Questions

1. What percentage of this company's revenue will still exist in its current form in 5 years? 10 years?
2. If the company lost its top 3 customers tomorrow, how long could it survive and on what reserves?
3. Is recurring revenue genuinely sticky (contractual, high switching cost) or superficially recurring (customer keeps paying but could leave easily)?
4. What is the renewal rate on contractual recurring revenue, and is it trending up or down?
5. If AI reduces the price of delivering this company's core product by 80%, what happens to revenue? (This tests whether durability is real or margin-dependent.)
6. Is the capex structure compatible with rapid adaptation, or would pivoting to AI-native delivery require a painful multi-year restructuring?
7. What is the 5-year revenue trajectory if the company does nothing differently? What if it executes perfectly on AI adaptation?

## Red Flags

- Recurring revenue below 30% — company is building from zero each year
- Single customer above 20% of revenue — durability is a relationship risk, not a business model risk
- Moat score below 40 (from moat-analysis skill) — no structural protection for cash flows
- CapEx ratio above 15% of revenue with heavy maintenance component — limited adaptation flexibility
- Revenue stream composition shifting toward project-based and one-time (visible in multi-year segment disclosures)
- Net revenue retention trending below 100% — existing customers are shrinking their spend
- Remaining performance obligations (RPO) declining as a multiple of quarterly revenue — forward visibility is eroding
- Management discussing "revenue mix shift" without explaining what replaces the declining streams
- Free cash flow margin declining while revenue grows — revenue quality is deteriorating

## Source Requirements

- **10-K annual report**: Revenue disaggregation (ASC 606 Note), segment disclosures, customer concentration risk factors, capex breakdown in cash flow statement
- **Earnings transcripts** (last 4 quarters): Management commentary on backlog, RPO, renewal rates, NRR
- **Investor day materials**: Long-term revenue model, recurring vs. non-recurring targets, segment-level growth assumptions
- **Moat Analysis output**: Required input for moat score pass-through sub-factor
- **AI Disruption Vulnerability output**: Required input for 10yr time-horizon discount
- **Industry-lifecycle assessment**: Required for 15yr modifier (structural decline check)

## Output

- Revenue stream table: stream name, % of revenue, durability archetype, primary AI risk
- Sub-factor scores: Diversity (20%), Recurring % (25%), Moat pass-through (20%), Customer concentration inverse (15%), CapEx flexibility (20%)
- Base Durability Score (0-100) with sub-factor breakdown
- 5-Year Durability Score (0-100)
- 10-Year Durability Score (0-100)
- 15-Year Durability Score (0-100)
- Key durability risks by horizon
- Monitoring triggers (e.g., "if NRR falls below 95%, revise 10yr score down by 10 points")
