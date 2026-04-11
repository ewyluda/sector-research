---
name: Options Flow
description: Analyze put/call ratios, unusual options activity, max pain, IV rank, and skew to determine how options market participants are positioning and what they expect
category: technical-market-structure
type: technique
requires: [options]
---

## Purpose

The options market is where institutional participants hedge large equity exposures and where sophisticated speculators express directional conviction with leverage. Unusual options activity can reveal positioning before price moves, and the structure of the options market (put/call ratio, skew, IV rank) reflects the aggregate expectation of future volatility and direction.

This skill does not predict the future — it reveals what the largest and most sophisticated market participants are paying to either hedge against or speculate on specific price moves. When unusual activity appears with no obvious catalyst, pay attention: someone with better information may be positioning ahead of a known event.

## Methodology

**Step 1 — Put/call ratio analysis**

Calculate the put/call ratio for the stock:

```
Put/Call Ratio = Total Put Volume / Total Call Volume
```

Evaluate both the single-session ratio and the 20-day trailing average:

| Ratio | Interpretation |
|-------|----------------|
| <0.5 | Very bullish sentiment — excessive call buying, potential contrarian concern (too much optimism) |
| 0.5-0.7 | Bullish sentiment — calls dominating, market participants expecting upside |
| 0.7-1.0 | Neutral to slightly bullish — balanced positioning with mild call preference |
| 1.0-1.3 | Bearish/hedging — put buying exceeds calls; institutional hedging or speculative downside bets |
| >1.3 | Strongly bearish/fear elevated — heavy put buying; potential capitulation zone or genuine institutional concern |

Interpretation caveat: The put/call ratio is both a sentiment indicator and a contrarian indicator at extremes. Very low ratios (<0.5) can signal excessive complacency (contrarian bearish). Very high ratios (>1.5) can signal fear-driven capitulation (contrarian bullish, especially if accompanied by a sharp price decline). Context matters: a rising put/call ratio during a price decline is confirmation; a rising put/call ratio during a price advance is a warning.

**Step 2 — Unusual options activity identification**

Screen for activity that is anomalous relative to normal volume for this stock's options:

- **Volume vs. Open Interest ratio**: Options where volume significantly exceeds open interest (ratio >3x) indicate new positions being opened, not existing positions being closed. New large positions are more informative than OI-based activity.
- **Large block trades**: Single option orders of 500+ contracts ($50,000+ in notional premium) are institutional in scale. Track:
  - Strike price relative to current stock price (ITM/ATM/OTM)
  - Expiration date (weekly = short-term directional bet; LEAPS = longer-term structural view)
  - Whether the trade was a buy or sell (bought at the ask = aggressive buyer with directional conviction; sold at the bid = premium seller, often covered)
  - OTM calls or puts with near-term expiration and large size are the most significant unusual activity signals
- **Sweep orders**: Large orders that sweep multiple exchanges simultaneously are almost always institutional. They indicate urgency — the buyer wants the position immediately at any available price.
- **Spread vs. single-leg**: Large single-leg purchases (naked calls or puts) indicate strong directional conviction. Spreads indicate defined risk hedging.

Document each notable unusual activity event: date, strike, expiration, contract size, premium paid, call/put classification, and directional interpretation.

**Step 3 — Max pain analysis**

Max pain (also called "maximum pain") is the options strike price at which the total value of all outstanding option contracts (both calls and puts) would expire worthless — meaning option sellers (predominantly market makers) would collect maximum premium.

Calculate max pain by finding the strike where the sum of in-the-money call and put values across all open interest is minimized:

```
For each strike K:
  Total loss to option holders = Sum of ITM call value + Sum of ITM put value
Max pain = Strike K that minimizes total option holder value
```

Practical application:
- Max pain is a short-term gravitational force — in the week leading up to monthly options expiration (OpEx), stocks often drift toward the max pain strike as market makers delta-hedge their books
- The effect is strongest in the final 3-5 trading days before expiration and diminishes beyond that window
- Stocks with very large open interest relative to float show the strongest max pain pinning effects
- Use max pain as a near-term target for stocks with heavy options activity, not as a long-term prediction

**Step 4 — Implied volatility (IV) rank and percentile**

Implied volatility (IV) reflects the market's expectation of future price movement embedded in option prices. IV rank compares current IV to its range over the trailing 52 weeks:

```
IV Rank = (Current IV - 52-Week IV Low) / (52-Week IV High - 52-Week IV Low) × 100
```

IV Percentile = percentage of days in the past year where IV was lower than today's reading.

Interpretation:
| IV Rank | Interpretation | Options Strategy Implication |
|---------|----------------|------------------------------|
| >80 | IV very elevated — options expensive, market expecting large move | Expensive to buy options; better environment for premium selling strategies |
| 60-80 | IV elevated — above-average uncertainty or upcoming event | Options carry a premium; directional bets cost more than historical average |
| 40-60 | IV neutral — near-average uncertainty | Options fairly priced; directional buying is not handicapped |
| 20-40 | IV compressed — market not expecting large moves | Options cheap; good environment for buying calls or puts ahead of potential catalyst |
| <20 | IV very compressed — complacency, or low event risk | Cheapest time to buy options; potential for IV expansion on any surprise |

Key application: An unusually large options position combined with low IV rank means the buyer paid a relatively low premium for that bet — suggesting confidence, not desperation. The same position combined with high IV rank means the buyer was willing to pay elevated prices — suggesting even higher conviction or urgency.

**Step 5 — Put/call skew assessment**

Options skew measures the difference in implied volatility between out-of-the-money (OTM) puts and OTM calls at the same delta:

```
Put Skew = IV of OTM puts (e.g., 25-delta put) - IV of OTM calls (e.g., 25-delta call)
```

A positive put skew (puts more expensive than equivalent calls) is the normal state — investors chronically overpay for downside protection. However, the degree of skew is informative:

- **Steep put skew (>5% IV differential)**: Institutional investors are actively paying up for downside protection. This reflects genuine concern about tail risk, not just routine hedging. Can precede price declines.
- **Flat or inverted skew**: Calls are bid up relative to puts — speculative call buying is dominating. Can precede short squeezes or earnings-driven upside moves, but also signals potential complacency.
- **Sudden skew increase**: A rapid steepening of put skew (over 1-2 sessions) without a corresponding stock price decline often precedes significant institutional risk reduction (selling the stock itself).

## Key Questions

1. Is the put/call ratio above or below 1.0 — and has it been trending in one direction over the past 20 days?
2. Has there been any unusual options activity (large blocks, sweeps, OTM with near-term expiration) in the past 2 weeks — and what directional bet does it imply?
3. Where is the max pain strike for the nearest monthly expiration, and how far is the stock from it?
4. What is the IV rank — and does the current implied volatility suggest options are cheap or expensive relative to the past year?
5. Is put/call skew elevated (>5% differential) — and has it changed materially in the past week?
6. Is the unusual options activity consistent with the fundamental thesis (e.g., large call buying in a stock you are also bullish on), or contradicting it (large put buying in a stock you are bullish on)?

## Red Flags

- Put/call ratio persistently >1.3 over 20 trading days while price is stable or rising — smart money hedging into strength; distribution risk
- Large OTM put blocks with near-term expiration and no public catalyst — possible informed hedging ahead of an undisclosed event
- IV rank >80 approaching earnings — options are expensive; both long calls and long puts face significant IV crush risk post-announcement
- Steep put skew increasing rapidly (>2% in a single session) without an obvious macro or stock-specific catalyst — institutional risk reduction may be imminent
- Max pain significantly below current price one week before monthly expiration — gravitational pull downward
- High put/call ratio combined with a sharp put skew increase and rising RVOL — triple confirmation of institutional concern; de-risk or investigate the cause

## Source Requirements

**Tier 1 (required):**
- Options chains: daily volume, open interest, IV by strike and expiration — minimum trailing 20 days for ratio analysis
- Platform: `OptionsAgent` → `GET /api/agent/data/{ticker}/options` (provides options chain with IV, volume, OI via yfinance)
- CBOE: IV data for skew calculation and IV rank computation (52-week high/low)

**Tier 2 (supplementary):**
- Options flow monitoring services (Unusual Whales, Market Chameleon, Barchart Options) for sweep and block trade identification — not available via platform, manual sourcing
- Sector/index put/call ratios (SPY, QQQ) for broader market hedging context — not available via platform

## Scoring

**Options Flow Score (0-100)** — used as input to TM Score at 20% weight

Base score from put/call ratio (20-day trailing average):
- <0.7 (bullish): 70-80 pts
- 0.7-1.0 (neutral-bullish): 50-70 pts
- 1.0-1.3 (bearish/hedging): 25-49 pts
- >1.3 (strongly bearish): 0-24 pts

Adjustments:
- Large unusual call buying (OTM, near-term, sweep): +10 pts
- Large unusual put buying (OTM, near-term, sweep): -10 pts
- Low IV rank (<20) with bullish flow: +5 pts (cheap to own upside)
- High IV rank (>80) with elevated put/call: -5 pts (hedging at scale)
- Steep put skew (>5% differential) and increasing: -10 pts
- Max pain significantly above current price (near-term expiration <1 week): +5 pts
- Max pain significantly below current price (near-term expiration <1 week): -5 pts

Cap: 0-100.

## Output

- Options Flow Score (0-100) for TM Score input
- Put/call ratio: current session and 20-day trailing average with trend direction
- Put/call interpretation: bullish / neutral / bearish / hedging at scale
- Unusual options activity log: date, strike, expiration, size (contracts), direction (call/put), trade type (sweep/block/spread), directional implication
- Max pain: strike price for nearest monthly expiration, distance from current price, relevance window (days to expiration)
- IV rank: current reading (0-100), interpretation (very cheap / cheap / neutral / elevated / very elevated), 52-week IV high and low
- Put/call skew: current differential, direction (normal / flat / elevated), recent trend (stable / steepening / flattening)
- Options flow alignment with thesis: CONFIRMING / NEUTRAL / CONFLICTING — one-sentence rationale
