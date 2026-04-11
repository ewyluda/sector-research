---
name: Stop-Loss & Invalidation
description: Define thesis invalidation conditions that combine price-based stops with fundamental deterioration triggers — distinguishing market noise from genuine thesis failure requiring exit
category: position-management
type: technique
requires: []
---

## Purpose

A stop-loss is not a price level. A stop-loss is a definition of thesis failure — and thesis failure can manifest as a price event, a fundamental event, or both simultaneously. The most common error in stop-loss design is treating a percentage price decline as equivalent to thesis invalidation. It is not.

**Stock drops 15% on no news**: This is market noise. It is not thesis invalidation. The business has not changed. The investor who exits here is not managing risk — they are letting short-term price volatility override a fundamental analysis that may still be correct.

**Stock drops 15% because the company's largest customer publicly terminated their contract**: This is thesis invalidation. The business has materially changed. The investor who does not exit here is rationalizing, not being patient.

The distinction matters enormously. Price-only stops cause investors to exit valid positions during normal drawdowns. Fundamentals-only stops cause investors to watch a position deteriorate for quarters while waiting for a data point that "confirms" what price already reflected.

Effective stop-loss design uses both: a price floor below which the risk/reward has degraded beyond acceptable levels, AND a fundamental trigger that confirms the thesis is broken. Either condition alone can be sufficient to exit — they are OR conditions, not AND conditions.

## Methodology

### Step 1: List Thesis Invalidation Conditions

Begin with the thesis risk map from the risk assessment phase (thesis-risk-mapping sub-skill). Extract the kill conditions for each bull thesis pillar. These become the candidate fundamental invalidation triggers.

For each pillar kill condition, evaluate:
- **Data availability**: Can this condition be confirmed from publicly available data (SEC filings, earnings reports, press releases) within 2-4 weeks of the event? If not, the kill condition is too slow to be a useful stop.
- **Objectivity**: Is the condition based on a measurable threshold (revenue growth below X%, gross margin below Y%) or on a subjective judgment ("management seems less confident")? Objective conditions are enforceable; subjective ones are rationalized away.
- **Materiality**: Does triggering this kill condition actually impair the investment thesis, or is it a yellow flag that warrants monitoring rather than exit?

Classify each kill condition as:
- **Hard stop**: fundamental condition that, if confirmed, requires full or majority exit within 2-3 trading days. No waiting for "one more quarter."
- **Review trigger**: fundamental condition that requires an immediate deep-dive review but does not require immediate exit. Position may be trimmed while review is underway.

Target: 2-4 hard stop conditions and 3-6 review triggers for a well-structured position.

### Step 2: Set the Price-Based Stop

The price-based stop is a floor that protects against scenarios where fundamental deterioration has occurred but has not yet been publicly confirmed, or where the investment thesis was simply wrong about the business.

**Price stop placement guidelines**:
- The price stop should be 15-25% below the entry price, calibrated to the volatility profile of the stock
- Lower volatility stocks (beta < 0.8): 12-18% below entry — tighter stop because large moves are less common
- Average volatility stocks (beta 0.8-1.3): 15-22% below entry — standard range
- Higher volatility stocks (beta > 1.3): 20-28% below entry — wider stop to avoid being shaken out by normal volatility

**Align with technical support**: The price stop should coincide with or be slightly below a meaningful technical support level. A stop placed 18% below entry that corresponds to the prior year low is stronger than one placed at an arbitrary percentage.

**Avoid round numbers**: Stops placed at exactly $50.00 or exactly -20% are often triggered by algorithmic trading targeting those levels. Place stops at slightly unconventional levels ($47.85, -17.3%).

**Price stop logic**: If price falls to the stop level AND there is no fundamental explanation (no news, no data, no visible reason), the appropriate response is:
1. Check for broad market selloff context — if the market is down 5%+ and the position is down proportionally, the stop may be temporarily suspended for 2-3 days while market conditions normalize
2. Check short interest and options activity for signs of a technical squeeze rather than fundamental selling
3. If price remains below stop for 3+ days without recovery, exit regardless of absence of fundamental trigger — the market may know something you do not

**Price stop is not a limit order**: The stop is a decision rule, not an automatic execution. Exercise judgment on intraday spikes vs. genuine closes below the stop level.

### Step 3: Define Fundamental Stop Conditions

Fundamental stops are event-based. They do not require price to reach a specific level — they require a specific piece of information to become public.

**Hard stop examples** (exit within 2-3 trading days):
- Revenue growth misses guidance by more than 500 basis points for two consecutive quarters, with management guidance revision downward
- Gross margin falls below the pre-defined threshold (e.g., below 60%) in any reported quarter, attributed to competitive pricing pressure
- Largest customer (>20% of revenue) publicly reduces or terminates the relationship
- Management reduces full-year guidance by more than 10% citing demand deterioration (not macro — demand-specific)
- CEO or CFO departure accompanied by an earnings restatement or SEC investigation announcement
- Acquisition announcement at greater than 15× revenue where the acquired business has no positive cash flow

**Review trigger examples** (immediate deep-dive, possible trim):
- Revenue growth misses guidance by 200-500 basis points in a single quarter with a cautious but maintained full-year outlook
- Gross margin compresses 200-300 basis points but management attributes it to temporary product mix and provides specific recovery timeline
- Key executive departure without immediate succession plan
- Competitor announces a product that directly competes with the most margin-accretive part of the business
- Insider selling cluster: 3+ executives sell meaningful positions within a 30-day window

**Distinguish from monitoring signals**: Fundamental stops require a response (exit or review). Monitoring signals (from the monitoring-inflections sub-skill) are regular check-ins that may or may not require action.

### Step 4: Define the Response Protocol

For each stop condition, pre-commit to the response. The response must be decided before the position is open.

**Full exit response** (applicable to hard stops):
- Position is reduced to zero within 2-3 trading days
- No waiting for "the next quarter to see if it improves"
- No averaging down after a hard stop trigger
- Re-entry is only permitted after a full thesis rebuild from scratch, with fresh analysis

**Trim to half response** (applicable to review triggers, pending review outcome):
- Position is reduced to 50% of current size immediately upon trigger
- Full exit or restoration to full size is decided within 2-3 weeks based on review findings
- If review is inconclusive, default to continued hold at half size until the next earnings report provides clarity

**No response (monitor only)** is not a response protocol. Every condition should map to either "investigate and maintain," "trim to half," or "exit fully."

## Key Questions

1. Can every hard stop condition be confirmed from public data within 2-4 weeks of the event occurring?
2. Is every fundamental stop condition objective and measurable, or are any of them subjective judgments that could be rationalized away?
3. Does the price stop align with a meaningful technical support level, or is it an arbitrary percentage?
4. Have the hard stop conditions been distinguished from review triggers — is it clear which conditions require exit vs. which require a deep-dive?
5. If a hard stop condition is triggered tomorrow, is the response pre-committed to full exit, or will there be deliberation about "waiting one more quarter"?
6. Is the price stop set wide enough to survive normal volatility for this stock's beta profile, while still being close enough to entry to be a meaningful risk limit?

## Red Flags

- Stop-loss defined only as a percentage price decline with no connection to fundamental events — cannot distinguish noise from signal
- Hard stop conditions that take more than 4-6 weeks to confirm from public data — too slow to be actionable
- Fundamental stop conditions written in subjective language ("management seems less confident," "growth is decelerating") — impossible to enforce because they can always be rationalized away
- Response protocol that maps every condition to "investigate" — investigation without pre-committed exit criteria is analysis paralysis during drawdown
- Averaging down after a hard stop condition is triggered — adding to a position whose thesis has been invalidated is not discipline; it is denial
- Price stop set so tight (below 10% from entry) that it will be triggered by normal volatility before the thesis has a chance to play out
- Price stop set so wide (above 30% from entry) that it renders the stop meaningless as a risk management tool
- Reviewing the stop conditions after a significant price decline and revising them to be more lenient — this is rationalization, not risk management

## Source Requirements

- **Platform thesis agent and risk assessment (thesis-risk-mapping)**: bull pillar kill conditions that become candidate fundamental stops — Tier 1
- **Platform technical agent**: support levels, beta, 52-week range for price stop calibration — Tier 1
- **Platform fundamentals agent**: revenue growth trends, gross margin history, earnings guidance — Tier 1 for threshold calibration
- **SEC EDGAR Form 4**: insider transaction data for insider selling cluster detection — Tier 1
- **Platform earnings review agent**: earnings vs. guidance comparison for consecutive miss detection — Tier 1
- **Market data**: beta, implied volatility for volatility-appropriate stop width — Tier 2

## Output

- 2-4 hard stop conditions: each with specific observable trigger, confirmation source, and full exit response
- 3-6 review trigger conditions: each with specific observable trigger and trim-to-half response
- Price-based stop: specific price level (not a percentage), technical support anchor, and exception protocol for market-wide selloffs
- Response protocol summary table: [Condition | Type | Trigger | Response | Timeline]
- Invalidation log template: a pre-formatted record to fill in if and when any stop condition is triggered, documenting the date, condition met, price at trigger, and action taken
