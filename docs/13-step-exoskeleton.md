# The Institutional Equity Research Process

## 13-Step Research Exoskeleton

---

## Thesis Development Arc (Steps 1–8)

### 01. Idea Origination
Thematic Screening, Quant Screens, Earnings Sourcing, Network Flow, Read-Throughs, 13F Analysis, Event Monitoring, Short ID, Alt Data, Pipeline Mgmt

### 02. Triage & Quick Assessment
Quality Sniff Test, Industry Check, Expectations Gap, Momentum, Complexity, Catalyst ID, Kill Criteria, Fit, Crowding, Priority

### 03. Foundational Due Diligence
Reading Stack, SEC Filings, Sell-Side Reports, Transcripts, Investor Decks, Industry Primer, Comps, Price Context, Ownership, Question Log

### 04. Financial Model Build
Source Docs, Formatting, P&L Input, Quarterly Data, Operating Data, BS & CF, Analysis Rows, Revenue Build, Cost Structure, Unit Econ, Key Drivers, Forecast, SUM Tab

### 05. Targeted Key Driver Deep Dive
Hypothesis, Expert Calls, Channel Checks, Mgmt/IR, Alt Data, Competitor Cross-Ref, Industry Experts, Sell-Side, Stress Test, Evidence

### 06. Insight Formation
Key Driver Synthesis, Variant Perception, Momentum, Competitive Position, Mgmt Quality, Unit Econ, Industry, Signal/Noise, Confidence, Info Gaps

### 07. Expectations & Valuation
Consensus Mapping, Dispersion, What's Baked In, Reverse DCF, Historical Valuation, Peer Comps, Revision Momentum, Whisper, Normalized, Framework

### 08. Thesis Construction
One-Sentence, Key Drivers, Bull/Base/Bear, Prob-Weighted R/R, Kill Criteria, Catalyst Map, Write-Up, Pre-Mortem

---

## Active Position Management (Steps 9–13)

### 09. Catalyst Path & Maintenance
Catalyst Calendar, Signposts, Model Maintenance, Industry Data, Peer Read-Throughs, Sell-Side Tracking, Ownership, Thesis Review, Competitive, Prioritization

### 10. Earnings Navigation
Pre-Earnings Review, Expectations, Key Metrics, Scenarios, Print Parsing, Transcript, Model Update, Revision Cycle, Thesis Check, Position Action

### 11. Management Touchpoints
Conference Scheduling, Questions, Commentary, Capital Allocation, Governance, Credibility, Org Signals, Trust Assessment, Peer Comparison, Red Flags

### 12. News & Event Navigation
Daily Monitoring, Signal/Noise, Materiality, Competitor Read-Throughs, Macro/Regulatory, Market Reaction, Thesis Check, Opportunity, PM Comms, Model Update

### 13. Position Management
R/R Recalc, Sizing, Correlation/Factor, Add Discipline, Trim Discipline, Exit Framework, Loss Mgmt, Hedging, Liquidity, Post-Mortem

---

# Framing AI — Push Button Workflows & Model Workspace

---

## Slide 23 — Seeing Some Signs of a Push Button World Emerging

### Key Points

- **Rogo accretion/dilution analysis** — example of an automated workflow already emerging
- **With time, focus & attention, more modeling elements can be turned into "push a button" workflows**
- An architecture like this saves time & reduces errors, and in a time-crunch frees the analyst up to **research the key inputs vs. build the mechanical structure**

### Illustrative Example: Accretion / Dilution Analysis (DHR / MASI)

A Pro Forma EPS Impact model spanning 2025A → 2031E (Year 5), structured in standard M&A-model blocks:

1. **DHR Standalone** — Revenue, EBITDA, Standalone EPS, Shares Outstanding, Net Income (Implied)
2. **MASI Contribution (Standalone)** — Revenue, EBITDA, D&A (est.), EBIT
3. **Synergy Phase-in Schedule** — Phase-in %, Cost Synergies (Full Run-Rate), Revenue Synergies, Realized amounts, EBITDA from Revenue Synergies, Total Synergy EBITDA Impact
4. **Acquisition Financing Cost** — New Acquisition Debt, Cost of Debt, Tax Rate, Pre-Tax / After-Tax Interest Expense, Lost Interest on Cash Used
5. **Pro Forma EPS Calculation** — DHR Standalone Net Income + MASI EBIT Contribution + Synergy EBITDA − After-Tax Interest − Lost Interest − PPA Intangible Amort = Pro Forma Net Income → Pro Forma EPS
6. **Output** — Accretion/(Dilution) per Share and % vs. DHR Standalone EPS

> The takeaway is structural, not the numbers themselves: this is the kind of mechanical scaffolding an agent should assemble so the analyst can spend cycles on inputs and judgment, not plumbing.

---

## Slide 46 — Creating a Model Workspace (In Development)

A 5-step model workflow, source: *Fundamental Edge*.

### Step 1 — Update / Refresh
- **Update** — enter new actuals from 10-Q and transcript
- **Roll forward** — extend forecast period
- **Sync consensus** — pull current sell-side and overlay
- **What changed** — diff vs. prior version, surface every move

### Step 2 — Research
- **Source it** — trace any cell back to the primary doc
- **Drill down** — expand a line into segment, geo, or SKU
- **Recent news** — developments since last update
- **What am I missing** — surface risks not in the model

### Step 3 — Validation / Sensitivity
- **Validate** — formulas, refs, circularities, hardcodes
- **Audit trail** — every assumption with source and timestamp
- **Sensitivity** — scenarios on key drivers
- **Reverse DCF** — what does the current price imply?

### Step 4 — Challenge / Sharpen
- **Pushback** — devil's advocate against the thesis
- **Variant view** — where the model implies non-consensus
- **What's priced in** — decompose valuation into expectations
- **Kill criteria** — define what would make me wrong

### Step 5 — Differentiation
- **Peer benchmark** — side-by-side on growth, margins, returns
- **Relative positioning** — where this name sits vs. peers
- **Read across** — apply peer earnings prints to this name
- **Best-in-class gap** — distance to peer leader, what closes it