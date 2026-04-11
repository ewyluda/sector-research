---
name: Analyst Expectations
description: Map consensus estimates, revision trends, and estimate dispersion to understand what the market has priced in and where surprises could originate
category: growth-earnings
type: technique
requires: [analyst-estimates, price-targets]
---

## Purpose

Analyst consensus is the benchmark against which every earnings report is measured. Understanding the current consensus, how it has been trending, and how much agreement exists among analysts provides critical context for assessing the risk/reward profile of a position.

Beating a consensus that has been revised up ten times is very different from beating a consensus that has been quietly walked down all year. Estimate dispersion tells you how much independent analysis exists — tight consensus anchored to management guidance is far more fragile than a dispersed consensus built on independent modeling.

## Methodology

**Step 1 — Pull current consensus estimates**

Gather consensus estimates for the current and next two fiscal years:
- Revenue (mean, median, high, low, number of estimates)
- EPS — GAAP and non-GAAP (mean, median, high, low, number of estimates)
- Gross margin consensus (if available)
- EBITDA consensus (if available)

Record the number of estimates contributing to the consensus. A consensus of 3 analysts is far less reliable than one of 25.

**Step 2 — Assess revision trends over 30/60/90 days**

For each metric, calculate:
```
Net Revision = (# Upgrades - # Downgrades) / Total Analysts
```

Track this over three windows: 30 days, 60 days, 90 days.

Classify revision momentum:
- **Positive**: Net revisions >+10% (more upgrades than downgrades)
- **Neutral**: Net revisions within ±10%
- **Negative**: Net revisions <-10% (more downgrades than upgrades)

Also track absolute estimate change: has the consensus EPS number moved up or down, and by how much?

**Step 3 — Measure estimate dispersion**

Calculate standard deviation of estimates across analysts for both revenue and EPS:
```
Dispersion = Standard Deviation / Mean Estimate
```

Express as a coefficient of variation (CV). Interpretation:
- CV <5%: tight consensus — analysts agree closely, often anchored to management guidance
- CV 5-15%: moderate dispersion — some independent analysis
- CV >15%: high dispersion — significant uncertainty or genuine analytical disagreement

Note: tight CV combined with a history of guidance-anchored analyst behavior means the consensus is fragile. A single guidance cut would force a synchronized downward revision.

**Step 4 — Identify estimate vs. price divergence**

Compare the direction of estimate revisions to stock price movement over the same period:
- Estimates revising up + stock rising = healthy momentum
- Estimates revising up + stock flat = potential lagged re-rating opportunity
- Estimates revising down + stock flat = delayed market reaction (caution)
- Estimates revising down + stock rising = crowded long vulnerable to estimate reset

**Step 5 — Assess whisper numbers (Tier 2 only)**

Whisper numbers are informal expectations that circulate among buy-side traders, often above the published consensus. They represent the true bar management must clear for the stock to react positively. Treat as qualitative context only — never use in quantitative models.

Indicators that whisper is above consensus:
- Stock rises on consensus "beat" but immediately fades (market expected more)
- Buy-side commentary suggests "the bar is higher than it looks"
- Company has a strong history of sandbagging

## Key Questions

1. Is consensus trending up or down, and how does that align with management's own guidance?
2. Are a few analysts driving the consensus, or is it broad-based with many independent estimates?
3. Is the estimate dispersion high (real uncertainty) or low (anchored to guidance without independent verification)?
4. Are estimates revising down while the stock holds — and is the market aware of the deteriorating expectations?
5. How far above or below consensus would actual results need to land to drive a meaningful stock reaction?

## Red Flags

- Consensus revisions trending negative for 60+ days while stock price remains flat (the market hasn't fully priced in the deterioration yet)
- Estimate dispersion extremely tight (<3% CV) with known guidance-following analysts — consensus is fragile and will move sharply on any surprise
- Large spread between GAAP and non-GAAP consensus (analysts disagree on what "real" earnings look like)
- Number of analysts covering the stock declining (buy-side losing interest, coverage drops often precede small-cap liquidity deterioration)
- Price targets clustered well below current price after recent runup (analysts have not reset targets to reflect new price levels — upgrade pressure building or targets stale)
- Estimate revision trend disconnecting from fundamentals (positive revisions despite weak data releases)

## Source Requirements

**Tier 1 (required for this analysis):**
- FMP / FactSet: analyst estimates endpoint (`analyst-estimates` via platform data provider)
- FMP / FactSet: price targets endpoint (`price-targets` via platform data provider)
- SEC EDGAR: actuals for comparison against estimates

**Tier 2 (qualitative context only — never for numeric models):**
- Sell-side research reports: individual analyst estimates and thesis
- Financial media: reporting on "whisper numbers" or buy-side expectations
- StockTwits / X: informal buy-side commentary on expectations (signal only, not data)

## Output

Analyst estimate trend table (current and forward year):

| Metric | Current FY Estimate | Prior 30d | Prior 60d | Prior 90d | Revision Direction | Dispersion (CV) |
|--------|--------------------|-----------|-----------|-----------|--------------------|-----------------|
| Revenue | [$B] | [$B] | [$B] | [$B] | Positive / Neutral / Negative | [%] |
| EPS (non-GAAP) | [$] | [$] | [$] | [$] | Positive / Neutral / Negative | [%] |
| EPS (GAAP) | [$] | [$] | [$] | [$] | Positive / Neutral / Negative | [%] |

Supporting outputs:
- Revision momentum classification: Positive / Neutral / Negative (30d / 60d / 90d windows)
- Estimate dispersion assessment: Tight (guidance-anchored) / Moderate / Dispersed (independent)
- Price vs. estimate divergence flag (if estimates moving against price)
- Price target distribution: mean, median, high, low, and % of analysts above current price
- Analyst count and coverage trend (growing, stable, shrinking)
- Whisper number assessment (Tier 2 only, qualitative label: ABOVE CONSENSUS / AT CONSENSUS / BELOW CONSENSUS)
