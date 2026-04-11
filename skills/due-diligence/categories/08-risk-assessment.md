---
name: Risk Assessment
description: Systematically identify, classify, and quantify risks that could impair the investment thesis — from SEC-disclosed threats to concentration vulnerabilities and tail scenarios
category: risk-assessment
type: category
sub_skills: [sec-risk-factors, thesis-risk-mapping, concentration-risk, tail-risk-scenarios]
---

## Purpose

Every investment thesis carries embedded assumptions about what will not happen. Risk assessment makes those assumptions explicit and evaluates whether the market is adequately compensating for their failure probability. Unlike upside analysis, risk work is adversarial — the goal is to find the most plausible path to loss and determine if that path is priced, manageable, or disqualifying.

Risk assessment covers four distinct layers: what the company itself has disclosed as material threats (SEC filings), whether the thesis is falsifiable and what would invalidate it (thesis risk mapping), whether the business is dangerously reliant on a small number of customers, geographies, or suppliers (concentration risk), and what catastrophic low-probability events could cause permanent capital loss (tail risk scenarios).

## Key Dimensions

| Dimension | Sub-Skill | Core Question |
|-----------|-----------|---------------|
| SEC Risk Factors | sec-risk-factors | What new, escalated, or reworded risks has the company disclosed in its latest 10-K Item 1A, and what do those changes signal? |
| Thesis Risk Mapping | thesis-risk-mapping | For each bull pillar, what observable condition would falsify it, and how likely is that condition? |
| Concentration Risk | concentration-risk | Is the business dangerously dependent on a small number of customers, geographies, products, or suppliers? |
| Tail Risk Scenarios | tail-risk-scenarios | What low-probability, high-impact events could cause permanent capital loss, and what is the probability-weighted downside? |

## Synthesis

After running all sub-skills, answer these integrative questions:
1. Is the risk profile **known and manageable**, or are there unquantified threats that make position sizing speculative?
2. Does the market valuation **reflect the risk level**, or is the company priced for perfection despite material vulnerabilities?
3. Which single risk dimension — SEC changes, thesis invalidation, concentration, or tail event — represents the **most underappreciated threat**?

## Scoring

**RA Score (0-100)** — inverted scale: 100 = low risk, 0 = extreme risk

RA Score = SEC risk changes (25%) + Thesis risk count (25%) + Concentration risk (25%) + Tail risk severity (25%)

SEC risk changes scoring: No new or escalated risks, prior risks de-escalated = 75-100; minor rewording or additions in low-severity categories = 50-74; new risks in medium-severity categories = 25-49; new or escalated risks in high-severity categories (litigation, regulatory, going concern) = 0-24.

Thesis risk count scoring: All bull pillars have clear, high-bar kill conditions and none are currently triggered = 75-100; most pillars mapped with some ambiguity = 50-74; several pillars undefined or already showing strain = 25-49; thesis is unfalsifiable or kill conditions already triggered = 0-24.

Concentration risk scoring: No dimension exceeds 30% concentration = 75-100; one dimension 30-50% = 50-74; one dimension exceeds 50% or two dimensions exceed 30% = 25-49; multiple dimensions exceed 50% with no mitigation = 0-24.

Tail risk severity scoring: No identified tail scenarios with probability × impact > moderate = 75-100; one moderate tail scenario = 50-74; multiple moderate or one severe tail scenario = 25-49; one or more catastrophic tail scenarios with meaningful probability = 0-24.

## Red Flags

- New risk factors in 10-K Item 1A that were absent from the prior year filing — legal obligation to disclose means management believes the threat is real
- Bull thesis pillars that cannot be falsified — an unfalsifiable thesis is not a thesis, it is wishful thinking
- Revenue concentration above 50% in any single customer, geography, product, or supplier without contractual protection
- Tail scenarios that would cause permanent capital loss (not just drawdown) and are mispriced or unhedged
- Management language in earnings calls that contradicts or minimizes risks disclosed in SEC filings
- Key-man dependency in a company where the founder or CEO is irreplaceable and has no succession plan
- Geographic concentration in a jurisdiction with deteriorating rule of law or rising expropriation risk

## Output

- RA Score (0-100, inverted: higher = lower risk) with sub-factor breakdown
- SEC risk factor change summary: new risks, escalated risks, de-escalated risks, and severity classification
- Thesis risk map: bull pillars with kill conditions, monitoring signals, and current status
- Concentration risk assessment: top customer/geography/product/supplier exposures with thresholds
- Tail risk matrix: probability × impact for each identified tail scenario
- Overall risk classification: LOW / MODERATE / HIGH / EXTREME with primary risk driver
- Recommended position sizing adjustment based on RA Score
