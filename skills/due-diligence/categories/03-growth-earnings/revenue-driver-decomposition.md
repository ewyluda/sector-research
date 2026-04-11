---
name: Revenue Driver Decomposition
description: Break revenue into component streams by product, service, and geography to identify growth engines, concentration risk, and acceleration patterns
category: growth-earnings
type: technique
requires: [financials, revenue-segments, earnings-transcripts]
---

## Purpose

Understand the structure of revenue — not just the headline growth number, but which streams are driving it, how durable they are, and where concentration risk lurks. A company growing 20% with two streams accelerating and one decelerating is a very different investment than one where all growth comes from a single segment at risk of commoditization.

Revenue decomposition is the foundation for all earnings quality and guidance analysis. You cannot assess guidance credibility without knowing which segments management tends to lowball, and you cannot assess earnings quality without knowing which segments carry the highest margins.

## Methodology

**Step 1 — Identify revenue streams**

Pull all disclosed revenue segments from SEC filings (10-K, 10-Q) and investor presentations. Classify each stream by:
- Type: product / service / subscription / transaction / licensing / geographic region
- Reporting basis: management segment vs. GAAP segment (note any differences)
- Historical availability: how many quarters of segment data exist?

Create a master list of all distinct revenue streams. If the company reports a single segment, use geographic breakdown or product mix disclosures from earnings transcripts.

**Step 2 — Calculate growth rates and share**

For each stream, calculate:
- YoY revenue growth rate (current quarter vs. prior year quarter)
- Sequential growth rate (QoQ, seasonally adjusted where relevant)
- % of total revenue (current quarter and 4-quarter trailing average)
- 3-year CAGR where data permits

Build a table: Stream | $Revenue | YoY Growth | % of Total | 3yr CAGR

**Step 3 — Assess margin contribution**

Where segment operating margin is disclosed, calculate:
- Gross margin per segment (if available)
- Operating margin per segment
- Revenue-weighted margin contribution to consolidated margins

Where segment margins are not disclosed, use proxy data: management commentary on segment profitability, product mix disclosures, and peer benchmarks for similar business lines.

**Step 4 — Classify acceleration vs. deceleration**

For each stream, classify growth trajectory:
- **Accelerating**: YoY growth rate increasing for 2+ consecutive quarters
- **Stable**: YoY growth rate within ±3 percentage points over trailing 4 quarters
- **Decelerating**: YoY growth rate declining for 2+ consecutive quarters
- **Reversing**: From growth to contraction or contraction to growth

Flag any stream where deceleration is occurring alongside increasing revenue share — this indicates a growing drag on overall performance.

**Step 5 — Identify concentration risk**

Calculate Herfindahl-Hirschman Index (HHI) equivalent for revenue: sum of squared revenue shares. Higher = more concentrated.

Apply concentration flags:
- Any single stream >50% of revenue = HIGH concentration risk (flag)
- Any single stream >30% of revenue AND decelerating = MODERATE-HIGH concentration risk
- Top 3 streams >80% of revenue = limited diversification
- Geographic concentration: single region >70% with no expansion = geopolitical/macro risk

## Key Questions

1. Which streams are growing faster than the company average — and are these the high-margin or low-margin streams?
2. Is the mix shift positive (growing share going to high-margin streams) or negative (growth concentrated in lower-margin segments)?
3. Are any large streams decelerating, and what would the consolidated growth rate look like if they stall completely?
4. Does management's narrative about growth drivers match the actual segment data?
5. Are there any streams not yet in the segment data that management discusses as a future driver — and what assumptions are baked in?

## Red Flags

- Single stream >50% of revenue with decelerating growth
- Core high-margin segment losing revenue share to lower-margin segments (negative mix shift)
- Management emphasizing a small, fast-growing segment while the large core segment decelerates (narrative distraction)
- Geographic concentration >70% in a single region facing regulatory, political, or economic risk
- Revenue growth driven primarily by price increases rather than volume — unsustainable if pricing power erodes
- Segment disclosures becoming less granular over time (management reducing transparency as performance weakens)

## Source Requirements

**Tier 1 (required for this analysis):**
- SEC EDGAR: 10-K and 10-Q filings, Note on Segment Information
- Company investor relations: segment revenue tables, supplemental data packages
- FMP / FactSet: revenue segment endpoint (`revenue-segments` via platform data provider)
- Earnings transcripts: management commentary on segment trends (for context and attribution)

**Tier 2 (qualitative context only):**
- Sell-side research: analyst models often have more granular segment builds
- Industry reports: external market size data for TAM comparison per segment
- News / channel checks: qualitative signals on segment demand

## Output

Revenue decomposition table with the following columns:

| Stream | Q Revenue ($M) | YoY Growth | % of Total | 3yr CAGR | Gross Margin | Trajectory | Concentration Flag |
|--------|---------------|------------|------------|----------|--------------|------------|-------------------|
| [name] | [value] | [%] | [%] | [%] | [% or N/A] | Accelerating / Stable / Decelerating / Reversing | None / MODERATE / HIGH |

Supporting outputs:
- Mix shift assessment: is revenue share moving toward or away from high-margin streams?
- Concentration risk summary: which streams, if disrupted, would most damage total revenue?
- Narrative alignment check: does segment data support management's stated growth thesis?
- Key streams to monitor in next 2-3 earnings reports
