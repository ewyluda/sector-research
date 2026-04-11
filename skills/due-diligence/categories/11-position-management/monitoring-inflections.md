---
name: Monitoring & Inflections
description: Define the signal set and response protocol for ongoing position monitoring — establishing review cadence, mapping signal types to pre-committed responses, and integrating with the platform's inflection detection system
category: position-management
type: technique
requires: []
---

## Purpose

A position without a monitoring plan is a bet, not an investment. Once entered, every position requires a structured approach to information intake — what to watch, how often to check, and what each observed condition requires in response.

The failure mode of position monitoring is not insufficient vigilance — it is undirected vigilance. Checking a position continuously without a defined signal list and response protocol produces anxiety, not insight. It also produces reactive decision-making: when something looks bad, you sell; when something looks good, you hold or add — with no consistency or framework.

Structured monitoring produces the opposite: specific signals with specific response protocols, checked at defined intervals, with a clear path from signal to decision. The monitoring plan is written before the position is opened and reviewed at each cadence checkpoint — not rewritten in response to market moves.

The platform's inflection detection system (available via the inflection endpoints in the platform API) provides algorithmic signal detection across ~30 KPIs. This monitoring plan defines which platform signals are relevant to this specific thesis and what action each triggers.

## Methodology

### Step 1: Define the Monitoring Cadence

Position monitoring occurs at three frequencies, each driven by different information availability:

**Quarterly cadence (mandatory)**: Triggered by earnings reports and associated SEC filings (10-Q, 10-K). Every position requires a full review at each earnings release.

The quarterly review checklist:
- Revenue growth vs. prior quarter and vs. guidance: is the growth trajectory intact?
- Gross margin trend: expanding, stable, or compressing? Compare to thesis expectation.
- Operating income and free cash flow: is the business generating or consuming cash at the expected rate?
- Forward guidance: did management raise, maintain, or lower? What language changed?
- Earnings transcript: any new risk disclosures, customer concentration changes, competitive commentary?
- Thesis pillar status: update each pillar's current status (Intact / Monitoring / Triggered)
- Stop-loss and review triggers: have any conditions been met or approached?

After the quarterly review, produce a one-paragraph position status update: thesis still intact / thesis stressed / thesis broken.

**Ad-hoc cadence (event-driven)**: Triggered by material corporate events outside the quarterly earnings cycle. Do not wait for the next quarterly review when material events occur.

Events that trigger immediate ad-hoc review:
- Earnings pre-announcement (guidance revision outside normal cycle)
- Material SEC filings: 8-K disclosures, proxy amendments, executive departures
- Significant insider transactions (Form 4 filings showing cluster selling or large individual sales)
- Competitor earnings results that directly reference competitive dynamics relevant to the thesis
- Regulatory action affecting the company or its primary market
- Macroeconomic regime change signals relevant to the macro sensitivity of the thesis

**Continuous awareness (not active monitoring)**: Maintaining awareness of news headlines, unusual price/volume action, and analyst rating changes. This is not a formal review — it is a tripwire that escalates to an ad-hoc review if something significant surfaces.

Continuous awareness tripwires:
- Stock price moves more than 5% in a single day without a publicly announced reason
- Unusual options activity (significant increase in put volume or IV spike) suggesting informed selling
- Analyst downgrade accompanied by specific thesis-relevant reasoning (not just valuation)
- News headline mentioning the company in the context of litigation, regulatory investigation, or a competitor win

### Step 2: Build the Signal List

The signal list is a maximum of 10 items. More than 10 signals cannot be properly monitored. Prioritize signals that are directly connected to the bull thesis pillars — not all possible negative information about the company.

**Signal types and their source**:

| Signal Type | Source | Relevance |
|-------------|--------|-----------|
| Earnings miss vs. guidance | Earnings report / platform earnings review agent | Core execution signal — directly tests revenue and margin thesis pillars |
| Guidance cut (revenue or margin) | Earnings transcript / 8-K | Forward-looking execution signal — management's own assessment of deteriorating trajectory |
| Insider selling cluster | SEC Form 4 / platform insider trading data | Information asymmetry signal — executives selling in volume often precede negative disclosures |
| Moat deterioration signal | Competitor earnings, channel checks, product announcements | Competitive positioning signal — tests the defensibility assumption of the business quality thesis |
| Macro regime change | FRED macro data / platform macro agent / Fed announcements | Macro sensitivity signal — relevant if the thesis depends on specific interest rate, inflation, or growth environment |
| Competitor breakthrough | Competitor earnings calls, product launch announcements, win/loss disclosures | Direct competitive threat — tests market share gain assumption |
| Customer concentration change | 10-K, 10-Q customer disclosures, press releases | Concentration risk signal — tests revenue stability assumption |
| Free cash flow inflection | Quarterly financial statements | Capital generation signal — tests the compounding / returns thesis |
| Management credibility event | Earnings transcript tone analysis, guidance accuracy track record | Leadership quality signal — tests the management execution thesis |
| SEC filing language changes | 10-K Item 1A, 10-Q risk factors | Disclosure signal — new or escalated risk language indicates management's internal assessment of threat level |

**Platform inflection integration**: The platform's inflection detection system monitors ~30 KPIs and flags statistical inflections. After initiating a position, configure the relevant ticker in the platform's watchlist and review inflection alerts at each quarterly cadence checkpoint. Platform-detected inflections relevant to this position's signal list should escalate to an ad-hoc review.

Platform inflection categories most relevant to equity position monitoring:
- Revenue growth rate change (direction or magnitude)
- Margin trend inflection (gross or operating)
- Sentiment shift (analyst consensus or social sentiment)
- Technical structure change (moving average crossovers, volume pattern changes)

### Step 3: Map Each Signal to a Response

Every signal in the monitoring list must have a pre-committed response. The response options are:

**Investigate (no immediate action)**: The signal is ambiguous and requires additional data before a conclusion can be drawn. Appropriate for signals with low specificity or single-quarter noise.
- Required follow-up: specific additional data to gather and timeline to gather it
- Default escalation: if investigation does not produce resolution within 3 weeks, default to Trim

**Review thesis (possible action)**: The signal suggests thesis stress but not clear invalidation. Appropriate for signals that confirm a review trigger condition from the stop-loss-invalidation sub-skill.
- Required follow-up: immediate deep-dive review, position trimmed to 50% during review period
- Decision deadline: full exit or restoration within 3 weeks of trigger

**Trim (immediate partial exit)**: The signal is a confirmed review trigger or the thesis is clearly stressed in a material dimension. Reduce to 50% of current size within 2-3 trading days.
- No deep-dive required to execute the trim — the trim is the response; the deep-dive follows
- Restoration to full size requires confirming evidence that the thesis is intact

**Exit (immediate full exit)**: The signal has confirmed a hard stop condition from the stop-loss-invalidation sub-skill. Exit within 2-3 trading days.
- No further deliberation. The decision was made when the position was opened.
- Log the exit with condition, date, price, and outcome for future calibration

**Response mapping table format**:

| Signal | Trigger Threshold | Response | Timeline | Follow-up Required |
|--------|-------------------|----------|----------|--------------------|
| Earnings miss vs. guidance | >500 bps miss for 2 consecutive quarters | Exit | 2-3 trading days | Log invalidation |
| Earnings miss vs. guidance | 200-500 bps miss, maintained guidance | Review thesis | Trim immediately, decide within 3 weeks | Re-evaluate pillar 2 |
| Guidance cut >10% | Single event, demand-specific | Exit | 2-3 trading days | Log invalidation |
| Guidance cut <10% | Single event, macro-attributed | Investigate | Gather macro data within 2 weeks | Assess macro agent output |
| Insider selling cluster | 3+ executives, >$1M combined, 30 days | Review thesis | Trim immediately | Check Form 4 for patterns |
| Moat deterioration | Competitor win rate >20% in core segment | Review thesis | Trim immediately | Assess competitive response |
| Competitor breakthrough | Direct product parity announcement | Investigate | Monitor for customer response, 6 weeks | Watch next 2 earnings calls |
| Macro regime change | Fed pivot to tightening, +200 bps surprise | Investigate | Assess thesis sensitivity within 2 weeks | Update macro agent context |

### Step 4: Integrate with Thesis Review Workflow

The monitoring plan connects to the broader thesis review workflow:

**Thesis review triggers** (conditions that require a full thesis rebuild, not just a signal check):
- Any hard stop condition is triggered (exit is required, but the post-exit analysis informs future thesis construction)
- Three or more monitoring signals are in active investigation or review simultaneously — convergent pressure suggests the thesis has weakened across multiple dimensions
- The time horizon expires without the thesis playing out and no stop condition has been triggered — a complete re-evaluation determines whether to hold, exit, or rebuild with a new horizon
- A position has been trimmed to half and held for 6+ months without restoration to full size — this signals thesis uncertainty that should be resolved through a full review

**Thesis review output**: After a full thesis review, produce a written decision: (1) Thesis intact — restore to full position size with updated monitoring signals, (2) Thesis weakened — maintain at half size with revised monitoring plan, or (3) Thesis broken — exit remaining position.

## Key Questions

1. Does the quarterly review checklist directly test each bull thesis pillar, or is it a generic financial review?
2. Is every signal in the monitoring list mapped to a specific, pre-committed response — or are any signals mapped to "watch" (which is not a response)?
3. Is the monitoring list capped at 10 signals? A longer list is not more rigorous — it is less actionable.
4. Are the platform's inflection detection alerts configured for this ticker, and is there a defined process for incorporating platform inflection signals into the quarterly review?
5. If three signals are simultaneously in active investigation or review status, is there a pre-committed protocol for addressing convergent thesis stress?
6. Is there a defined process for what happens when the time horizon expires?

## Red Flags

- Monitoring plan longer than 10 signals — cognitive overload produces undifferentiated anxiety, not insight
- Any signal mapped to "watch" or "monitor" without a specific action threshold — watching without an action trigger is not monitoring, it is avoidance
- Quarterly review checklist that does not reference the bull thesis pillars — a review that does not test the thesis is not a thesis review
- No integration with the platform's inflection detection system — leaves mechanical signal detection unused
- Convergent signal pressure (3+ simultaneous investigations) treated as normal — multiple simultaneous signals are a systemic warning, not individual noise events
- Thesis review workflow without a decision deadline — open-ended reviews produce indefinite position holding during deterioration
- Monitoring plan that is identical to the original due diligence checklist — once a position is open, monitoring should focus on what has changed, not re-running the original analysis

## Source Requirements

- **Platform inflection detection system**: `/api/inflections/{ticker}` and `/api/inflections/{ticker}/timeseries` — Tier 1 for ongoing KPI monitoring
- **Platform earnings review agent**: quarterly earnings vs. guidance comparison — Tier 1
- **Platform fundamentals agent**: revenue, margin, and cash flow trends — Tier 1
- **SEC EDGAR Form 4**: insider transaction data — Tier 1
- **SEC EDGAR 8-K, 10-Q, 10-K**: material event disclosures, risk factor changes — Tier 1
- **Platform macro agent**: FRED macro data for regime change signals — Tier 1 (if thesis has macro sensitivity)
- **Platform news agent**: ad-hoc event detection (tripwire, not structured monitoring) — Tier 2
- **Platform technical agent**: price/volume unusual activity detection — Tier 2

## Output

- Quarterly review checklist: 8-12 specific questions directly tied to the bull thesis pillars
- Ad-hoc review trigger list: specific events that require immediate response outside the quarterly cadence
- Monitoring signal list: maximum 10 signals with response protocol table
- Response protocol summary: [Signal | Threshold | Response | Timeline | Follow-up]
- Thesis review workflow: conditions that trigger a full thesis rebuild and the three possible outcomes
- Calendar: next 4 quarterly review dates based on the company's earnings calendar
- Platform inflection configuration note: which KPI categories to monitor in the platform for this ticker
