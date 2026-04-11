---
name: Leadership Assessment
description: Evaluate CEO and CFO track records, tenure stability, prior company performance, and strategic consistency
category: management-governance
type: technique
requires: []
---

## Purpose

Assess whether the current executive team has the experience, incentives, and judgment to compound shareholder value over time. Leadership quality is difficult to quantify, but it is not unmeasurable — executives leave track records at prior companies, make public commitments on earnings calls, and either follow through or they don't.

The distinction between founder-led and professional management matters significantly: founders typically have stronger alignment (equity concentration, reputational stakes) but may lack operational discipline; professional managers may have superior process but weaker ownership mentality.

## Methodology

**Step 1 — Executive background review**

For the CEO and CFO, compile:
- Full prior employment history (roles, companies, tenures)
- Whether they founded, built, or inherited the business
- Industry depth: have they operated in this specific business model before, or are they a generalist?
- Board composition: what is their network, and are they bringing relevant expertise?
- Notable achievements and failures at prior organizations — both matter

For founder-led companies: assess the founder's transition from founder-mode (hands-on builder) to operator (system and process). Founders who cannot scale themselves with the company become bottlenecks.

For professional management: assess the hiring rationale. Was the hire driven by operational need (domain expertise), financial engineering (cost-cutting mandate), or board politics? The mandate shapes behavior.

**Step 2 — Tenure and turnover analysis**

Review C-suite changes over the trailing 5 years:
- Count departures of CEO, CFO, COO, CTO, and business unit heads
- Classify each departure: voluntary (retirement, new opportunity), involuntary (fired), or ambiguous
- Assess severance disclosures in proxy statements — large severance packages on "mutual agreement" departures often signal involuntary exits
- Benchmark turnover against sector peers: some industries have naturally higher executive mobility (technology vs. utilities)

Acceptable turnover: one planned CEO succession or one CFO change per 5-year period. Elevated risk: 2+ C-suite departures in 12 months without a clear strategic rationale.

**Step 3 — Prior company performance during their tenure**

For the CEO (and CFO if relevant), pull public data from their prior companies:
- Total shareholder return (TSR) during their tenure vs. the S&P 500 and sector index
- Revenue and earnings growth trajectory under their leadership
- Did the company's ROIC improve, hold flat, or decline?
- Were there any notable failures: missed guidance repeatedly, led a company into financial distress, value-destructive acquisitions?

Adjust for macro conditions: a CEO who outperformed in a bear market environment or turnaround situation deserves more credit than one who delivered in a rising tide.

**Step 4 — Strategic consistency**

Assess whether management delivers on what they publicly commit to:
- Pull the last 3 annual Investor Day or long-range plan presentations
- Compare stated targets (revenue, margins, ROIC, market share) to actual outcomes 12-24 months later
- Classify management on a consistency spectrum: DELIVERS / ADJUSTS REASONABLY / MISSES REPEATEDLY
- Distinguish between ambitious targets that were missed by a narrow margin (acceptable) vs. systematic overstatement (credibility killer)
- Listen for language shifts in earnings calls: do they maintain consistent framing or constantly redefine success to match outcomes?

## Key Questions

1. Has this CEO built sustainable shareholder value at a prior organization — not just presided over a favorable macro environment?
2. Are C-suite departures increasing in frequency, and does the stated reason match the observable pattern?
3. What specific commitments did management make at the last Investor Day, and how closely did they deliver?
4. Is this a founder-led business — and if so, does the governance structure allow for appropriate oversight without stifling execution?
5. Is the CFO a strategic partner to the CEO or primarily a financial controller? Strong CFOs typically build analyst credibility independently.

## Red Flags

- CEO with a consistent pattern of missed guidance at prior companies (>50% of major targets)
- Multiple CFO departures within a 3-year window — CFOs who leave abruptly often signal accounting or strategic disagreements
- Investor Day targets set so far out (5+ years) that accountability is effectively deferred
- Founder refusing to build succession depth — no COO, no internal candidates, over-reliance on one person
- Management team assembled from personal networks rather than operational expertise
- CEO with no meaningful financial stake in the company (options only, no open-market purchases)
- Rapid strategic pivots without clear explanation — each new initiative disowns the prior one

## Source Requirements

**Tier 1 (required for this analysis):**
- SEC EDGAR: DEF 14A (proxy statement) — executive bios, compensation, board composition, tenure history
- Company IR: earnings call transcripts (Investor Day, quarterly calls) for stated commitments
- FMP / platform data provider: management endpoint (`get_management`) for current executives
- Prior employer 10-K/proxy filings for tenure dates and financial performance

**Tier 2 (qualitative context only):**
- News and press: leadership announcements, departure coverage, profile interviews
- LinkedIn: career history verification, board cross-memberships
- Glassdoor/Blind: employee sentiment on leadership (directional only — not scored)

## Scoring

**Leadership Score (0-100)**

| Factor | Weight | Score Bands |
|--------|--------|-------------|
| Track record at prior companies (TSR, ROIC trend) | 40% | Strong outperformance = 80-100; Inline = 50-70; Underperformance = 0-40 |
| Tenure stability (C-suite turnover rate) | 30% | <1 departure/3yrs = 90-100; 1-2 = 60-80; 3+ = 0-40 |
| Strategic consistency (Investor Day hit rate) | 30% | >80% targets met = 80-100; 60-80% = 50-70; <60% = 0-40 |

Score ranges:
- 80-100: Strong leadership — experienced, stable, accountable
- 60-79: Adequate — some concerns in track record or follow-through
- 40-59: Mixed — meaningful gaps in experience or consistency
- 0-39: Weak — material track record failures or instability

## Output

- Leadership Score (0-100) with sub-factor breakdown
- CEO/CFO background summary (prior roles, relevant experience, industry depth)
- C-suite turnover log (trailing 5 years) with departure classification
- Investor Day commitment scorecard (last 2-3 presentations vs. actual outcomes)
- Founder-led vs. professional management classification with alignment assessment
- Strategic consistency rating: DELIVERS / ADJUSTS REASONABLY / MISSES REPEATEDLY
- Top leadership risk and monitoring signal
