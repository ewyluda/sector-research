---
name: Thesis Risk Mapping
description: For each bull thesis pillar, define the observable kill condition that would invalidate it, map to monitoring signals, and assign probability and impact ratings
category: risk-assessment
type: technique
requires: []
---

## Purpose

A thesis without falsification criteria is a belief, not an investment argument. Thesis risk mapping forces explicit definition of the conditions under which each core bull assumption fails. The discipline serves two functions: it identifies what to monitor (so position management is proactive, not reactive), and it exposes theses that cannot be falsified — which are the most dangerous because they admit no exit trigger.

The technique does not require pessimism about the investment. A strong bull case can still have clear kill conditions — the clarity is what makes the position manageable. An investor who knows exactly what would change their mind is in a far better position than one who will always find a reason to stay bullish.

## Methodology

### Step 1: List Bull Thesis Pillars

Extract the explicit or implicit bull thesis pillars. These are the key assumptions that must hold for the investment to generate the expected return. A well-formed thesis typically has 3-6 pillars.

Identify pillars from:
- Analyst research reports (bull case assumptions)
- Investor presentations and management guidance
- Solution agent or thesis agent output if available in the platform
- Your own articulation of why this investment should outperform

Example format for each pillar:
- **Pillar 1**: Market share gains in enterprise software as legacy vendors lose ground
- **Pillar 2**: Gross margin expansion from 65% to 72% as product mix shifts to high-margin SaaS
- **Pillar 3**: Management team's track record of successful M&A creates value-accretive acquisition runway

Each pillar should be a specific, positive claim — not a generic "the business is good" statement.

### Step 2: Define Observable Kill Conditions

For each pillar, define the specific, observable condition that would demonstrate the pillar is false. Kill conditions must be:
- **Observable**: based on data that can actually be obtained (earnings reports, SEC filings, channel checks, market data)
- **Specific**: not vague ("growth slows") but concrete ("revenue growth falls below 10% YoY for two consecutive quarters")
- **Binary or threshold-based**: the condition is either met or not met

Kill condition format: "The pillar is invalidated when [specific metric] [crosses threshold] for [duration/confirmation period]."

Examples:
- Pillar 1 kill condition: "Market share gains are invalidated when two consecutive quarters show flat or declining win rate in competitive deal disclosures, or when enterprise NPS falls below 40."
- Pillar 2 kill condition: "Margin expansion is invalidated when gross margin in any trailing twelve months is below 64% or when the company guides explicitly for margin compression due to mix shift."
- Pillar 3 kill condition: "M&A value creation is invalidated when a completed acquisition results in goodwill impairment, or when acquired business achieves <50% of pro-forma revenue targets in the first 18 months post-close."

**Unfalsifiable pillar examples** (red flags to rewrite or reject):
- "Management is talented" — no observable kill condition
- "The TAM is large" — large TAMs do not guarantee execution
- "The brand is strong" — brand strength without a measurable anchor is not falsifiable

### Step 3: Map to Monitoring Signals

For each kill condition, identify the leading indicators and data sources that would give advance warning before the kill condition is triggered. These become the ongoing monitoring checklist for the position.

Monitoring signal types:
- **Earnings-based**: quarterly revenue growth rate, gross margin trend, customer count or ARR, guidance tone
- **Operational**: headcount changes, product launch timing, customer churn disclosures
- **Competitive**: competitor earnings calls, win/loss disclosures, pricing announcements
- **Market-based**: relative stock performance vs. peers, options market implied volatility, short interest changes
- **Regulatory**: SEC filings, regulatory announcements, legal docket changes
- **Management behavior**: insider selling patterns, change in forward guidance language, executive departures

For each pillar, list 2-4 monitoring signals that would give 1-3 quarter advance warning before the kill condition is officially confirmed.

### Step 4: Assign Probability and Impact

For each identified risk (pillar + kill condition pair), assign:

**Probability** (likelihood kill condition is triggered within the investment horizon):
- **Unlikely** (<15%): kill condition requires a significant departure from current trajectory
- **Possible** (15-35%): kill condition is a realistic downside scenario within normal variance
- **Likely** (35-60%): kill condition has meaningful probability given current trends
- **Expected** (>60%): kill condition appears to be the base case trajectory

**Impact** (effect on thesis if kill condition is triggered):
- **Moderate**: one pillar falls but remaining pillars still support a reduced but positive expected return
- **Significant**: pillar is central enough that its failure reduces expected return below the risk-free rate
- **Thesis-ending**: pillar failure renders the entire investment thesis invalid — position should be exited

**Risk matrix output**: for each pillar, record [Pillar Name | Kill Condition | Probability | Impact | Current Status].

Current status should be one of:
- **Intact**: no evidence the kill condition is approaching
- **Monitoring**: leading indicators showing early-stage deterioration; heightened watch
- **Triggered**: kill condition has been met or is in the process of being confirmed

## Key Questions

1. Can every bull pillar be falsified with a specific, observable condition? If not, which pillars are unfalsifiable and why?
2. Are any kill conditions currently in monitoring or triggered status? If so, does the current position size reflect that?
3. Which single pillar failure would cause the most damage to the overall thesis?
4. Are the monitoring signals for each pillar available on a quarterly or more frequent basis, or is there a long blind spot between signal and confirmation?
5. Is there a pillar with both a high probability of being triggered and a thesis-ending impact? If so, this is the primary risk to the position.
6. Have any of the kill conditions been triggered historically for this company or in similar companies, providing base rate data on likelihood?

## Red Flags

- Any bull thesis pillar that cannot be assigned a specific, observable kill condition — unfalsifiable pillars are the most dangerous because they enable rationalization of any negative data
- Kill conditions that can only be confirmed 12+ months after the underlying dynamics have shifted (long blind spots between signal and confirmation)
- A pillar rated "Likely" or "Expected" probability of triggering combined with "Significant" or "Thesis-ending" impact — this combination suggests the position should not be held at full size
- Multiple pillars in monitoring status simultaneously — convergent pillar pressure is far more dangerous than isolated single-pillar stress
- Kill conditions that have already been triggered but the investor is rationalizing why "this time is different"
- Monitoring signals that rely entirely on management disclosure rather than independent data sources — management has incentives to delay negative disclosures
- Thesis built on 2 or fewer pillars — insufficient diversification of thesis foundations; one failure ends everything

## Source Requirements

- **Earnings reports and transcripts**: SEC EDGAR (10-K, 10-Q), FMP earnings transcripts, platform earnings_review agent — Tier 1
- **Analyst research**: sell-side initiation reports, sector research — Tier 2 (for pillar identification)
- **Competitive intelligence**: competitor earnings calls, industry conferences, trade publications — Tier 2
- **Insider transactions**: SEC Form 4 filings via EDGAR — Tier 1
- **Options market data**: yfinance options chain, implied volatility surface — Tier 2
- **Platform thesis agent output**: platform-generated bull/bear synthesis — Tier 2 (starting point for pillar extraction)

## Output

- Bull thesis pillars list (3-6 items) with explicit statement of each assumption
- Thesis risk map table: [Pillar | Kill Condition | Monitoring Signals | Probability | Impact | Current Status]
- Prioritized risk list: pillars ranked by probability × impact
- Unfalsifiable pillar warnings (if any pillars cannot be assigned kill conditions)
- Monitoring cadence recommendation: which signals to track quarterly vs. monthly vs. continuously
- Overall thesis integrity rating: STRONG (all pillars intact, no monitoring flags) / MODERATE (1-2 pillars in monitoring, no triggers) / STRESSED (1+ pillars triggered or multiple in monitoring) / INVALID (core pillar kill condition confirmed)
