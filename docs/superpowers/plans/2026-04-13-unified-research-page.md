# Unified Research Page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the pipeline runner and report pages into a single streaming page that runs phases 1-5 without interrupts, with prompt deduplication to eliminate cross-phase repetition.

**Architecture:** Remove interrupt gates from the pipeline service so phases run continuously. Inject prior-phase outputs into thesis/risk prompts with explicit "don't repeat" instructions. Replace the current multi-page flow with a single `/pipeline/[runId]` page that streams all phases into a unified layout: Report Header → Deep Dive Dashboard → Thesis → Risk → optional Position Plan.

**Tech Stack:** FastAPI, LangGraph, Next.js 16 App Router, React 19, Tailwind v4, Recharts

**Note:** No backend test framework is configured. Verification uses the running dev server and browser. Frontend verification uses `tsc --noEmit` and the browser.

---

## File Map

| Action | Path | Responsibility |
|--------|------|---------------|
| Modify | `backend/app/services/pipeline.py` | Remove interrupt gates, auto-advance phases 1-5 |
| Modify | `backend/app/graph/nodes.py` | Remove `awaiting_approval` from quick_screen, deep_dive, thesis, risk nodes |
| Modify | `backend/app/graph/prompts.py` | Add dedup context blocks to THESIS_USER and RISK_USER |
| Modify | `backend/app/api/pipeline.py` | Update advance endpoint for position-only triggering |
| Create | `frontend/components/deep-dive/ReportHeader.tsx` | Unified header: identity + verdict + metrics + thesis/risk callouts + radar + scores |
| Modify | `frontend/components/deep-dive/DashboardSidebar.tsx` | Add Overview, Thesis, Risk, Position, Citations sidebar entries |
| Rewrite | `frontend/app/pipeline/[runId]/page.tsx` | Unified streaming page replacing the current phase-gated runner |
| Modify | `frontend/app/report/[runId]/page.tsx` | Redirect to `/pipeline/[runId]` |
| Modify | `frontend/lib/api.ts` | Add SSE events for thesis/risk completion |

---

### Task 1: Remove interrupt gates from pipeline nodes

**Files:**
- Modify: `backend/app/graph/nodes.py:793-795,862-863,930-939`

The quick_screen, deep_dive, thesis_construction, and risk_stress_test nodes each set `state.status = "awaiting_approval"` at the end. Remove this from all except risk_stress_test's loop-back path. Instead set `status = "in_progress"` so the pipeline service continues automatically.

- [ ] **Step 1: Update `node_quick_screen` — remove approval pause**

In `backend/app/graph/nodes.py`, find the line at the end of `node_quick_screen` (currently line ~213):

```python
    state.status = "awaiting_approval"
    return state
```

Replace with:

```python
    state.status = "in_progress"
    return state
```

- [ ] **Step 2: Update `node_deep_dive` — remove approval pause**

Find the line at the end of `node_deep_dive` (currently line ~624):

```python
    state.status = "awaiting_approval"
    return state
```

Replace with:

```python
    state.status = "in_progress"
    return state
```

- [ ] **Step 3: Update `node_thesis_construction` — remove approval pause**

Find the line at the end of `node_thesis_construction` (currently line ~862):

```python
    state.status = "awaiting_approval"
```

Replace with:

```python
    state.status = "in_progress"
```

- [ ] **Step 4: Update `node_risk_stress_test` — keep loop-back logic, remove approval pause on non-loop path**

In `node_risk_stress_test`, find the section that handles the loop-back decision (around lines 918-940). Currently it sets `awaiting_approval` in all three branches. Update so:

- Loop-back triggered (`loop_required and loop_count < 2`): keep `state.status = "in_progress"` (was `awaiting_approval`)
- Loop cap reached: keep `state.status = "watchlist"` (unchanged)
- No loop needed: set `state.status = "completed"` (was `awaiting_approval`)

Replace this block:

```python
        if loop_required and state.loop_count < 2:
            state.loop_count += 1
            state.loop_context = {
                "categories": loop_cats,
                "reason": loop_reason,
                "rr_ratio": rr_ratio,
            }
            # Pause for human review — user sees the risk card with the
            # loop-back recommendation and approves. _next_phase() routes
            # back to deep_dive when loop_context is set.
            state.status = "awaiting_approval"
            logger.info("[%s] Loop-back triggered (count %d): %s", state.ticker, state.loop_count, loop_cats)
        elif loop_required and state.loop_count >= 2:
            state.status = "watchlist"
            state.thesis_status = "BROKEN"
            logger.info("[%s] Loop cap reached — forcing WATCHLIST", state.ticker)
        else:
            state.status = "awaiting_approval"
            logger.info(
                "[%s] risk_stress_test complete: RR %.1f:1 — approved (structured=%s)",
                state.ticker, rr_ratio, structured is not None,
            )
```

With:

```python
        if loop_required and state.loop_count < 2:
            state.loop_count += 1
            state.loop_context = {
                "categories": loop_cats,
                "reason": loop_reason,
                "rr_ratio": rr_ratio,
            }
            state.status = "in_progress"
            logger.info("[%s] Loop-back triggered (count %d): %s", state.ticker, state.loop_count, loop_cats)
        elif loop_required and state.loop_count >= 2:
            state.status = "watchlist"
            state.thesis_status = "BROKEN"
            logger.info("[%s] Loop cap reached — forcing WATCHLIST", state.ticker)
        else:
            state.status = "completed"
            logger.info(
                "[%s] risk_stress_test complete: RR %.1f:1 — approved (structured=%s)",
                state.ticker, rr_ratio, structured is not None,
            )
```

Also remove the trailing `state.status = "awaiting_approval"` line in the except handler (around line 784) — replace with `state.status = "completed"`.

- [ ] **Step 5: Verify imports compile**

```bash
source backend/venv/bin/activate && python -c "from backend.app.graph.nodes import node_quick_screen, node_deep_dive, node_thesis_construction, node_risk_stress_test; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/nodes.py
git commit -m "feat: remove interrupt gates from pipeline phases 1-5"
```

---

### Task 2: Auto-advance phases in PipelineService

**Files:**
- Modify: `backend/app/services/pipeline.py:148-209`

Currently `_run_phase` runs one phase, persists state, and emits an interrupt event for the frontend to show approval buttons. With interrupts removed, `_run_phase` should automatically chain to the next phase when status is `in_progress`.

- [ ] **Step 1: Update `_run_phase` to auto-advance**

In `backend/app/services/pipeline.py`, replace the `_run_phase` method (lines 162-212) with:

```python
    async def _run_phase(
        self, run_id: str, state: ResearchState, db: AsyncSession
    ) -> None:
        """Execute phases sequentially until the run pauses or completes."""
        while state.status == "in_progress":
            phase = state.phase
            self._emit(run_id, {"type": "phase_start", "phase": phase,
                                 "label": PHASE_META.get(phase, {}).get("label", phase)})

            try:
                if phase == "quick_screen":
                    state = await nodes.node_quick_screen(state, self._fmp)
                elif phase == "deep_dive":
                    state = await self._run_deep_dive_with_streaming(state, run_id)
                elif phase == "thesis_construction":
                    state = await nodes.node_thesis_construction(state)
                elif phase == "risk_stress_test":
                    state = await nodes.node_risk_stress_test(state)
                elif phase == "position_monitor":
                    state = await nodes.node_position_monitor(state)

                # Persist state after each phase
                async with db.begin():
                    result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
                    run = result.scalar_one_or_none()
                    if run:
                        run.state = state.to_dict()
                        run.phase = state.phase
                        run.status = state.status
                        run.loop_count = state.loop_count

                # Emit phase completion event
                output_key = PHASE_OUTPUT_KEYS.get(phase, phase)
                phase_output = state.phase_outputs.get(output_key, {})
                self._emit(run_id, {
                    "type": "phase_complete",
                    "phase": phase,
                    "output": phase_output,
                    "conviction_score": state.conviction_score,
                })

                # If still in_progress, advance to next phase
                if state.status == "in_progress":
                    next_phase = self._next_phase(state)
                    state.phase = next_phase
                    # Persist the phase advance
                    async with db.begin():
                        result = await db.execute(select(ResearchRun).where(ResearchRun.id == run_id))
                        run = result.scalar_one_or_none()
                        if run:
                            run.phase = next_phase
                            run.state = state.to_dict()

            except Exception as e:
                logger.error("Phase %s failed for run %s: %s", phase, run_id, e)
                self._emit(run_id, {"type": "error", "phase": phase, "message": str(e)})
                break

        # Run finished — emit final event
        if state.status in ("completed", "watchlist", "pass"):
            self._emit(run_id, {"type": "complete", "status": state.status,
                                 "conviction_score": state.conviction_score,
                                 "thesis_status": state.thesis_status})
```

- [ ] **Step 2: Update `_next_phase` — route to completed after risk (not position)**

Position monitor is now manually triggered. Update `_next_phase`:

```python
    def _next_phase(self, state: ResearchState) -> str:
        """Determine next phase based on current phase and state."""
        phase_sequence = {
            "quick_screen": "deep_dive",
            "deep_dive": "thesis_construction",
            "thesis_construction": "risk_stress_test",
            "risk_stress_test": (
                "deep_dive" if (state.loop_context and state.loop_count <= 2)
                else "completed"
            ),
            "position_monitor": "completed",
        }
        return phase_sequence.get(state.phase, "completed")
```

- [ ] **Step 3: Verify imports compile**

```bash
source backend/venv/bin/activate && python -c "from backend.app.services.pipeline import PipelineService; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/pipeline.py
git commit -m "feat: auto-advance pipeline phases 1-5 without interrupts"
```

---

### Task 3: Add prompt deduplication to thesis and risk

**Files:**
- Modify: `backend/app/graph/prompts.py:168-269`
- Modify: `backend/app/graph/nodes.py:800-862` (thesis node) and `865-950` (risk node)

- [ ] **Step 1: Update THESIS_SYSTEM prompt**

In `backend/app/graph/prompts.py`, update `THESIS_SYSTEM` — add dedup instruction to the rules section. Replace the last rule line:

```python
- Every claim must trace to a category analysis from the deep dive results below."""
```

With:

```python
- Every claim must trace to a category analysis from the deep dive results below.
- Do NOT restate observations already documented in the established findings. Reference categories by name (e.g. "as shown in Financial Health"). Only introduce new observations if the data reveals something the category analyses missed."""
```

- [ ] **Step 2: Update THESIS_USER prompt**

Replace the `THESIS_USER` template:

```python
THESIS_USER = """Ticker: {ticker}
Theme: {theme}

## Established findings (reference these — do NOT restate)

Quick Screen: {quick_screen_verdict} ({quick_screen_score}/100)
Quick Screen Thesis: "{quick_screen_thesis}"
Quick Screen Key Risk: "{quick_screen_risk}"

## Deep dive category results (scores and key findings)
{category_summary}

## Full category analyses (for evidence only — do not repeat)
{category_results}

Failed categories (treat as data gaps):
{failed_categories}

Loop context (if re-run):
{loop_context}

Synthesize these findings into an investment thesis. Reference categories by name. Output the JSON described above."""
```

- [ ] **Step 3: Update RISK_USER prompt**

Replace the `RISK_USER` template:

```python
RISK_USER = """Ticker: {ticker}
Theme: {theme}
Loop count: {loop_count}/2

## Thesis to stress-test (do NOT re-derive the underlying analysis)

{thesis}

## Category scores for context
{scores}

Stress-test this thesis — find the scenarios where it breaks. Do NOT restate the thesis or re-analyze the underlying data. Output the JSON risk register described above."""
```

- [ ] **Step 4: Update `node_thesis_construction` to format the new template fields**

In `backend/app/graph/nodes.py`, update the `node_thesis_construction` function. Replace the section that formats `results_text` and calls `complete()` (lines ~806-829):

```python
    # Format category results
    results = state.get_deep_dive_results()

    # Build concise summary (scores + top 2 findings per category)
    summary_lines = []
    results_text = ""
    for cat, result in results.items():
        if isinstance(result, CategoryResult):
            top_findings = "; ".join(result.key_findings[:2]) if result.key_findings else "No key findings"
            summary_lines.append(f"- {cat}: {result.score}/100 — {top_findings}")
            results_text += f"\n\n## {cat} (Score: {result.score}/100)\n{result.content[:800]}"
        else:
            summary_lines.append(f"- {cat}: FAILED — {result.reason}")
            results_text += f"\n\n## {cat}\n[FAILED: {result.reason}]"

    category_summary = "\n".join(summary_lines)

    # Extract quick screen context
    qs_output = state.phase_outputs.get("quick_screen", {})
    qs_structured = qs_output.get("structured") if isinstance(qs_output, dict) else None
    qs_verdict = "N/A"
    qs_score = qs_output.get("score", "N/A") if isinstance(qs_output, dict) else "N/A"
    qs_thesis = "N/A"
    qs_risk = "N/A"
    if qs_structured and isinstance(qs_structured, dict):
        qs_verdict = qs_structured.get("recommendation", "N/A")
        qs_thesis = qs_structured.get("thesis", "N/A")
        qs_risk = qs_structured.get("key_risk", "N/A")

    failed = state.failed_categories()
    loop_ctx = str(state.loop_context) if state.loop_context else "None"

    try:
        response = await complete(
            system=THESIS_SYSTEM,
            user=THESIS_USER.format(
                ticker=state.ticker,
                theme=state.theme_id,
                quick_screen_verdict=qs_verdict,
                quick_screen_score=qs_score,
                quick_screen_thesis=qs_thesis,
                quick_screen_risk=qs_risk,
                category_summary=category_summary,
                category_results=results_text,
                failed_categories=", ".join(failed) if failed else "None",
                loop_context=loop_ctx,
            ),
            model=SONNET,
            max_tokens=4000,
        )
```

- [ ] **Step 5: Verify imports compile**

```bash
source backend/venv/bin/activate && python -c "from backend.app.graph.nodes import node_thesis_construction, node_risk_stress_test; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/prompts.py backend/app/graph/nodes.py
git commit -m "feat: add prompt deduplication to thesis and risk phases"
```

---

### Task 4: Update advance endpoint for position-only triggering

**Files:**
- Modify: `backend/app/api/pipeline.py`

The `/advance` endpoint currently handles mid-pipeline approval. With interrupts removed, it only needs to handle triggering position monitor on completed runs.

- [ ] **Step 1: Update the advance endpoint**

In `backend/app/api/pipeline.py`, find the `advance_run` function. Add a check at the top: if the run is already `completed`, treat an `approve` action as a trigger for position monitor.

After the existing `if not run:` check in the advance handler, add:

```python
    # If run is completed and action is approve, trigger position monitor
    if run.status == "completed" and body.action == "approve":
        state = ResearchState.from_dict(run.state)
        state.status = "in_progress"
        state.phase = "position_monitor"
        run.phase = "position_monitor"
        run.status = "in_progress"
        run.state = state.to_dict()
        await db.commit()
        asyncio.create_task(pipeline_service._run_phase(run.id, state, db))
        return _run_to_detail(run)
```

- [ ] **Step 2: Verify imports compile**

```bash
source backend/venv/bin/activate && python -c "from backend.app.api.pipeline import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/pipeline.py
git commit -m "feat: repurpose advance endpoint for position monitor triggering"
```

---

### Task 5: Add `phase_complete` SSE event type to frontend

**Files:**
- Modify: `frontend/lib/api.ts`

The backend now emits `phase_complete` events (replacing `interrupt` for phases 1-5). Add this to the SSE discriminated union.

- [ ] **Step 1: Add `phase_complete` to SSEEvent union**

In `frontend/lib/api.ts`, find the `SSEEvent` type union. Add a new member:

```typescript
  | { type: "phase_complete"; phase: string; output: Record<string, unknown>; conviction_score: number }
```

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat: add phase_complete SSE event type"
```

---

### Task 6: Create ReportHeader component

**Files:**
- Create: `frontend/components/deep-dive/ReportHeader.tsx`

Combines company identity, verdict badge, conviction ring, headline metrics, thesis/risk one-liners, radar chart, and score bar into one dense header section.

- [ ] **Step 1: Create the ReportHeader component**

Create `frontend/components/deep-dive/ReportHeader.tsx`:

```tsx
import type { CuratedFinancials, QuickScreenStructured } from "@/lib/api";
import { HeadlineMetrics } from "./HeadlineMetrics";
import { ScoreRadar } from "./ScoreRadar";
import { ScoreBar } from "./ScoreBar";
import { ScoreRing } from "@/components/ScoreRing";

interface ReportHeaderProps {
  financials: CuratedFinancials | null;
  quickScreen: QuickScreenStructured | null;
  scores: Record<string, number>;
  convictionScore: number | null;
  ticker: string;
  isLive?: boolean;
}

function VerdictBadge({ verdict }: { verdict: string }) {
  const styles: Record<string, string> = {
    GO: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    WATCHLIST: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    PASS: "bg-red-500/15 text-red-400 border-red-500/30",
  };
  return (
    <span className={`px-2.5 py-1 rounded-lg text-xs font-bold border ${styles[verdict] ?? styles.WATCHLIST}`}>
      {verdict}
    </span>
  );
}

export function ReportHeader({ financials, quickScreen, scores, convictionScore, ticker, isLive }: ReportHeaderProps) {
  const companyName = financials?.company_name ?? ticker;
  const sector = financials?.sector;
  const industry = financials?.industry;
  const marketCap = financials?.market_cap;
  const price = financials?.current_price;

  return (
    <section id="report_header" className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden">
      {/* Top: Identity + Verdict + Conviction + Headline Metrics */}
      <div className="p-5 border-b border-[var(--color-border)]">
        <div className="flex items-start justify-between gap-6">
          {/* Left: Company identity + verdict */}
          <div className="min-w-0">
            <div className="flex items-center gap-3 mb-1">
              <h1 className="text-2xl font-bold font-mono text-[var(--color-text-primary)] tracking-tight">{ticker}</h1>
              {quickScreen && <VerdictBadge verdict={quickScreen.recommendation} />}
            </div>
            <p className="text-sm text-[var(--color-text-primary)]">{companyName}</p>
            {sector && (
              <p className="text-xs text-[var(--color-text-muted)] mt-0.5">
                {sector}{industry ? ` · ${industry}` : ""}
                {marketCap ? ` · $${(marketCap / 1e9).toFixed(1)}B` : ""}
                {price ? ` · $${price.toFixed(2)}` : ""}
              </p>
            )}
          </div>

          {/* Right: Conviction score */}
          <div className="flex-shrink-0">
            {convictionScore != null ? (
              <ScoreRing score={convictionScore} size={72} label="Conviction" />
            ) : isLive ? (
              <div className="w-[72px] h-[72px] rounded-full border-2 border-[var(--color-border)] animate-pulse" />
            ) : null}
          </div>
        </div>

        {/* Headline metrics */}
        {financials && (
          <div className="mt-4">
            <HeadlineMetrics financials={financials} />
          </div>
        )}
      </div>

      {/* Thesis / Risk one-liners */}
      {quickScreen && (quickScreen.thesis || quickScreen.key_risk) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-px bg-[var(--color-border)]">
          {quickScreen.thesis && (
            <div className="bg-[var(--color-surface)] p-4">
              <p className="text-[10px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">Thesis</p>
              <p className="text-xs text-[var(--color-text-primary)] leading-relaxed">{quickScreen.thesis}</p>
            </div>
          )}
          {quickScreen.key_risk && (
            <div className="bg-[var(--color-surface)] p-4">
              <p className="text-[10px] font-semibold text-red-400 uppercase tracking-wider mb-1">Key Risk</p>
              <p className="text-xs text-[var(--color-text-primary)] leading-relaxed">{quickScreen.key_risk}</p>
            </div>
          )}
        </div>
      )}

      {/* Radar + Score Bar */}
      {Object.keys(scores).length > 0 && (
        <div className="p-5 grid grid-cols-1 lg:grid-cols-[1fr_2fr] gap-4">
          <ScoreRadar scores={scores} />
          <ScoreBar scores={scores} />
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/components/deep-dive/ReportHeader.tsx
git commit -m "feat: create ReportHeader component combining identity, verdict, metrics, radar"
```

---

### Task 7: Expand DashboardSidebar with synthesis sections

**Files:**
- Modify: `frontend/components/deep-dive/DashboardSidebar.tsx`

- [ ] **Step 1: Add new sidebar entries**

In `frontend/components/deep-dive/DashboardSidebar.tsx`, update the `ITEMS` array. Add `report_header` at the top and synthesis sections at the bottom:

```typescript
const ITEMS: SidebarItem[] = [
  { key: "report_header", label: "Overview", tier: "overview" },
  { key: "financial_health", label: "Financial Health", tier: "data-rich" },
  { key: "growth_earnings", label: "Growth & Earnings", tier: "data-rich" },
  { key: "technical_market_structure", label: "Technical & Market", tier: "data-rich" },
  { key: "cross_category", label: "Correlations", tier: "data-rich" },
  { key: "business_quality", label: "Business Quality", tier: "mixed" },
  { key: "macro_regime", label: "Macro & Regime", tier: "mixed" },
  { key: "risk_assessment", label: "Risk Assessment", tier: "mixed" },
  { key: "management_governance", label: "Management", tier: "qualitative" },
  { key: "sentiment_narrative", label: "Sentiment", tier: "qualitative" },
  { key: "future_durability", label: "Future", tier: "qualitative" },
  { key: "thesis_section", label: "Thesis", tier: "synthesis" },
  { key: "risk_section", label: "Risk Stress-Test", tier: "synthesis" },
];
```

Update the `SidebarItem` tier type:

```typescript
interface SidebarItem {
  key: string;
  label: string;
  tier: "overview" | "data-rich" | "mixed" | "qualitative" | "synthesis";
}
```

Update `TIER_LABELS`:

```typescript
const TIER_LABELS: Record<string, string> = {
  overview: "OVERVIEW",
  "data-rich": "DATA-RICH",
  mixed: "MIXED",
  qualitative: "QUALITATIVE",
  synthesis: "SYNTHESIS",
};
```

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

Expected: no new errors

- [ ] **Step 3: Commit**

```bash
git add frontend/components/deep-dive/DashboardSidebar.tsx
git commit -m "feat: expand sidebar with overview and synthesis sections"
```

---

### Task 8: Rewrite the unified pipeline page

**Files:**
- Rewrite: `frontend/app/pipeline/[runId]/page.tsx`

This is the largest task. The page now handles both live streaming and completed run display in a single unified layout.

- [ ] **Step 1: Rewrite the page**

Replace the entire contents of `frontend/app/pipeline/[runId]/page.tsx` with a new unified page. The key changes from the current implementation:

1. **No PhaseRail** — replaced by the expanded DashboardSidebar
2. **No ActionBar** — no approval buttons between phases
3. **All phases render in one scrollable layout** — Report Header at top, deep dive dashboard in the middle, thesis and risk cards below
4. **SSE handler processes `phase_complete` instead of `interrupt`** — populates phase outputs as they arrive
5. **Position monitor button** at the bottom for completed runs
6. **Fetches from report API for completed runs** — same component, different data source

The page should:
- On mount: fetch run state via `api.get(runId)`
- If run is `in_progress`: connect to SSE, stream events, render progressively
- If run is `completed`/`watchlist`: fetch report via `api.report(runId)`, render all sections statically
- ReportHeader renders when quick screen data is available
- DeepDiveDashboard renders when curated financials + categories arrive
- ThesisCard renders when thesis phase completes
- RiskCard renders when risk phase completes
- "Generate Position Plan" button shows when run is completed and position not yet generated

This step is large — implement it as a complete file rewrite following the patterns in the current page for SSE handling, but restructured for the unified layout.

- [ ] **Step 2: Verify types compile**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```

Expected: no new errors

- [ ] **Step 3: Verify in browser**

Start both servers. Create a new pipeline run and verify:
- The page streams all phases progressively without approval gates
- Report Header appears after quick screen
- Deep dive dashboard builds up as categories complete
- Thesis section appears after thesis phase
- Risk section appears after risk phase
- "Generate Position Plan" button appears at the bottom
- Sidebar navigation works for all sections

- [ ] **Step 4: Commit**

```bash
git add frontend/app/pipeline/[runId]/page.tsx
git commit -m "feat: rewrite pipeline page as unified streaming research report"
```

---

### Task 9: Redirect report page to pipeline page

**Files:**
- Modify: `frontend/app/report/[runId]/page.tsx`

- [ ] **Step 1: Replace report page with redirect**

Replace the entire contents of `frontend/app/report/[runId]/page.tsx` with:

```tsx
import { redirect } from "next/navigation";

export default async function ReportRedirectPage({
  params,
}: {
  params: Promise<{ runId: string }>;
}) {
  const { runId } = await params;
  redirect(`/pipeline/${runId}`);
}
```

Note: In Next.js 16, `params` is a Promise and must be awaited. Check `frontend/node_modules/next/dist/docs/` if the redirect API has changed.

- [ ] **Step 2: Verify redirect works**

Navigate to `http://localhost:3000/report/{some-run-id}` — should redirect to `/pipeline/{some-run-id}`.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/report/[runId]/page.tsx
git commit -m "feat: redirect /report/[runId] to /pipeline/[runId]"
```

---

### Task 10: Update CLAUDE.md with new architecture

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the pipeline section**

Update the pipeline flow diagram in CLAUDE.md to reflect no interrupts:

```
quick_screen (Haiku)
  → deep_dive (Sonnet, 9 categories in parallel)
  → thesis_construction (Sonnet)
  → risk_stress_test (Sonnet)
       ├─ loop_required & loop_count ≤ 2 → back to deep_dive
       └─ else → completed
  → [optional: position_monitor (Haiku) — manually triggered]
```

Update the interrupt explanation paragraph to note that interrupts have been removed and phases run continuously.

Update the frontend layout section to note the unified page at `/pipeline/[runId]` and that `/report/[runId]` redirects there.

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for unified research page architecture"
```
