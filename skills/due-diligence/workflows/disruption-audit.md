---
name: Disruption Audit
description: 1-2 hour workflow to assess AI and technology disruption risk for a specific company — produces a RESILIENT / EXPOSED / CRITICAL rating with probability-weighted valuation impact
type: workflow
estimated_time: 1-2 hours
---

## When to Use

- Evaluating any company in a sector facing meaningful AI or technology disruption (software, professional services, media, financial services, healthcare administration, logistics, education)
- An existing holding is showing competitive pressure from AI-native entrants (margin compression, customer churn, pricing power erosion)
- Conducting a portfolio-wide technology exposure review to identify holdings with unpriced disruption risk
- A major AI capability announcement (new model, new product category) warrants re-examining an existing thesis
- Any ticker that scored below 6.0 on Future Durability in a prior deep-dive

This workflow can be run standalone or as a supplement to a deep-dive when the Future Durability phase requires more depth.

## Process

### Step 1 — Revenue Foundation (20 min)

Before assessing disruption risk, establish exactly what is being disrupted. A company with a complex revenue mix requires segment-level analysis — disruption rarely hits all revenue streams equally.

**Skills used:**
- `categories/03-growth-earnings/revenue-driver-decomposition`
- `categories/02-financial-health` (data validation — pull segment breakdown from most recent 10-K)

**Deliverable: Revenue vulnerability map**

For each revenue segment or product line, document:

| Segment | % of Revenue | % of Gross Profit | AI Substitutability | Human Judgment Required | Assessment |
|---------|-------------|-------------------|--------------------|-----------------------|------------|
| [Segment A] | X% | X% | High / Medium / Low | High / Medium / Low | [Vulnerable / Defensible / Unknown] |

**AI Substitutability scoring guide:**
- **High** — the task can be replicated by an LLM, vision model, or automation with minimal workflow integration (data entry, basic content generation, routine legal/financial analysis, first-tier customer support)
- **Medium** — AI can handle 50-70% of the workflow but requires human review, complex judgment, or relationship management
- **Low** — the core value delivery requires physical presence, deep relationship trust, complex multi-system integration, or regulatory sign-off that AI cannot currently provide

**Flag any segment where AI Substitutability is High AND that segment represents > 15% of gross profit.** These are the primary disruption vectors.

---

### Step 2 — Moat Under Pressure (20 min)

The standard moat analysis asks whether competitors can replicate the business in 5 years. This step asks the harder question: can an AI-native entrant replicate the business in 2 years at 10% of the cost?

**Skills used:**
- `categories/01-business-quality/moat-analysis` (focused on AI survival — apply the standard framework then stress-test each moat source against AI capabilities)
- `categories/01-business-quality/competitive-positioning` (map AI-native competitors specifically — who has entered or is emerging in this space?)

**For each moat source, answer:**

| Moat Source | Strength (Pre-AI) | AI Survival? | Reasoning |
|-------------|------------------|--------------|-----------|
| Switching costs | High / Medium / Low | Yes / Partial / No | [Why] |
| Network effects | High / Medium / Low | Yes / Partial / No | [Why] |
| Scale economies | High / Medium / Low | Yes / Partial / No | [Why] |
| Intangible assets (brand, IP) | High / Medium / Low | Yes / Partial / No | [Why] |
| Cost advantages | High / Medium / Low | Yes / Partial / No | [Why] |

**AI-native competitor mapping:**
- Name the top 3 AI-native entrants or AI-augmented incumbents competing in each high-vulnerability segment
- For each: founding year, funding raised, reported customer wins, pricing vs. incumbent
- Assess: are they winning on price only, or on capability? Price-only wins are more defensible; capability wins signal structural displacement

**Key question:** Does the moat protect against an AI-native competitor who enters with a 10x cost advantage and a 3x speed advantage? If the moat is primarily "we have a large sales force and existing customer relationships," that is not AI-resilient.

---

### Step 3 — Durability Assessment (30 min)

This is the analytical core of the audit. Run all four Future Durability sub-skills with an AI-specific lens.

**Skills used:**
- `categories/09-future-durability/cash-flow-durability`
- `categories/09-future-durability/ai-disruption-vulnerability` (full analysis — do not abbreviate)
- `categories/09-future-durability/revenue-defensibility`
- `categories/09-future-durability/technology-adoption-curve`

**Cash-flow durability focus questions:**
- If AI competitors compress pricing by 20-30% over the next 3 years, what happens to EBITDA margins?
- Does the company have sufficient free cash flow to fund a technology transition (R&D ramp, retraining, platform rebuild) while maintaining competitive pricing?
- What is the revenue-at-risk if the 2-3 most vulnerable segments face 30% volume decline over 5 years?

**AI disruption vulnerability — key outputs to extract:**
- Disruption timeline estimate (near-term: < 3 years / medium-term: 3-7 years / long-term: > 7 years)
- Probability of meaningful disruption (best estimate, state your reasoning)
- Which job functions, workflows, or products are most exposed?
- What would a fully AI-native version of this company look like, and what would it cost to build?

**Revenue defensibility focus questions:**
- What percentage of revenue is locked in via long-term contracts, high switching costs, or regulatory requirement?
- What percentage is exposed to spot pricing, annual renewal, or customer discretion?
- Is pricing power increasing, stable, or declining in the most recent 3 quarters?

**Technology adoption curve — position this company:**
- Is the AI disruption wave in this sector in Early Adopter, Early Majority, Late Majority, or Laggard phase?
- What is the typical adoption pace in this vertical (fast: fintech, media / slow: healthcare, government)?
- Where is the company positioned relative to that curve — ahead of it, on it, or behind it?

---

### Step 4 — Management Response (15 min)

Disruption risk is not just about the technology — it is about whether management has the awareness, urgency, and resources to respond. A capable management team in an exposed sector is more investable than a complacent team in a less exposed sector.

**Skills used:**
- `categories/04-management-governance/capital-allocation` (focused on AI investment — what % of capex and R&D is going toward AI/technology transformation?)
- Transcript review — pull the most recent 2 earnings call transcripts and search for AI-related language

**Capital allocation AI investment check:**
- What is the company spending on AI/technology R&D as a percentage of revenue?
- Has that allocation increased, been flat, or decreased over the past 4 quarters?
- Are they building internally, acquiring capabilities, or partnering? Which approach is most credible given their balance sheet?
- Any AI-related acquisitions in the past 18 months? At what valuation multiples?

**Transcript analysis — record verbatim quotes for:**
- How management describes the AI opportunity vs. threat
- Specific AI product initiatives mentioned with timelines
- Any customer wins or competitive losses attributed to AI
- Management's stated view on disruption risk to their own business model

**AI readiness score (your assessment, 1-10):**
- 8-10: Specific AI initiatives with timelines, dedicated investment, demonstrated customer traction
- 5-7: AI acknowledged, some investment, no clear product roadmap or customer proof points
- 2-4: AI mentioned only as a tailwind or opportunity, no specific initiatives or investment evidence
- 1: AI not mentioned or dismissed; no evidence of strategic response

---

### Step 5 — Scenario Synthesis (15 min)

Build three probability-weighted scenarios and calculate the valuation impact of each. The goal is to arrive at a probability-weighted expected value that accounts for disruption risk — which may or may not be priced by the market.

**Scenario definitions:**

**Scenario A: AI-Enhanced**
- Description: The company successfully integrates AI into its products and workflows, becoming more efficient and improving its competitive position
- Key assumptions: Management AI readiness score > 7, moat survives under AI pressure, adoption curve gives 3+ years of runway
- Valuation impact: Assign a multiple expansion or FCF growth rate uplift
- Probability: [Your estimate]

**Scenario B: AI-Disrupted**
- Description: AI competitors take meaningful market share in 2-3 high-vulnerability segments, compressing margins and slowing growth, but the business survives and adapts over time
- Key assumptions: 20-35% volume loss in vulnerable segments over 5 years, margin compression of 500-1000bps, management partially responds
- Valuation impact: Apply revenue-at-risk calculation; model 3-5 year path to new equilibrium
- Probability: [Your estimate]

**Scenario C: AI-Destroyed**
- Description: AI-native competitors structurally displace the business model — customers migrate to significantly cheaper or better alternatives faster than the company can adapt
- Key assumptions: 50%+ revenue loss in core segments within 5 years, management response insufficient, capital not available to fund transformation
- Valuation impact: Terminal value impairment; model as a declining annuity or liquidation
- Probability: [Your estimate]

**Probability-weighted valuation impact:**
```
Expected Value = (P_enhanced × V_enhanced) + (P_disrupted × V_disrupted) + (P_destroyed × V_destroyed)
vs. Current Market Price
```

If Expected Value > Current Price: market may be underpricing resilience
If Expected Value < Current Price: market may be underpricing disruption risk

---

## Output

**Required deliverables:**

1. **Disruption risk rating** — one of:
   - **RESILIENT** — moat survives AI pressure, management is investing, AI-Enhanced scenario probability > 50%
   - **EXPOSED** — meaningful disruption risk in 1-3 revenue segments, management response uncertain, probability-weighted value within 15% of current price
   - **CRITICAL** — high-probability structural displacement, management unprepared, probability-weighted value materially below current price

2. **Per-stream vulnerability map** — the table from Step 1, completed for all revenue segments, with final assessment per segment

3. **Management AI readiness score (1-10)** — with the specific evidence and reasoning behind the score

4. **Probability-weighted valuation impact** — all three scenarios with probability estimates, per-scenario valuation impact, and expected value vs. current market price

5. **Recommended action** — one of:
   - HOLD — disruption risk is manageable and priced or over-priced by market
   - REDUCE — position size should come down pending evidence of management response
   - EXIT — structural displacement probability too high; thesis is broken regardless of current valuation
   - MONITOR — sufficient uncertainty that the position should be maintained at reduced size with specific re-evaluation triggers defined
