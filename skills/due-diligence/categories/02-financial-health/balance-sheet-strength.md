---
name: Balance Sheet Strength
description: Evaluate leverage, liquidity, debt maturity, and debt service capacity using the deterministic Fortress Score (0-100)
category: financial-health
type: technique
requires: [fundamentals-data, historical-financials, debt-maturity-schedule]
---

## Purpose

Determine whether the company can survive an adverse revenue or margin shock without requiring a dilutive capital raise, covenant breach, or restructuring. Balance sheet strength is the financial immune system — it separates companies that are merely profitable in good times from those that can endure downturns and emerge with competitive position intact.

This technique produces the **Fortress Score** (0-100), a fully deterministic calculation with no discretionary inputs. A Fortress Score below 40 requires elevated risk flags in the investment thesis regardless of other factors.

## Methodology

### Step 1: Net Debt / EBITDA

Net Debt = Total Debt (short-term + long-term) - Cash and Cash Equivalents
EBITDA = TTM EBIT + Depreciation & Amortization

Verify EBITDA components trace to SEC EDGAR 10-K or 10-Q directly. Do not use adjusted or non-GAAP EBITDA without explicitly noting the adjustment and its materiality.

Track trend over 5 years: is leverage increasing or decreasing? Rising leverage during falling EBITDA is a compounding risk.

### Step 2: Interest Coverage Ratio

Interest Coverage = EBIT (TTM) / Interest Expense (TTM)

Use GAAP EBIT. Interest expense from the income statement or cash flow statement notes.

A coverage ratio below 3x means a 33% decline in EBIT would push coverage below 1x — the company would not earn enough to cover its debt obligations from operations.

### Step 3: Current Ratio

Current Ratio = Current Assets / Current Liabilities

Note that the current ratio is industry-dependent. Retailers naturally carry low current ratios (negative working capital from deferred revenue); SaaS companies may carry high ratios. Compare to sector median, not an absolute threshold.

For industries with deferred revenue in current liabilities (SaaS, insurance), consider the adjusted current ratio excluding deferred revenue from the denominator.

### Step 4: Debt Maturity Profile

Pull the debt maturity schedule from the 10-K Notes to Financial Statements (typically "Long-Term Debt" footnote). Map maturities by year:

| Time Horizon | Risk Level |
|-------------|-----------|
| Maturity within 12 months | Immediate refinancing or liquidity risk |
| Maturity within 12-24 months | Near-term wall; assess refinancing optionality |
| Maturity within 24-36 months | Moderate — manageable if cash flow supports |
| No major maturities in 3 years | Minimal maturity risk |

Also check: covenant terms (leverage covenants, coverage covenants, springing covenants); proximity to breach matters independent of maturity timing.

### Step 5: FCF / Debt Service Coverage

FCF Debt Service Coverage = Levered Free Cash Flow / (Interest Expense + Scheduled Principal Repayments)

Levered FCF = Operating Cash Flow - Capex (maintenance only, if separable)
Scheduled principal from debt maturity schedule or cash flow statement financing section.

This ratio answers: after servicing debt, is there meaningful FCF left for growth or shareholder returns?

## Scoring

### Fortress Score (0-100)

The Fortress Score is fully deterministic. Each component maps directly to a score with no analyst discretion. Weighted sum = Fortress Score.

**Component 1: Net Debt / EBITDA — weight 25%**

| Net Debt / EBITDA | Component Score |
|------------------|----------------|
| Less than 1x | 100 |
| 1x to 2x | 75 |
| 2x to 3x | 50 |
| 3x to 4x | 25 |
| Greater than 4x | 0 |

**Component 2: Interest Coverage — weight 25%**

| Interest Coverage (EBIT / Interest) | Component Score |
|------------------------------------|----------------|
| Greater than 10x | 100 |
| 5x to 10x | 75 |
| 3x to 5x | 50 |
| 1x to 3x | 25 |
| Less than 1x | 0 |

**Component 3: Current Ratio — weight 15%**

| Current Ratio | Component Score |
|--------------|----------------|
| Greater than 2.0 | 100 |
| 1.5 to 2.0 | 75 |
| 1.0 to 1.5 | 50 |
| Less than 1.0 | 25 |

**Component 4: Debt Maturity Profile — weight 20%**

| Maturity Profile | Component Score |
|-----------------|----------------|
| No major maturities within 3 years | 100 |
| Some maturities within 2-3 years | 50 |
| Significant maturity wall within 2 years | 0 |

*Major maturity = any single tranche >15% of total debt or >1.0x EBITDA*

**Component 5: FCF / Debt Service — weight 15%**

| FCF / Debt Service Coverage | Component Score |
|-----------------------------|----------------|
| Greater than 3x | 100 |
| 2x to 3x | 75 |
| 1x to 2x | 50 |
| Less than 1x | 0 |

**Fortress Score = (C1 × 0.25) + (C2 × 0.25) + (C3 × 0.15) + (C4 × 0.20) + (C5 × 0.15)**

**Score Interpretation:**

| Fortress Score | Classification | Investment Implication |
|---------------|---------------|----------------------|
| 80-100 | Fortress | Balance sheet is a competitive advantage; can self-fund growth through downturns |
| 60-79 | Strong | Solid balance sheet; modest refinancing risk in severe downturns |
| 40-59 | Adequate | Serviceable under normal conditions; vulnerable in a sustained downturn |
| 20-39 | Stressed | Elevated financial risk; requires close monitoring of covenant proximity |
| 0-19 | Distressed | Existential balance sheet risk; position sizing must reflect possible impairment |

## Key Questions

1. What is the Fortress Score, and which single component is dragging it down most — leverage, coverage, maturity, or liquidity?
2. Does the company have a near-term debt maturity wall that will require refinancing at potentially higher rates?
3. Under a 20% revenue decline scenario, does interest coverage drop below 1.5x — which would trigger covenant risk?
4. Is the leverage trend moving in the right direction — are they paying down debt with FCF or adding leverage?
5. Does the company have an undrawn revolving credit facility that provides a meaningful liquidity backstop?

## Red Flags

- Debt maturity wall within 18 months with current cash + FCF insufficient to retire without refinancing — near-term existential risk
- Leverage covenants close to breach (within 0.5x of covenant trigger) — even modest EBITDA miss could force covenant waiver or restructuring
- Rising net debt combined with declining EBITDA — leverage ratio deteriorating on both numerator and denominator simultaneously
- Interest coverage below 2x for two consecutive quarters — business not generating enough earnings to comfortably service debt
- Fortress Score drop of more than 20 points quarter-over-quarter — rapid deterioration, often precedes credit rating downgrade or equity dilution
- Significant off-balance-sheet obligations (operating leases, pension deficits, contingent liabilities) not reflected in headline Net Debt / EBITDA

## Source Requirements

**Tier 1 (required — all inputs must trace here):**
- SEC EDGAR 10-K / 10-Q — all balance sheet items, debt schedule notes, covenant disclosures, operating lease obligations
- Company IR earnings releases — for TTM EBITDA and management commentary on liquidity position
- FMP, Bloomberg, or FactSet — for pre-calculated ratios as a cross-check only (verify against EDGAR)
- Credit rating reports (Moody's, S&P, Fitch) — if available, useful for covenant detail and stress scenario analysis

**Tier 2 (qualitative context only):**
- News coverage of credit events, refinancing announcements — directional signal
- Earnings call transcripts — management commentary on liquidity and capital structure priorities

## Output

- Fortress Score (0-100) with full component breakdown (all 5 components and weights shown)
- Net Debt / EBITDA current and 5-year trend
- Interest coverage current and 5-year trend
- Debt maturity schedule summary (maturities by year for next 5 years)
- Current ratio and sector comparison
- FCF / debt service coverage ratio
- Fortress Score classification: FORTRESS / STRONG / ADEQUATE / STRESSED / DISTRESSED
- Key balance sheet risks and covenant proximity flags
