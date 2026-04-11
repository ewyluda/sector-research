---
name: Entry & Exit Strategy
description: Define entry zones based on technical support and valuation floors, establish three pre-committed exit triggers, and set the intended time horizon before initiating a position
category: position-management
type: technique
requires: []
---

## Purpose

The single most common error in investment execution is conflating "thesis validated" with "enter now at any price." Entry discipline separates investors who buy at reasonable prices from those who chase. Exit discipline separates investors who respect their own thesis from those who rationalize indefinite holding.

Entry and exit decisions made before the position is open are rational. Made after entry, they are emotional. This technique produces a written entry zone and three pre-committed exit triggers that can be followed without in-the-moment deliberation when the position moves adversely.

Entry zones acknowledge that prices move and precise timing is impossible. Exits acknowledge that there are three legitimate reasons to close a position — and only three.

## Methodology

### Step 1: Define the Ideal Entry Zone

An entry zone is a price range, not a single price. Entry zones are defined by two boundaries: an upper boundary above which the risk/reward deteriorates meaningfully, and a lower boundary below which the setup is likely no longer valid (fundamental deterioration, not just price decline).

**Identify the upper boundary** using valuation discipline:
- Compute the DCF bear case (from the platform's fundamentals agent or your own model) — this is the minimum fair value under pessimistic assumptions
- Compute the current analyst consensus price target — this anchors the midpoint expected return
- The upper boundary is the price at which the upside to price target falls below your minimum required return (typically 20-30% for equities; adjust for risk level)
- If current price is already above the upper boundary, the entry zone has not been reached — wait

**Identify the lower boundary** using technical support:
- Identify the nearest meaningful technical support level (52-week low, prior consolidation base, 200-day moving average) from the platform's technical agent output or price chart
- The lower boundary is typically 3-7% above that support level — close enough to benefit from the support, with a small buffer for a brief violation
- If price falls through the lower boundary on high volume, the setup has likely changed character; re-evaluate before entering

**Zone format**: "Entry zone is $X to $Y. Above $Y, risk/reward is insufficient. Below $X, the technical setup is broken and fundamental review is required before entry."

**Entry conditions within the zone**: Consider requiring at least one confirming condition before executing within the zone:
- Price stabilizing after a pullback (2+ days of constructive price action)
- Volume declining on down days within the zone (sellers exhausting)
- A catalyst timing alignment (entering 4-6 weeks before an expected positive catalyst)

Never require all conditions simultaneously — that eliminates the zone entirely. One condition is sufficient confirmation.

### Step 2: Define Three Exit Triggers

Every position has exactly three legitimate exit reasons. Document each with specific, observable criteria before entering.

**Exit Trigger 1 — Thesis Invalidation**: The thesis is wrong, and the position should be exited regardless of price, profit or loss.

Define the invalidation condition by drawing from the thesis risk map (from the risk assessment category):
- Identify the single most thesis-critical pillar
- Define the specific observable condition that confirms that pillar has failed
- This is not a price condition — price is downstream of fundamentals. The trigger is a fundamental event or data point.
- Examples: "Exit if two consecutive quarters show revenue growth below 5% YoY after guiding for 15%+" or "Exit if gross margin falls below 60% due to product mix shift confirming the competitive pricing pressure thesis"

Commitment: When Trigger 1 is met, the exit is not optional. It is not subject to "let me wait one more quarter." The position is exited within 2-3 trading days of confirmation.

**Exit Trigger 2 — Price Target Reached**: The thesis has worked, and the expected return has been realized.

Define the price target exit:
- Base case DCF or analyst consensus target is the primary reference (from the platform's fundamentals agent)
- The exit is not necessarily the exact price target — it is a zone approaching the target (typically within 5-10%)
- When price approaches the target zone, evaluate whether the thesis has new information that justifies a higher target, or whether the original expected return has been earned
- Trim or exit based on whether a new thesis can be constructed at the current price

Commitment: Do not move the price target higher simply because price is approaching it. A target should only move if the underlying fundamentals justify it — not because you want to stay in a winning position.

**Exit Trigger 3 — Opportunity Cost**: A clearly superior risk/reward alternative exists, and capital is better deployed elsewhere.

Define the opportunity cost exit:
- This trigger requires a specific alternative position with a documented thesis, not a vague sense that "something better is out there"
- The alternative must offer materially better expected return (typically 30%+ higher) or meaningfully lower risk for equivalent expected return
- This trigger is rarely invoked — most exits happen via Trigger 1 or 2 — but having it pre-committed prevents indefinite holding when better opportunities arise

Commitment: Opportunity cost exits should be rare and well-documented. A portfolio full of Trigger 3 exits indicates excessive trading, not disciplined capital allocation.

### Step 3: Set the Time Horizon

Define the expected investment duration before the thesis plays out.

**Time horizon categories**:
- **Short-term** (3-6 months): Catalyst-driven trades — earnings beats, product launches, regulatory approvals. Exit if catalyst does not materialize within the window.
- **Medium-term** (6-18 months): Operational execution plays — margin expansion, market share gains, product mix shifts. Exit if no evidence of execution progress within 2-3 earnings cycles.
- **Long-term** (18+ months): Compounding thesis plays — secular growth, moat expansion, multi-year market transitions. Requires higher conviction and tolerance for near-term noise.

**Time horizon discipline**: If the time horizon passes without the thesis playing out AND no Trigger 1 or 2 condition has been met, conduct a full re-evaluation. Do not extend the horizon by default. A conscious decision to extend requires a new, documented thesis with a new horizon.

State the time horizon explicitly: "The thesis is expected to play out within [X] months. If the position has not reached the price target zone and Trigger 1 has not been met by [date], a full thesis review is required."

## Key Questions

1. Is the entry zone defined by both a valuation ceiling and a technical floor, or is it based on only one anchor?
2. Can each of the three exit triggers be written as a specific, observable condition — not a feeling or a vague sense that "something has changed"?
3. Is Exit Trigger 1 (thesis invalidation) based on a fundamental event rather than a price level?
4. Is the time horizon consistent with the type of thesis (catalyst-driven vs. operational execution vs. long-term compounding)?
5. If forced to execute the exit triggers right now, could all three conditions be evaluated without any additional research?
6. Does the entry zone still exist — is the current price within the defined zone, or has the opportunity passed?

## Red Flags

- Entry zone defined as a single exact price — false precision that will either never be hit or leads to chasing the print
- Exit strategy limited to "sell at the price target" — no provision for thesis failure before target is reached
- Thesis invalidation trigger defined as a percentage price decline rather than a fundamental event — conflates price volatility with thesis failure
- Price target moved higher as price approaches it, without corresponding fundamental justification — classic rationalization of not wanting to exit a winner
- Time horizon set to "long term" for a thesis that is actually catalyst-dependent — mismatched horizon creates false tolerance for failed catalysts
- Opportunity cost exit trigger invoked without a specific documented alternative thesis — vague "something better" is not an exit trigger
- All three exit triggers defined as price-based — no connection to the underlying business reality

## Source Requirements

- **Platform fundamentals agent**: DCF valuation, analyst price targets, earnings estimates — Tier 1 for valuation-based entry upper boundary
- **Platform technical agent**: price history, support/resistance levels, 52-week range, moving averages — Tier 1 for technical-based entry lower boundary
- **Platform thesis agent**: bull thesis pillars and synthesis — Tier 1 input for Trigger 1 thesis invalidation condition
- **Platform risk assessment (thesis-risk-mapping)**: kill conditions per pillar — direct input to Trigger 1 criteria
- **SEC EDGAR**: earnings transcript and 10-K for forward guidance establishing time horizon anchors — Tier 1
- **Analyst consensus**: price target distribution for Exit Trigger 2 calibration — Tier 2

## Output

- Entry zone: upper boundary (price) with valuation rationale + lower boundary (price) with technical rationale
- Entry conditions: 1-2 confirming signals required within the zone before execution
- Exit Trigger 1 (thesis invalidation): specific fundamental event or data threshold, with commitment to exit within 2-3 trading days of confirmation
- Exit Trigger 2 (price target): price zone approaching target with re-evaluation criteria
- Exit Trigger 3 (opportunity cost): specific threshold for what constitutes a "clearly superior" alternative
- Time horizon: duration category (short/medium/long), expected play-out date, and review trigger if horizon passes without resolution
