---
name: Cash Flow Quality
description: Assess FCF yield, FCF conversion, capex decomposition, and working capital trends to determine whether earnings are backed by real cash
category: financial-health
type: technique
requires: [fundamentals-data, historical-financials, capex-detail-by-category]
---

## Purpose

Verify that reported net income translates into actual free cash flow. High earnings quality means the business generates cash in proportion to or in excess of its net income — a ratio commonly called FCF conversion. When FCF consistently lags net income, the gap is almost always explained by one or more of: aggressive revenue recognition, rising receivables, capitalizing expenses that peers expense, or growth capex that is undisclosed as such.

This technique does not produce an individual score — it contributes qualitatively to the FH composite. A FCF conversion below 60% is a category-level red flag regardless of FH score.

## Methodology

### Step 1: FCF Conversion Analysis

FCF Conversion = Free Cash Flow / Net Income

Free Cash Flow = Operating Cash Flow (from cash flow statement) - Capital Expenditures

Track FCF conversion for each of the past 5 fiscal years and the TTM period:

| FCF Conversion | Quality Classification |
|---------------|----------------------|
| Greater than 100% | Exceptional — cash earnings exceed accounting earnings |
| 80% to 100% | High quality — minor accrual-to-cash gap |
| 60% to 80% | Acceptable — moderate non-cash items or working capital build |
| 40% to 60% | Concerning — investigate root cause before proceeding |
| Below 40% | Red flag — earnings are not converting to cash; do not invest without understanding why |

If conversion is trending down over 3+ years, even if still above 60%, flag the trajectory.

### Step 2: Capex Decomposition

Total capex consists of two economically distinct components:

- **Maintenance capex**: Required to sustain the current revenue base. Approximate as: depreciation × average asset age adjustment, or use management disclosure if available.
- **Growth capex**: Discretionary spend expected to generate incremental future revenue. This is an investment in the business, not a cost.

Calculate:
- Capex as % of revenue (current vs. 5-year average vs. sector median)
- If capex as % of revenue is rising while revenue growth is flat or declining, growth capex is not yielding returns
- Maintenance capex estimate: use (D&A × maintenance intensity ratio) as a proxy if not disclosed; note as estimate

Capex intensity benchmarks by sector:
- Asset-light (SaaS, consulting): 1-3% of revenue
- Moderate (consumer goods, healthcare): 3-7%
- Asset-heavy (manufacturing, utilities, telecom): 8-20%+

Compare to sector median. A company spending materially above sector median on capex without corresponding revenue outperformance is either over-investing or misallocating capital.

### Step 3: Working Capital Trend Analysis

Working Capital = Current Assets - Current Liabilities (excluding cash and short-term debt)

Key working capital components:
- **Days Sales Outstanding (DSO)** = (Accounts Receivable / Revenue) × 365 — rising DSO means collecting cash more slowly; can signal revenue recognition issues
- **Days Inventory Outstanding (DIO)** = (Inventory / COGS) × 365 — rising DIO signals slowing demand or build-ahead
- **Days Payable Outstanding (DPO)** = (Accounts Payable / COGS) × 365 — rising DPO extends supplier credit; can be efficiency or can indicate cash pressure

Cash Conversion Cycle (CCC) = DSO + DIO - DPO

A rising CCC means the company is consuming more cash to fund the same level of business. An expanding CCC faster than revenue growth is a cash quality red flag.

Track each component for 5 years and compare to sector peer median.

### Step 4: FCF Sustainability Assessment

Determine whether the current FCF level is structural or episodic:

- Is FCF volatile year-to-year (cyclical business, lumpy capex) or stable? Stable FCF is more valuable.
- Is FCF being supported by working capital drawdown (one-time benefit) or by genuine earnings conversion?
- Is the company generating FCF during periods of heavy investment — i.e., is it self-funding its growth capex?
- What is the FCF yield (FCF / Market Cap)? Compare to: 10yr Treasury yield, peer FCF yields, and historical own FCF yield.

FCF Yield interpretation: >5% on a sustainable basis is generally considered attractive; <2% suggests the market is pricing in significant future growth.

## Key Questions

1. Has FCF conversion been above 80% consistently over 5 years, or is there a structural gap between net income and cash that requires explanation?
2. Is capex rising as a percentage of revenue, and if so, is it growth capex (acceptable) or maintenance capex inflation (concern)?
3. Is DSO trending up — indicating the company is booking revenue faster than it is collecting cash from customers?
4. What is the FCF yield, and does it provide an adequate return relative to the risk-free rate?
5. Is working capital expanding faster than revenue, signaling that the business model requires increasing cash to sustain each dollar of growth?

## Red Flags

- Net income positive but FCF negative for 2+ consecutive quarters — the business is consuming cash while reporting profits; investigate whether this is growth capex or earnings quality issue
- Rising capex as % of revenue for 3+ years without a corresponding acceleration in revenue growth — growth capex not yielding returns; capital misallocation risk
- Working capital expanding faster than revenue for 2+ years — operational efficiency deteriorating; each incremental dollar of revenue requires progressively more cash to support it
- DSO rising more than 15% year-over-year — aggressive revenue recognition, slowing customer collections, or customer financial distress
- FCF conversion trending from above 80% to below 60% over a 3-year period — structural degradation in earnings quality, not a one-time event
- Large gap between EBITDA and OCF not explained by known working capital build or unusual tax payments — suggests accrual-to-cash leakage from income statement

## Source Requirements

**Tier 1 (required — all inputs must trace here):**
- SEC EDGAR 10-K / 10-Q — operating cash flow, capex, working capital components (A/R, inventory, A/P), D&A; all FCF calculations must use GAAP cash flow statement, not adjusted figures
- Company IR earnings releases — for management capex guidance and working capital commentary
- FMP, Bloomberg, or FactSet — for historical FCF yield and peer capex intensity comparisons (cross-check against EDGAR)

**Tier 2 (qualitative context only):**
- Earnings call transcripts — management discussion of capex allocation between maintenance and growth (qualitative only; verify against filings)
- Analyst research — for industry capex intensity benchmarks and FCF yield context

## Output

- FCF conversion table: 5 years of (FCF / Net Income) with trend direction
- FCF conversion classification: EXCEPTIONAL / HIGH / ACCEPTABLE / CONCERNING / RED FLAG
- Capex decomposition: total capex as % of revenue, estimated maintenance vs. growth split, trend vs. sector median
- Working capital analysis: DSO, DIO, DPO, and CCC trends over 5 years vs. peer median
- FCF yield: current vs. 5-year own history vs. peer median vs. 10yr Treasury
- FCF sustainability assessment: structural or episodic, self-funded or externally dependent
- Note: not individually scored — contributes qualitatively to FH composite score
