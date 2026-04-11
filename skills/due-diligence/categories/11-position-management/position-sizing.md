---
name: Position Sizing
description: Determine the correct position size as a percentage of portfolio using Kelly criterion-informed analysis, conviction score adjustments, and portfolio-level concentration constraints
category: position-management
type: technique
requires: []
---

## Purpose

Position sizing is the most mathematically tractable decision in investing — and the most commonly ignored. The Kelly criterion provides a theoretical framework for optimal capital allocation given a known win probability and win/loss ratio. In practice, the criterion is modified heavily: full Kelly produces ruinously large swings, estimated probabilities are imprecise, and correlation across a portfolio demands additional haircuts.

The goal is to size positions large enough to meaningfully contribute to portfolio returns when right, and small enough to survive and recover when wrong. A position sized at 1% of portfolio cannot move the needle when correct. A position sized at 25% can cause permanent impairment when incorrect. The right answer lives between those extremes, calibrated to conviction and thesis robustness.

## Methodology

### Step 1: Establish Win Probability and Win/Loss Ratio

The Kelly formula requires two inputs: the probability of a winning outcome and the ratio of the average win to the average loss.

**Win probability (p)**:
- Draw from the bull/bear scenarios in the platform's thesis agent or solution agent output
- Win probability = probability that the bull case or base case plays out
- Conservative default: if the thesis is well-constructed but uncertainty is high, use p = 0.55 (slight edge, not certainty)
- High-conviction thesis with strong catalyst visibility: p = 0.60-0.65
- Speculative thesis with significant uncertainty: p = 0.45-0.50 (near coin flip — size accordingly)
- Do not use p > 0.70 for any single equity position. That level of certainty is almost never warranted.

**Win/Loss ratio (W/L)**:
- Win magnitude: expected return from entry to price target (from analyst consensus or DCF base case)
- Loss magnitude: expected loss from entry to stop-loss level (from Stop-Loss & Invalidation sub-skill)
- W/L ratio = Win % / Loss %
- Example: if the price target implies 35% upside and the stop-loss implies 18% downside, W/L = 35/18 = 1.94
- The W/L ratio should be at minimum 1.5:1 for any position worth initiating. Below 1.5:1, the risk/reward is insufficient regardless of Kelly output.

**Loss probability (q)**:
- q = 1 − p (probability of losing outcome)

### Step 2: Calculate Kelly Percentage

**Kelly formula**:

```
Kelly % = (p × W/L − q) / W/L
```

Or equivalently:

```
Kelly % = (Win prob × Win/Loss ratio − Loss prob) / Win/Loss ratio
```

**Example calculation**:
- p = 0.60, q = 0.40, W/L = 1.94
- Kelly % = (0.60 × 1.94 − 0.40) / 1.94
- Kelly % = (1.164 − 0.40) / 1.94
- Kelly % = 0.764 / 1.94
- Kelly % = 39.4%

Full Kelly of 39.4% would mean allocating 39.4% of portfolio to this single position. That is not a recommendation — it is a ceiling from which practical sizing begins.

**If Kelly % is negative**: the expected value of the position is negative. Do not initiate the position. Re-examine the thesis or the win/loss ratio.

**If Kelly % is above 30%**: the inputs are almost certainly too optimistic. Re-examine the win probability estimate.

### Step 3: Apply Half-Kelly and Practical Caps

Full Kelly is theoretically optimal only when probabilities are known with certainty and the investor has an infinite horizon. Neither condition holds for equity investing. Apply the following haircuts:

**Half-Kelly baseline**: Start at 50% of the full Kelly result as the base position size.
- Example: Full Kelly of 39.4% → Half-Kelly baseline = 19.7%

**Practical maximum cap**: No single equity position should exceed 10% of portfolio, regardless of Kelly output. This is a hard cap, not a guideline.
- Apply: `Practical size = min(Half-Kelly, 10%)`
- Example: min(19.7%, 10%) = 10%

**Practical minimum threshold**: Do not initiate positions below 1% of portfolio. Sub-1% positions are too small to matter and create monitoring overhead without return contribution.

**Additional concentration haircut**: If the position is in the same sector as more than 20% of existing portfolio, apply an additional 25% haircut to the calculated size to manage sector concentration.

### Step 4: Apply Conviction Score Adjustment

The preceding analysis phases produce a composite conviction score derived from Business Quality, Financial Health, Growth & Earnings, Management, Technical Structure, Macro Regime, Sentiment, Risk Assessment, and Future Durability scores. Use that score to scale the position size.

**Conviction adjustment table**:

| Overall Conviction Score | Sizing Multiplier | Rationale |
|--------------------------|-------------------|-----------|
| 80-100 | 1.0× (full calculated size) | Strong across all dimensions; maximum warranted size |
| 60-79 | 0.75× | Good thesis with meaningful uncertainty in 1-2 dimensions |
| 40-59 | 0.50× | Mixed picture; half-size reflects genuine ambiguity |
| Below 40 | Do not size | Insufficient conviction; do not initiate position |

**Example**: Practical calculated size of 8%, conviction score of 68 → Final size = 8% × 0.75 = 6%.

**Conviction override rule**: If the conviction score is above 80 but any single sub-category score is below 30 (extreme weakness in one area), apply the 0.75× multiplier regardless. A single dimension of extreme weakness is not offset by strength elsewhere when sizing.

### Step 5: Document the Final Size Decision

Record the sizing decision with all inputs visible:
- Win probability estimate and source
- Win/loss ratio calculation (upside to target / downside to stop)
- Full Kelly result
- Half-Kelly result
- Practical cap applied (if any)
- Conviction score and multiplier applied
- Final position size (%)
- Dollar amount at current portfolio value

This documentation serves two purposes: accountability to the pre-committed decision, and a reference for sizing adjustments if the thesis develops.

## Key Questions

1. Is the win probability estimate grounded in specific thesis pillars and scenario analysis, or is it a hopeful round number?
2. Is the W/L ratio at least 1.5:1? If not, the position should not be initiated regardless of conviction.
3. Does the final size represent a meaningful allocation (above 1%) without creating concentration risk (below 10%)?
4. If the conviction score adjustment reduced the size significantly, does that reduction reflect a genuine lack of conviction — or is it being overridden mentally?
5. How does this position interact with existing sector and factor exposures in the portfolio? Does the sizing account for those correlations?
6. At the final position size, what is the maximum dollar loss if the stop-loss is triggered? Is that loss tolerable within the portfolio context?

## Red Flags

- Win probability estimated above 70% for a single equity — almost certainly overconfident; use 0.65 as a hard ceiling
- W/L ratio below 1.5:1 — insufficient risk/reward to warrant any position regardless of conviction
- Final position size above 10% of portfolio — concentration risk that no level of conviction justifies for a single equity
- Kelly calculation skipped in favor of "gut feel" sizing — bypasses the only systematic check on overconfidence
- Conviction score below 40 but position initiated anyway — the framework exists for a reason
- Position sized at less than 1% — monitoring overhead without return impact; do not initiate
- Sizing decision not documented — undocumented sizing is susceptible to post-hoc rationalization when the position moves

## Source Requirements

- **Platform solution agent / thesis agent**: bull case, bear case, and base case scenario probabilities and return estimates — Tier 1 for win probability and win magnitude
- **Platform stop-loss calculation** (from stop-loss-invalidation sub-skill): loss magnitude from entry to stop — Tier 1 for loss magnitude input
- **Platform fundamentals agent**: analyst price targets, DCF valuation — Tier 1 for upside calibration
- **Platform overall conviction score**: composite score from preceding analysis phases — Tier 1 for adjustment multiplier
- **Portfolio management system or spreadsheet**: existing sector and factor exposures for concentration check — Tier 1

## Output

- Full Kelly % with all inputs shown
- Half-Kelly % after applying 50% haircut
- Practical size % after applying 10% cap (if applicable)
- Final position size % after conviction score adjustment
- Dollar amount at current portfolio value
- Maximum dollar loss scenario: final size × stop-loss percentage
- Concentration check: sector exposure before and after this position
- Sizing rationale in one sentence explaining the primary driver of the final number
