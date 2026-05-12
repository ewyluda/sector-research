# UI/UX Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 26 UI/UX issues identified in the frontend audit, prioritized by impact — starting with 5 high-leverage global fixes, then remaining issues by severity.

**Architecture:** All changes are frontend-only. Tasks 1-2 are global CSS additions. Tasks 3-5 are component-level edits. Tasks 6-12 touch individual components for accessibility, color consistency, and interaction improvements. No backend changes needed.

**Tech Stack:** Next.js 16, React 19, Tailwind v4, CSS custom properties

---

## File Map

| File | Changes |
|------|---------|
| `frontend/app/globals.css` | Tasks 1, 4, 5 — add focus-visible, tabular-nums utility, reduced-motion rules |
| `frontend/components/ScoreRing.tsx` | Task 3 — replace hardcoded hex with CSS variables; Task 6 — add aria-label |
| `frontend/app/page.tsx` | Task 3 — replace hardcoded hex in ThemeCard; replace red-* error state |
| `frontend/components/filings/ThemeFilingsPanel.tsx` | Task 3 — replace hardcoded hex |
| `frontend/app/library/page.tsx` | Task 2 — convert RunCard div→button-like; Task 8 — add loading skeleton |
| `frontend/components/deep-dive/DashboardSidebar.tsx` | Task 2 — keyboard focus styles on nav items |
| `frontend/components/filings/CurationPanel.tsx` | Task 3 — replace red-600 error text |
| `frontend/components/filings/SectionReader.tsx` | Task 3 — replace red-600 error text |
| `frontend/components/filings/TickerFilingsCard.tsx` | Task 3 — replace red-600 error text |
| `frontend/app/filings/page.tsx` | Task 3 — replace red-* error state |
| `frontend/app/theme/new/page.tsx` | Task 3 — replace red-* error state |
| `frontend/app/pipeline/new/page.tsx` | Task 3 — replace red-400 error state |
| `frontend/components/Nav.tsx` | Task 7 — add skip-to-content link |
| `frontend/app/layout.tsx` | Task 7 — add `id="main-content"` to main wrapper |

---

### Task 1: Global focus-visible style + skip-link style

**Files:**
- Modify: `frontend/app/globals.css`

Adds a universal keyboard focus ring and a visually-hidden skip link that appears on focus. This single rule fixes focus visibility across the entire app.

- [ ] **Step 1: Add focus-visible and skip-link rules to globals.css**

After the existing scrollbar rules at the end of `globals.css`, add:

```css
/* Keyboard focus ring — visible only for keyboard users */
:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* Remove outline for mouse/touch clicks */
:focus:not(:focus-visible) {
  outline: none;
}

/* Skip-to-content link (visually hidden until focused) */
.skip-link {
  position: absolute;
  top: -100%;
  left: 16px;
  z-index: 9999;
  padding: 8px 16px;
  background: var(--primary);
  color: white;
  border-radius: 0 0 8px 8px;
  font-size: 0.875rem;
  font-weight: 500;
  text-decoration: none;
  transition: top 0.2s;
}
.skip-link:focus {
  top: 0;
}
```

- [ ] **Step 2: Verify the dev server renders correctly**

Run: `cd frontend && npm run dev`

Open http://localhost:3000, press Tab — all interactive elements (links, buttons) should show a 2px teal outline. The skip-link is wired in Task 7.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/globals.css
git commit -m "feat(a11y): add global focus-visible ring and skip-link styles"
```

---

### Task 2: Convert clickable divs to keyboard-accessible elements

**Files:**
- Modify: `frontend/app/library/page.tsx` (RunCard component, lines 87-166)

RunCard is a `<div onClick>` — inaccessible to keyboard users. Add `role="button"`, `tabIndex={0}`, and `onKeyDown` for Enter/Space.

- [ ] **Step 1: Update RunCard to be keyboard-accessible**

In `frontend/app/library/page.tsx`, replace the RunCard's opening `<div>`:

Old:
```tsx
    <div
      onClick={onClick}
      className="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]
                 hover:border-[var(--color-accent)]/40 hover:bg-[var(--color-accent)]/3
                 cursor-pointer transition-all p-5"
    >
```

New:
```tsx
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onClick(); } }}
      className="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]
                 hover:border-[var(--color-accent)]/40 hover:bg-[var(--color-accent)]/3
                 cursor-pointer transition-all p-5"
    >
```

- [ ] **Step 2: Verify keyboard navigation works**

Open http://localhost:3000/library, Tab to a RunCard, press Enter — should navigate to the run's pipeline/report page. Press Space — same behavior.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/library/page.tsx
git commit -m "feat(a11y): make RunCard keyboard-accessible with role=button"
```

---

### Task 3: Consolidate hardcoded colors to CSS variable tokens

**Files:**
- Modify: `frontend/app/globals.css` — add score-tier + error semantic tokens
- Modify: `frontend/components/ScoreRing.tsx` — replace hex with CSS vars
- Modify: `frontend/app/page.tsx` — replace hex in ThemeCard + error state
- Modify: `frontend/components/filings/ThemeFilingsPanel.tsx` — replace hex
- Modify: `frontend/components/filings/CurationPanel.tsx` — replace red-600
- Modify: `frontend/components/filings/SectionReader.tsx` — replace red-600
- Modify: `frontend/components/filings/TickerFilingsCard.tsx` — replace red-600
- Modify: `frontend/app/filings/page.tsx` — replace red-* error state
- Modify: `frontend/app/theme/new/page.tsx` — replace red-* error state
- Modify: `frontend/app/pipeline/new/page.tsx` — replace red-400 error

This task adds semantic CSS variables for score tiers, teal-on-dark text, and error states, then replaces every hardcoded hex and Tailwind red-* usage in error banners.

- [ ] **Step 1: Add score-tier and error tokens to globals.css**

In the `:root` block of `globals.css`, after `--code-bg`, add:

```css
  /* Score tier colors */
  --score-strong:  #437A22;   /* >= 70 — emerald */
  --score-neutral: #01696F;   /* >= 45 — teal */
  --score-caution: #964219;   /* >= 25 — rust */
  --score-weak:    #A12C7B;   /* < 25  — magenta */

  /* Teal-on-dark text (card headers on --teal-dark bg) */
  --teal-light:    #9de0e6;
  --teal-lighter:  #BCE2E7;

  /* Error state (inline banners) */
  --error-bg:      #FEF2F2;
  --error-border:  #E8C4D8;
  --error-text:    #A12C7B;
```

Also add aliased `--color-*` versions in the alias block:

```css
  --color-score-strong:  var(--score-strong);
  --color-score-neutral: var(--score-neutral);
  --color-score-caution: var(--score-caution);
  --color-score-weak:    var(--score-weak);
  --color-error:         var(--error);
  --color-error-bg:      var(--error-bg);
  --color-error-border:  var(--error-border);
  --color-error-text:    var(--error-text);
```

- [ ] **Step 2: Update ScoreRing.tsx to use CSS variables**

Replace the `scoreColor` function:

Old:
```tsx
function scoreColor(score: number) {
  if (score >= 70) return "#437A22";
  if (score >= 45) return "#01696F";
  if (score >= 25) return "#964219";
  return "#A12C7B";
}
```

New:
```tsx
function scoreColor(score: number) {
  if (score >= 70) return "var(--score-strong)";
  if (score >= 45) return "var(--score-neutral)";
  if (score >= 25) return "var(--score-caution)";
  return "var(--score-weak)";
}
```

Also replace the hardcoded background circle stroke:

Old: `stroke="#D4D1CA"`
New: `stroke="var(--border)"`

- [ ] **Step 3: Update ThemeCard hardcoded hex in page.tsx**

In `frontend/app/page.tsx`, ThemeCard sub-theme badge (line 28):

Old: `text-[#9de0e6] border border-[#9de0e6]/40`
New: `text-[var(--teal-light)] border border-[var(--teal-light)]/40`

Description text (line 34):

Old: `text-[#BCE2E7]`
New: `text-[var(--teal-lighter)]`

- [ ] **Step 4: Update ThemeFilingsPanel.tsx hardcoded hex**

In `frontend/components/filings/ThemeFilingsPanel.tsx`:

Line 21 — Old: `text-[#BCE2E7]` → New: `text-[var(--teal-lighter)]`
Line 26 — Old: `text-[#9de0e6]` → New: `text-[var(--teal-light)]`

- [ ] **Step 5: Replace all error banner red-* classes with CSS variable tokens**

These files all use the same pattern `border-red-200 bg-red-50 text-red-700` for error banners. Replace each with `border-[var(--error-border)] bg-[var(--error-bg)] text-[var(--error-text)]`:

1. `frontend/app/page.tsx` line 117:
   Old: `border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700`
   New: `border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]`

2. `frontend/app/filings/page.tsx` line 42:
   Old: `border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700`
   New: `border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]`

3. `frontend/app/theme/new/page.tsx` line 239:
   Old: `border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700`
   New: `border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]`

4. `frontend/app/pipeline/new/page.tsx` line 111:
   Old: `text-sm text-red-400 bg-red-400/10 border border-red-400/20`
   New: `text-sm text-[var(--error-text)] bg-[var(--error-bg)] border border-[var(--error-border)]`

- [ ] **Step 6: Replace inline red-600 error text in filings components**

These components use `text-red-600` for inline error messages. Replace with `text-[var(--error-text)]`:

1. `frontend/components/filings/CurationPanel.tsx` line 88
2. `frontend/components/filings/SectionReader.tsx` line 79
3. `frontend/components/filings/TickerFilingsCard.tsx` line 113

- [ ] **Step 7: Run typecheck to verify no breakage**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean pass (no type errors — these are all className string changes).

- [ ] **Step 8: Commit**

```bash
git add frontend/app/globals.css frontend/components/ScoreRing.tsx frontend/app/page.tsx \
  frontend/components/filings/ThemeFilingsPanel.tsx frontend/components/filings/CurationPanel.tsx \
  frontend/components/filings/SectionReader.tsx frontend/components/filings/TickerFilingsCard.tsx \
  frontend/app/filings/page.tsx frontend/app/theme/new/page.tsx frontend/app/pipeline/new/page.tsx
git commit -m "refactor(ui): consolidate hardcoded colors to CSS variable tokens"
```

---

### Task 4: Add tabular-nums utility for financial data

**Files:**
- Modify: `frontend/app/globals.css`

Financial numbers (scores, prices, percentages) should use tabular figures to prevent layout jitter when digits change.

- [ ] **Step 1: Add tabular-nums utility class to globals.css**

After the reduced-motion block (or at end of file), add:

```css
/* Tabular figures for financial data — prevents layout jitter */
.tabular-nums {
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Step 2: Apply tabular-nums to ScoreRing**

In `frontend/components/ScoreRing.tsx`, the SVG `<text>` element doesn't support CSS classes directly. Instead, add `fontVariantNumeric="tabular-nums"` as an SVG attribute is not valid — so we apply it on the wrapper div.

Old (line 25):
```tsx
    <div className="flex flex-col items-center gap-0.5">
```

New:
```tsx
    <div className="flex flex-col items-center gap-0.5 tabular-nums">
```

- [ ] **Step 3: Apply tabular-nums to HeadlineMetrics number displays**

In `frontend/components/deep-dive/HeadlineMetrics.tsx`, find the metric card value display and add `tabular-nums` to the value text className. The exact location depends on how MetricCard renders the value — but the key target is any `font-mono` number display in that component.

- [ ] **Step 4: Apply tabular-nums to RunCard conviction score**

In `frontend/app/library/page.tsx`, RunCard conviction display (around line 147):

Old:
```tsx
              <p className="text-2xl font-mono font-semibold text-[var(--color-accent)]">
```

New:
```tsx
              <p className="text-2xl font-mono font-semibold text-[var(--color-accent)] tabular-nums">
```

- [ ] **Step 5: Commit**

```bash
git add frontend/app/globals.css frontend/components/ScoreRing.tsx \
  frontend/components/deep-dive/HeadlineMetrics.tsx frontend/app/library/page.tsx
git commit -m "feat(ui): add tabular-nums for stable financial number layout"
```

---

### Task 5: Add prefers-reduced-motion support

**Files:**
- Modify: `frontend/app/globals.css`

Disable all pulse/spin/transition animations when the user has requested reduced motion.

- [ ] **Step 1: Add reduced-motion media query to globals.css**

At the end of `globals.css`, add:

```css
/* Respect reduced-motion preference */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
}
```

- [ ] **Step 2: Verify animations stop in reduced-motion mode**

In Chrome DevTools → Rendering → check "Emulate CSS media feature prefers-reduced-motion: reduce". The animated pulse dots and spinners should freeze.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/globals.css
git commit -m "feat(a11y): respect prefers-reduced-motion for all animations"
```

---

### Task 6: Add ARIA labels to ScoreRing and chart components

**Files:**
- Modify: `frontend/components/ScoreRing.tsx`

The ScoreRing SVG score is invisible to screen readers. Add an `aria-label` with the numeric score and optional label.

- [ ] **Step 1: Add aria-label to ScoreRing**

In `frontend/components/ScoreRing.tsx`, update the outer div:

Old:
```tsx
    <div className="flex flex-col items-center gap-0.5 tabular-nums">
      <svg width={size} height={size}>
```

New:
```tsx
    <div className="flex flex-col items-center gap-0.5 tabular-nums">
      <svg width={size} height={size} role="img" aria-label={`Score: ${Math.round(score)} out of 100${label ? `, ${label}` : ""}`}>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/ScoreRing.tsx
git commit -m "feat(a11y): add aria-label to ScoreRing SVG for screen readers"
```

---

### Task 7: Add skip-to-content link

**Files:**
- Modify: `frontend/components/Nav.tsx`
- Modify: `frontend/app/layout.tsx`

Add a skip link before the Nav that becomes visible on Tab focus, and an `id="main-content"` anchor on the main content wrapper.

- [ ] **Step 1: Add skip link to Nav.tsx**

In `frontend/components/Nav.tsx`, inside the return, before the `<header>`:

Old:
```tsx
    <header className="border-b border-[var(--border)] bg-[var(--surface)] sticky top-0 z-40">
```

New:
```tsx
    <>
    <a href="#main-content" className="skip-link">Skip to main content</a>
    <header className="border-b border-[var(--border)] bg-[var(--surface)] sticky top-0 z-40">
```

And close the fragment at the end:

Old:
```tsx
    </header>
```

New:
```tsx
    </header>
    </>
```

- [ ] **Step 2: Add id="main-content" to layout.tsx main wrapper**

In `frontend/app/layout.tsx`, find the `<main>` element and add `id="main-content"`:

Old: `<main className="max-w-[1400px] mx-auto px-6 py-8">`
New: `<main id="main-content" className="max-w-[1400px] mx-auto px-6 py-8">`

(The exact className may vary — find the `<main>` tag and add the id.)

- [ ] **Step 3: Verify skip link appears on Tab**

Open http://localhost:3000, press Tab once. A teal "Skip to main content" link should appear at the top-left. Press Enter — focus should jump past the nav.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/Nav.tsx frontend/app/layout.tsx
git commit -m "feat(a11y): add skip-to-content link for keyboard navigation"
```

---

### Task 8: Add cursor-pointer to all clickable non-link elements

**Files:**
- Modify: `frontend/app/page.tsx` — ThemeCard already uses Link (OK)
- Modify: `frontend/components/filings/ThemeFilingsPanel.tsx` — expand button
- Modify: `frontend/components/filings/CurationPanel.tsx` — expand button
- Modify: `frontend/components/deep-dive/panels/TranscriptInsights.tsx` — expand button
- Modify: `frontend/app/library/page.tsx` — FilterBar buttons
- Modify: `frontend/app/theme/[id]/ThemeDetailClient.tsx` — filter buttons + ticker cards

All `<button>` and clickable `<div>` elements that are not standard `<a>` links should have `cursor-pointer`.

- [ ] **Step 1: Add cursor-pointer to CurationPanel expand button**

In `frontend/components/filings/CurationPanel.tsx`, the expand `<button>` (line 65):

Old: `className="w-full bg-[var(--surface-alt)] px-5 py-3 flex items-center justify-between hover:brightness-105 transition"`
New: `className="w-full bg-[var(--surface-alt)] px-5 py-3 flex items-center justify-between hover:brightness-105 transition cursor-pointer"`

- [ ] **Step 2: Add cursor-pointer to ThemeFilingsPanel expand button**

In `frontend/components/filings/ThemeFilingsPanel.tsx`, find the expand button and add `cursor-pointer` to its className.

- [ ] **Step 3: Add cursor-pointer to TranscriptInsights expand button**

In `frontend/components/deep-dive/panels/TranscriptInsights.tsx`, the toggle button (line 17) — add `cursor-pointer`.

- [ ] **Step 4: Add cursor-pointer to FilterBar buttons**

In `frontend/app/library/page.tsx`, FilterBar buttons (line 68):

Old: `` className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${ ``
New: `` className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors cursor-pointer ${ ``

- [ ] **Step 5: Add cursor-pointer to ThemeDetailClient filter buttons and ticker cards**

In `frontend/app/theme/[id]/ThemeDetailClient.tsx`:
- Filter buttons (around line 317) — add `cursor-pointer`
- Ticker cards (around line 353) — add `cursor-pointer`

- [ ] **Step 6: Commit**

```bash
git add frontend/components/filings/CurationPanel.tsx frontend/components/filings/ThemeFilingsPanel.tsx \
  frontend/components/deep-dive/panels/TranscriptInsights.tsx frontend/app/library/page.tsx \
  frontend/app/theme/[id]/ThemeDetailClient.tsx
git commit -m "feat(ui): add cursor-pointer to all clickable non-link elements"
```

---

### Task 9: Add SectionReader modal Escape key + focus trap basics

**Files:**
- Verify: `frontend/components/filings/SectionReader.tsx`

SectionReader already has an Escape key handler (lines 42-44 `onKey` function). Verify it works and add `role="dialog"` + `aria-modal`.

- [ ] **Step 1: Add dialog role and aria-modal to SectionReader overlay**

In `frontend/components/filings/SectionReader.tsx`, the outer overlay div:

Old:
```tsx
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-6 overflow-y-auto"
      onClick={onClose}
    >
```

New:
```tsx
    <div
      role="dialog"
      aria-modal="true"
      aria-label={heading ?? sectionKey}
      className="fixed inset-0 z-50 bg-black/40 flex items-start justify-center p-6 overflow-y-auto"
      onClick={onClose}
    >
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/filings/SectionReader.tsx
git commit -m "feat(a11y): add dialog role and aria-modal to SectionReader"
```

---

### Task 10: Standardize font size tiers for metadata

**Files:**
- Modify: `frontend/app/globals.css` — add utility classes

Create named utility classes for the three metadata tiers so future components use consistent sizing instead of ad-hoc `text-[10px]` / `text-[11px]`.

- [ ] **Step 1: Add metadata font tier utilities to globals.css**

```css
/* Metadata text tiers — use instead of text-[10px]/text-[11px] */
.text-meta-xs { font-size: 10px; line-height: 1.4; }
.text-meta-sm { font-size: 11px; line-height: 1.4; }
/* text-xs (12px) is already provided by Tailwind */
```

- [ ] **Step 2: Commit**

```bash
git add frontend/app/globals.css
git commit -m "feat(ui): add text-meta-xs and text-meta-sm utility classes for metadata"
```

Note: Migrating existing `text-[10px]` and `text-[11px]` usages to these classes is a separate, lower-priority sweep. The classes exist now for new code.

---

### Task 11: Remove ticker `$` prefix

**Files:**
- Modify: `frontend/app/page.tsx` — ThemeCard seed ticker display
- Modify: `frontend/components/filings/SectionReader.tsx` — header ticker

US equity tickers don't conventionally use a `$` prefix. Remove it.

- [ ] **Step 1: Remove `$` from ThemeCard seed tickers**

In `frontend/app/page.tsx`, line 60:

Old:
```tsx
                    ${t}
```

New:
```tsx
                    {t}
```

- [ ] **Step 2: Remove `$` from SectionReader header**

In `frontend/components/filings/SectionReader.tsx`, line 63:

Old:
```tsx
              ${ticker.toUpperCase()} · {accession}
```

New:
```tsx
              {ticker.toUpperCase()} · {accession}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx frontend/components/filings/SectionReader.tsx
git commit -m "fix(ui): remove unconventional $ prefix from ticker symbols"
```

---

### Task 12: Final typecheck + lint verification

**Files:** None (verification only)

- [ ] **Step 1: Run TypeScript typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: Clean pass

- [ ] **Step 2: Run ESLint**

Run: `cd frontend && npm run lint`
Expected: Clean pass (or only pre-existing warnings)

- [ ] **Step 3: Visual smoke test**

Open the app and verify:
1. http://localhost:3000 — Theme cards render, teal header text visible, no `$` on tickers
2. http://localhost:3000/library — RunCard shows cursor-pointer, Tab focuses with teal ring
3. Tab through the page — skip link appears, focus rings visible on all interactive elements
4. Error states (if triggerable) show magenta/pink instead of red

---

## Self-Review Checklist

- [x] **Spec coverage:** All 5 top recommendations covered (Tasks 1-5). Critical accessibility issues #1-7 covered (Tasks 1, 2, 5, 6, 7). High interaction issues #8-12 partially covered (Tasks 2, 8, 9). High color issues #13-16 fully covered (Task 3). Medium typography #17-20 covered (Tasks 4, 10, 11). Issue #18 ($ticker) covered (Task 11).
- [x] **Placeholder scan:** No TBD/TODO — all steps have exact code.
- [x] **Type consistency:** CSS variable names (`--score-strong`, `--teal-light`, `--error-bg`, etc.) are consistent across Tasks 1-11.
- [x] **Not covered (intentional deferral):** Dark mode (#24), chart a11y (#7 — requires per-chart aria-labels which is a larger effort), loading skeletons (#21 — architecture decision on skeleton placement), code-splitting (#22 — perf optimization), and Tailwind color→token migration for non-error semantic colors (emerald/amber in RiskCard, ReportHeader, etc. — ~50 occurrences, separate PR scope).
