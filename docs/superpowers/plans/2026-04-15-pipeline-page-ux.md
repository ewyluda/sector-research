# Pipeline Page UI/UX Improvements

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve the pipeline analysis page's readability, navigation, and data density handling across 9 targeted changes.

**Architecture:** All changes are frontend-only, touching deep-dive section containers, chart components, the score bar, and the pipeline page shell. No backend changes needed. Each task is independent — they can be done in any order.

**Tech Stack:** Next.js 16, React 19, Tailwind v4, Recharts, CSS custom properties

---

### Task 1: Collapsible Deep-Dive Sections

**Files:**
- Modify: `frontend/components/deep-dive/sections/DataRichSection.tsx`
- Modify: `frontend/components/deep-dive/sections/MixedSection.tsx`
- Modify: `frontend/components/deep-dive/sections/QualitativeCard.tsx`

All three section containers need a collapse/expand toggle on their header bar. Default state: expanded. Clicking the header or chevron toggles the body visibility.

- [ ] **Step 1: Add collapse toggle to DataRichSection**

In `frontend/components/deep-dive/sections/DataRichSection.tsx`, add a `useState` for collapsed state and a chevron icon. The header div already has `flex items-center justify-between` — add a clickable wrapper.

```tsx
// Add at top of file:
import { useState } from "react";

// Inside the component, before the return:
const [collapsed, setCollapsed] = useState(false);

// Replace the header div's inner content. The header div is:
// <div className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40 flex items-center justify-between">
// Change it to be clickable:
<div
  className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40 flex items-center justify-between cursor-pointer select-none"
  onClick={() => setCollapsed((c) => !c)}
>
  <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">{label}</h3>
  <div className="flex items-center gap-2">
    <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded ${scoreBadge(score)}`}>
      {score != null ? `${score}/100` : "—"}
    </span>
    <svg
      className={`w-4 h-4 text-[var(--color-text-muted)] transition-transform ${collapsed ? "" : "rotate-180"}`}
      fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  </div>
</div>

// Wrap the grid body in a conditional:
{!collapsed && (
  <div className="grid grid-cols-1 lg:grid-cols-[3fr_2fr] gap-4 p-5">
    <div className="space-y-4">{children}</div>
    <div>
      {structured ? (
        <AICompanionPanel structured={structured} categoryLabel={label} expandAnalysis={false} fallback={fallback} />
      ) : isLive ? (
        <PanelSkeleton />
      ) : null}
    </div>
  </div>
)}
```

- [ ] **Step 2: Add collapse toggle to MixedSection**

Same pattern in `frontend/components/deep-dive/sections/MixedSection.tsx`. Add `useState` import and `collapsed` state. Make header clickable with chevron. Wrap the `grid` div in `{!collapsed && (...)}`.

```tsx
// Add import:
import { useState } from "react";

// Add state:
const [collapsed, setCollapsed] = useState(false);

// Header becomes clickable with chevron (same pattern as DataRichSection)
// Body wrapper:
{!collapsed && (
  <div className="grid grid-cols-1 lg:grid-cols-[2fr_3fr] gap-4 p-5">
    ...existing content...
  </div>
)}
```

- [ ] **Step 3: Add collapse toggle to QualitativeCard**

Same pattern in `frontend/components/deep-dive/sections/QualitativeCard.tsx`. The header already has a `headerAddon` — place the chevron after the score badge, not inside the left-side flex.

```tsx
// Add import:
import { useState } from "react";

// Add state:
const [collapsed, setCollapsed] = useState(false);

// Header becomes clickable with chevron
// Body wrapper:
{!collapsed && (
  <div className="p-5">
    ...existing content...
  </div>
)}
```

- [ ] **Step 4: Verify all sections collapse/expand**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/deep-dive/sections/DataRichSection.tsx frontend/components/deep-dive/sections/MixedSection.tsx frontend/components/deep-dive/sections/QualitativeCard.tsx
git commit -m "feat: add collapse/expand toggle to deep-dive section headers"
```

---

### Task 2: Expand AI Analysis by Default in DataRichSection

**Files:**
- Modify: `frontend/components/deep-dive/sections/DataRichSection.tsx`

The DataRichSection passes `expandAnalysis={false}` to AICompanionPanel, hiding the detailed analysis behind an accordion. The MixedSection and QualitativeCard already pass `true`. Change DataRichSection to match.

- [ ] **Step 1: Change expandAnalysis prop**

In `frontend/components/deep-dive/sections/DataRichSection.tsx`, find:
```tsx
<AICompanionPanel structured={structured} categoryLabel={label} expandAnalysis={false} fallback={fallback} />
```
Change to:
```tsx
<AICompanionPanel structured={structured} categoryLabel={label} expandAnalysis={true} fallback={fallback} />
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/deep-dive/sections/DataRichSection.tsx
git commit -m "feat: expand AI analysis by default in data-rich sections"
```

---

### Task 3: Chart Height + Axis Font Size Increase

**Files:**
- Modify: `frontend/components/deep-dive/charts/TrendLineChart.tsx`
- Modify: `frontend/components/deep-dive/charts/GroupedBarChart.tsx`
- Modify: `frontend/components/deep-dive/charts/StackedBarChart.tsx`

Charts currently use `height={200}` and `fontSize: 10` for axis ticks. Increase to 260px height and 12px font for better readability.

- [ ] **Step 1: Update TrendLineChart**

In `frontend/components/deep-dive/charts/TrendLineChart.tsx`:
- Change `<ResponsiveContainer width="100%" height={200}>` to `height={260}`
- Change all `tick={{ fontSize: 10,` to `tick={{ fontSize: 12,`

- [ ] **Step 2: Update GroupedBarChart**

In `frontend/components/deep-dive/charts/GroupedBarChart.tsx`:
- Change `height={200}` to `height={260}` in ResponsiveContainer
- Change `fontSize: 10` to `fontSize: 12` in tick props

- [ ] **Step 3: Update StackedBarChart**

In `frontend/components/deep-dive/charts/StackedBarChart.tsx`:
- Change `height={200}` to `height={260}` in ResponsiveContainer
- Change `fontSize: 10` to `fontSize: 12` in tick props

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/deep-dive/charts/TrendLineChart.tsx frontend/components/deep-dive/charts/GroupedBarChart.tsx frontend/components/deep-dive/charts/StackedBarChart.tsx
git commit -m "feat: increase chart height to 260px and axis font to 12px"
```

---

### Task 4: Score Bar Tooltips

**Files:**
- Modify: `frontend/components/deep-dive/ScoreBar.tsx`

The ScoreBar shows cryptic abbreviations (BizQ, Fin, Grw, etc.) with no explanation. Add `title` attributes mapping to full category names.

- [ ] **Step 1: Add full names to CATEGORIES and render tooltips**

In `frontend/components/deep-dive/ScoreBar.tsx`, extend the CATEGORIES array to include full names and add a `title` attribute:

```tsx
const CATEGORIES = [
  { key: "business_quality", short: "BizQ", full: "Business Quality" },
  { key: "financial_health", short: "Fin", full: "Financial Health" },
  { key: "growth_earnings", short: "Grw", full: "Growth & Earnings" },
  { key: "management_governance", short: "Mgt", full: "Management & Governance" },
  { key: "technical_market_structure", short: "Tech", full: "Technical & Market" },
  { key: "macro_regime", short: "Mac", full: "Macro & Regime" },
  { key: "sentiment_narrative", short: "Sen", full: "Sentiment & Narrative" },
  { key: "risk_assessment", short: "Rsk", full: "Risk Assessment" },
  { key: "future_durability", short: "Fut", full: "Future Durability" },
];

// In the map, change the div to include title:
{CATEGORIES.map(({ key, short, full }) => {
  const score = scores[key] ?? null;
  return (
    <div
      key={key}
      title={`${full}: ${score ?? "N/A"}/100`}
      className={`flex-1 py-1.5 text-center ${segmentColor(score)}`}
    >
      <p className="text-[8px] font-medium uppercase">{short}</p>
      <p className="text-[10px] font-mono font-semibold">{score ?? "—"}</p>
    </div>
  );
})}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/deep-dive/ScoreBar.tsx
git commit -m "feat: add hover tooltips to score bar abbreviations"
```

---

### Task 5: Line Style Differentiation in Multi-Series Charts

**Files:**
- Modify: `frontend/components/deep-dive/charts/TrendLineChart.tsx`

When a chart has multiple lines, they're distinguished only by color. Add dashed/dotted stroke patterns for the 2nd and 3rd lines.

- [ ] **Step 1: Add strokeDasharray to alternating lines**

In `frontend/components/deep-dive/charts/TrendLineChart.tsx`, the `lines.map()` renders `<Line>` components. Add a `strokeDasharray` prop based on the line index:

```tsx
const LINE_DASH_PATTERNS = ["", "6 3", "2 3"]; // solid, dashed, dotted

// In the map:
{lines.map((line, idx) => (
  <Line
    key={line.name}
    type="monotone"
    dataKey={line.name}
    stroke={line.color}
    strokeWidth={2}
    strokeDasharray={LINE_DASH_PATTERNS[idx % LINE_DASH_PATTERNS.length] || undefined}
    dot={{ r: 3 }}
  />
))}
```

Note: The first line (index 0) gets an empty string which means solid. Only 2nd+ lines get dashes. Pass `undefined` for index 0 to avoid React warning about empty string prop.

Correction — use a ternary:
```tsx
strokeDasharray={idx > 0 ? LINE_DASH_PATTERNS[idx % LINE_DASH_PATTERNS.length] : undefined}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/deep-dive/charts/TrendLineChart.tsx
git commit -m "feat: add dashed/dotted line styles for multi-series chart differentiation"
```

---

### Task 6: Risk Severity Icons in RAGStrip

**Files:**
- Modify: `frontend/components/deep-dive/charts/RAGStrip.tsx`

The RAGStrip shows text labels (Low/Medium/High) but no icons. Add inline SVG icons for each severity level to make them more scannable.

- [ ] **Step 1: Add severity icons**

In `frontend/components/deep-dive/charts/RAGStrip.tsx`, update the `severityColor` function to include an icon SVG path, and render it in the strip:

```tsx
function severityColor(score: number): { bg: string; text: string; label: string; icon: React.ReactNode } {
  if (score >= 70) return {
    bg: "bg-emerald-500/20", text: "text-emerald-400", label: "Low",
    icon: <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
  };
  if (score >= 50) return {
    bg: "bg-amber-500/20", text: "text-amber-400", label: "Medium",
    icon: <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
  };
  return {
    bg: "bg-red-500/20", text: "text-red-400", label: "High",
    icon: <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" /></svg>
  };
}

// In the JSX, add the icon before the label:
<div key={i} className={`flex items-center gap-2 rounded-md px-3 py-1.5 ${sev.bg}`}>
  <span className={`${sev.text} flex items-center gap-1`}>
    {sev.icon}
    <span className="text-[10px] font-semibold uppercase w-12 shrink-0">{sev.label}</span>
  </span>
  <span className="text-xs text-[var(--color-text-primary)] leading-snug">{f.finding}</span>
</div>
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/deep-dive/charts/RAGStrip.tsx
git commit -m "feat: add severity icons to risk assessment RAGStrip"
```

---

### Task 7: Chart Empty States

**Files:**
- Modify: `frontend/components/deep-dive/charts/TrendLineChart.tsx`
- Modify: `frontend/components/deep-dive/charts/GroupedBarChart.tsx`
- Modify: `frontend/components/deep-dive/charts/StackedBarChart.tsx`

When charts receive an empty data array, they show a blank rectangle. Add a helpful empty state message instead.

- [ ] **Step 1: Add empty state to TrendLineChart**

In `frontend/components/deep-dive/charts/TrendLineChart.tsx`, add an early return before the ResponsiveContainer:

```tsx
// After merging data, check if merged is empty:
if (merged.length === 0) {
  return (
    <div className="flex items-center justify-center h-[260px] rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-surface-alt)]/30">
      <p className="text-xs text-[var(--color-text-faint)]">No data available for this period</p>
    </div>
  );
}
```

- [ ] **Step 2: Add empty state to GroupedBarChart**

Same pattern in `frontend/components/deep-dive/charts/GroupedBarChart.tsx` — check if data prop is empty and show the empty state div.

- [ ] **Step 3: Add empty state to StackedBarChart**

Same pattern in `frontend/components/deep-dive/charts/StackedBarChart.tsx`.

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/deep-dive/charts/TrendLineChart.tsx frontend/components/deep-dive/charts/GroupedBarChart.tsx frontend/components/deep-dive/charts/StackedBarChart.tsx
git commit -m "feat: add empty state messages to chart components"
```

---

### Task 8: Mobile Section Navigation

**Files:**
- Create: `frontend/components/deep-dive/MobileSectionNav.tsx`
- Modify: `frontend/components/deep-dive/DeepDiveDashboard.tsx`

The DashboardSidebar is `hidden lg:block` — on mobile there's no way to jump between sections. Add a sticky horizontal scrollable section nav at the bottom of the viewport on `<lg` screens.

- [ ] **Step 1: Create MobileSectionNav component**

Create `frontend/components/deep-dive/MobileSectionNav.tsx`:

```tsx
"use client";

import { useState, useEffect } from "react";

const SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "financial_health", label: "Financial" },
  { id: "growth_earnings", label: "Growth" },
  { id: "technical_market_structure", label: "Technical" },
  { id: "cross_category", label: "Cross-Cat" },
  { id: "business_quality", label: "Business" },
  { id: "supply_chain", label: "Supply" },
  { id: "macro_regime", label: "Macro" },
  { id: "risk_assessment", label: "Risk" },
  { id: "management_governance", label: "Mgmt" },
  { id: "sentiment_narrative", label: "Sentiment" },
  { id: "future_durability", label: "Future" },
];

export function MobileSectionNav() {
  const [active, setActive] = useState("overview");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setActive(entry.target.id);
          }
        }
      },
      { rootMargin: "-40% 0px -55% 0px" }
    );
    for (const s of SECTIONS) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, []);

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 lg:hidden bg-[var(--color-bg)]/95 backdrop-blur border-t border-[var(--color-border)]">
      <div className="flex overflow-x-auto gap-1 px-3 py-2 scrollbar-hide">
        {SECTIONS.map(({ id, label }) => (
          <button
            key={id}
            onClick={() => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className={`shrink-0 px-3 py-1.5 rounded-full text-[11px] font-medium transition-colors ${
              active === id
                ? "bg-[var(--color-primary)] text-white"
                : "bg-[var(--color-surface-alt)] text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    </nav>
  );
}
```

- [ ] **Step 2: Integrate into DeepDiveDashboard**

In `frontend/components/deep-dive/DeepDiveDashboard.tsx`, import and add the MobileSectionNav:

```tsx
import { MobileSectionNav } from "./MobileSectionNav";

// At the end of the component's return, after the closing </div> of the flex container:
// Wrap the return in a fragment:
return (
  <>
    <div className="flex gap-6">
      <DashboardSidebar scores={scores} />
      <div className="flex-1 space-y-6 min-w-0">
        ...existing sections...
      </div>
    </div>
    <MobileSectionNav />
  </>
);
```

- [ ] **Step 3: Add scrollbar-hide utility**

In `frontend/app/globals.css`, add (if not already present):

```css
.scrollbar-hide {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
.scrollbar-hide::-webkit-scrollbar {
  display: none;
}
```

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/deep-dive/MobileSectionNav.tsx frontend/components/deep-dive/DeepDiveDashboard.tsx frontend/app/globals.css
git commit -m "feat: add sticky mobile section navigation for deep-dive dashboard"
```

---

### Task 9: Breadcrumb + Back Link at Page Top

**Files:**
- Modify: `frontend/app/pipeline/[runId]/page.tsx`

The pipeline page has no way to navigate back except the bottom "Back to Library" button. Add a breadcrumb trail at the top: `Library > TICKER > Deep Dive`.

- [ ] **Step 1: Add breadcrumb to pipeline page**

In `frontend/app/pipeline/[runId]/page.tsx`, find the opening of the main content area (after the `<main>` tag and any loading guard). Add a breadcrumb above the existing content. The ticker is available from `run?.ticker`. Find the point where content renders (after the loading spinner check) and add:

```tsx
{/* Breadcrumb — rendered when we have a run */}
{run && (
  <nav className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] mb-4" aria-label="Breadcrumb">
    <a href="/library" className="hover:text-[var(--color-text-primary)] transition-colors">Library</a>
    <span className="text-[var(--color-text-faint)]">/</span>
    <span className="text-[var(--color-text-primary)] font-medium">{run.ticker}</span>
    <span className="text-[var(--color-text-faint)]">/</span>
    <span>Deep Dive</span>
  </nav>
)}
```

Place this right after the `max-w-7xl` container div opens.

- [ ] **Step 2: Verify build**

Run: `cd frontend && npm run build`
Expected: Build succeeds.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/pipeline/[runId]/page.tsx
git commit -m "feat: add breadcrumb navigation to pipeline analysis page"
```
