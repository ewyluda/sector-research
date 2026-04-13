# Approach B: Topic-Organized Report

**Status:** Parked — recorded for future reference. We're proceeding with Approach A (Unified Streaming Page) first.

**Date:** 2026-04-13

---

## Problem

The pipeline produces analysis in 5 sequential phases (quick screen, deep dive x9, thesis, risk stress-test, position monitor), but the user reads it as a research report. Phase boundaries are implementation details, not how an analyst thinks. Content repeats across phases because each phase re-derives observations from raw data instead of building incrementally.

## Core Idea

Keep the pipeline phases as invisible processing plumbing but reorganize the final output by **topic** rather than by phase. The page reads like an institutional research report, not a pipeline trace.

## Proposed Sections

### 1. Executive Summary
**Sources:** Quick screen verdict + thesis core_thesis + conviction score + thesis_status

A 3-5 sentence overview: what the company does, the investment thesis in one line, the conviction score, and the single biggest risk. This replaces the quick screen card and thesis header — the user sees the conclusion first, then drills into evidence.

### 2. Company Snapshot
**Sources:** CuratedFinancials identity fields + company profile

Ticker, sector, industry, market cap, current price, 52-week range, beta. A single row of headline metrics. No phase attribution — it's just facts.

### 3. Financial Dashboard
**Sources:** Deep dive data-rich categories (Financial Health, Growth & Earnings, Technical & Market Structure) + CuratedFinancials + Cross-Category Correlations

The existing deep-dive dashboard components, but without the per-category AI companion panels competing for attention. Charts and metrics front and center. The AI analysis moves to a collapsible "Analyst Notes" drawer per section.

### 4. Qualitative Assessment
**Sources:** Deep dive qualitative/mixed categories (Business Quality, Management & Governance, Sentiment & Narrative, Future Durability, Macro & Regime)

Organized as a set of cards with scores and key findings. Transcript insights (management credibility, narrative consistency, Q&A tensions) are woven into the relevant cards rather than being a separate sub-section.

### 5. Investment Thesis
**Sources:** Thesis phase output (bull_case, bear_case, variant_perception, catalysts)

The structured thesis with bull/bear columns, variant perception callout, and catalyst timeline. No restating of the evidence — it references sections above via anchors (e.g., "supported by the margin expansion shown in Financial Dashboard").

### 6. Risk Register
**Sources:** Risk stress-test output (scenarios, risk_reward_ratio, risk factors)

Risk scenarios as cards with severity/probability. The stress-test's loop-back decision (if any) shown as a historical note. Risk/reward ratio prominently displayed.

### 7. Position Plan (optional)
**Sources:** Position monitor output (entry zones, sizing, stops, monitoring cadence)

Only shown if phase 6 was executed. Tactical and time-sensitive — visually separated from the analytical sections above.

### 8. Data Provenance
**Sources:** All citations accumulated across phases

A single deduplicated citation table at the bottom, grouped by data source (FMP, FRED, X, Earnings Transcript). Replaces the per-phase citation scattering.

## Key Differences from Approach A

| Aspect | Approach A (Unified Streaming) | Approach B (Topic-Organized) |
|--------|-------------------------------|------------------------------|
| Page structure | Phase-sequential (quick screen → deep dive → thesis → risk) | Topic-organized (summary → data → qualitative → thesis → risk) |
| Phase visibility | Phases visible as sections with clear boundaries | Phases invisible — content reorganized by topic |
| Deep dive dashboard | Rendered as-is in the deep dive section | Split: data-rich charts in "Financial Dashboard", qualitative in "Qualitative Assessment" |
| Thesis | Own section after deep dive | Rendered after all evidence, references earlier sections |
| Citations | Per-phase | Deduplicated at bottom, grouped by source |
| Implementation effort | Moderate — new page + prompt changes | Heavy — new page + content routing logic + prompt changes |
| Reading experience | Familiar phase flow, less repetition | Most natural report flow, but lossy phase→topic mapping |

## Why We Parked This

1. **Phase→topic mapping is non-trivial.** Some deep-dive category content spans multiple topics. Business Quality findings might belong in both "Financial Dashboard" (margins data) and "Qualitative Assessment" (moat analysis). The routing logic adds complexity.

2. **Approach A gets 80% of the benefit.** The main pain points are repetition (fixed by prompt changes) and fragmentation (fixed by a single page). Topic reorganization is polish on top.

3. **Risk of over-engineering.** The app is a personal tool. An analyst reading phase-by-phase with good prompts that don't repeat is already a solid experience.

## When to Revisit

- If after Approach A ships, the phase-sequential layout still feels unnatural for reading
- If we add an "export to PDF/Obsidian" feature where report structure matters for external consumption
- If we build a "compare two tickers" view where topic alignment makes side-by-side comparison possible
