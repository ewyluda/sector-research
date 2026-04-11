---
name: SEC Risk Factors
description: Analyze 10-K Item 1A risk factor disclosures by diffing current and prior year filings to identify new, escalated, de-escalated, and reworded risks with severity classification
category: risk-assessment
type: technique
requires: []
---

## Purpose

The SEC mandates that public companies disclose all material risks in Item 1A of their annual 10-K filing. When a company adds a new risk factor or significantly expands existing language, it signals that management's legal counsel believes the threat is real enough to require disclosure. These changes are legally consequential — executives who knowingly omit material risks face liability. For investors, SEC risk factor changes are one of the highest-signal, least-analyzed inputs available: the company is telling you what keeps the board awake at night.

The technique focuses on the **delta** between filings, not the static list. A company that has disclosed the same thirty risk factors for five years is revealing nothing new. A company that introduces a new regulatory risk or significantly expands litigation language is disclosing emerging information.

## Methodology

### Step 1: Pull Current and Prior Year Item 1A

Retrieve both filings:
- **Current 10-K**: Item 1A (Risk Factors) — the full section as filed
- **Prior year 10-K**: same section, same company, filed approximately 12 months earlier

Sources:
- SEC EDGAR full-text search (efts.sec.gov) — most reliable
- Company investor relations page (direct 10-K link)
- FMP EDGAR API if available in the platform

Extract just the Item 1A text from each filing. Remove boilerplate headers, page numbers, and formatting artifacts that would interfere with comparison.

### Step 2: Diff Analysis — Identify Changes

Compare the two Item 1A sections systematically across four change types:

**New risks** (appeared in current filing, absent in prior):
- Search for risk factor headers present in the current filing that have no equivalent in the prior filing
- Verify the risk is genuinely new, not a renamed version of an existing risk
- New risks are the highest-priority signal — they represent legal disclosures of emerging threats

**Removed risks** (appeared in prior filing, absent in current):
- Identify risk factors that were disclosed last year but dropped this year
- Removal can signal resolution of the risk (positive) or that the risk has become so significant it was reorganized
- Verify the risk was not consolidated into another section

**Escalated risks** (present in both filings, but with significantly expanded or strengthened language):
- Compare paragraph length — substantial expansion (>50% word count increase) suggests escalation
- Look for addition of specific dollar amounts, legal proceedings, regulatory citations, or named jurisdictions
- Hedging language removed (e.g., prior year: "may impact" → current year: "will impact") is a strong escalation signal

**De-escalated risks** (present in both filings, but with contracted or softened language):
- Contraction in paragraph length with simplified language
- Hedging language added (e.g., prior year: "faces significant competition" → current year: "competition exists in the market")
- De-escalation can signal genuine risk reduction — but verify against fundamentals

**Reworded risks** (same substance but changed framing):
- Note these for documentation but treat as lower priority
- Watch for reframing that obscures the severity of the underlying risk

### Step 3: Classify Changes by Category

Assign each changed risk factor to one of the following categories:

| Category | Examples | Base Severity |
|----------|----------|--------------|
| Litigation & Legal | Lawsuits, regulatory investigations, patent disputes | High |
| Regulatory & Compliance | New laws, licensing risks, antitrust scrutiny | High |
| Operational | Supply chain, technology failures, cybersecurity | Medium-High |
| Financial | Liquidity, debt covenants, going concern language | High |
| Competitive | New entrants, pricing pressure, market share | Medium |
| Macroeconomic | Interest rates, inflation, recession sensitivity | Medium |
| Geopolitical | Trade restrictions, sanctions, political instability | Medium-High |
| Personnel | Key-man dependency, talent retention, labor | Medium |
| Environmental & ESG | Climate risk, sustainability compliance | Low-Medium |
| Product & Technology | Obsolescence, product defects, R&D failure | Medium |

### Step 4: Severity Rating

Rate each identified change as HIGH, MEDIUM, or LOW severity:

**HIGH severity criteria** (any one sufficient):
- New risk in Litigation, Regulatory, Financial, or Going Concern categories
- Escalated risk with specific dollar exposure >5% of market cap mentioned
- Risk factor involving regulatory investigation, government enforcement action, or active litigation
- Language explicitly mentions bankruptcy, covenant breach, or going concern

**MEDIUM severity criteria**:
- New risk in Operational, Geopolitical, or Personnel categories
- Escalated risk with expanded language but no specific financial exposure cited
- Competitive risk with named competitors or specific market dynamics mentioned

**LOW severity criteria**:
- Reworded risk with same underlying substance
- De-escalated risk (generally positive signal)
- New risk in Macroeconomic or ESG categories with generic industry-wide applicability

## Key Questions

1. Are there any new risk factors this year that did not appear in the prior filing? What category do they fall in?
2. Has the company expanded its litigation or regulatory risk language significantly — particularly regarding ongoing investigations or enforcement actions?
3. Is there any going concern language, covenant concern, or liquidity risk that was absent in the prior filing?
4. Have any risks been removed, and is the removal consistent with publicly available information (e.g., a lawsuit settled, a regulatory issue resolved)?
5. Does management's tone in earnings calls contradict or minimize any of the risks disclosed in the 10-K?
6. Are any of the escalated risks systemic (affecting the industry) or company-specific (idiosyncratic)?

## Red Flags

- New risk factor appearing in the Litigation, Regulatory, or Financial categories — these categories have the highest correlation with material negative outcomes
- Specific dollar amounts cited for the first time in a risk factor (e.g., "we may be subject to fines of up to $500 million") — first-time quantification signals a real and estimated exposure
- Going concern language added or expanded — audit firms require disclosure when doubt about 12-month viability exists
- Cybersecurity or data breach risk expanded with specific system or customer data mentioned — suggests an incident may have occurred or is under investigation
- Management discussed a topic on earnings calls as "immaterial" or "resolved" that appears as a new or escalated risk in the concurrent 10-K
- Risk factor removed despite the underlying issue remaining unresolved per public records (news, court filings)
- Language shift from "may" to "will" or from "could" to "does" in describing risk impact

## Source Requirements

- **Current 10-K Item 1A**: SEC EDGAR (sec.gov/cgi-bin/browse-edgar) — Tier 1 (primary source, authoritative)
- **Prior year 10-K Item 1A**: SEC EDGAR — Tier 1
- **EDGAR full-text search**: efts.sec.gov — Tier 1 (for keyword search within filings)
- **FMP EDGAR API**: `/stable/sec-filings` and `/stable/sec-filing-sections` endpoints — Tier 2 (convenience access)
- **SEC EDGAR viewer**: viewer.sec.gov — Tier 2 (formatted display)
- **News validation**: Bloomberg, Reuters — Tier 2 (to cross-check whether disclosed risks are consistent with news)

## Output

- SEC Risk Factor Change Summary table: change type (new/removed/escalated/de-escalated), category, severity (HIGH/MEDIUM/LOW), and one-line description
- New risks list with full text excerpt and severity rating
- Escalated risks list with prior vs. current language comparison
- De-escalated or removed risks list (potential positive signals)
- SEC Risk Score (0-100, inverted: 100 = no material changes, 0 = multiple high-severity new risks): calculated as 100 minus (25 per HIGH-severity change + 10 per MEDIUM-severity change + 5 per LOW-severity change), floor of 0
- Overall SEC risk assessment: CLEAN / MINOR CHANGES / MATERIAL CHANGES / SIGNIFICANT NEW RISKS
