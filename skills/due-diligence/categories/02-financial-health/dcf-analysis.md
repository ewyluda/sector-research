---
name: DCF Analysis
description: Discounted cash flow model with bear/base/bull scenarios and sensitivity table to determine intrinsic value range
category: financial-health
type: technique
requires: [fundamentals-data, historical-financials, wacc-inputs, industry-growth-benchmarks]
---

## Purpose

Estimate the intrinsic value of the company by discounting projected future free cash flows back to present value. DCF analysis forces explicit assumption-making — revenue growth, margins, capex, and cost of capital — which reveals what the current stock price implies about the future. The goal is not a single "right" answer but a defensible range (bear/base/bull) and a sensitivity table that maps uncertainty across key inputs.

## Methodology

### Step 1: Build Revenue Growth Assumptions

Define three scenarios for revenue growth over a 5-year explicit forecast period:

| Scenario | Basis | Typical Range |
|----------|-------|---------------|
| Bear | Conservative — assumes headwinds, market share loss, or macro pressure | 0-50% of historical CAGR |
| Base | Consensus-informed — management guidance adjusted for credibility discount | Historical CAGR ± 20% |
| Bull | Optimistic — assumes market share gains, product launches, or TAM expansion | 120-150% of historical CAGR |

Constraint: revenue growth assumptions must not exceed industry CAGR without written justification citing specific, quantifiable sources of incremental share.

### Step 2: Project Margin Trajectory

For each scenario, project:
- **Gross margin**: Is the company gaining or losing pricing power? Compare to 5-year trend and peer median
- **EBIT margin**: Operating leverage as revenue scales — does the cost structure allow margin expansion?
- **FCF margin**: Net income adjusted for D&A, capex, and working capital changes

Use actual historical margins as the anchor. Do not assume margin expansion beyond the 75th percentile of peers without explicit justification.

### Step 3: Capex and Working Capital

- **Maintenance capex**: Required capex to sustain current revenue base (estimate from asset age, depreciation rate)
- **Growth capex**: Discretionary spend to drive incremental revenue (exclude from bear case)
- **Working capital**: Project as % of revenue based on historical 5-year average; expanding WC = cash consumption
- Free Cash Flow = EBIT × (1 - Tax Rate) + D&A - Capex - Change in Working Capital

### Step 4: WACC Calculation

WACC = (Equity / Total Capital) × Cost of Equity + (Debt / Total Capital) × Cost of Debt × (1 - Tax Rate)

- **Cost of Equity**: Risk-free rate (10yr Treasury) + Beta × Equity Risk Premium (use 5.5% ERP as baseline)
- **Cost of Debt**: Current interest expense / total debt (or credit spread + risk-free rate)
- **Beta**: Use 2-year weekly beta; adjust toward 1.0 for cyclicals in late cycle
- Typical WACC range for US equities: 7-11%

### Step 5: Terminal Value

Terminal Value = FCF in Year 5 × (1 + Terminal Growth Rate) / (WACC - Terminal Growth Rate)

- Terminal growth rate: 1-3% for stable businesses; no higher than long-term nominal GDP growth (typically 2-2.5%)
- Red flag: if terminal value exceeds 70% of total DCF value, the model is highly sensitive to terminal assumptions and the output should be used with caution
- Cross-check terminal value implicitly: what multiple does the terminal FCF imply? Should be consistent with sector exit multiples.

### Step 6: Sensitivity Table

Build a 5×4 sensitivity table with WACC on one axis and terminal growth rate on the other:

| | TGR 1% | TGR 2% | TGR 3% | TGR 4% |
|---|--------|--------|--------|--------|
| WACC 7% | — | — | — | — |
| WACC 8% | — | — | — | — |
| WACC 9% | — | — | — | — |
| WACC 10% | — | — | — | — |
| WACC 11% | — | — | — | — |

Mark the base case cell. Shade cells representing upside/downside vs. current price to show margin of safety range.

## Key Questions

1. What revenue growth rate is the current stock price implying — is that achievable given industry CAGR and historical actuals?
2. What WACC and terminal growth rate combination is required to justify the current price — are those assumptions reasonable?
3. How much of the DCF value comes from the terminal value vs. the explicit forecast period? (>70% in terminal = model instability)
4. Under the bear case, what is the implied downside — and is that a level where the position would be sized correctly?
5. What single assumption has the highest impact on intrinsic value, and what is the probability it is wrong?

## Red Flags

- Terminal value exceeds 70% of total DCF value — model is backward-driven by terminal assumptions, not fundamentals
- Revenue growth assumptions in the base case exceed industry CAGR by more than 30% without documented share gain thesis
- WACC below 8% for a cyclical, leveraged, or early-stage company — underestimates risk
- EBIT margin assumptions exceed the company's own best-ever margin without specific catalyst explaining how that will be achieved
- Bear case intrinsic value still above current price — the stock has no margin of safety even in pessimistic scenario
- FCF projections inconsistent with working capital trends (growing revenue but no WC build assumed = unrealistic)

## Source Requirements

**Tier 1 (required):**
- SEC EDGAR 10-K / 10-Q — historical revenue, EBIT, D&A, capex, working capital, tax rate, debt
- Company IR earnings releases and guidance — for base case revenue and margin anchors
- Federal Reserve / St. Louis FRED — 10-year Treasury rate for risk-free rate input
- FMP or Bloomberg — current beta, market cap, debt structure for WACC inputs
- Industry research / FRED — industry CAGR benchmarks to constrain growth assumptions

**Tier 2 (context only):**
- Analyst price targets — useful for sanity-checking model outputs, not for input assumptions
- Sell-side DCF models — structural reference only; never copy assumptions without independent verification

## Output

- Intrinsic value range: bear / base / bull (price per share)
- Discount or premium to current price for each scenario
- WACC and terminal growth rate used (base case, with range)
- Sensitivity table (5×4, WACC vs. terminal growth rate)
- Terminal value as % of total DCF (flag if >70%)
- Key assumption risks: which three inputs most drive model uncertainty
- Note: not individually scored — produces intrinsic value range that feeds FH composite
