---
name: Profitability Analysis
description: Evaluate margin stack, ROIC vs. WACC spread, and DuPont ROE decomposition to determine whether the business creates or destroys economic value
category: financial-health
type: technique
requires: [fundamentals-data, historical-financials, wacc-inputs, sector-peer-list]
---

## Purpose

Determine whether the business is genuinely profitable at an economic level — not just on an accounting basis. A company can report positive net income while destroying shareholder value if its returns on capital fall below its cost of capital. This technique examines the margin stack, ROIC vs. WACC spread, and ROE decomposition to distinguish true value creators from capital destroyers.

Trend matters more than level. An expanding margin profile with stable revenue is a more bullish signal than high but declining margins. Direction indicates trajectory; trajectory indicates whether the business is getting stronger or weaker.

## Methodology

### Step 1: Margin Stack Analysis

Build the full margin stack for the trailing twelve months (TTM) and each of the prior 4 full fiscal years:

| Metric | Formula | Benchmark |
|--------|---------|-----------|
| Gross Margin | (Revenue - COGS) / Revenue | Compare to sector median and 5-year own history |
| EBITDA Margin | EBITDA / Revenue | Useful for comparing across capital structures |
| EBIT (Operating) Margin | EBIT / Revenue | Core operating profitability; excludes financing |
| Net Margin | Net Income / Revenue | Bottom line; sensitive to tax and interest |
| FCF Margin | Free Cash Flow / Revenue | Cash-adjusted; preferred quality indicator |

For each margin:
- Calculate 5-year trend (expanding, stable, or contracting)
- Compare to sector peer median (top quartile, median, or bottom quartile)
- Flag divergences between adjacent margins (e.g., gross expanding but operating contracting = opex leverage failure)

### Step 2: ROIC vs. WACC Analysis

Return on Invested Capital (ROIC) = NOPAT / Invested Capital

Where:
- NOPAT = EBIT × (1 - Effective Tax Rate)
- Invested Capital = Total Equity + Total Debt - Excess Cash (or: Net PP&E + Net Working Capital + Goodwill + Other Intangibles)

ROIC - WACC = **Economic Spread**

| Spread | Interpretation |
|--------|----------------|
| >+5% | Strong value creation; moat likely present |
| +1% to +5% | Modest value creation; competitive position adequate |
| -1% to +1% | Breakeven; covering cost of capital but not creating wealth |
| < -1% | Value destruction; growth investments are reducing intrinsic value |

Track ROIC trend over 5 years. A declining ROIC approaching WACC is an early warning of moat erosion even before it shows up in revenue growth.

### Step 3: DuPont ROE Decomposition

ROE = Net Margin × Asset Turnover × Financial Leverage

Where:
- Net Margin = Net Income / Revenue (profitability)
- Asset Turnover = Revenue / Total Assets (efficiency)
- Financial Leverage = Total Assets / Equity (balance sheet risk)

Decompose ROE for each of the past 5 years. Identify what is driving ROE:

| ROE Driver | Signal |
|-----------|--------|
| High net margin improvement | Genuine business improvement |
| High asset turnover improvement | Operational efficiency gains |
| High leverage increase | Financial engineering, not operational improvement |
| All three declining | Broad deterioration; high conviction short signal |

Red flag: ROE high (>20%) driven primarily by leverage (leverage multiplier >3x) rather than margin or asset efficiency.

### Step 4: Cross-Sector Profitability Benchmarking

Compare gross margin, EBIT margin, ROIC, and ROE against 8-12 direct sector peers:
- Rank the company's current profitability on each metric (percentile in peer group)
- Identify whether profitability gap vs. best peers is widening or narrowing
- Note whether sector-wide margin pressure would affect this company more or less than peers (operating leverage analysis)

## Key Questions

1. Is ROIC above WACC, and has that spread been expanding or contracting over the past 3 years?
2. What is driving gross margin trend — is it pricing power, volume leverage, or input cost relief (only the first two are durable)?
3. Is ROE being manufactured through leverage, or does it reflect genuine operational profitability?
4. If revenue grows 0% for the next two years, do current cost structures produce positive ROIC?
5. At what revenue level does the business reach a breakeven ROIC — and how close is the company to that level?

## Red Flags

- ROIC declining toward or below WACC for 2+ consecutive years — value creation is eroding or already gone
- Gross margin declining while operating margin holds flat — company is cutting opex to hide cost-of-goods pressure; unsustainable and will eventually flow through
- ROE above 20% driven by leverage multiplier >3.0 — financial engineering, not a durable advantage; leverage will amplify downside in a revenue shock
- FCF margin persistently below net margin by more than 10 percentage points — earnings not converting to cash; see cash-flow-quality for root cause
- EBITDA margin expanding while revenue growth is negative — mix shift or accounting change rather than genuine improvement; verify against segment data
- Profitability declining while peers are expanding margins — company is losing structural ground in its competitive position

## Source Requirements

**Tier 1 (required):**
- SEC EDGAR 10-K / 10-Q — all margin, ROIC, and ROE inputs must trace to GAAP financials
- FMP, Bloomberg, FactSet, or S&P Capital IQ — peer comparison data, sector median margins, ROIC benchmarks
- Company IR earnings releases — for segment-level margin disclosure and management commentary on cost drivers

**Tier 2 (context only):**
- Analyst research — useful for understanding industry margin dynamics and peer context
- Management earnings call transcripts — for qualitative color on margin trajectory and cost initiatives (Tier 2 for narrative, Tier 1 for confirmed financials)

## Output

- Margin stack table: 5 years of gross, EBITDA, EBIT, net, and FCF margins
- Margin trend classification: expanding / stable / contracting (for each margin)
- ROIC vs. WACC: 5-year trend and current economic spread
- DuPont decomposition: identifies whether ROE is margin-driven, turnover-driven, or leverage-driven
- Peer benchmarking: percentile rank on gross margin, EBIT margin, and ROIC
- Profitability trend conclusion: IMPROVING / STABLE / DETERIORATING
- Note: not individually scored — contributes qualitatively to FH composite score
