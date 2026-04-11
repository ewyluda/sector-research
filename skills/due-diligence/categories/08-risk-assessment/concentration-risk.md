---
name: Concentration Risk
description: Quantify dangerous dependencies across four dimensions — customer, geographic, product, and supplier — and assess the financial impact of losing a top relationship
category: risk-assessment
type: technique
requires: []
---

## Purpose

Concentration risk is the probability that the business is more fragile than it appears because a disproportionate share of its revenue, supply, or operational capability depends on a small number of counterparties, markets, or products. A company with 60% of revenue from a single customer does not have a customer — it has a landlord. When the landlord leaves, the business may not be viable.

Concentration risk is systematically underanalyzed in bull market conditions because concentration and scale are correlated — dominant companies often have concentrated customer bases by design (enterprise software, defense contractors). The key distinction is between healthy concentration (large deals won through superiority) and fragile concentration (the business cannot replace a lost relationship). This technique measures the level and evaluates the fragility.

## Methodology

### Step 1: Customer Concentration — Top 10 Customer Revenue Percentage

Identify the revenue contribution of top customers:

**Data sources**:
- 10-K Item 1 (Business section) — required disclosure when any customer exceeds 10% of revenue
- 10-K footnotes to financial statements — "Major Customers" or "Revenue Concentration" note
- 10-Q filings (same disclosures on a quarterly basis)

**Build the concentration table**:
- Customer 1: % of total revenue, known vs. anonymous, contract expiration (if disclosed)
- Customer 2: same
- Continue to the top 10 or until cumulative % exceeds 80% of revenue
- Note: many companies anonymize customers. If "Customer A" and "Customer B" are cited, attempt to identify via earnings call disclosures, press releases, or investigative channel checks

**Assess contractual protection**:
- Long-term contracts (3+ years, minimum purchase commitments): reduce fragility significantly
- Annual contracts with renewal clauses: moderate protection
- Month-to-month or no formal contract: maximum fragility
- Government contracts (federal, state): generally stable but subject to appropriations

**Revenue replacement difficulty**: estimate how many months it would take to replace the top customer's revenue through new customer acquisition at current sales velocity.

### Step 2: Geographic Concentration — Revenue by Region and Jurisdiction

Map revenue by geography:
- **Domestic vs. international split**: What percentage is USD-denominated vs. foreign currency exposure?
- **Country-level breakdown**: Which countries individually exceed 10% of revenue?
- **Regulatory jurisdiction risk**: Does significant revenue come from jurisdictions with elevated expropriation, trade restriction, or regulatory divergence risk?
- **Currency risk**: How much of international revenue is hedged vs. exposed to FX volatility?

**Special attention to**:
- China exposure above 15% of revenue (tariff risk, technology restriction risk, VIE structure risk if applicable)
- Russia or sanctioned jurisdiction exposure (compliance and access risk)
- Single EU country above 25% of international revenue (regulatory risk from GDPR, digital markets legislation)
- Emerging market exposure above 20% without hedging program (FX and macro volatility)

### Step 3: Product and Revenue Stream Concentration

Assess how revenue is distributed across products, product lines, or revenue streams:

- **Primary product %**: What percentage of revenue comes from the single largest product or product line?
- **Recurring vs. one-time split**: What percentage is contracted recurring revenue (SaaS subscriptions, maintenance contracts) vs. project/transaction revenue?
- **Product obsolescence risk**: Is the highest-concentration product in a market facing technological disruption or commodity pricing pressure?
- **Platform vs. point-solution**: Platform companies have inherently lower product concentration risk; point-solution companies depend entirely on the performance of one product category

**Revenue stream concentration scoring**:
- Top product or stream > 70% of revenue: HIGH concentration
- Top product or stream 50-70%: MODERATE-HIGH concentration
- Top product or stream 30-50%: MODERATE concentration
- Top product or stream < 30%: LOW concentration (well-diversified)

### Step 4: Key Supplier and Vendor Dependencies

Identify critical input dependencies:

**Types of supplier concentration**:
- **Raw material suppliers**: single-source materials, rare earth inputs, semiconductor components
- **Manufacturing partners**: contract manufacturers (particularly sole-source relationships)
- **Technology vendors**: critical software, cloud infrastructure, intellectual property licensors
- **Distribution partners**: channel partners that control access to end customers

**Assessment questions**:
- Is any critical input sourced from a single supplier with no qualified alternative?
- What is the lead time to qualify an alternative supplier for the most critical inputs?
- Does any supplier relationship represent a counterparty with leverage over pricing (supplier captures margin)?
- Is the company dependent on a single cloud provider, logistics carrier, or distribution partner without contractual protections or alternatives?

**Scoring**:
- Sole-source supplier for >20% of COGS with no alternative: HIGH dependency
- Single supplier for 20-40% of COGS with alternative in qualification: MODERATE dependency
- Multiple suppliers for all critical inputs, alternative in production: LOW dependency

## Key Questions

1. Does any single customer represent more than 10% of revenue? What would the business look like if that customer churned?
2. What percentage of revenue is under long-term contract vs. at-risk on annual renewal or transactional terms?
3. Is there geographic concentration in a jurisdiction undergoing regulatory change, trade restriction, or political instability?
4. Does the company disclose single-source supplier dependencies in its 10-K? What is the contingency if that supplier fails?
5. How has concentration changed year-over-year — is the business becoming more or less concentrated over time?
6. In past quarters, has the company disclosed losing a top customer and what was the revenue impact and recovery timeline?

## Red Flags

- Any single customer exceeds 20% of revenue with no multi-year contract — this customer's loss would immediately impair financial guidance
- Top 3 customers collectively exceed 50% of revenue — the business has effectively made a bet on relationship retention, not market building
- Geographic concentration above 30% in a single country outside the US with active trade restriction, tariff escalation, or political instability risk
- Sole-source supplier for any critical input with a lead time of 12+ months to qualify an alternative — this is an operational single point of failure
- Company has not disclosed customer concentration details in its most recent 10-K despite analysts asking on earnings calls — non-disclosure of a material concentration can itself be a warning sign
- Revenue concentration increased year-over-year (company becoming more dependent, not less) without a strategic rationale (e.g., a deliberate enterprise upmarket move)
- Product concentration in a category facing commoditization or competitive pricing pressure from well-funded entrants

## Source Requirements

- **10-K Item 1 (Business section)**: SEC EDGAR — Tier 1 (primary customer concentration disclosure)
- **10-K financial statement footnotes**: SEC EDGAR — Tier 1 (major customer disclosures, geographic revenue breakdown)
- **10-Q quarterly reports**: SEC EDGAR — Tier 1 (for quarterly concentration monitoring)
- **Earnings call transcripts**: FMP earnings transcripts, platform earnings_review agent — Tier 2 (management commentary on top customer relationships)
- **Supplier disclosures**: 10-K supply chain risk section, proxy statements — Tier 1
- **News and channel checks**: Bloomberg, Reuters, trade publications — Tier 3 (for identifying anonymous customers)

## Scoring

**Concentration Risk Score (0-100, inverted: 100 = no material concentration):**

For each of the four dimensions, assign:
- HIGH concentration (>50% in any single dimension): 0-25 points for that dimension
- MODERATE concentration (30-50%): 26-60 points
- LOW concentration (<30%): 61-100 points

Overall score = average of four dimension scores.

Contractual protection modifier: If HIGH or MODERATE concentration is backed by multi-year contracted minimums, add 10 points to that dimension's score (floor of dimension maximum: HIGH max remains 40, MODERATE max remains 75).

## Output

- Customer concentration table: top 10 customers (named or anonymized), % of revenue, contract status, estimated replacement timeline
- Geographic concentration breakdown: domestic vs. international, country-level for any >10% exposure, currency hedging status
- Product concentration summary: top product/stream %, recurring vs. transactional mix, obsolescence risk
- Supplier dependency assessment: critical inputs, sole-source relationships, alternative qualification status
- Concentration Risk Score (0-100) with dimension breakdown
- Overall concentration classification: LOW / MODERATE / HIGH / CRITICAL with primary concentration driver
- Recommended monitoring triggers: conditions that would cause a reassessment of the concentration risk level
