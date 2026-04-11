---
name: Insider Activity
description: Analyze Form 4 SEC filings to identify net insider buying and selling patterns, cluster signals, and contextual intent
category: management-governance
type: technique
requires: [insider-trading]
---

## Purpose

Insiders — executives, directors, and major shareholders — have access to non-public information about the business. While they cannot trade on material non-public information, their discretionary buying and selling of company stock in the open market is a meaningful signal of their conviction in the stock's valuation relative to fundamentals.

The key insight is asymmetric interpretation: insider buying is almost always a positive signal (insiders have many uses for cash but choose to buy company stock), while insider selling must be contextualized (insiders sell for many reasons — diversification, tax planning, life events — and most are not informational signals).

## Methodology

**Step 1 — Pull Form 4 filings for the last 12 months**

Form 4 must be filed within 2 business days of any insider transaction. Pull all Form 4 filings for the company over the trailing 12 months. For each transaction, record:
- Insider name and title (CEO, CFO, Director, >10% shareholder)
- Transaction date
- Transaction type: open-market purchase, open-market sale, option exercise, gift, planned 10b5-1 sale
- Shares transacted and price per share
- Post-transaction holdings (shares owned directly and indirectly)
- Whether transaction was part of a 10b5-1 pre-planned trading program

Focus on open-market transactions — these are the only discretionary signals. Option exercises are mechanical (exercise-and-sell is not a sell signal; exercise-and-hold is a modest positive). Gifts are neutral. RSU vesting and automatic sell-to-cover are neutral.

**Step 2 — Net buy/sell ratio by insider and in aggregate**

Calculate for each insider and in aggregate across the trailing 3, 6, and 12 months:
- Total shares purchased (open-market only)
- Total shares sold (open-market, excluding 10b5-1 and exercise-and-sell)
- Net shares: purchases minus discretionary sales
- Net dollar value of transactions
- Net buy/sell ratio: total purchase value / (total purchase value + total sale value)

Classify each period:
- Net buy ratio > 60%: net buyers
- Net buy ratio 40-60%: neutral / mixed
- Net buy ratio < 40%: net sellers

**Step 3 — Cluster analysis**

Cluster buying is a substantially stronger signal than single-executive buying. A cluster is defined as 3 or more distinct insiders (not the same person multiple times) making open-market purchases within a 30-day window.

Evaluate:
- How many insiders bought in the most recent 30-day period?
- Are they diverse (CEO + CFO + Directors) or concentrated in one role?
- Is the cluster buying occurring near a specific price level — suggesting insiders view it as a floor?
- Did any cluster buying follow a significant stock price decline (insiders stepping in on weakness)?

Cluster signals by strength:
- 5+ insiders buying within 30 days: VERY STRONG bullish signal
- 3-4 insiders buying within 30 days: STRONG bullish signal
- 1-2 insiders buying: MODERATE positive signal
- No buying despite price decline: NEUTRAL to cautious
- Cluster selling (3+ insiders selling discretionarily within 30 days): STRONG caution signal

**Step 4 — Context check: 10b5-1 vs. discretionary transactions**

Not all selling is equal. Apply context filters before concluding a sale is bearish:

Selling that is generally NOT informational:
- Pre-announced 10b5-1 trading plans (filed months before execution)
- Selling immediately after IPO or secondary offering lock-up expiration (diversification imperative)
- Selling to cover tax obligations on RSU vesting (often disclosed as "sell to cover")
- Selling by retirement-age directors at a regular schedule
- First-time post-IPO sales by founders within 12 months of listing

Selling that IS a potential signal:
- Selling not covered by a prior 10b5-1 plan
- Selling that accelerates in size or frequency vs. prior periods
- Multiple insiders selling simultaneously without 10b5-1 coverage (discretionary cluster selling)
- Selling into stock weakness (below 52-week average) by operating executives
- Selling by executives who have simultaneously communicated bullish forward guidance

## Key Questions

1. Are insiders net buyers or net sellers over the trailing 6 months — and does the pattern align or contradict the public narrative management is telling?
2. Has there been any cluster buying event (3+ insiders) in the past 6 months?
3. What percentage of recent selling is covered by pre-disclosed 10b5-1 plans vs. discretionary?
4. Are the CEO and CFO specifically buying or selling — they have the most complete picture of the business?
5. Is insider ownership as a percentage of shares outstanding increasing or decreasing over time?

## Red Flags

- Discretionary cluster selling (3+ executives selling without 10b5-1 plans) while stock is near all-time highs and management is bullish publicly
- CEO or CFO selling into stock weakness without a pre-established 10b5-1 plan
- Insider ownership percentage declining materially year-over-year through sales (not dilution)
- No open-market purchases by any insider over a 12-month period despite a 20%+ stock price decline
- Executives filing new 10b5-1 plans during positive-news blackout windows, then accelerating sales after plan activation
- Simultaneous sale by multiple directors who recently received restricted stock grants (suggests they don't believe in the long-term story)

## Source Requirements

**Tier 1 (required for this analysis):**
- SEC EDGAR: Form 4 filings (mandatory; 2-day filing deadline)
- FMP / platform data provider: insider trading endpoint (`get_insider_trading`) for structured Form 4 data
- SEC EDGAR: Form 144 (planned block sales notification) for context on large upcoming sales

**Tier 2 (qualitative context only):**
- News: coverage of notable insider transactions (large buys or sells often covered by financial media)
- Company proxy (DEF 14A): beneficial ownership table — aggregate insider ownership percentage

## Scoring

**Insider Activity Score (0-100)**

| Factor | Weight | Score Bands |
|--------|--------|-------------|
| Net buy/sell ratio (trailing 6 months, open-market only) | 40% | >70% net buy = 90-100; 50-70% = 65-80; 30-50% = 40-60; <30% = 0-35 |
| Cluster signal (3+ insiders buying in trailing 6 months) | 35% | 5+ insiders = 90-100; 3-4 = 70-85; 1-2 = 50-65; 0 = 30-40; cluster sell = 0-20 |
| Context quality (% of sales with 10b5-1 / diversification explanation) | 25% | >80% explained = 80-100; 50-80% = 50-70; <50% unexplained = 0-40 |

Score interpretation:
- 80-100: BULLISH — meaningful discretionary buying with no offsetting concerns
- 60-79: NEUTRAL TO POSITIVE — modest buying signals or explained selling
- 40-59: NEUTRAL — no clear directional signal from insiders
- 20-39: CAUTIOUS — net selling with limited buying; monitor closely
- 0-19: BEARISH — cluster selling, selling into weakness, no buying despite price decline

## Output

- Insider Activity Score (0-100) with sub-factor breakdown
- Insider activity signal: BULLISH / NEUTRAL / BEARISH
- Transaction log (trailing 12 months): insider name, date, type, shares, price, 10b5-1 flag
- Net buy/sell summary table by 3-month, 6-month, and 12-month periods
- Cluster event log: any 30-day windows with 3+ insiders transacting
- Context classification for all selling transactions (10b5-1, diversification, discretionary)
- Insider ownership trend: % of outstanding shares held by insiders (trailing 3 years)
