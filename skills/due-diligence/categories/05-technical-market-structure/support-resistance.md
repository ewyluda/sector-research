---
name: Support & Resistance
description: Identify key price levels from volume profile, prior highs/lows, and moving average confluence to define entry zones, stop placement, and price targets
category: technical-market-structure
type: technique
requires: [price-history]
---

## Purpose

Define the structural price architecture of the stock — the levels where buyers and sellers have repeatedly transacted, and where future price action is likely to pause, reverse, or accelerate. Support and resistance levels are not arbitrary — they reflect the collective memory of market participants who bought or sold at specific prices and will act again when price returns to those levels.

This skill produces a practical map of 3 support levels and 3 resistance levels that directly feed into position management decisions: entry zone selection, stop-loss placement, and price target setting.

## Methodology

**Step 1 — Volume profile analysis (primary method)**

Volume profile shows where the most trading activity has occurred over a historical period. High-volume nodes (HVNs) represent prices where large amounts of stock changed hands — these become strong support or resistance because many participants have a vested interest in defending those levels.

Identify:
- **Point of Control (POC)**: The single price level with the highest volume over the measurement period. This is the strongest magnet for price action.
- **High-Volume Nodes (HVNs)**: Price levels with 2x+ average volume density — act as strong support (below current price) or resistance (above current price)
- **Low-Volume Nodes (LVNs)**: Price levels with sparse volume — price tends to move quickly through these zones; they do not provide meaningful support or resistance

If a volume profile tool is unavailable, substitute with a price density map derived from the daily price history: calculate the frequency of closes within each $0.50-$1.00 price band over the trailing 52 weeks. High-frequency bands function as HVNs.

**Step 2 — Prior highs and lows (structural method)**

Historical price extremes serve as support and resistance because they mark levels where supply overwhelmed demand (prior highs = resistance) or where demand overwhelmed supply (prior lows = support).

Identify key price levels at:
- **6-month prior high and low**: Near-term structural levels with active market memory
- **52-week prior high and low**: Medium-term structural levels; 52-week high in particular is a psychologically significant resistance level for breakout analysis
- **All-time high (if applicable)**: The most significant resistance level — also a breakout level with upside price discovery potential
- **Gap levels**: Price gaps on daily charts (unfilled) often act as magnets for fill attempts and then as support/resistance

**Step 3 — Moving average confluence**

When multiple moving averages cluster near the same price level, they create a confluent support or resistance zone that is significantly stronger than any single MA.

Evaluate confluence at:
- **50 DMA / 100 DMA / 200 DMA convergence zones**: If these three averages are within 3-5% of each other at the same price level, the zone is high-confidence support (if below price) or resistance (if above)
- **MA slope consistency**: A rising 200 DMA below a rising 50 DMA creates dynamic support that strengthens over time
- **Price retests of MAs**: Each successful retest of an MA as support (bounce from the level) increases the probability that future retests will also hold

**Step 4 — Compile the level table**

Synthesize the three methods to identify the 6 key levels:

For each level, record:
- **Price**: The specific price or narrow range ($0.50 width maximum)
- **Source**: Volume profile / prior high-low / MA confluence / combination
- **Confluence count**: How many methods converge at this level (1 = weak, 2 = moderate, 3 = strong)
- **Last test**: When did price last interact with this level, and what was the result (bounced, broke through, approaching)
- **Confidence**: HIGH (3 confluent methods or clean historical bounces) / MODERATE (2 methods) / LOW (1 method, limited test history)

**Step 5 — Entry and exit zone definition**

Apply the level map to position management:

- **Entry zone**: The highest-confidence support level below current price that offers a favorable risk/reward ratio. The ideal entry is when price pulls back to support in an established uptrend (Stage 2). Avoid entering at resistance or in the middle of a range with no nearby support.
- **Stop-loss placement**: Just below the entry support level (typically 3-5% below the level to avoid false breakdowns). The stop defines your maximum loss on the trade — if price closes below the defined support level, the analysis was wrong.
- **Primary target**: The first significant resistance level above entry. Calculate reward-to-risk: (Target - Entry) / (Entry - Stop). Minimum 2:1 ratio required; 3:1 or better is preferred.
- **Secondary target**: The second resistance level if primary is breached on volume.

## Key Questions

1. Where is the highest-volume price node over the trailing 52 weeks — and is current price above or below it?
2. What are the 3 nearest support levels, and how many times has price bounced from each?
3. What is the nearest overhead resistance, and how significant is it (single-method vs. confluent)?
4. Is the 200 DMA acting as dynamic support — is it rising and below the current price?
5. Are there unfilled price gaps on the chart that could act as support (gap below price) or resistance (gap above price)?
6. Does the current price location relative to support and resistance offer a favorable risk/reward setup, or is price in the middle of a wide range?
7. What would have to happen technically for the support/resistance map to become invalid (e.g., index collapse, sector rotation out)?

## Red Flags

- Price sitting directly at major resistance with no catalyst — poor risk/reward for new longs
- All significant support levels more than 15% below current price — wide, unprotected risk
- Price in a low-volume node — likely to move quickly in either direction; high-whipsaw risk
- Multiple prior highs clustering just above current price — heavy overhead supply
- 52-week high acting as resistance multiple times without a breakout — distribution phase, not breakout setup
- Support levels formed in a different market environment (e.g., 2020 COVID lows) may be less reliable in current regime
- Failed support retests (price broke below a level, rallied back, then rejected again) — former support now acting as resistance (role reversal)

## Source Requirements

**Tier 1 (required):**
- Exchange data: daily OHLCV — minimum 2 years for meaningful prior high/low analysis and volume profiling
- Platform: `GET /api/agent/data/{ticker}/price-history` (daily price data for structural level identification)
- Platform: `GET /api/agent/data/{ticker}/technical` (pre-calculated 50/200 DMA for confluence analysis)

**Tier 2 (supplementary):**
- Charting platforms with volume profile overlays (TradingView, Thinkorswim, Interactive Brokers) for visual validation
- Options open interest by strike (max pain analysis) as a cross-reference for short-term magnetic levels

## Output

- Support level table:
  | Level | Price | Source | Confluence | Last Test | Result | Confidence |
  |-------|-------|--------|------------|-----------|--------|------------|
  | S1 (nearest) | $X.XX | ... | 1-3 | Date | Bounced/Broke | HIGH/MOD/LOW |
  | S2 | $X.XX | ... | 1-3 | Date | Bounced/Broke | HIGH/MOD/LOW |
  | S3 (deepest) | $X.XX | ... | 1-3 | Date | Bounced/Broke | HIGH/MOD/LOW |

- Resistance level table (same format, 3 levels above current price)
- Point of Control (POC): $X.XX — highest-volume price level over trailing 52 weeks
- Entry zone recommendation: price range, rationale, stop-loss level, primary target, reward-to-risk ratio
- Key observation: where does current price sit in the support/resistance architecture?
