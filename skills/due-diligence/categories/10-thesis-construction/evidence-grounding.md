---
name: Evidence Grounding
description: Map every claim in the investment thesis to a specific finding from a prior due diligence sub-skill, flag unsupported claims, and ensure quantitative assertions cite Tier 1 sources
category: thesis-construction
type: technique
requires: []
---

## Purpose

Evidence Grounding is the quality control layer of the thesis construction phase. It enforces a single rule: **every claim in the thesis must trace to a specific finding from a prior due diligence sub-skill.** No assertion floats free.

This sub-skill prevents the most common failure mode in investment research — the plausible narrative. A plausible narrative is a thesis that sounds right, uses correct terminology, and cites real companies and numbers, but whose specific claims are not independently verifiable from the underlying analysis. Plausible narratives produce confident-sounding research and unpredictable investment outcomes because the analyst cannot distinguish between claims that are well-evidenced and claims that are assumptions dressed as facts.

Evidence Grounding creates an audit trail. If a claim survives the grounding process, it has a named source, a source tier, and a specific data point. If it does not survive, it is either upgraded (analyst finds the supporting evidence) or downgraded (claim is removed or qualified with an explicit confidence caveat).

This sub-skill is not scored. It is a process gate. A thesis that has not been through evidence grounding is not complete.

## Methodology

### Step 1: Extract All Claims from the Thesis

Pull every claim from the three components of the thesis constructed so far:
- Bull/Bear Framing: core arguments, evidence points, key assumptions
- Catalyst Identification: catalyst descriptions, probability estimates, magnitude estimates
- Variant Perception: variant perception statement, evidence for/against

Separate claims into two types:

**Quantitative claims**: Any claim that contains a number, a percentage, a ratio, a timeframe, or a comparison to a benchmark. Examples:
- "Revenue growth of 18-22% CAGR over 3 years"
- "Gross margin expansion of 200-300 basis points by FY2026"
- "The company trades at a 30% discount to its software peer group"
- "Customer retention rate of 94% vs. industry average of 87%"
- "Management has repurchased $2.1B of stock over the past 18 months"

**Qualitative claims**: Any claim that describes a competitive position, strategic direction, management quality, market dynamic, or risk factor without a specific number. Examples:
- "The company has a durable moat in payments processing"
- "Management has a strong track record of capital allocation"
- "AI disruption risk in this segment is low"
- "The regulatory environment is favorable for market share consolidation"

Both types require grounding. Quantitative claims require harder evidence (Tier 1 or Tier 2 sources). Qualitative claims can be supported by Tier 2 or Tier 3 sources, but must still cite a specific finding.

### Step 2: For Each Claim, Cite Category, Sub-Skill, Data Point, and Source Tier

For every claim extracted in Step 1, complete the following citation:

**Category**: Which of the 9 prior due diligence categories does this finding come from? (Business Quality, Financial Health, Growth & Earnings, Management & Governance, Technical & Market Structure, Macro Regime, Sentiment & Narrative, Risk Assessment, Future Durability)

**Sub-Skill**: Which specific sub-skill within that category produced this finding?

**Data Point**: The specific number, ratio, statement, or finding that supports the claim. This must be reproducible — another analyst reading the same sub-skill output should be able to find the same data point.

**Source Tier**:
- **Tier 1**: Primary sources — 10-K, 10-Q, 8-K, audited financial statements, SEC EDGAR filings, official government data (FRED, Census Bureau, BLS). These are the highest-reliability sources because they are legally attested and audited.
- **Tier 2**: Secondary analytical sources — earnings call transcripts (management speaking, not management filings), industry reports from named research firms (Gartner, IDC, Forrester), peer-reviewed academic studies, court filings, regulatory proceeding records. These are credible but not audited — they reflect someone's analysis or statements.
- **Tier 3**: Tertiary sources — analyst reports, news articles, management presentations (investor day decks, roadshow materials), company-produced case studies, blog posts, expert interviews. These are informative but represent opinions or marketing, not independent verification.

### Step 3: Flag Claims Without Tier 1 Support

After mapping all claims, identify every **quantitative claim** that is supported only by Tier 2 or Tier 3 sources. These are the highest-risk claims in the thesis.

For each flagged claim, choose one of three resolutions:
1. **Upgrade**: Find the Tier 1 source that independently confirms the claim (e.g., the earnings call transcript states the retention rate, but it also appears in the 10-K customer metrics disclosure — cite the 10-K instead)
2. **Qualify**: Add an explicit confidence caveat to the claim in the thesis (e.g., "per management guidance on the Q3 earnings call — not independently verified in SEC filings")
3. **Remove**: If no Tier 1 or Tier 2 source can be found and the claim is material to the thesis, remove it and adjust the thesis accordingly

A quantitative assertion that rests only on Tier 3 sources and cannot be resolved through options 1 or 2 is a red flag. If the claim is central to the bull or bear case, the thesis probability estimates must be adjusted to reflect the uncertainty.

### Step 4: Flag Claims Relying on Forward Projections Without Historical Support

Forward projections (growth rates, margin targets, market share estimates) are structurally different from historical data. They are inherently uncertain. The question is not whether a forward claim is present — all theses require forward projections — but whether the forward claim is **anchored in historical evidence**.

For each forward projection in the thesis, check:
- **Historical precedent**: Has this company achieved this metric before? In which period? Under what conditions?
- **Peer validation**: Have comparable companies achieved this metric? Under what conditions?
- **Management track record**: Has management made similar forward claims before, and did they deliver?

**Red flag condition**: A quantitative forward projection that has no historical precedent at this company, no peer validation, and no management track record supporting it is an unsupported forward claim. These must be explicitly labeled in the thesis as high-uncertainty assumptions.

Example of acceptable forward claim: "FY2026 gross margin target of 72% is supported by the company's historical margin trajectory (68% → 70% → 71% in FY2023-FY2025), management's stated 200-300bps annual improvement target (Q4 FY2025 earnings call), and comparable SaaS peers at 70-75% gross margins."

Example of unacceptable forward claim: "FY2026 gross margin of 72%" cited only to an analyst note without historical trajectory or peer data.

### Step 5: Produce the Evidence Map

The evidence map is the final output of this sub-skill. It is a structured table that lists every material claim in the thesis alongside its citation.

**Evidence Map structure (per claim):**

| Claim | Claim Type | Category | Sub-Skill | Data Point | Source Tier | Flag |
|-------|-----------|----------|-----------|------------|-------------|------|
| [Claim text] | Quantitative / Qualitative | [Category name] | [Sub-skill name] | [Specific data] | Tier 1/2/3 | GROUNDED / QUALIFIED / FLAGGED |

**Flag definitions:**
- **GROUNDED**: Claim has Tier 1 or Tier 2 support with a specific data point. No further action needed.
- **QUALIFIED**: Claim has only Tier 3 support or relies on an unverified forward projection. Claim is retained but must carry an explicit confidence caveat in the thesis.
- **FLAGGED**: Claim has no identifiable source, is inconsistent with prior sub-skill findings, or is a quantitative assertion from Tier 3 only. Claim must be removed or replaced before the thesis is deployed.

**Grounding summary:**
- Total claims: N
- GROUNDED: X (X%)
- QUALIFIED: Y (Y%)
- FLAGGED: Z (Z%)

A thesis is considered evidence-complete when: FLAGGED count = 0 and QUALIFIED claims each carry an explicit caveat in the thesis document.

## Key Questions

1. If a skeptical analyst challenged every number in this thesis, which claims would I be unable to defend with a primary source?
2. Are the claims that are hardest to ground the most important to the thesis, or peripheral? (Hard-to-ground claims that are central to the bull case are the highest-risk elements of the thesis.)
3. Is the management track record cited in the thesis based on historical delivery (Tier 1/2) or management guidance (Tier 3)? The difference matters enormously for probability weighting.
4. For forward projections, what would have to happen historically for this projection to be reasonable? Have those conditions ever existed at this company?
5. Are there any claims in the thesis that I assumed were well-known facts but have not verified against a primary source? (Common examples: addressable market sizes, industry growth rates, competitive market share figures — these are frequently cited from analyst reports that themselves cite other analyst reports.)
6. Does the evidence map reveal a concentration of Tier 3 sources in any one scenario (bull or bear)? If the bull case is mostly Tier 3-supported and the bear case is mostly Tier 1-supported, the probability estimates should reflect the evidence asymmetry.
7. Are there findings from prior sub-skills that were NOT included in the thesis but that would materially change the probability estimates if they were? Omission of inconvenient evidence is a bias risk.

## Red Flags

- Quantitative assertions sourced only from analyst reports or management presentations — these are not independently verified and are subject to optimism bias
- Market size claims (TAM, SAM, SOM) cited to a single analyst note or consulting firm report without cross-referencing multiple independent sources
- Retention rates, NPS scores, or win rates cited only from company-produced marketing materials — these are unaudited and self-selected
- Forward margin or growth targets sourced from management guidance without historical trajectory or peer validation to anchor them
- Evidence map shows more than 30% of claims are QUALIFIED or FLAGGED — thesis has insufficient grounding for deployment
- Claims about competitive position or market share that rely on company-published data without independent validation (companies report their own market share in favorable terms)
- Historical financial data cited from investor presentations rather than 10-K filings — presentations sometimes restate or adjust figures; 10-K is the authoritative source
- Evidence map is missing entire claim categories — suggests the analyst reviewed only bull-supporting evidence and did not systematically map bear case claims

## Source Requirements

- **All prior category outputs**: Required. Evidence Grounding cannot be completed without the findings from all 9 prior due diligence categories.
- **Bull/Bear Framing output**: Required. The claim list is derived from the completed bull/bear scenarios.
- **Catalyst Identification output**: Required. Catalyst descriptions and magnitude estimates are claims that require grounding.
- **Variant Perception output**: Required. Evidence for/against the variant view are claims that require grounding.
- **SEC EDGAR**: Primary Tier 1 source for all financial statement data, segment disclosures, risk factors, and management certifications.
- **FRED / BLS / Census**: Primary Tier 1 source for all macro data cited in the thesis.
- **Earnings call transcripts**: Tier 2 source for management commentary. Verify transcript source is from an authoritative transcription service (Seeking Alpha, S&P Global, company IR page) not a paraphrased summary.

## Output

- Evidence map: complete table of all material thesis claims with category, sub-skill, data point, source tier, and flag (GROUNDED / QUALIFIED / FLAGGED)
- Grounding summary: total claims, GROUNDED count (%), QUALIFIED count (%), FLAGGED count (%)
- Flagged claims list: each FLAGGED claim with the specific reason for flagging and the required resolution
- Qualified claims list: each QUALIFIED claim with the confidence caveat that must be added to the thesis
- Forward projection audit: each forward projection with historical precedent, peer validation, and management track record assessment
- Evidence completeness verdict: COMPLETE (FLAGGED = 0, all QUALIFIED claims caveated) / INCOMPLETE (requires resolution before deployment)
