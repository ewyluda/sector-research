---
name: Bull / Bear Framing
description: Construct explicit bull and bear investment cases with evidence from prior deep-dive categories, probability estimates, and price targets — combined into a probability-weighted base case
category: thesis-construction
type: technique
requires: []
---

## Purpose

Bull/Bear Framing converts the outputs of nine prior due diligence categories into a structured set of scenarios — explicit enough to trade on, specific enough to monitor, and honest enough to include the ways you might be wrong.

Most investment research produces a single-path narrative: the company is good (or bad) for these reasons, and the stock should go up (or down). Bull/Bear Framing forces the analyst to commit to a three-scenario structure where each scenario has a core argument, supporting evidence, a probability estimate, and a price target. The scenarios must sum to ~100% probability. If you cannot write the bear case with the same quality as the bull case, you do not yet understand the investment.

The output of this sub-skill is the primary deliverable of the thesis construction phase. Catalyst Identification, Variant Perception, and Evidence Grounding all serve to strengthen or challenge the scenarios produced here.

## Methodology

### Step 1: Assemble the Evidence Base

Before writing any scenario, organize the outputs from all prior categories into two lists:

**Supporting evidence** (facts pointing toward positive outcomes):
- High scores from Business Quality, Financial Health, Growth & Earnings
- Strong management signals from Management & Governance
- Positive technical setup from Technical & Market Structure
- Favorable macro positioning from Macro Regime
- Positive sentiment inflections from Sentiment & Narrative
- Low risk scores from Risk Assessment
- High durability from Future Durability

**Complicating or contrary evidence** (facts pointing toward risk or underperformance):
- Low scores or red flags from any category above
- Valuation stretch beyond historical ranges or peer group
- AI disruption vulnerability identified in Future Durability
- Deteriorating technical structure
- Negative sentiment inflections or narrative breakdown
- Concentration risk, governance concerns, or management red flags

This evidence base is the raw material. The scenarios are constructed from it — they do not introduce new claims.

### Step 2: Write the Bull Case

The bull case is the affirmative investment argument at its strongest honest form. It is not the best-case dream scenario — it is the scenario that plays out if the supporting evidence proves correct and the risks do not materialize.

**Bull Case structure:**

**Core Argument** (1-2 sentences): The single most important reason this investment works. This is not a list of positives — it is the primary claim. Example: "The market is pricing this company as a hardware vendor when it has already transitioned to a recurring software model, and the revenue mix inflection will become undeniable in the next two quarters."

**Evidence Points** (3-5 items): Each evidence point cites a specific finding from a prior category and sub-skill. Format: [Category / Sub-Skill] → [Specific Finding]. Do not write evidence points that are not traceable to prior analysis.

**Probability Estimate**: The analyst's subjective probability that the bull scenario plays out. This is not a model output — it is a commitment. State it as a percentage (e.g., 35%).

**Price Target / Return**: The stock price or percentage return expected if the bull case plays out over a stated time horizon (e.g., 12 months). This should be consistent with the valuation analysis from Financial Health or the DCF from Business Quality — not a round number pulled from intuition.

**Key Assumptions**: The 2-3 things that must be true for the bull case to materialize. If any assumption is violated, the bull case breaks.

### Step 3: Write the Bear Case

The bear case is the negative investment argument at its strongest honest form. It is not a doom scenario — it is the scenario that plays out if the complicating evidence proves correct and the supporting evidence is wrong.

**Bear Case structure (same format as bull):**

**Core Argument** (1-2 sentences): The single most important reason this investment fails. Example: "The company's core revenue stream faces direct AI substitution within 24 months, and current margins reflect a competitive position that will not survive the product-to-commodity transition."

**Evidence Points** (3-5 items): Traceable to prior category/sub-skill findings. Each point names the source.

**Probability Estimate**: Analyst's subjective probability that the bear scenario plays out (e.g., 25%).

**Price Target / Return**: Expected price or return if the bear case materializes. Should be internally consistent with the risk analysis and valuation floor from prior categories.

**Key Assumptions**: The 2-3 things that must be true for the bear case to materialize.

### Step 4: Derive the Base Case

The base case is not a third independent scenario. It is the probability-weighted expected value of the bull and bear cases, with explicit accounting for the remaining probability mass.

**Calculation:**

1. Assign probabilities: Bull = B%, Bear = Bear%, Base = 100% − B% − Bear%
2. Base Case price target = (Bull Target × Bull %) + (Bear Target × Bear %) + (Mean Scenario Target × Base %)
3. Where Mean Scenario = current price × (1 + median of bull and bear returns)

**Base Case narrative**: 1-2 sentences describing the most likely path. This is the scenario where neither the bull nor bear thesis fully plays out — the company executes reasonably, some risks materialize partially, and the stock moves in line with fundamentals and the market multiple.

**Expected Return**: The probability-weighted return across all three scenarios. This is the primary output used for position sizing.

### Step 5: Verify Internal Consistency

Before finalizing, check:
- Do probabilities sum to ~100%?
- Do the bull and bear cases contradict each other on any factual claim? (If the bull case assumes margin expansion and the bear case assumes margin compression, both must explain how — not just assert it.)
- Is the bear case price target above zero and above liquidation value?
- Is the bull case price target consistent with the valuation multiples implied by the growth assumptions?
- Does the base case expected return justify the position given the risk? (A 5% expected return with 40% bear probability is not worth the risk unless the portfolio construction rationale is explicit.)

## Key Questions

1. What is the single most important thing the market has wrong about this company — and is it in the bull direction or the bear direction?
2. If I had to bet my own money on the bear case being right, what evidence would I point to?
3. Is the bull case driven primarily by multiple expansion (valuation re-rating) or by fundamental improvement? Multiple-expansion bull cases carry higher probability uncertainty.
4. What is the expected return at each scenario, and what probability distribution is implied by the current stock price?
5. If the bull case plays out but takes 3 years instead of 12 months, does the annualized return still justify the position?
6. Is the bear case a temporary setback (buy more on weakness) or a structural impairment (exit the position)?
7. What does the evidence base say about base rates? How often does a company with this profile (score pattern, industry, macro environment) produce bull vs. bear outcomes?

## Red Flags

- Bull and bear cases have identical core arguments with only a magnitude difference — this is a sensitivity analysis, not a scenario analysis
- Probability estimates are symmetric (e.g., 33/33/33) without a rationale — symmetric probabilities suggest the analyst has no conviction
- Bull case target is set by working backward from a desired return, not forward from a valuation model
- Evidence points cite analyst price targets or management guidance as primary support (Tier 3 only) — these are not independent evidence
- Bear case is significantly shorter or less developed than the bull case — asymmetric rigor is a bias signal
- The three scenarios do not sum to ~100% probability — either scenarios overlap or the analyst is not committing to full probability coverage
- Core argument is longer than 2 sentences — a core argument that requires extensive qualification is not yet a core argument
- Bull case requires 5+ independent things to go right simultaneously — the compound probability is almost certainly lower than stated

## Source Requirements

- **All prior category outputs**: Required. Bull/Bear Framing cannot be completed without outputs from Business Quality, Financial Health, Growth & Earnings, Management & Governance, Technical & Market Structure, Macro Regime, Sentiment & Narrative, Risk Assessment, and Future Durability.
- **Valuation analysis**: Required for price targets. Multiples and DCF from Financial Health sub-skills.
- **Peer group benchmarks**: Required for relative return context. From Business Quality or Financial Health comps.
- **Historical scenario base rates**: Optional but recommended. Industry databases, academic studies on similar company profiles.

## Output

- Bull Case: core argument (1-2 sentences), 3-5 evidence points with source citations, probability estimate, 12-month price target / expected return, key assumptions (2-3)
- Bear Case: core argument (1-2 sentences), 3-5 evidence points with source citations, probability estimate, 12-month price target / expected return, key assumptions (2-3)
- Base Case: probability-weighted expected return, narrative (1-2 sentences), current price implied probability distribution
- Probability table: Bull % + Bear % + Base % = ~100%
- Expected return (probability-weighted)
- Internal consistency check results
- Conviction level: HIGH / MEDIUM / LOW (based on evidence quality and probability asymmetry)
