---
name: Regime Classification
description: Synthesize all macro signals into a unified market regime classification (RISK-ON / RISK-OFF / TRANSITION) to determine appropriate sizing, allocation, and hedging
category: macro-regime
type: technique
requires: [rate-environment, inflation-cycle, yield-curve, sector-rotation]
---

## Purpose

Regime classification is the synthesis layer of the macro analysis. After assessing rates, inflation, yield curve, and sector rotation independently, this technique aggregates all signals into a single actionable regime label: RISK-ON, RISK-OFF, or TRANSITION. The regime label directly informs position sizing decisions — not whether to buy or sell a specific stock, but how aggressively to size any position given the macro backdrop. A great investment thesis is worth more in a RISK-ON regime than a RISK-OFF one.

## Methodology

### Step 1: Collect Sub-Category Signal Outputs

Before classifying the regime, ensure the following outputs are available from prior sub-skills:
- Rate environment: direction and rate impact score
- Inflation cycle: phase and inflation impact score
- Yield curve: curve shape and recession probability
- Sector rotation: cycle phase and alignment score

If any sub-skill has not been run, apply a neutral (50) score for that component and note the data gap.

### Step 2: Score Individual Regime Signals

Evaluate 10 regime signals across 5 categories. Score each signal as RISK-ON (+1), NEUTRAL (0), or RISK-OFF (-1):

**Rates (2 signals)**
1. Rate direction: Falling or at trough = RISK-ON; stable at neutral level = NEUTRAL; rising = RISK-OFF
2. Real rate level: Negative to low positive (<1%) = RISK-ON; mildly positive (1-2%) = NEUTRAL; significantly positive (>2%) = RISK-OFF

**Inflation (2 signals)**
3. Inflation cycle phase: FALLING or BOTTOMING = RISK-ON; PEAKING = NEUTRAL; RISING = RISK-OFF
4. Fed policy stance: Dovish/cutting = RISK-ON; on hold = NEUTRAL; hawkish/hiking = RISK-OFF

**Yield Curve (2 signals)**
5. Curve shape: Normal/steepening = RISK-ON; flat = NEUTRAL; inverted or steepening after inversion = RISK-OFF
6. Recession probability (NY Fed model): <20% = RISK-ON; 20-40% = NEUTRAL; >40% = RISK-OFF

**Market Structure (2 signals)**
7. Credit spreads (HY): <300 bps and tightening = RISK-ON; 300-500 bps stable = NEUTRAL; >500 bps or widening = RISK-OFF
8. Market breadth: Advancing issues > declining issues, new highs expanding = RISK-ON; mixed = NEUTRAL; deteriorating breadth = RISK-OFF

**Sentiment & Volatility (2 signals)**
9. VIX level: <15 = RISK-ON; 15-25 = NEUTRAL; >25 and rising = RISK-OFF
10. Risk asset trend: S&P 500 above 200-day moving average and trending = RISK-ON; near moving average = NEUTRAL; below and declining = RISK-OFF

### Step 3: Aggregate Regime Score

Sum the 10 signals:
- **+7 to +10**: RISK-ON — strong, broad-based positive macro environment
- **+4 to +6**: RISK-ON (moderate) — constructive but not uniformly positive; size normally
- **+1 to +3**: TRANSITION leaning RISK-ON — mixed signals; signals improving; reduce position sizing slightly
- **-2 to 0**: TRANSITION — genuinely mixed; reduce sizing meaningfully; increase hedges
- **-3 to -5**: TRANSITION leaning RISK-OFF — majority of signals deteriorating; defensive posture
- **-6 to -10**: RISK-OFF — broad deterioration; only tactical positions, maximum hedges

### Step 4: Assign Regime Classification with Confidence

**RISK-ON** (score +4 or above):
- All or most macro indicators supportive: rates stable/falling, inflation moderating, yield curve positive, credit spreads tight, VIX low, breadth expanding
- Appropriate response: full position sizing; aggressive entry on pullbacks; growth-oriented allocation
- Historical equity environment: above-average returns, low volatility

**RISK-OFF** (score -3 or below):
- Majority of macro indicators negative: rates high/rising, inflation persistent, yield curve inverted, credit spreads wide, VIX elevated, market breadth narrow or declining
- Appropriate response: reduced position sizing (25-50% of normal); tight stop-losses; hedges in place (puts, inverse ETFs, cash); rotate to defensives
- Historical equity environment: elevated drawdown risk, high volatility, correlation spikes

**TRANSITION** (score -2 to +3):
- Mixed signals: some indicators constructive, others deteriorating; unclear directional conviction
- Appropriate response: moderate position sizing (50-75% of normal); avoid highly leveraged or long-duration names; shorter time horizons; wait for regime confirmation before adding
- Historical equity environment: elevated volatility, sector dispersion, difficult for trend-following

### Step 5: Identify Regime Trigger Events

Define 3-5 specific events that would cause a regime reclassification:

**RISK-ON to TRANSITION triggers**:
- Inflation re-accelerates (CPI MoM above 0.4% for 2+ consecutive months)
- Fed resumes hiking cycle unexpectedly
- Credit spreads widen by 100+ bps in less than 3 months
- Yield curve re-inverts after steepening

**TRANSITION to RISK-OFF triggers**:
- NY Fed recession probability model exceeds 50%
- ISM Manufacturing PMI falls below 45
- VIX sustained above 30 for 3+ weeks
- Leading indicators (LEI) decline 6+ consecutive months

**RISK-OFF to TRANSITION triggers**:
- Fed explicitly signals rate cuts with conviction (dot plot shift)
- VIX falls below 20 and stays there for 3+ weeks
- High-yield spreads tighten below 400 bps
- ISM rebounds above 50 from below 47

### Step 6: Translate to Position Sizing Guidance

Convert regime classification to concrete position sizing adjustments for the investment under analysis:

| Regime | Standard Sizing | Sizing Multiplier | Stop-Loss | Hedge |
|--------|----------------|-------------------|-----------|-------|
| RISK-ON (strong) | Full | 1.0x | Wide (15-20%) | None required |
| RISK-ON (moderate) | Normal | 0.9x | Normal (10-15%) | Optional |
| TRANSITION (leaning on) | Reduced | 0.7x | Tight (8-12%) | Recommended |
| TRANSITION | Reduced | 0.5x | Tight (6-10%) | Required |
| TRANSITION (leaning off) | Minimal | 0.35x | Very tight (5-8%) | Required |
| RISK-OFF | Tactical only | 0.25x | Very tight (5%) | Mandatory |

## Key Questions

1. Of the 10 regime signals, how many are RISK-ON vs. RISK-OFF? Is there a strong directional majority, or is the regime genuinely mixed?
2. Are regime signals converging (moving toward agreement) or diverging (contradicting each other)?
3. If currently in TRANSITION, which way is the weight of evidence leaning — and what single event would confirm the direction?
4. Does the investment thesis have an embedded macro assumption? If so, is that assumption consistent with the current regime?
5. What is the appropriate position size given the regime, and what is the stop-loss level that limits drawdown to an acceptable amount?

## Red Flags

- Investor is sizing a position as if RISK-ON when regime signals are clearly TRANSITION or RISK-OFF
- More than 6 of 10 regime signals are RISK-OFF but the investment has no hedge and a wide stop-loss
- Regime has been TRANSITION for 3+ months without resolution — elevated volatility is persistent, not temporary
- VIX above 30 while simultaneously adding growth/long-duration positions without tight risk controls
- Regime assumption in the investment thesis has not been updated for new data (stale macro assessment)
- All 10 signals aligned to RISK-OFF — concentration in any single equity position is inappropriate; cash and hedges dominate

## Source Requirements

- **VIX**: CBOE Volatility Index (cboe.com), Bloomberg, FRED (VIXCLS) — Tier 1
- **Market breadth**: NYSE advance-decline data; new 52-week highs/lows — Tier 1
- **High-yield credit spreads**: FRED (BAMLH0A0HYM2), ICE BofA index — Tier 1
- **200-day moving average**: price data via any standard financial data source — Tier 1
- **Fed policy signals**: FOMC statements, Chair press conferences (federalreserve.gov) — Tier 1
- **Sub-skill outputs**: rate-environment, inflation-cycle, yield-curve, sector-rotation scores — required inputs

## Scoring

**Regime Classification Score (0-100)** — this is a directional score, not a company-quality score:

- 80-100: RISK-ON — strong macro support for equities; full position sizing appropriate
- 60-79: RISK-ON (moderate) — constructive environment with minor concerns; normal sizing
- 40-59: TRANSITION — mixed regime; reduce sizing; hedges recommended
- 20-39: RISK-OFF leaning — majority of signals negative; minimal sizing, tight stops, hedges required
- 0-19: RISK-OFF — broad deterioration; tactical positions only; maximum defensive posture

## Output

- Regime Classification Score (0-100)
- Regime label: RISK-ON / TRANSITION / RISK-OFF with confidence: HIGH / MODERATE / LOW
- 10-signal scorecard: individual RISK-ON / NEUTRAL / RISK-OFF rating for each signal
- Aggregate signal score (sum of -10 to +10 signals)
- Regime trigger events: 3-5 specific events that would cause reclassification
- Position sizing recommendation: sizing multiplier, stop-loss range, hedge requirement
- Regime consistency check: does the investment thesis assume a regime consistent with current classification?
