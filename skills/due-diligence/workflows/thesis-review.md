---
name: Thesis Review
description: 30-60 minute structured thesis maintenance workflow for existing positions — produces a drift status (ON TRACK / DRIFTING / BROKEN) and a pre-committed position action
type: workflow
estimated_time: 30-60 min per position
cadence: quarterly minimum, monthly for high-conviction positions
---

## When to Use

- **Scheduled quarterly review** — every position in the portfolio requires a thesis review at least once per quarter, regardless of whether anything has happened
- **Price move trigger** — the stock has moved more than 20% (in either direction) since the last formal thesis review
- **Material event trigger** — a significant event has occurred: CEO departure, major acquisition or divestiture, regulatory ruling, earnings miss/beat beyond normal range, M&A approach
- **Inflection detection trigger** — the platform has flagged an inflection event (via `categories/11-position-management/monitoring-inflections`) that crosses the defined response threshold
- **Time-based catalyst check** — a time-bound catalyst from the original thesis was expected to fire and either did or did not

**Important distinction:** A thesis review is not research — it is maintenance. You are not building a new thesis from scratch. You are checking whether the existing thesis is still intact. This means the original thesis document must exist before running this workflow. If no thesis document exists, run `deep-dive` first.

## Process

### Step 1 — Thesis Recall (5 min)

Pull the original thesis document and re-read it completely before looking at any current data. The goal is to hold the original thesis in mind before exposure to current price or news framing, which creates anchoring and recency bias.

**Do not skip this step or abbreviate it.** Looking at the stock chart before recalling the original thesis is the single most common mistake in position maintenance — it causes investors to rationalize current price action rather than evaluate it against the original thesis.

**From the original thesis document, record:**

| Element | Original Thesis |
|---------|----------------|
| Core thesis (one sentence) | |
| Bull case | Probability: [X%], Price target: [Y] |
| Base case | Probability: [X%], Expected return: [Y] |
| Bear case | Probability: [X%], Price target/floor: [Y] |
| Catalyst 1 | [Description], Timeline: [Q/Year], Status: Pending |
| Catalyst 2 | [Description], Timeline: [Q/Year], Status: Pending |
| Catalyst 3 | [Description], Timeline: [Q/Year], Status: Pending |
| Invalidation condition 1 | |
| Invalidation condition 2 | |
| Conviction level at time of entry | Low / Medium / High |
| Entry price | |
| Current position size | % of portfolio |
| Date of original thesis / last review | |

**Price performance since last review:**
- Price at last review: [X]
- Current price: [Y]
- Change: [+/-Z%]
- Attribution (rough): Was the move driven by multiple expansion, earnings growth, or sentiment shift?

---

### Step 2 — Evidence Freshness Check (10 min)

Determine whether the factual foundation of the original thesis is current and whether any new evidence has emerged since the last review.

**Skills used:**
- `categories/02-financial-health` (data validation — have the financial inputs to the thesis materially changed since last review?)

**Catalyst status check:**
For each catalyst listed in the original thesis, answer:

| Catalyst | Expected Timeline | Status | Outcome |
|----------|------------------|--------|---------|
| [Catalyst 1] | [Q/Year] | FIRED / PENDING / MISSED / DELAYED | [If fired: did it produce the expected effect?] |
| [Catalyst 2] | [Q/Year] | FIRED / PENDING / MISSED / DELAYED | |
| [Catalyst 3] | [Q/Year] | FIRED / PENDING / MISSED / DELAYED | |

**Invalidation condition check:**
Have any of the pre-defined invalidation conditions been triggered?

| Invalidation Condition | Status | Evidence |
|-----------------------|--------|----------|
| [Condition 1] | TRIGGERED / NOT TRIGGERED | |
| [Condition 2] | TRIGGERED / NOT TRIGGERED | |

**If ANY invalidation condition is triggered: stop here. Classify as BROKEN. Execute the pre-committed exit action. Do not proceed to further analysis — additional analysis at this point is rationalization, not due diligence.**

**New evidence check:**
- [ ] New earnings or guidance since last review — summarize in one sentence
- [ ] New SEC filings (10-Q, 8-K, proxy) with material changes — note any
- [ ] Analyst estimate revisions (direction and magnitude) — trending up, flat, or down?
- [ ] Material news events (M&A, leadership change, regulatory, competitive) — list any

---

### Step 3 — Category Delta Scan (15-30 min)

For each of the 9 analytical categories, ask one focused change question. This is not a full re-analysis — it is a delta check designed to surface meaningful changes since the last review.

The time budget varies by position: 15 min for watchlist / small positions where a quick scan suffices; 30 min for high-conviction or large positions where each category deserves more depth.

**For each category, answer the change question with: IMPROVING / STABLE / DETERIORATING and one sentence of evidence.**

| Category | Change Question | Status | Evidence (one sentence) |
|----------|----------------|--------|------------------------|
| **Business Quality (BQ)** | Has the moat widened or narrowed since last review? Evidence of pricing power change, market share gain/loss, or new competitive entrant? | | |
| **Financial Health (FH)** | Are margins and ROIC moving with or against the thesis? Any balance sheet deterioration (leverage, covenant pressure, liquidity tightening)? | | |
| **Growth & Earnings (GE)** | Is revenue growth accelerating or decelerating vs. prior review? Has earnings quality improved or degraded (accruals, guidance revision direction)? | | |
| **Management & Governance (MG)** | Any leadership changes or capital allocation shifts since last review? Is management executing on stated priorities from the original thesis? | | |
| **Technical & Market Structure (TM)** | Is price action confirming or diverging from the fundamental thesis? Is the stock showing relative strength or weakness vs. sector? | | |
| **Macro Regime (MR)** | Has the macro regime changed in a way that affects the original thesis? Rate environment, inflation cycle, sector rotation — any regime shift? | | |
| **Sentiment & Narrative (SN)** | Has the dominant market narrative around this stock or sector shifted? Is the thesis moving from consensus-contrarian to consensus-consensus (losing variant)? | | |
| **Risk Assessment (RA)** | Have new risk factors emerged since last review? Any new SEC filings disclosing material risks not in the original thesis? | | |
| **Future Durability (FD)** | Have any new AI or technology threats emerged? Has the competitive disruption timeline accelerated? Any new AI-native entrants in core markets? | | |

**Skill references for deeper follow-up on any category showing DETERIORATING:**
- BQ deteriorating: re-run `categories/01-business-quality/moat-analysis` and `competitive-positioning`
- FH deteriorating: re-run `categories/02-financial-health/profitability-analysis` and `cash-flow-quality`
- GE deteriorating: re-run `categories/03-growth-earnings/revenue-driver-decomposition` and `earnings-quality`
- MG deteriorating: re-run `categories/04-management-governance/capital-allocation` and `leadership-assessment`
- TM diverging: re-run `categories/05-technical-market-structure/trend-momentum` and `support-resistance`
- MR shifted: re-run `categories/06-macro-regime/regime-classification` and `rate-environment`
- SN shifted: re-run `categories/07-sentiment-narrative/market-narrative` and `institutional-positioning`
- RA escalated: re-run `categories/08-risk-assessment/sec-risk-factors` and `thesis-risk-mapping`
- FD deteriorating: run `disruption-audit` workflow for full assessment

---

### Step 4 — Drift Assessment (5 min)

Synthesize the evidence from Steps 1-3 into a thesis drift classification. This requires honest assessment — cognitive dissonance (the desire to justify holding a position because you entered it) is the primary threat to accurate drift assessment.

**Drift classification framework:**

**ON TRACK**
- The majority of the 9 categories are STABLE or IMPROVING
- No catalysts have MISSED their expected timeline by more than one quarter
- No invalidation conditions have been triggered
- The core variant perception is still intact (the market still disagrees with your thesis in the way you originally anticipated)
- The probability-weighted expected return still justifies the current position size

**DRIFTING**
- 2-3 categories are DETERIORATING, but the core thesis has not been directly contradicted
- One catalyst has MISSED its timeline but remains plausible within an extended window
- The variant perception is weakening (consensus is beginning to converge on the thesis, reducing the edge)
- Probability weights have shifted materially but the expected value case still exists
- The position is performing worse than the base case trajectory would imply

**BROKEN**
- Any invalidation condition has been triggered (see Step 2)
- 4+ categories are DETERIORATING
- The core variant perception has collapsed (consensus now holds the same view as the thesis — the edge is gone)
- The fundamental data directly contradicts the primary claim of the bull case
- Management has explicitly abandoned or failed at the strategy that was central to the thesis

**Classify the thesis:** ON TRACK / DRIFTING / BROKEN

---

### Step 5 — Action Decision (5 min)

Apply the pre-committed action decision tree. The action must follow from the drift classification — deviation requires explicit documentation of the reasoning and must be reviewed within 30 days.

| Drift Status | Default Action | Position Guidance |
|-------------|---------------|-------------------|
| **ON TRACK** | HOLD | Maintain current position size. Consider adding on any meaningful price pullback (10-15%) if conviction remains high. Reset next review date. |
| **ON TRACK + Price Down > 20%** | ADD (conditional) | If price decline is sentiment-driven (not fundamental), add up to 50% of current position at defined levels. Confirm categories are STABLE before adding. |
| **DRIFTING** | REDUCE | Trim to half of current position size. Define a specific restore condition (the evidence that would return status to ON TRACK) AND a specific exit condition (the evidence that would classify the thesis as BROKEN). Set 60-day re-review. |
| **DRIFTING + No Restore Condition** | EXIT | If you cannot articulate a clear restore condition, the thesis is effectively broken. Begin exit process. |
| **BROKEN** | EXIT | Exit full position. No negotiating. The pre-commitment to exit on thesis break exists precisely because in-the-moment justifications for holding a broken thesis are almost always wrong. |

**Document the action taken:**
- Action: HOLD / ADD / TRIM / EXIT
- Size change: [From X% to Y% of portfolio]
- Reasoning: [Reference the drift classification and the specific evidence from Steps 2-4]
- Restore condition (if DRIFTING): [Specific evidence that would return thesis to ON TRACK]
- Exit condition (if DRIFTING): [Specific evidence that would classify thesis as BROKEN]
- Next review trigger: [Date OR specific event that triggers next review, whichever comes first]

---

## Output

**Required deliverables:**

1. **Thesis drift status (traffic light):**
   - ON TRACK (green) — thesis intact, maintain or add
   - DRIFTING (yellow) — partial deterioration, reduce and define restore/exit conditions
   - BROKEN (red) — exit; thesis invalidated

2. **Evidence changelog** — a concise list of what has changed since the last review, organized by category. Entries should be specific and evidence-based, not general impressions (e.g., "Gross margin contracted 180bps YoY in Q3 vs. prior thesis assumption of stable margins" not "margins are under pressure").

3. **Updated probability weights** — revised bull / base / bear probabilities with one-sentence reasoning for any change from the original thesis.

4. **Position action** — HOLD / ADD / TRIM / EXIT with:
   - Specific size change (or confirmation of no change)
   - Reasoning referenced to drift classification
   - If TRIM: restore condition and exit condition documented
   - If EXIT: brief post-mortem on what the thesis got right and wrong (required — this is how you improve)

5. **Next review trigger or date** — either a specific calendar date (quarterly minimum) or a specific event that will trigger an unscheduled review (upcoming earnings, catalyst timeline, regulatory decision, M&A outcome)
