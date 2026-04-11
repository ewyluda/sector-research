---
name: Volume Analysis
description: Assess accumulation vs. distribution patterns, institutional footprint, and OBV divergence to determine whether volume is confirming or contradicting price action
category: technical-market-structure
type: technique
requires: [price-history]
---

## Purpose

Volume is the one metric that cannot be faked in liquid markets — it reflects the actual money committed by market participants. When price and volume agree, the move is trustworthy. When they diverge, the move is suspect.

The central question of volume analysis: are buyers or sellers in control — and is that control strengthening or weakening? High volume on up days with low volume on down days is accumulation (institutional buyers are absorbing supply). The reverse pattern is distribution (institutional sellers are offloading into retail demand). Identifying which pattern is dominant before price reflects it is the core edge of volume analysis.

## Methodology

**Step 1 — Up-day vs. down-day volume comparison**

Classify each trading day over the trailing 20 sessions as an "up day" (close above open) or "down day" (close below open). Calculate:

- **Average up-day volume**: Mean volume across all up days in the window
- **Average down-day volume**: Mean volume across all down days in the window
- **Up/down volume ratio**: Average up-day volume / average down-day volume

Interpretation:
- Ratio >1.5: Strong accumulation — buyers are consistently more aggressive than sellers
- Ratio 1.0-1.5: Mild accumulation — slight buyer advantage
- Ratio 0.7-1.0: Balanced or slight distribution
- Ratio <0.7: Strong distribution — sellers are consistently more aggressive than buyers

Extend this analysis over 3-month and 6-month windows to distinguish short-term trading noise from sustained institutional activity.

**Step 2 — Relative volume (RVOL) analysis**

Calculate the 20-day average daily volume (ADAV). For any given trading session, compute:

```
Relative Volume = Today's Volume / 20-Day ADAV
```

Significance thresholds:
- **>2.0x (significant event)**: Unusual activity — institutional order flow, news catalysts, options expiration, index rebalancing. Identify the cause. If volume spike has no news catalyst, it may reflect a dark-pool print or institutional accumulation/distribution.
- **1.5-2.0x (elevated)**: Above-average participation — the move is more meaningful than a low-volume drift
- **0.5-1.0x (normal)**: Ordinary session — trend analysis holds but no exceptional signals
- **<0.5x (thin)**: Low conviction — price moves on thin volume are prone to reversal; do not read too much into the direction

Key application: A breakout above resistance on <1.0x RVOL is a false breakout candidate. A breakout on >2.0x RVOL is significantly more likely to sustain.

**Step 3 — On-Balance Volume (OBV) trend analysis**

On-Balance Volume is a cumulative indicator that adds volume on up days and subtracts it on down days:

```
OBV(today) = OBV(yesterday) + Volume(today)  [if close > prior close]
OBV(today) = OBV(yesterday) - Volume(today)  [if close < prior close]
```

The absolute OBV value is meaningless — what matters is the trend and its relationship to price:

**OBV confirming price** (healthy trend):
- Price trending up + OBV trending up = smart money is buying; uptrend is real
- Price trending down + OBV trending down = sellers are active; downtrend is confirmed

**OBV diverging from price** (potential reversal warning):
- Price making new highs + OBV failing to make new highs = buyers are not participating in the rally; distribution likely. Bearish divergence — watch for reversal.
- Price making new lows + OBV failing to make new lows = sellers are exhausting; smart money may be accumulating on weakness. Bullish divergence — watch for reversal.

Calculate OBV over trailing 3 months and 6 months. Short-term OBV divergences can reverse; sustained 6-month divergences have significantly higher predictive value.

**Step 4 — Institutional footprint identification**

Look for evidence of institutional-scale activity that typical retail flow cannot explain:

- **Large block trades**: Trades of 10,000+ shares in a single transaction (visible in time & sales or Level 2 data). Block trades above the day's RVOL baseline suggest institutional order execution.
- **Unusual volume on no-news days**: If a stock sees 3x+ RVOL with no earnings, no news headline, no analyst action — this is often dark pool institutional activity (accumulation or distribution). Mark the date and price level. If price subsequently trends in the direction implied by the session (up volume + up price for accumulation), this confirms institutional intent.
- **Volume cluster at specific prices**: If outsized volume repeatedly occurs in a narrow $0.50 band, this band is likely an institutional entry zone (for accumulation) or exit zone (for distribution). These levels often become strong support or resistance.
- **End-of-day volume spikes**: Institutions frequently execute large orders in the final 15-30 minutes to minimize market impact. An end-of-day volume surge on price appreciation is an accumulation signal; on price deterioration it is distribution.

## Key Questions

1. What is the up-day vs. down-day volume ratio over the trailing 20 sessions — and does it signal accumulation or distribution?
2. Has there been any session with >2x relative volume in the past 3 months — and was there a news catalyst, or was the volume "unexplained"?
3. Is OBV trending in the same direction as price, or is there a divergence — and how long has that divergence persisted?
4. Are there any price levels with unusual volume cluster patterns that suggest institutional accumulation or distribution zones?
5. Has OBV made a new high (or low) before price — a leading indicator of the next price leg?
6. If the stock recently broke a major support or resistance level, was the volume sufficient to confirm the move (>1.5x RVOL)?

## Red Flags

- Distribution pattern for 4+ consecutive weeks: down-day volume consistently exceeds up-day volume while price is flat or rising (the stock is being distributed into retail demand)
- OBV negative divergence sustained >6 weeks: price making higher highs but OBV in a downtrend — institutional sellers are active
- High relative volume (>3x) on a large down-day with no news — potential institutional exit; monitor closely in following sessions
- Breakout on <1.0x RVOL — likely a false breakout without institutional sponsorship
- Declining average volume over 3 months as price rises (trend is losing participation; distribution risk)
- Repeated volume spikes at a specific resistance level without a breakout — institutional sellers are actively capping the stock at that price

## Source Requirements

**Tier 1 (required):**
- Exchange data: daily OHLCV with volume — minimum 6 months for meaningful OBV trend analysis, 1 year preferred
- Platform: `GET /api/agent/data/{ticker}/price-history` (daily OHLCV for volume calculations)
- Platform: `GET /api/agent/data/{ticker}/technical` (pre-calculated technical indicators may include OBV)

**Tier 2 (supplementary):**
- Level 2 / time & sales data (Nasdaq TotalView, NYSE OpenBook) for block trade identification — not available via platform, requires broker access
- Dark pool volume data (FINRA OTC data, Quandl) for institutional footprint analysis — manual sourcing

## Scoring

**Volume Score (0-100)** — used as input to TM Score at 25% weight

| Pattern | Score |
|---------|-------|
| Strong accumulation (up/down ratio >1.5, OBV confirming uptrend, recent high RVOL on up days) | 80-100 |
| Mild accumulation (ratio 1.0-1.5, OBV roughly tracking price) | 60-79 |
| Neutral or mixed (ratio 0.7-1.0, no clear OBV trend) | 35-59 |
| Mild distribution (ratio 0.5-0.7, OBV diverging negatively) | 15-34 |
| Strong distribution (ratio <0.5, OBV in clear downtrend vs. price, high RVOL on down days) | 0-14 |

Adjustments:
- Sustained OBV divergence >6 weeks (either direction): ±10 pts toward the divergence direction
- Recent unexplained high-RVOL session (>2x) with clear directional follow-through: ±5 pts in follow-through direction
- Breakout or breakdown with confirming volume (>1.5x RVOL): ±5 pts in move direction (cap at range max/min)

## Output

- Volume Score (0-100) for TM Score input
- Volume pattern classification: strong accumulation / mild accumulation / neutral / mild distribution / strong distribution
- Up/down day volume ratio (trailing 20 sessions, 3 months, 6 months)
- 20-day average daily volume (ADAV) and current RVOL
- OBV trend: rising / flat / declining — and relationship to price trend (confirming / neutral / diverging)
- OBV divergence alert (if applicable): direction, duration, and severity
- Notable high-RVOL sessions in trailing 3 months (date, volume multiple, price action, news catalyst or unexplained)
- Institutional footprint observations: any block trade clusters, volume anomalies, or distribution zone identification
