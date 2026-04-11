---
name: Catalyst Identification
description: Identify and track time-bound events that will unlock bull-case value or accelerate bear-case deterioration, with probability, magnitude, and status tracking
category: thesis-construction
type: technique
requires: []
---

## Purpose

A thesis without catalysts is a research report. Catalyst Identification converts the bull/bear scenarios from Bull/Bear Framing into an actionable, monitorable event timeline. Each catalyst is a specific, time-bound event — not a condition or a trend — that will materially move the stock toward one of the three scenarios.

Catalysts serve two functions: they bound the investment thesis in time (forcing the analyst to commit to "when," not just "if"), and they provide real-time feedback during the holding period (each catalyst that fires, expires, or misses updates the probability distribution of the three scenarios).

The minimum viable thesis requires at least 3 catalysts: at least one that could unlock the bull case and at least one that could accelerate the bear case. A thesis with only positive catalysts is optimistic bias dressed as analysis. A thesis with only negative catalysts is a short thesis, not a long thesis — and must be labeled as such.

## Methodology

### Step 1: Derive Catalysts from Bull and Bear Cases

Review the key assumptions in each scenario from Bull/Bear Framing. For each assumption, ask: **what event would confirm or refute this assumption within the investment horizon?**

The catalyst must meet three criteria:
1. **Specific**: Can be described in one sentence with a named event type (earnings report, product launch, regulatory ruling, contract announcement, etc.)
2. **Time-bound**: Has a quarter or year in which it is expected to occur or expire
3. **Material**: If it fires in the expected direction, it would move the stock at least 5% — or meaningfully shift scenario probabilities

Examples of events that qualify as catalysts:
- Earnings report where management provides guidance above or below consensus on a specific metric (revenue, margins, units)
- Product launch or customer adoption milestone (named product, named customer cohort, stated adoption threshold)
- Regulatory decision (FDA approval, FTC ruling, EU Digital Markets Act designation)
- Contract renewal or loss (named contract, stated renewal date)
- M&A announcement (acquisition or divestiture of named business unit or target)
- Management change (named executive, stated role)
- Competitive event (named competitor's product launch, pricing move, market share announcement)
- Macro inflection (specific Fed rate decision, CPI release meeting or missing a threshold, GDP revision)
- Capital allocation event (buyback announcement, dividend initiation, debt maturity, equity offering)

Examples of things that are NOT catalysts (they are conditions or trends):
- "Continued strong execution" — not an event, cannot be tracked as fired/expired
- "Macro tailwinds" — not specific enough; name the event
- "Market share gains" — ongoing process, not a time-bound event
- "Multiple expansion" — outcome, not a catalyst

### Step 2: Document Each Catalyst

For each catalyst, complete the following fields:

**Description**: One sentence describing the specific event. Include the relevant company, metric, or decision body. Example: "Q2 FY2026 earnings report where the company provides FY2026 revenue guidance above the $4.2B analyst consensus estimate."

**Direction**: BULL (fires in direction of bull case) or BEAR (fires in direction of bear case)

**Expected Timeline**: Quarter (e.g., Q2 2026) or half-year (H1 2026) in which the event is expected to occur. If uncertain, state a range (Q2-Q3 2026).

**Probability**: Analyst's subjective probability that this catalyst fires in the bull or bear direction (as stated). Example: 55% probability that Q2 guidance comes in above consensus.

**Magnitude**: Expected stock price impact if the catalyst fires in the stated direction. Express as a percentage range: e.g., +8-12% or −15-20%. This should be consistent with how similar events have historically moved the stock (use historical earnings move data from Financial Health or Technical analysis).

**Scenario Impact**: How does this catalyst change the probability distribution of bull/bear/base scenarios if it fires? State the delta: e.g., "If fired, bull probability increases from 35% to 50%; base decreases from 40% to 28%; bear stays at 22%."

**Status**: One of three states:
- **PENDING**: Event has not yet occurred and is within the investment horizon
- **FIRED**: Event has occurred; record actual outcome and actual stock impact vs. expected
- **EXPIRED**: Event window has passed without firing; record reason and whether scenario probabilities need updating

### Step 3: Construct the Catalyst Timeline

Organize all catalysts chronologically by expected timeline. Display as a timeline — earliest to latest — with BULL catalysts above the timeline and BEAR catalysts below. This visual structure allows the analyst to see:
- Which direction has more near-term catalysts (this affects entry timing)
- Whether there are gaps in the timeline where no catalyst exists (these periods have low information value for monitoring)
- Whether catalysts cluster (overlapping catalysts create higher volatility windows)

If no catalyst exists within the next 90 days, note this explicitly. A thesis with no near-term catalysts requires either a longer time horizon or an explanation of why the position is worth holding through a low-information period.

### Step 4: Validate Catalyst Coverage

Before finalizing, verify:
1. **Minimum count**: At least 3 catalysts identified (framework gate — a thesis with fewer than 3 catalysts is not ready for deployment)
2. **Direction coverage**: At least 1 BULL catalyst and at least 1 BEAR catalyst. If all catalysts are in one direction, the thesis is either a short or the analyst is only looking in one direction.
3. **Timeline coverage**: At least 1 catalyst within the next 6 months. If the first catalyst is more than 6 months away, note the implication for capital efficiency and monitoring frequency.
4. **Probability calibration**: Total BULL catalyst probability × estimated magnitude should be roughly consistent with the Bull Case expected return. If catalysts are too weak to drive the bull case return, something is missing.

### Step 5: Set Monitoring Protocol

For each PENDING catalyst, define:
- **Monitoring signal**: What to watch in real-time that indicates the catalyst is materializing or failing (e.g., "Weekly check on earnings estimate revisions from FactSet; watch for consensus cuts as early warning that Q2 guidance miss is more likely")
- **Trigger to re-evaluate thesis**: State a specific condition that would force a full thesis review rather than routine monitoring. Example: "If consensus revenue estimate for FY2026 is cut by more than 5% before Q2 earnings, initiate thesis review and update scenario probabilities."

## Key Questions

1. Is each catalyst specific enough that you would know unambiguously whether it fired or did not fire?
2. For each catalyst, what is the observable signal between now and the event that would update the probability?
3. If all bull catalysts fire and all bear catalysts do not fire, does the resulting stock return match the bull case price target?
4. What is the average time for a catalyst of this type to move from announcement to full stock price impact (earnings catalysts typically reprice the same day; regulatory catalysts may have 3-6 month lag as implementation becomes clear)?
5. Is there a catalyst that would resolve the thesis definitively — one that, if it fires, makes continued monitoring largely unnecessary?
6. What is the risk of catalyst timing slippage? If a product launch moves from Q2 to Q4, does it change the probability distribution or just delay it?
7. Are any catalysts binary (pass/fail with no middle ground), and if so, how does that affect position sizing discipline?

## Red Flags

- Fewer than 3 catalysts identified — thesis is not ready for deployment (framework gate)
- All catalysts are in one direction — directional bias in catalyst identification, not a balanced thesis
- No catalyst expected within the next 6 months — capital is tied up with no information signal
- Catalysts described as conditions ("continued margin improvement") rather than events — not trackable
- Probability estimates are not stated — analyst is avoiding commitment to falsifiability
- Magnitude estimates are absent — no way to verify expected return is consistent with catalyst strength
- Catalyst timeline has no FIRED examples in historical analysis — no validation that prior catalysts have been accurate
- Multiple catalysts depend on the same underlying condition — they are not independent; if the condition fails, all catalysts fail simultaneously (concentrated catalyst risk)
- No monitoring protocol defined — thesis will be monitored by watching the stock price, which provides no thesis-relevant information

## Source Requirements

- **Bull/Bear Framing output**: Required. Catalysts are derived from the key assumptions of the bull and bear cases — cannot be identified without them.
- **Earnings calendar**: Required. Identifies earnings report dates within the investment horizon. Sources: company investor relations, earnings calendar services (Bloomberg, FactSet, Nasdaq.com).
- **Event calendar**: Required for regulatory, macro, and competitive catalysts. Sources: company regulatory filings, FDA calendar, FOMC meeting schedule, product roadmap disclosures.
- **Historical earnings move data**: Required for magnitude estimates. Sources: options implied move from Technical analysis, historical earnings surprise data from Financial Health.
- **Analyst estimate revisions**: Required for monitoring protocol. Sources: FactSet, Bloomberg, Refinitiv consensus.

## Output

- Catalyst list: minimum 3 entries, each with description, direction (BULL/BEAR), expected timeline, probability, magnitude, scenario impact, and status (PENDING/FIRED/EXPIRED)
- Catalyst timeline: chronological display with BULL above and BEAR below the timeline axis
- Direction coverage check: confirmed at least 1 BULL and 1 BEAR catalyst
- Near-term catalyst flag: confirms at least 1 catalyst within 6 months, or explains the implication of none
- Monitoring protocol: per-catalyst observable signal and thesis review trigger
- Catalyst coverage validation: pass/fail on all 4 validation criteria (count, direction, timeline, probability calibration)
