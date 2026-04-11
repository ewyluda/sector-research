---
name: Guidance Analysis
description: Evaluate management's guidance credibility by comparing forecasts to actuals over multiple quarters and classifying guidance behavior patterns
category: growth-earnings
type: technique
requires: [earnings, transcript]
---

## Purpose

Management guidance is the market's anchor for near-term expectations. But not all guidance is created equal. Some management teams systematically set the bar low and then beat it — creating predictable, confidence-building quarterly sequences. Others genuinely try to be accurate. A third group consistently overshoots, surprising investors with misses that erode trust and compress multiples.

Knowing which type of management team you are dealing with is essential for interpreting current guidance and calibrating how much to trust their forward outlook. A sandbagging management team with "disappointing" guidance is an opportunity; an optimistic team with "exciting" guidance is a warning.

## Methodology

**Step 1 — Build the guidance vs. actuals history**

Pull management guidance for each of the trailing 4-8 quarters:
- Revenue guidance: point estimate or range (midpoint if range)
- EPS guidance: GAAP and/or non-GAAP (note which basis management provides)
- Gross margin guidance (if provided)
- Operating income or EBITDA guidance (if provided)
- Full-year guidance revisions: track each update across the fiscal year

For each metric, calculate:
```
Guidance Error = (Actual - Guided Midpoint) / Guided Midpoint × 100%
```

Positive = beat, Negative = miss.

**Step 2 — Classify management guidance style**

Apply classification rules across the trailing history:
- **Sandbagger**: consistently beats revenue or EPS guidance by >5% in the same direction for 4+ consecutive quarters
- **Accurate**: guidance error within ±3% on average across trailing 4-8 quarters
- **Optimist**: consistently misses guidance by >3% in 2+ of the last 4 quarters

Note: classify separately for revenue vs. EPS — a management team can be an accurate revenue guesser but an optimistic margin guesser.

**Step 3 — Track guidance revision patterns**

For any fiscal year with multiple guidance updates, assess:
- Did they raise guidance early and confirm, or lower at the last minute?
- Did they raise guidance only to miss the final number?
- Were revisions accompanied by clear explanations, or were reasons vague?

Pattern types:
- **Walk-up**: guidance consistently raised through the year, finishing above initial guide (best)
- **Hold-and-hit**: guidance unchanged, hit at year-end (good)
- **Lower-and-recover**: guidance cut once, then stabilized and hit (acceptable if isolated)
- **Serial lowering**: multiple guidance cuts in a single year (red flag — management had poor visibility)

**Step 4 — Assess non-GAAP vs. GAAP divergence**

Calculate the gap between non-GAAP and GAAP EPS over trailing 8 quarters. Flag if:
- Gap is widening (more adjustments being added over time)
- Excluded items are genuine recurring costs (stock-based comp, amortization of intangibles)
- Non-GAAP metrics change definition without clear disclosure

**Step 5 — Check guidance range width**

Wide guidance ranges that always "hit" the midpoint are a sign of management providing little information. Evaluate:
- Is the guidance range proportionate to business uncertainty?
- Does the range narrow or widen as the year progresses?
- Has the company ever missed its own guidance range entirely?

## Key Questions

1. Does this management team systematically beat, meet, or miss their guidance?
2. When they miss, is it concentrated in one metric (revenue vs. margins) or broad-based?
3. Do they lower guidance early in the year or wait until the quarter before to cut?
4. Is non-GAAP EPS diverging from GAAP EPS in a way that obscures true economic performance?
5. Are guidance ranges so wide that they provide no useful information to investors?

## Red Flags

- Serial guidance cuts within a single fiscal year (3+ cuts = management had fundamentally poor visibility)
- Guidance raised aggressively in Q2/Q3, then missed at year-end (over-confident mid-year)
- Non-GAAP to GAAP EPS gap widening by more than 10 percentage points over 2 years
- Wide guidance ranges that always hit the midpoint to three decimal places (guidance reverse-engineered from actuals)
- Guidance provided for easy metrics (revenue) but not hard metrics (margins, FCF), allowing narrative control
- Management attributing misses entirely to external factors while taking full credit for beats
- Changing the definition of non-GAAP metrics without clear disclosure or restated comparisons

## Source Requirements

**Tier 1 (required for this analysis):**
- SEC EDGAR: 10-K and 10-Q filings for full-year and quarterly actuals
- FMP / FactSet: earnings endpoint (`earnings` via platform data provider) for EPS actuals vs. estimates
- Company earnings releases: guidance tables (initial, revised, final)
- Earnings transcripts: management commentary on guidance rationale and misses

**Tier 2 (qualitative context only):**
- Sell-side research: analyst notes on guidance credibility and revision history
- News: coverage of earnings surprises, investor reactions to guidance

## Output

- Guidance credibility rating: **HIGH** / **MODERATE** / **LOW**
  - HIGH: Accurate or Sandbagger style, <10% of periods with meaningful miss, walk-up or hold-and-hit revision pattern
  - MODERATE: Mixed record, some misses, no systematic pattern of deception
  - LOW: Optimist style, serial guidance cuts, widening non-GAAP gap, or aggressive raise-then-miss pattern

- Guidance vs. actuals table (trailing 4-8 quarters):

| Quarter | Revenue Guided | Revenue Actual | Error % | EPS Guided | EPS Actual | Error % |
|---------|---------------|----------------|---------|------------|------------|---------|
| [period] | [$M] | [$M] | [±%] | [$] | [$] | [±%] |

- Management style classification: Sandbagger / Accurate / Optimist (with supporting evidence)
- Revision pattern classification: Walk-up / Hold-and-hit / Lower-and-recover / Serial lowering
- Non-GAAP vs. GAAP divergence trend
- Specific guidance statements from current quarter with credibility assessment
