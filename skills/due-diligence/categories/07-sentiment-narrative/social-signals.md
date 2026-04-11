---
name: Social Signals
description: Measure retail and social media sentiment across Reddit, StockTwits, and X to identify crowd positioning, crowding extremes, and divergence from institutional consensus
category: sentiment-narrative
type: technique
requires: []
---

## Purpose

Social media signals capture the retail investor crowd's current posture toward a stock. Unlike news sentiment, which reflects professional media coverage, social signals reveal what non-institutional participants are thinking, doing, and amplifying. The signal value is two-directional: moderate positive social sentiment can confirm improving fundamentals, but extreme social bullishness — especially when divorced from fundamentals — is a contrarian warning. The primary value of this sub-skill is detecting crowding extremes before they unwind and identifying divergences between retail enthusiasm and institutional caution.

## Methodology

### Step 1: Measure Mention Volume Against 30-Day Baseline

Collect mention data across the three primary retail social platforms:

- **Reddit**: r/wallstreetbets, r/stocks, r/investing, r/SecurityAnalysis, and any sector-specific subreddits. Measure daily/weekly post and comment counts mentioning the ticker.
- **StockTwits**: Message volume per day using the StockTwits API or aggregator (ticker stream). StockTwits users self-tag sentiment (bullish/bearish) — use this native tagging as a data input.
- **X (formerly Twitter)**: Cashtag mentions ($TICKER) per day. Filter for accounts with established financial focus where possible; pure viral noise (celebrity mention, meme context) should be flagged separately.

Calculate:
- **Current 7-day average daily mentions** across all platforms
- **30-day average daily mentions** as the baseline
- **Mention velocity ratio** = current 7-day average / 30-day average
  - Ratio > 2.0x: significant volume spike — warrants crowding assessment
  - Ratio 1.2x–2.0x: elevated interest — monitor trajectory
  - Ratio 0.8x–1.2x: normal range
  - Ratio < 0.8x: declining interest — potential sentiment exhaustion or sentiment vacuum

### Step 2: Assess Dominant Sentiment Direction

Extract sentiment classification from available data:

- **StockTwits native tags**: calculate % bullish vs. % bearish from the stream. Note: StockTwits users are a retail-leaning sample — interpret accordingly.
- **Reddit post tone**: manually classify top posts by upvote count as: bullish thesis, bearish thesis, neutral/question, meme/humor. Weighted by upvote engagement.
- **X sentiment**: use cashtag stream to classify prevailing tone. Watch for influencer amplification — single high-follower accounts can distort aggregate read.

Classify dominant social sentiment as:
- **STRONGLY BULLISH**: >70% bullish tags, top posts overwhelmingly positive, no significant bear counterpoint
- **BULLISH**: 55-70% bullish, generally positive with some skepticism present
- **MIXED**: 45-55% bullish, competing narratives, meaningful engagement on both sides
- **BEARISH**: 30-45% bullish, or negative posts dominating engagement
- **STRONGLY BEARISH**: <30% bullish, short thesis amplification, high-engagement negative posts

### Step 3: Crowding Assessment — Identify Extreme Positioning

Extreme social sentiment is a contrarian signal, not a confirming one. Assess crowding on the following indicators:

- **Mention velocity > 3.0x baseline**: crowd rushing in — crowding risk is elevated
- **StockTwits bullish tag > 80%** or **< 20%**: sentiment extreme on either side
- **Reddit post frequency from new accounts or low-karma accounts dominant**: indicates potential coordinated retail activity rather than informed sentiment
- **Cashtag trending on X without a fundamental catalyst**: viral amplification without news — short-lived by nature
- **Options market corroboration (if available)**: unusually high call/put ratio on short-dated options combined with social spike confirms retail crowding

Crowding classification:
- **EXTREME BULLISH CROWDING**: 2+ indicators above threshold — contrarian caution signal; historically associated with near-term pullbacks
- **ELEVATED**: 1 indicator at threshold — monitor but not actionable alone
- **NORMAL**: no indicators at threshold — social signal can be read at face value
- **EXTREME BEARISH CROWDING**: heavy short-side social amplification, high bearish tags — potential short squeeze setup; validate with short interest data

## Key Questions

1. Is the mention volume spike driven by a specific catalyst (earnings, news) or is it organic crowd momentum without a trigger?
2. Is the dominant social sentiment aligned with or diverging from the most recent institutional flow data?
3. Are the most-engaged contributors in the discussion sophisticated (detailed fundamental arguments) or noise-level (memes, FOMO)?
4. Has sentiment been at extreme levels for more than 2 weeks? Extended extremes are more concerning than single-day spikes.
5. Is social sentiment improving on good fundamental news, or is it rising despite flat or declining fundamentals — a divergence that warrants caution?

## Red Flags

- Mention velocity exceeds 3.0x the 30-day baseline with no corresponding fundamental catalyst — pure momentum crowding
- StockTwits bullish tag percentage above 85% — historically associated with near-term reversals in retail-heavy names
- Social sentiment strongly bullish while institutional ownership is declining (13F data) — retail filling institutional exit
- Reddit coordination signals (simultaneous post surge from low-karma accounts, identical ticker lists across posts)
- Sentiment held at extreme for 3+ consecutive weeks without fundamental support — exhaustion risk increases
- Social buzz driven by influencer amplification (single account) rather than distributed organic interest
- Cashtag trending simultaneously across multiple unrelated stocks — sector rotation hype, not company-specific conviction

## Source Requirements

- **Reddit**: Reddit API, Pushshift archive, or aggregators (Swaggy Stocks, Quiver Quantitative) — Tier 2 (retail-driven, qualitative)
- **StockTwits**: StockTwits API or web stream — Tier 2 (native sentiment tags add value; user base is retail-skewed)
- **X (Twitter)**: Cashtag stream via Twitter API v2 or aggregators — Tier 2 (high noise; filter for financial accounts)
- **Social aggregators**: Stockbeep, Unusual Whales social feed, Finviz news tab — Tier 2 (convenient but normalize against raw platform data)
- **Options flow** (for crowding corroboration): CBOE data, Unusual Whales, Market Chameleon — Tier 1 when used for crowding cross-check

**Tier classification note**: All social signals are Tier 2. They provide directional color and crowding warnings but never override fundamental or institutional data. Extreme crowding signals are most actionable when confirmed by a Tier 1 signal (institutional flow, options positioning, or valuation).

## Output

- Mention velocity ratio: current 7-day average vs. 30-day baseline (numerical)
- Platform breakdown: Reddit, StockTwits, X — mention volume and dominant tone per platform
- Dominant social sentiment classification: STRONGLY BULLISH / BULLISH / MIXED / BEARISH / STRONGLY BEARISH
- Crowding assessment: EXTREME BULLISH / ELEVATED / NORMAL / EXTREME BEARISH with indicators triggered
- Divergence flag: social sentiment vs. institutional positioning — ALIGNED / DIVERGING (bullish retail, bearish institutional) / DIVERGING (bearish retail, bullish institutional)
- Catalyst attribution: mention spike tied to specific event YES / NO
- Contrarian signal flag: YES (extreme crowding present) / NO with supporting evidence
- Confidence note: quality of social signal (high engagement from informed accounts vs. noise-dominated)
