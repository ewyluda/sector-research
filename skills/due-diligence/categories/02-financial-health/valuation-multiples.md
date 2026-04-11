---
name: Valuation Multiples
description: Evaluate stock valuation relative to sector peers and historical range using P/E, EV/EBITDA, P/S, P/FCF, and PEG
category: financial-health
type: technique
requires: [fundamentals-data, sector-peer-list, 5yr-price-and-earnings-history]
---

## Purpose

Determine whether the stock is cheap, fairly valued, or expensive relative to its sector peers and its own historical trading range. Multiples are context-dependent — a high P/E is justified for a high-growth compounder, and a low P/E is a trap for a deteriorating business. This technique provides relative context, not absolute value (see dcf-analysis for intrinsic value).

## Methodology

### Step 1: Gather Current Multiples

Collect the following from Tier 1 sources (FMP, Bloomberg, FactSet):

| Multiple | Formula | What It Captures |
|----------|---------|-----------------|
| P/E (trailing) | Price / TTM EPS | Basic earnings valuation; sensitive to one-time items |
| P/E (forward) | Price / Next-12-month consensus EPS | Market expectation of future earnings |
| EV/EBITDA | Enterprise Value / TTM EBITDA | Capital-structure-neutral; preferred for leveraged companies |
| P/S | Market Cap / TTM Revenue | Useful when earnings are negative or distorted |
| P/FCF | Market Cap / TTM Free Cash Flow | Cash-quality-adjusted valuation |
| PEG | Forward P/E / EPS Growth Rate | Growth-adjusted P/E; <1.0 often considered attractive |

Note: EV = Market Cap + Total Debt - Cash. Verify EV components directly from balance sheet.

### Step 2: Compare to Sector Median

- Identify 8-12 direct peers (same sub-industry, similar business model) from SEC EDGAR peer filings or FMP peer list
- For each multiple, note the company's **percentile rank** within the peer group
- Interpret: top quartile (expensive) vs. bottom quartile (cheap) vs. median (fairly valued)
- Flag mismatches: cheap on P/E but expensive on EV/EBITDA often indicates hidden debt burden

### Step 3: Compare to 5-Year Historical Range

- Pull 5 years of monthly P/E and EV/EBITDA from Tier 1 data provider
- Calculate: current multiple vs. 5-year mean, 5-year high, 5-year low
- Compute z-score: (current - mean) / standard deviation
- Interpret: z-score >+2.0 = historically expensive; z-score <-2.0 = historically cheap
- Flag regime changes: if business model changed substantially, pre-change history may not be comparable

### Step 4: Growth-Adjusted Assessment (PEG Normalization)

- PEG = Forward P/E / Consensus 3-year EPS CAGR
- PEG <1.0 = growing into its multiple; PEG >2.0 = expensive even accounting for growth
- For non-earnings businesses (negative EPS), substitute P/S growth adjustment: P/S divided by revenue growth rate
- Cross-check growth assumptions against historical actuals — use management guidance cautiously (see guidance-analysis)

## Key Questions

1. Is the company trading above its own 5-year historical average on EV/EBITDA, and if so, what has changed to justify the premium?
2. Does the valuation gap vs. peers reflect a real quality difference (moat, growth rate) or temporary sentiment?
3. Is the stock cheap on P/E but expensive on P/FCF — suggesting earnings quality issues?
4. At what price would the stock reach a PEG of 1.0 — is that materially below the current price?
5. If growth assumptions embedded in the current multiple are wrong by 30%, what is the downside?

## Red Flags

- Trading >2 standard deviations above 5-year historical mean on EV/EBITDA without corresponding acceleration in fundamentals
- P/E multiple contracting (or expected to contract) while earnings growth is also decelerating — double compression risk
- Cheap on trailing P/E but expensive on EV/EBITDA — debt is masking true valuation; the business is not as cheap as it appears
- PEG >3.0 with declining analyst estimate revisions — expensive and momentum deteriorating
- Significantly cheaper than peers on every metric with no obvious catalyst — potential value trap
- P/S >10x for a company with declining revenue growth — narrative premium with no fundamental support

## Source Requirements

**Tier 1 (required for all quantitative multiples):**
- SEC EDGAR 10-K / 10-Q filings — GAAP earnings, revenue, shares outstanding
- FMP (Financial Modeling Prep), Bloomberg, FactSet, or S&P Capital IQ — current and historical multiples, peer comparisons
- Company IR earnings releases — for guidance-based forward P/E

**Tier 2 (qualitative context only):**
- Analyst research reports — useful for peer group construction and narrative context
- News coverage — for explaining current premium or discount vs. history

## Output

- Valuation multiple summary table: current vs. sector median vs. 5-year mean (6 multiples)
- Peer percentile rank for each multiple
- Historical z-score (current vs. 5-year mean, in standard deviations)
- PEG ratio and growth-adjusted assessment
- Valuation conclusion: EXPENSIVE / FAIRLY VALUED / ATTRACTIVE, with specific multiple context
- Note: not individually scored — contributes qualitatively to FH composite score
