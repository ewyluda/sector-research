---
name: Earnings Quality
description: Assess whether reported earnings are backed by real cash flows or inflated by accruals, one-time items, and aggressive revenue recognition
category: growth-earnings
type: technique
requires: [financials, earnings]
---

## Purpose

Net income is an accounting construct. Cash is not. When a company reports strong earnings but weak operating cash flows, the gap is filled by accruals — balance sheet entries that represent future obligations or receivables that may never convert to cash. Consistently high accruals are one of the most reliable leading indicators of earnings disappointment and, in extreme cases, fraud.

Earnings quality analysis asks: are reported earnings a fair representation of the economic value being created? Four diagnostic lenses are applied: accruals analysis, OCF-to-NI consistency, non-recurring item prevalence, and revenue recognition aggressiveness.

## Methodology

**Step 1 — Accrual ratio analysis**

Calculate the balance-sheet accrual ratio:

```
Accrual Ratio = (Net Income - Operating Cash Flow) / Total Assets
```

A positive accrual ratio means net income exceeds cash generation — the gap is funded by accruals. The larger the gap relative to total assets, the more aggressive the earnings.

Evaluate over trailing 4 quarters (TTM basis). Flag if trending upward — an expanding accrual ratio signals deteriorating earnings quality even if absolute earnings are rising.

**Step 2 — OCF-to-NI consistency**

Calculate the cash conversion ratio each quarter:

```
Cash Conversion = Operating Cash Flow / Net Income
```

Track the trailing 4-quarter average. A ratio consistently above 1.0 indicates earnings are understated relative to cash (conservative accounting). A ratio below 1.0 indicates cash is lagging earnings (aggressive accounting or working capital deterioration).

Also look for volatility: a ratio that swings wildly quarter-to-quarter may indicate earnings management to smooth reported results.

**Step 3 — Non-recurring item decomposition**

Pull all items management classifies as "non-recurring," "one-time," or "special" over the trailing 8 quarters:
- Restructuring charges
- Impairments (goodwill, asset write-downs)
- Acquisition-related costs
- Litigation settlements
- Stock-based compensation adjustments (addback in non-GAAP)

Calculate non-recurring items as a percentage of total reported earnings each period. If the same "one-time" category appears in multiple periods, reclassify it as recurring for scoring purposes.

**Step 4 — Revenue recognition aggressiveness**

Calculate Days Sales Outstanding (DSO) trend:

```
DSO = (Accounts Receivable / Revenue) × 90
```

Rising DSO means the company is booking revenue before collecting cash — a sign of either loosening credit terms, channel stuffing, or aggressive recognition. Compare DSO to sector peers.

Also examine deferred revenue trends: declining deferred revenue relative to revenue can signal front-loading of recognition.

## Key Questions

1. Is operating cash flow tracking net income over multiple quarters, or is a persistent gap opening up?
2. Are the same "non-recurring" items appearing across multiple annual periods?
3. Is DSO rising faster than revenue growth — and how does this compare to industry peers?
4. Is management adding back items in non-GAAP earnings that represent real ongoing costs (stock comp, amortization of acquired intangibles)?
5. Are accounts receivable growing faster than revenue (potential channel stuffing or collection risk)?

## Red Flags

- OCF consistently below net income for 3+ consecutive quarters
- Accrual ratio above 15% and trending upward
- Annual "non-recurring" restructuring charges that never actually restructure the business
- Accounts receivable growing materially faster than revenue (2x+ the revenue growth rate)
- DSO rising >10% YoY without a clear explanation (new payment terms, geographic mix shift)
- Capitalizing expenses that peers expense (R&D, sales costs, software development) — inflates earnings and understates cash costs
- Non-GAAP EPS diverging from GAAP EPS by >30% and the gap is widening

## Source Requirements

**Tier 1 (required for this analysis):**
- SEC EDGAR: 10-K and 10-Q filings — income statement, cash flow statement, balance sheet
- FMP / FactSet: financial statements endpoint (`financials` via platform data provider)
- Company earnings releases: non-GAAP reconciliation tables
- Earnings transcripts: management commentary on non-recurring items and working capital

**Tier 2 (qualitative context only):**
- Sell-side research: accounting quality notes, adjusted earnings models
- News: any analyst or short-seller reports citing accounting concerns

## Scoring

**Earnings Quality Score (0-100)**

| Factor | Weight | Score Bands |
|--------|--------|-------------|
| Accrual ratio | 30% | <5% = 100 pts; 5-10% = 75 pts; 10-15% = 50 pts; >15% = 25 pts |
| OCF-to-NI consistency (4Q trailing avg) | 25% | >1.0 = 100 pts; 0.8-1.0 = 75 pts; 0.5-0.8 = 50 pts; <0.5 = 0 pts |
| Non-recurring prevalence (8Q trailing avg as % of earnings) | 25% | <5% = 100 pts; 5-15% = 60 pts; >15% = 20 pts |
| Revenue recognition aggressiveness (DSO trend) | 20% | Declining or flat = 100 pts; Rising <10% YoY = 50 pts; Rising >10% YoY = 0 pts |

**Composite**: Earnings Quality Score = (Accrual score × 0.30) + (OCF score × 0.25) + (Non-recurring score × 0.25) + (DSO score × 0.20)

Score ranges:
- 80-100: High quality — earnings are a reliable representation of economic value
- 60-79: Moderate quality — some accrual risk or non-recurring noise; monitor closely
- 40-59: Questionable quality — meaningful gap between reported earnings and cash; dig deeper
- 0-39: Low quality — significant red flags; discount reported earnings materially in any valuation

## Output

- Earnings Quality Score (0-100) with sub-factor breakdown
- Accrual ratio table (trailing 4 quarters)
- OCF-to-NI ratio table (trailing 4 quarters) with trend classification
- Non-recurring item inventory (trailing 8 quarters) with recurrence classification
- DSO trend chart (trailing 8 quarters) vs. sector median
- List of specific accounting concerns and recommended follow-up questions for management
