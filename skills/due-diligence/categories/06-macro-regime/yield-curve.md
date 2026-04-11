---
name: Yield Curve
description: Analyze yield curve shape and dynamics as a leading indicator of economic growth expectations, recession probability, and credit conditions
category: macro-regime
type: technique
requires: []
---

## Purpose

The yield curve — the relationship between short-term and long-term interest rates — is one of the most reliable leading indicators in macroeconomics. An inverted yield curve has preceded every U.S. recession since 1970, typically by 6 to 18 months. Beyond the inversion signal, the steepness of the curve and the direction of change carry important information about growth expectations, credit conditions, and where we are in the economic cycle.

## Methodology

### Step 1: Collect Key Yield Curve Spreads

Gather current levels and 3, 6, and 12-month history for:
- **2-Year / 10-Year spread (2Y10Y)**: the canonical recession indicator; most commonly cited
- **3-Month / 10-Year spread (3M10Y)**: the Federal Reserve Bank of New York's preferred recession model input; tends to invert later in a cycle but has higher recession prediction accuracy
- **Fed funds rate / 10-Year spread**: measures monetary policy restrictiveness relative to long-run growth expectations
- **10-Year / 30-Year spread**: signals long-run inflation and term premium expectations

Note whether each spread is:
- **Positive (normal)**: longer-term rates higher than shorter-term — growth expected
- **Flat**: spreads near zero — uncertainty; transition signal
- **Inverted (negative)**: short rates above long rates — growth slowdown or recession priced

### Step 2: Identify Curve Shape and Dynamic

Classify the current curve shape:

**Steepening normal curve**: short rates falling or stable; long rates rising — early economic recovery; risk-on environment forming; growth expectations building
- Historical context: follows recessions; typically the best environment for cyclicals and early-cycle plays

**Bear flattening**: long rates rising faster than short rates — inflation concern; market pricing higher long-run rates while short rates lag Fed action
- Common signal: late-cycle, early hiking environments; precursor to inversion

**Bull flattening**: short rates rising faster than long rates during a hiking cycle — market pricing in eventual slowdown even as Fed raises; the path toward inversion
- Warning signal: market seeing limited long-run growth despite current Fed action

**Inversion (flat to negative)**: short rates exceed long rates — market pricing in future rate cuts due to anticipated growth slowdown or recession
- Most bearish signal for economic growth; not necessarily immediately bearish for equities, but risk is elevated

**Steepening after inversion (bear steepener)**: long rates rising while curve is still partially inverted or recently uninverted — the most reliable actual recession signal historically; indicates the recession is imminent or already beginning

### Step 3: Apply the NY Fed Recession Probability Model

The New York Fed publishes a monthly estimate of 12-month recession probability based on the 3-month/10-year spread:
- **Below 20%**: low recession probability; baseline case is continued expansion
- **20-40%**: elevated but manageable risk; warrants monitoring
- **40-60%**: high probability; position for late-cycle and defensive rotation
- **Above 60%**: recession likely; risk-off positioning appropriate

If the NY Fed model is not available, approximate using the 3M10Y spread:
- 3M10Y > 100 bps positive: very low recession risk (~5-15%)
- 3M10Y 0-100 bps: moderate risk (~15-25%)
- 3M10Y 0 to -50 bps: elevated risk (~25-40%)
- 3M10Y -50 to -150 bps: high risk (~40-60%)
- 3M10Y below -150 bps: very high risk (>60%)

### Step 4: Assess Term Premium

The term premium is the extra yield investors demand for holding long-term bonds vs. rolling short-term bonds. The ACM (Adrian-Crump-Moench) model from the NY Fed provides a decomposition of the 10-year yield into expected short rates + term premium.
- **Positive and rising term premium**: market demands compensation for uncertainty; signals credit stress, inflation uncertainty, or supply concerns — headwind for long-duration equities
- **Negative term premium**: investors willing to pay a premium for long-term safety — flight to quality behavior; suggests risk-off sentiment even if spreads appear positive

### Step 5: Cross-Check with Credit Spreads

The yield curve does not operate in isolation. Cross-check with:
- **High-yield (HY) spread**: yield spread of HY corporate bonds over Treasuries (ICE BofA HY index)
  - HY spread < 300 bps: benign credit environment; risk appetite intact
  - HY spread 300-500 bps: elevated; growing stress
  - HY spread > 500 bps: stress or distress conditions; risk-off
- **Investment-grade (IG) spread**: IG spread < 100 bps is healthy; > 200 bps signals significant stress
- **Consistency check**: inverted yield curve + widening credit spreads = strongly confirmed negative signal; inverted curve + tight credit spreads = mixed signal

## Key Questions

1. Has the 2Y10Y or 3M10Y been inverted, and for how long? Duration of inversion matters — brief inversions are less predictive than sustained ones (6+ months).
2. Has the curve recently started steepening after a period of inversion? This is the most actionable recession signal — it often marks the beginning of the actual recession.
3. What does the NY Fed recession probability model show, and is it rising or falling?
4. Are credit spreads confirming the yield curve signal, or are they diverging (which reduces conviction in either direction)?
5. How does the current curve shape align with where we are in the Fed rate cycle?

## Red Flags

- 3M10Y inverted for 6+ consecutive months — historical recession signal triggered
- Curve beginning to steepen after a period of inversion — actual recession signal, not just leading indicator
- HY credit spreads widening concurrently with inversion — credit markets confirming growth concerns
- Term premium negative and falling — flight-to-quality behavior; risk sentiment deteriorating beneath the surface
- Market pricing 200+ bps of rate cuts within 12 months — means futures market expects significant economic slowdown
- Yield curve inversion in multiple countries simultaneously — global recession risk elevated

## Source Requirements

- **Treasury yields (2Y, 3M, 10Y, 30Y)**: U.S. Department of the Treasury, FRED (DGS2, DGS3MO, DGS10, DGS30) — Tier 1
- **NY Fed recession probability model**: newyorkfed.org/research/capital_markets/ycfaq — Tier 1
- **ACM term premium model**: newyorkfed.org/research/data_indicators/term_premia — Tier 1
- **TIPS real rates**: FRED (DFII10) — Tier 1
- **High-yield and IG credit spreads**: FRED (BAMLH0A0HYM2, BAMLC0A0CM) — Tier 1
- **Historical curve analysis**: Federal Reserve research, NBER working papers — Tier 2

## Scoring

**Yield Curve Signal Score (0-100)** based on curve shape and associated recession probability:

- 80-100: Normal and steepening curve; NY Fed probability < 15%; credit spreads tight — expansion regime confirmed
- 60-79: Flat to mildly positive; NY Fed probability 15-25%; credit spreads normal — late cycle but no immediate signal
- 40-59: Mildly inverted or recently uninverted; NY Fed probability 25-40%; some credit spread widening — caution warranted
- 20-39: Inverted (3M10Y negative); NY Fed probability 40-60%; credit spreads widening — recession risk elevated
- 0-19: Deeply inverted or steepening after inversion; NY Fed probability > 60%; HY spreads > 500 bps — recession likely

## Output

- Yield Curve Signal Score (0-100)
- 2Y10Y and 3M10Y current spreads and 12-month trend
- Curve shape classification: STEEPENING / FLAT / BEAR FLATTENING / INVERTED / STEEPENING AFTER INVERSION
- Duration of inversion (if applicable) in months
- NY Fed 12-month recession probability (current and trend)
- Term premium assessment: positive, negative, direction
- Credit spread confirmation: HY and IG spreads with interpretation
- Recession probability summary and implied timeline for risk if applicable
