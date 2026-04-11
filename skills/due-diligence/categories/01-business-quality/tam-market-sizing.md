---
name: TAM Market Sizing
description: Bottom-up estimation of total, serviceable, and obtainable addressable market
category: business-quality
type: technique
requires: []
---

## Purpose

Estimate the realistic size and growth trajectory of the market the company competes in. TAM narratives are frequently abused — this skill enforces bottom-up rigor to distinguish genuine large markets from inflated story-telling.

## Methodology

### Step 1: Define Market Boundaries

- What specific problem does the company solve?
- Who are the current customers? Who could be customers but aren't yet?
- What do customers currently pay to solve this problem (including non-obvious alternatives)?
- Explicitly exclude adjacent markets the company does not serve today.

### Step 2: Bottom-Up TAM Estimation

Calculate TAM = Number of potential customers × Average revenue per customer

Break into segments:
- By geography (domestic, international, specific regions)
- By customer type (enterprise, SMB, consumer)
- By use case (if the product serves multiple needs)

For each segment: estimated customer count × realistic ARPU = segment TAM.

**Do NOT use top-down estimates** ("the global cloud market is $500B and we'll capture 1%"). Top-down estimates are narratives, not analysis.

### Step 3: Funnel to SAM and SOM

- **SAM (Serviceable Addressable Market)**: TAM filtered by geography, product fit, and go-to-market reach. What can the company actually serve today?
- **SOM (Serviceable Obtainable Market)**: SAM filtered by competitive dynamics, sales capacity, and realistic win rates. What can the company realistically capture in the next 3-5 years?

### Step 4: Assess Growth Trajectory

- Is the TAM expanding (new use cases, new geographies, price increases)?
- Is the TAM contracting (commoditization, substitution, regulation)?
- What is the TAM CAGR over the next 5 years?

## Key Questions

1. Is the company's TAM narrative bottom-up or top-down? (Top-down = skepticism warranted)
2. Is the company creating new TAM (expanding the market) or capturing existing TAM (taking share)?
3. At current growth rates, when does the company saturate its SOM?
4. Are there adjacent markets that represent realistic TAM expansion?

## Red Flags

- TAM narrative conflates adjacent markets the company doesn't serve
- TAM is presented top-down without customer-level validation
- SAM is >50% of TAM without geographic/product expansion already underway
- SOM growth requires market share gains from entrenched competitors
- TAM is growing but the company's share is shrinking

## Source Requirements

- Market size estimates: Tier 1 (SEC filings, company IR presentations) + Tier 2 (industry research — qualitative cross-reference only)
- Company revenue by segment: Tier 1 (SEC filings)
- Customer count/ARPU: Tier 1 (company disclosures) or Tier 2 (estimates — flagged as such)
- Growth rates: Tier 1 (SEC filings for historical; licensed data providers for projections)

## Output

- TAM / SAM / SOM estimates ($ values)
- TAM CAGR (5-year projected)
- TAM growth trajectory: EXPANDING / STABLE / CONTRACTING
- Segment breakdown with largest opportunity identified
- TAM credibility assessment: RIGOROUS (bottom-up validated) / NARRATIVE (top-down only) / MIXED
