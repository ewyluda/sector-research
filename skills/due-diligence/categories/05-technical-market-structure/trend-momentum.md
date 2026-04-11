---
name: Trend & Momentum
description: Assess the direction, strength, and stage of a stock's price trend using moving averages, RSI, MACD, and Weinstein stage analysis
category: technical-market-structure
type: technique
requires: [price-history]
---

## Purpose

Determine whether the stock has an established directional trend, how strong that trend is, and what stage of the market cycle it occupies. Trend analysis answers the most fundamental question in technical analysis: is the market rewarding buyers or sellers of this stock right now?

Momentum indicators confirm or challenge the trend — a strong trend with weakening momentum is a warning; a weak trend with building momentum is an opportunity. The goal is not to predict reversals but to identify the current directional bias and act in alignment with it.

## Methodology

**Step 1 — Moving average analysis**

Calculate and evaluate the 50-day and 200-day simple moving averages (SMA):

- **Price vs. 50 DMA**: Is price above (bullish) or below (bearish) the 50 DMA? How far is it extended (% deviation)?
- **Price vs. 200 DMA**: Is price above (bullish) or below (bearish) the long-term trend line?
- **50 DMA vs. 200 DMA relationship**:
  - Golden cross: 50 DMA crosses above 200 DMA = long-term bullish signal, often marks the beginning of Stage 2 (markup)
  - Death cross: 50 DMA crosses below 200 DMA = long-term bearish signal, often marks the beginning of Stage 4 (markdown)
  - Slope of 200 DMA: rising 200 DMA = healthy uptrend; flat = range; declining = downtrend

Note: a freshly crossed golden or death cross carries more weight than one that occurred 6+ months ago. The further price has moved from the MA lines, the higher the probability of mean reversion before trend continuation.

**Step 2 — RSI (Relative Strength Index) assessment**

Calculate the 14-period RSI (0-100 scale):

- **>70 (overbought zone)**: Momentum is extended but not necessarily a sell signal. In strong uptrends, RSI can remain above 70 for extended periods. Look for RSI failure swings (RSI peaks at lower high while price peaks at higher high) as a bearish divergence signal.
- **30-70 (neutral zone)**: Price is in equilibrium without extreme momentum in either direction. Most reliable RSI signals occur from within this range.
- **<30 (oversold zone)**: Momentum is compressed. In downtrends, can remain below 30. Look for RSI failure swings (RSI makes higher low while price makes lower low) as a bullish divergence signal.

Key divergence patterns:
- **Bullish divergence**: Price makes lower low, RSI makes higher low — momentum exhausting to the downside
- **Bearish divergence**: Price makes higher high, RSI makes lower high — momentum exhausting to the upside

**Step 3 — MACD crossover analysis**

Calculate MACD (12-period EMA minus 26-period EMA) and the 9-period signal line:

- **MACD above signal line**: Short-term momentum is bullish (faster EMA diverging above slower)
- **MACD below signal line**: Short-term momentum is bearish
- **Crossover events**: A MACD crossing above its signal line is a buy momentum signal; crossing below is a sell momentum signal
- **Zero-line relationship**: MACD above zero = both short and medium-term trends are up; below zero = bearish momentum dominates
- **Histogram trend**: Growing histogram bars = trend strengthening; shrinking bars = trend weakening before a potential crossover

Combine: A bullish MACD crossover above zero with RSI in the 50-65 range (not overbought yet) in a stock above its 200 DMA is a high-confidence entry signal. The opposite configuration (bearish crossover, below zero, below 200 DMA, RSI 35-50) is a high-confidence avoidance/exit signal.

**Step 4 — Weinstein stage classification**

Classify the stock into one of four stages based on the relationship between price, volume, and the 30-week (150-day) moving average:

- **Stage 1 — Accumulation**: Price is base-building in a flat range, volume is declining, 30-week MA is flat. Smart money is accumulating a position quietly. No directional action yet — watch for Stage 2 breakout.
- **Stage 2 — Markup**: Price breaks above resistance from Stage 1 on expanding volume, 30-week MA turns upward. This is the ideal time to initiate or add to positions. The trend is your friend.
- **Stage 3 — Distribution**: Price is range-bound at a high level after a prolonged Stage 2, volume is irregular, 30-week MA begins to flatten. Smart money is distributing. Risk of Stage 4 breakdown increases.
- **Stage 4 — Markdown**: Price breaks below Stage 3 support on expanding volume, 30-week MA turns downward. This is the stage to avoid or be short. No buying until Stage 1 re-establishes.

The stages are cyclical — every Stage 4 eventually transitions back to Stage 1, but the timeline can span months to years.

**Step 5 — Classify trend strength**

Combine all signals into a single trend classification:

| Classification | Criteria |
|----------------|----------|
| Strong Uptrend | Price > 50 DMA > 200 DMA, 200 DMA rising, RSI 50-70, MACD above signal and zero, Weinstein Stage 2 |
| Weak Uptrend | Price > 200 DMA but 50 DMA flattening, RSI oscillating 40-65, MACD mixed signals, early Stage 2 or late Stage 1 |
| Range-Bound | Price oscillating around flat 200 DMA, RSI ranging 40-60, MACD near zero with frequent crossovers, Weinstein Stage 1 or Stage 3 |
| Weak Downtrend | Price < 200 DMA, 50 DMA declining but not sharply, RSI 30-50, MACD below signal but flattening, early Stage 4 |
| Strong Downtrend | Price < 50 DMA < 200 DMA, both MAs declining, RSI 20-40, MACD below signal and zero, death cross confirmed, Weinstein Stage 4 |

## Key Questions

1. Is the stock above or below its 200 DMA, and is the 200 DMA itself trending up, flat, or down?
2. Has a golden cross or death cross occurred recently (within 3 months), or is one forming?
3. Is RSI showing a divergence — and if so, is it bullish (potential reversal up) or bearish (potential reversal down)?
4. Is the MACD generating a fresh crossover signal, or has it been trending in one direction for 4+ weeks?
5. What Weinstein stage is this stock in — and how long has it been in this stage?
6. If the stock is in Stage 1, what would a Stage 2 breakout look like (price level, volume confirmation)?
7. If the stock is in Stage 3, what would a Stage 4 breakdown look like, and is there a pre-defined exit plan?

## Red Flags

- Death cross (50 DMA below 200 DMA) with both MAs pointing down
- Bearish RSI divergence: price making new highs while RSI prints lower highs — momentum is not confirming the move
- MACD death cross below the zero line — double confirmation of bearish momentum
- Weinstein Stage 4 classification: the trend is your enemy; avoid until Stage 1 base forms
- RSI below 30 in a downtrend (oversold in a bear) — oversold gets more oversold before reversal
- Price more than 30% above its 200 DMA — extremely extended, high mean-reversion risk
- Declining 200 DMA while fundamentals appear sound — market pricing something the fundamentals have not yet reflected

## Source Requirements

**Tier 1 (required):**
- Exchange data: daily OHLCV (open, high, low, close, volume) — minimum 1 year of history for MA calculations
- Platform: `TechnicalAgent` → `GET /api/agent/data/{ticker}/technical` (provides 50/200 DMA, RSI, MACD pre-calculated)
- Platform: `GET /api/agent/data/{ticker}/price-history` (raw daily prices for custom calculations)

**Tier 2 (qualitative context only):**
- Charting platforms (TradingView, StockCharts) for visual pattern confirmation
- Technical analyst commentary for broader market context (sector rotation, index trends)

## Scoring

**Trend Score (0-100)** — used as input to TM Score at 35% weight

| Classification | Score Range |
|----------------|-------------|
| Strong Uptrend | 80-100 |
| Weak Uptrend | 60-79 |
| Range-Bound | 35-59 |
| Weak Downtrend | 15-34 |
| Strong Downtrend | 0-14 |

Fine-tune within range using signal confluence:
- RSI divergence in favorable direction: +5 pts
- Fresh MA crossover in favorable direction (within 4 weeks): +5 pts
- MACD and RSI both confirming: +5 pts (cap at range max)
- Conflicting signals (e.g., uptrend but bearish divergence): -5 pts

## Output

- Trend classification: strong uptrend / weak uptrend / range-bound / weak downtrend / strong downtrend
- Trend Score (0-100) for TM Score input
- 50 DMA, 200 DMA levels with price relationship (% above/below each)
- 200 DMA slope direction: rising / flat / declining
- Golden/death cross status: active (date), forming (proximity), or none
- RSI current reading with interpretation (neutral / overbought / oversold / bullish divergence / bearish divergence)
- MACD status: above/below signal, above/below zero, crossover event (date and direction if recent)
- Weinstein stage: 1 / 2 / 3 / 4 with estimated stage duration
- Key level to watch for stage transition (breakout or breakdown price)
