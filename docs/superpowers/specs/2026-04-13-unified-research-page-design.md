# Unified Research Page

**Date:** 2026-04-13
**Status:** Approved

## Problem

The pipeline produces analysis across 5 sequential phases, each rendered on separate pages with interrupt gates between them. This causes two issues:

1. **Content repetition** — Each phase's LLM prompt re-analyzes raw fundamentals independently, so the same observations (revenue growth, margin trends, key risks) get restated across quick screen, deep dive, thesis, and risk stress-test.
2. **Fragmented reading** — Users context-switch between 4 pages to review a single research run, re-reading summaries at each phase boundary to orient themselves.

## Solution

Merge all analytical phases (1-5) into a single streaming page. Remove interrupt gates so the pipeline runs to completion. Inject prior-phase outputs into later prompts with explicit dedup instructions so each phase builds on — rather than restates — earlier analysis.

---

## 1. Page Structure

Single route: `/pipeline/[runId]`. Replaces both the current pipeline runner page and the report page. During a live run it streams progressively (sections appear as phases complete). After completion it renders the same layout statically from the report API.

`/report/[runId]` redirects to `/pipeline/[runId]`.

### Section Flow (top to bottom)

**1. Report Header**
Combines the current QuickScreenCard and OverviewBanner into one dense, scannable header.

- Left: company identity (ticker, name, sector/industry, market cap, current price) + verdict badge (GO/WATCHLIST/PASS) + conviction score ring
- Right: headline metrics strip (revenue, FCF, DCF gap, D/E, op margin, EPS) — the existing HeadlineMetrics component
- Below: quick screen one-line thesis (left) and one-line key risk (right) as a subtle callout pair
- Below that: radar chart + score bar spanning all categories (quick screen dimensions + deep dive categories)

The 5 quick screen dimensions no longer need a standalone table — they're visible in the radar chart. The full QuickScreenCard component is retired from this page.

**2. Deep Dive Dashboard**
The existing deep-dive component tree, unchanged:
- Data-rich: Financial Health, Growth & Earnings, Technical & Market Structure
- Cross-Category Correlations
- Mixed: Business Quality, Macro & Regime, Risk Assessment
- Qualitative: Management & Governance, Sentiment & Narrative (with velocity sparkline), Future Durability

**3. Thesis**
Bull/bear columns, variant perception callout, catalyst timeline, conviction rationale. Rendered from thesis phase structured output. Does not restate evidence — references deep dive categories by name.

**4. Risk Stress-Test**
Risk/reward ratio display, risk scenario cards with severity/probability, loop-back history (if the pipeline looped). Attacks the thesis directly rather than re-analyzing fundamentals.

**5. Position Plan (optional)**
Entry zones, sizing, stops, monitoring cadence, exit conditions. Only rendered if the user clicks a "Generate Position Plan" button at the bottom of the risk section. Position monitor (phase 6) remains manually triggered — it's tactical and time-sensitive, separate from the durable analysis.

**6. Citations**
All citations accumulated across all phases, deduplicated, at the bottom. Grouped by source type (FMP, FRED, X, Earnings Transcript).

### Sidebar Navigation

The existing DashboardSidebar expands to cover the full page. New entries added:

```
OVERVIEW
  ● Report Header

DATA-RICH
  ● Financial Health
  ● Growth & Earnings
  ● Technical & Market
  ● Correlations

MIXED
  ● Business Quality
  ● Macro & Regime
  ● Risk Assessment

QUALITATIVE
  ● Management
  ● Sentiment
  ● Future

SYNTHESIS
  ● Thesis
  ● Risk Stress-Test
  ● Position Plan (if present)
```

---

## 2. Pipeline Changes (Backend)

### Remove Interrupt Gates

Currently the pipeline pauses at 3 interrupt points by setting `state.status = "awaiting_approval"`. With the new design:

- **Remove all interrupts from phases 1-5.** After `POST /api/runs` starts a run, it runs quick_screen → deep_dive → thesis → risk_stress_test continuously without pausing.
- **Position monitor (phase 6)** remains manually triggered. The existing `POST /api/runs/{run_id}/advance` endpoint is repurposed: when called on a completed run, it triggers phase 6.
- **Phase routing:** `_next_phase()` in `services/pipeline.py` advances automatically through phases 1-5. After risk_stress_test, the run status becomes `"completed"` (or `"watchlist"` / `"pass"` based on the risk stress-test's loop decision).
- **Loop-back:** If the risk stress-test triggers a loop-back (`loop_required=True, loop_count < 2`), the pipeline still loops back to deep_dive automatically — no interrupt. After loop-back completes, it continues through thesis → risk again.

### Prompt Deduplication

**Thesis prompt** — inject prior-phase context:

```
## Established findings (do NOT restate — reference by category name)

Quick Screen: {verdict} ({score}/100)
Thesis: "{quick_screen_thesis}"
Key Risk: "{quick_screen_key_risk}"

Deep Dive Category Scores:
{for each category: "- {category}: {score}/100 — {top 2 key_findings}"}

## Instructions
Synthesize these findings into a formal investment thesis. Do NOT
re-analyze the underlying data or repeat observations already documented
above. Reference categories by name when building your argument. Only
introduce new observations if the data reveals something the category
analyses missed.
```

**Risk stress-test prompt** — inject thesis as context:

```
## Thesis to stress-test

"{thesis_core_thesis}"

Bull case: {bull_case_titles}
Bear case: {bear_case_titles}
Conviction: {conviction_score}/100

## Instructions
Your job is to attack THIS thesis — find the scenarios where it breaks.
Do NOT re-derive the underlying analysis. The deep dive findings and
thesis above are established. Stress-test their assumptions and identify
what would invalidate them.
```

### SSE Streaming

No changes to the streaming infrastructure. The event stream continues to push `phase_start`, `category_complete`, `phase_complete` events. The unified page consumes them identically to the current pipeline page — it just renders all phases into one continuous layout instead of gating between them.

Events still emitted:
- `quick_screen_complete` → Report Header populates
- `deep_dive_start` → CuratedFinancials arrive, dashboard skeleton appears
- `category_complete` (×9) → Dashboard sections fill in progressively
- `deep_dive_complete` → Dashboard fully rendered
- `thesis_complete` → Thesis section appears below dashboard
- `risk_complete` → Risk section appears below thesis

---

## 3. Frontend Changes

### New: Unified Page Component

Replace the current `/pipeline/[runId]/page.tsx` implementation with a unified page that renders all phases in a single scrollable view. The component:

- Connects to SSE on mount (for live runs) or fetches from report API (for completed runs)
- Renders the Report Header as soon as quick screen data arrives
- Renders the deep dive dashboard progressively as categories complete
- Renders thesis and risk sections as those phases complete
- Shows a "Generate Position Plan" button after risk completes
- Handles the `isLive` state toggle (streaming skeleton → static content)

### New: Report Header Component

Combines company identity, verdict badge, conviction ring, headline metrics, thesis/risk one-liners, radar chart, and score bar. Sources data from:
- Quick screen structured output (verdict, dimensions, thesis, key_risk)
- CuratedFinancials (headline metrics, company identity)
- All category scores (radar + score bar)

### Modified: DashboardSidebar

Expands ITEMS array to include Report Header, Thesis, Risk Stress-Test, and Position Plan entries. Adds a "SYNTHESIS" tier label. IntersectionObserver already handles arbitrary section IDs.

### Modified: ThesisCard / RiskCard

These components still exist but are adapted to render inline within the unified flow — no standalone page wrapper, consistent styling with the rest of the dashboard.

### Deprecated: `/report/[runId]`

Redirects to `/pipeline/[runId]`. The report API endpoint remains (it's used by the unified page for completed runs) but the dedicated report page is removed.

### Deprecated: Advance/approval UI

The "Approve" / "Send to Watchlist" / "Pass" buttons between phases are removed. The pipeline runs to completion. Final status is determined by the pipeline itself (completed / watchlist based on risk stress-test output).

---

## 4. Scope Boundaries

### In scope
- Unified page layout with streaming + static modes
- Remove interrupt gates from phases 1-5
- Prompt deduplication for thesis and risk phases
- Report Header combining quick screen + overview banner
- Sidebar expansion for full-page navigation
- `/report/[runId]` redirect
- Position monitor as optional manual trigger

### Out of scope
- Topic-organized report (Approach B) — parked in `docs/topic-organized-report-design.md`
- Changes to deep dive dashboard components — they work well as-is
- Changes to deep dive category prompts — repetition is mainly in thesis/risk
- New pipeline phases or categories
- Mobile layout optimization
- Obsidian export changes (the export endpoint can be updated separately)
