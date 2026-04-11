---
name: Scoring Methodology
description: Composite score definitions, weighting math, and interpretation ranges for the due diligence framework
type: framework
---

## Purpose

Define how qualitative and quantitative assessments are converted into scores for dashboard visualization. Scoring is applied only where it adds signal — qualitative-by-nature items use traffic-light or categorical displays instead.

## Source Tier System

All scored metrics must declare their source tier. Scores derived from Tier 2 sources are flagged.

| Tier | Label | Sources | Usage |
|------|-------|---------|-------|
| 1 | Trusted | SEC EDGAR, company IR, FMP/Bloomberg/FactSet/S&P, FRED, CBOE/exchange | All quantitative analysis |
| 2 | Conditional | News (Reuters, Bloomberg, WSJ), social media, analyst reports | Qualitative signal only |

## Leaf Skill Scores (0-100)

Each scored leaf skill produces a single number from weighted sub-factors. Sub-factor scores are assessed on a 0-100 scale where 0 = worst possible, 50 = neutral, 100 = best possible.

| Skill | Score Name | Sub-Factors & Weights |
|-------|-----------|----------------------|
| Moat Analysis | Moat Strength | Pricing power (25%), switching costs (25%), network effects (20%), cost advantage (15%), intangible assets (15%) |
| Competitive Positioning | Position Score | Market share trend (30%), relative margin vs. peers (25%), value chain power (25%), customer dependency (20%) |
| Earnings Quality | Quality Score | Accrual ratio (30%), OCF-to-NI consistency (25%), non-recurring prevalence (25%), revenue recognition aggressiveness (20%) |
| Balance Sheet Strength | Fortress Score | Net debt/EBITDA (25%), interest coverage (25%), current ratio (15%), debt maturity profile (20%), FCF/debt service (15%) |
| Management Quality | Alignment Score | Insider ownership (25%), comp vs. peers (20%), capital allocation track record (25%), tenure stability (15%), skin-in-game ratio (15%) |
| Cash Flow Durability | Durability Score (per horizon) | Revenue stream diversity (20%), recurring revenue % (25%), moat score pass-through (20%), customer concentration inverse (15%), capex flexibility (20%) |
| AI Disruption Vulnerability | Vulnerability Score | Per-stream weighted by revenue share: feasibility × economics × (1 − switching cost) × timeline proximity |

## Category Composite Scores (0-100)

Each category aggregates its leaf skill scores into a composite. Non-scored leaf skills within a category are excluded from the composite (their insights are captured qualitatively).

| Category | Composite | Sub-Factor Weights |
|----------|-----------|-------------------|
| Business Quality | BQ Score | Moat (40%) + Positioning (30%) + TAM trend (15%) + Lifecycle stage (15%) |
| Financial Health | FH Score | Valuation attractiveness (25%) + Profitability (25%) + Balance sheet (25%) + Cash flow quality (25%) |
| Growth & Earnings | GE Score | Revenue growth (30%) + Earnings quality (30%) + Guidance credibility (20%) + Analyst momentum (20%) |
| Management & Governance | MG Score | Leadership (25%) + Capital allocation (30%) + Insider activity (20%) + Comp alignment (25%) |
| Technical & Market Structure | TM Score | Trend (35%) + Volume (25%) + Support/resistance (20%) + Options flow (20%) |
| Macro & Regime | MR Score | Rate impact (25%) + Inflation impact (20%) + Yield curve (20%) + Sector rotation (20%) + Regime (15%) |
| Sentiment & Narrative | SN Score | News sentiment (35%) + Social signals (15%) + Institutional positioning (35%) + Narrative alignment (15%) |
| Risk Assessment | RA Score (inverted: 100 = low risk) | SEC risk changes (25%) + Thesis risk count (25%) + Concentration risk (25%) + Tail risk severity (25%) |
| Future Durability | FD Score | Durability-5yr (20%) + Durability-10yr (30%) + Durability-15yr (20%) + AI vulnerability inverse (30%) |

## Overall Conviction Score (0-100)

```
Conviction = weighted average of:
  Business Quality    (20%)
  Financial Health    (15%)
  Growth & Earnings   (15%)
  Management          (10%)
  Technical           ( 5%)
  Macro Alignment     ( 5%)
  Sentiment           ( 5%)
  Risk (inverted)     (10%)
  Future Durability   (15%)
```

Weights reflect a long-term fundamental bias. Technical and sentiment carry low weight because they are noisy over longer horizons. The conviction score is the headline number on a dashboard card.

## Interpretation Ranges

| Range | Label | Dashboard Color | Meaning |
|-------|-------|----------------|---------|
| 80-100 | Strong | Green | High conviction, strong fundamentals, durable business |
| 60-79 | Moderate | Blue | Solid but with notable concerns in 1-2 categories |
| 40-59 | Neutral | Yellow | Mixed signals, insufficient edge to act with conviction |
| 20-39 | Weak | Orange | Multiple red flags, proceed only with specific catalyst thesis |
| 0-19 | Avoid | Red | Fundamental problems across most categories |

## Items NOT Scored (by design)

| Item | Reason | Display Instead |
|------|--------|----------------|
| Variant Perception | Inherently narrative — forcing a number loses the insight | Text summary: consensus vs. your view |
| Catalyst Identification | Binary events with timelines, not a spectrum | Timeline with status: FIRED / PENDING / EXPIRED |
| Market Narrative | Qualitative by nature | Tagged themes |
| Tail Risk Scenarios | Already probability-weighted in thesis | Scenario table: probability × impact |
| Industry Lifecycle | Ordinal classification, not a continuum | Stage label: Introduction / Growth / Maturity / Decline |

## Thesis Status — Traffic Light System

| Status | Color | Meaning | Action |
|--------|-------|---------|--------|
| ON TRACK | Green | Evidence accumulating in favor, catalysts progressing | Hold or add on pullback |
| DRIFTING | Yellow | Mixed signals, some pillars weakening but core intact | Reduce to half position, define re-add or exit condition |
| BROKEN | Red | Invalidation condition triggered or fundamental change | Exit. No negotiating with a broken thesis. |

### Per-Catalyst Tracking

| Status | Meaning |
|--------|---------|
| PENDING | Catalyst has not yet occurred |
| FIRED | Catalyst occurred — assess impact |
| EXPIRED | Catalyst window passed without occurring |

### Per-Invalidation Condition

| Status | Meaning |
|--------|---------|
| CLEAR | No sign of invalidation |
| WARNING | Early signals — investigate |
| TRIGGERED | Condition met — execute pre-committed action |

## Output

This document is a reference — it does not produce analysis output itself. It is consumed by:
- Category skills (to define their composite scoring section)
- Workflow skills (to aggregate category scores into conviction)
- Dashboard implementations (to render scores, colors, and traffic lights)
