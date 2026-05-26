# Fiscal.ai — Stock Analysis UX Teardown & Inspiration

> **Source**: https://fiscal.ai/company/NasdaqGS-NBIS/ (and sibling tabs)
> **Captured**: 2026-05-25
> **Purpose**: Reference document for designing the stock-research surface area of our app.
> **Status**: Inspiration / research notes — not a spec.

---

## 1. TL;DR

Fiscal.ai is a desktop-first, dark-mode equity research workstation that condenses an analyst's entire workflow (overview, financials, estimates, transcripts, research, ownership, peers, modeling, filings) into a **single persistent company workspace** with a consistent shell.

The patterns most worth borrowing:

1. A **two-column "company in one screen"** Overview that pairs prose + KPI grids on the left with an interactive multi-metric chart on the right.
2. A **persistent header + primary tab strip** with deep-linkable URLs (`/company/<exchange>-<ticker>/<section>/<subsection>/`).
3. A **shared toolbar grammar** (toggles, chips, units, currency, granularity) repeated across every data view so users learn the controls once.
4. **Italic derivative rows interleaved with absolute rows** in financial tables (e.g., `Total Revenues` then _Total Revenues %Chg_ then _Gross Profit Margin_).
5. A **horizontal time-period slider with a dot per period** as the primary range selector for dense historical data.
6. **Document + AI Summary + Custom Summary** three-pane layout for transcripts and research reports.
7. An **editable in-browser DCF model** with input cells inline and implied upside auto-computed.
8. An **Industry tab that is a peer-comparison builder**, not a pre-baked competitor card.
9. **Graceful premium gating**: inline "Content Restricted — Upgrade" overlay rather than hidden sections.

---

## 2. Global Layout

```
┌──────────────────────────────────────────────────────────────────────────┐
│  Search 50,000+ companies                                       ❓  🔔   │ ← global omnibar
├──┬───────────────────────────────────────────────────────────────────────┤
│  │  [Logo] Company Name 🔖 ✎    $214.36  -$5.57 (-2.5%)  15min   ▶ Q1'26 │ ← company header
│ R│                                                                       │
│ A├───────────────────────────────────────────────────────────────────────┤
│ I│  Overview │ Financials │ IR │ Research │ Estimates │ News │ Ownership │
│ L│  │ Industry │ Modeling │ Filings                                      │ ← primary tabs
│  ├───────────────────────────────────────────────────────────────────────┤
│  │  [Section-specific sub-tabs + toolbar]                                │
│  │                                                                       │
│  │  [Main content — usually two-column]                                  │
│  │                                                                       │
└──┴───────────────────────────────────────────────────────────────────────┘
```

### 2.1 Left icon rail (app-level)

- Dashboard
- **Analysis** (the company workspace — where everything below lives)
- Charting (fundamental charting tool)
- Screener
- Query
- Resources
- Settings
- Version label at the top (e.g., `v5.6.8`) — trust signal for power users.

### 2.2 Top company header (persistent across all tabs)

- Logo, company name, exchange-prefixed ticker (`NasdaqGS-NBIS`).
- Bookmark icon + edit/notes icon.
- **Live price + absolute Δ + percent Δ** in a colored pill (red = down, green = up).
- "15 min delay" label.
- Right side: period selector (e.g., `Q1 2026`) with ▶ play icon (launch latest earnings call) and 📄 document icon (latest report).

### 2.3 Primary tab strip

Order is fixed and consistent for every company:

`Overview · Financials · Investor Relations · Research · Estimates · News · Ownership · Industry · Modeling · Filings`

Each tab has its own URL slug, so views are deep-linkable and bookmarkable.

---

## 3. Tab-by-Tab Specification

### 3.1 Overview — `/company/<ticker>/`

**Layout**: two columns (≈ 60/40 split). Left = facts, right = chart.

#### Left column

| Block                  | Content                                                           |
| ---------------------- | ----------------------------------------------------------------- |
| Company Overview       | Prose description from filings; "Show more" expander.             |
| Key Facts              | Name, CEO, Website, Sector, Year Founded (label-value table).     |
| **Company Statistics** | Dense 3-column grid grouped by theme. Currency toggle in header.  |
| Bulls Say / Bears Say  | 3 bullets each, sourced from Morningstar with attribution + date. |
| Earnings widget        | Beat/Miss summary + dot-line chart.                               |

**Company Statistics groups** (this is the most idea-dense block — replicate it):

- **Profile** — Market Cap, EV, Shares Out, Revenue, Employees
- **Margins** — Gross, EBITDA, Operating, Pre-Tax, Net, FCF
- **Returns (5Yr Avg)** — ROA, ROTA, ROE, ROCE, ROIC
- **Valuation (TTM)** — P/E, P/B, EV/Sales, EV/EBITDA, P/FCF, EV/Gross Profit
- **Valuation (NTM)** — Price Target, P/E, PEG, EV/Sales, EV/EBITDA, P/FCF
- **Financial Health** — Cash, Net Debt, Debt/Equity, EBIT/Interest
- **Growth (CAGR)** — Rev 3/5/10Yr, Dil EPS 3/5/10Yr, Rev Fwd 2Yr, EBITDA Fwd 2Yr, EPS Fwd 2Yr, EPS LT Growth Est
- **Dividends** — Yield, Payout, DPS, DPS Growth 3/5/10Yr, DPS Growth Fwd 2Yr

**Earnings widget controls**:

- Period: Annual / Semi-Annual / **Quarterly**
- Metric: **Revenue** / EPS (Normalized)
- Shows: latest revenue, estimate, beat/miss %, hit-rate ("Revenue beat 23 of 33 (70%)"), dot-line chart with green/red/grey markers.

#### Right column — Price chart

- Symbol search box (supports multi-ticker overlay).
- Range chips: `1D · 5D · 1M · 3M · 6M · YTD · 1Y · 3Y · 5Y · 10Y · MAX`.
- Custom Min/Max date pickers.
- Metric selector dropdown ("Price" — can switch to fundamentals).
- Chart-type toggle (line/bar).
- Fullscreen + Download buttons.
- Headline: "$214.36 +$147.50 (220.6%) past 5 years".
- Legend footer summarizing total change and CAGR.

---

### 3.2 Financials — `/company/<ticker>/financials/<statement>/<granularity>/`

**Sub-tabs**: Income Statement · Balance Sheet · Cash Flow Statement · Ratios · Segments & KPIs · Adjusted · Custom Metrics.

**Toolbar (above table)**:

- Horizontal **time-period slider** with green dot per reporting period + `LTM` waypoint, draggable min/max handles.
- Min date / Max date inputs.
- Metric search field.
- **Metric Templates** dropdown (preset bundles).
- `% Chg.` toggle, `Common Size` toggle.
- Decimal precision (`.0` / `.00`).
- `Standardized` vs. `As Reported`.
- Currency (USD).
- Units (K / M / B).
- Granularity: Annual / Quarterly / Semi-Annual / LTM.
- Reverse Dates toggle (most recent left vs. right).
- Share link, Download, Refresh.

**Table pattern**:

- Row label on left with chevron for drill-down children.
- Columns: `LTM`, `Dec '25`, `Dec '24`, … (≈ 9–10 years).
- Italic derivative rows interleaved (`Total Revenues %Chg`, `Gross Profit Margin`, `Operating Margin`, `EBITDA`, `Effective Tax Rate`).
- Checkbox per row → likely "add to chart / watchlist".

**Standard income-statement rows observed**:
Total Revenues → Cost of Sales → Gross Profit → SG&A → D&A → R&D → Other OpEx → Operating Profit → Interest Income → Interest Expense → Non-Op Income → Total Non-Op Income → Income Before Tax → Provision for Income Taxes → Consolidated Net Income → Minority Interests → Discontinued Ops → Net Income to Common → Basic EPS → Diluted EPS → Basic Shares → Diluted Shares → Shares Outstanding → EBITDA → Effective Tax Rate.

---

### 3.3 Investor Relations — `/company/<ticker>/investor-relations/`

**Three-pane layout**:

- **Left rail**: chronological list of events. Filterable ("All Events" dropdown). Each entry: quarter label + date (e.g., `Q1 2026 / May 2026`). Includes conference appearances (Morgan Stanley, UBS, etc.) interleaved with earnings calls.
- **Center**: Transcript / Report sub-tabs. Transcript is speaker-segmented (bold speaker name, paragraph body). Transcript search box. Download icon.
- **Right**: `AI Summary` and `Custom Summary` buttons opening a side panel.
- **Bottom**: persistent audio player (Quartr-powered) with play/pause, 1x speed, skip back, **"Skip to Q&A"** button, timeline scrub. Audio persists while user navigates other tabs.

---

### 3.4 Research — `/company/<ticker>/research/`

**Three-pane layout**:

- **Left rail**: dated list of analyst reports (Morningstar). One entry per refresh, going back ~6+ months.
- **Center**: PDF viewer with page thumbnails (vertical strip) + zoom controls (`133%`) + page indicator (`1 / 20`). Sub-tabs: `Morningstar Report` / `AI Generated Report`.
- **Right**: `AI Summary` / `Custom Summary` panel.

The Morningstar report header is itself a great mini-dashboard: Last Price, Fair Value Estimate, Price/FVE, Market Cap, Economic Moat, Equity Style Box, Uncertainty, Capital Allocation, ESG Risk Rating — all as labeled pills.

---

### 3.5 Estimates — `/company/<ticker>/estimates/<metric>/`

**Sub-tabs (by metric)**:
Revenue · EPS · Price Targets · EBITDA · EBIT · Free Cash Flow · FFO / Share · AFFO / Share · NAV · NAV / Share · Book Value / Share · CapEx.

**Toolbar**: `% Chg.` toggle, precision, units, Annual/Semi-Annual/Quarterly, line/bar toggle.

**Main view**:

- Consensus chart with green dots (beats), red dots (misses), grey forward dots, dashed projection line, shaded confidence band on future periods.
- Horizontal year slider mirroring the financials timeline.
- "Content Restricted — Upgrade" overlay on far-future periods (graceful gating).

**Estimates detail table** (rows × fiscal years labeled `(A)` actual or `(E)` estimate):

| Row                | Notes                           |
| ------------------ | ------------------------------- |
| Mean               | Consensus mean                  |
| Median             | Consensus median                |
| Actual             | Reported value                  |
| High / Low         | Range of estimates              |
| Standard Deviation | Dispersion                      |
| # of Estimates     | Number of contributing analysts |
| % Beat/Miss        | Surprise %                      |
| Beat/Miss          | Surprise absolute               |

**Long-Term Revision Trends** chart below — shows how the FY estimate evolved month by month. Extremely valuable for sentiment tracking.

---

### 3.6 News — `/company/<ticker>/news/`

Chronological news feed (not deeply explored here). Standard date-grouped list.

---

### 3.7 Ownership — `/company/<ticker>/insiders/`

**Sub-tabs**: Insiders · Trades · Holders.

**Insiders table columns**: Insider · Title · Date · Shares · % Owned · Market Value. Sortable. Multi-role officers get a `Show All` expander on Title. Totals row at the bottom.

(Trades = Form 4 buys/sells over time; Holders = institutional 13F positions — same table pattern.)

---

### 3.8 Industry — `/company/<ticker>/industry/`

A **peer-comparison builder**, not a static peer card:

- "Select & search metrics" input → adds metric columns (chips with `×` to remove).
- "Add companies" input → adds peer rows.
- Currency toggle (USD / Local), units (K / M / B), download.
- Table: drag handle, ticker (with brand favicon), `×` to remove, then the user's chosen metric columns. Sortable per column. Paginated.

Subject company appears pre-selected; default peer set (e.g., for NBIS: AMZN, MSFT, ORCL, GOOGL, NVDA, IBM, ANET, BABA) is pre-populated.

---

### 3.9 Modeling — `/company/<ticker>/financial-modeling/`

**The differentiator.** A fully editable DCF rendered as a spreadsheet.

**Toolbar**: precision (`.0` / `.00`), units (K/M/B), `Unlevered` / `Levered` toggle, `Reverse Dates` toggle, refresh.

**Rows (Build Up Free Cash)**:
Revenue → Revenue % Chg → EBIT → EBIT Margin → Tax Rate → NOPAT → NOPAT Margin → D&A → D&A / Revenue → Capex → Capex / Revenue → Chg. NWC → Chg. NWC / Revenue → Unlevered FCF (UFCF) → UFCF % Chg → PV of UFCF → Sum of PV of UFCF.

**Columns**: historical actuals `(A)` (fixed) + forward years `(E)` (editable). Forward cells are visually distinct (darker outlined input cells).

**Below the build-up**:

- WACC build: Cost of Debt → Tax Rate → After-Tax Cost of Debt → Risk-Free Rate → Market Risk Premium → Beta → Cost of Equity → Total Debt → Market Cap → Total Capital → Debt Weighting → Equity Weighting → **WACC**.
- Terminal Value: `Perpetuity` / `Multiple` toggle, Exit Multiple selector.
- Outputs: Terminal Value → PV of Terminal Value → Cumulative PV of UFCF → Net Debt → Equity Value → Shares Outstanding → **Implied Share Price** → Current Share Price → **Implied Upside / (Downside) %**.

**Scenario tabs**: bottom of page (`Untitled +`) — multiple scenarios per company.

---

### 3.10 Filings — `/company/<ticker>/filings/`

- Search box.
- Filter chips: `All` · `Annual & Quarterly Reports` · `News` · `Prospectuses and Registrations` · `Other`.
- List rows: Title · Date · Tag pill. Chevron to open.

---

## 4. Design System Notes

### 4.1 Color & theme

- **Dark-first** background (near-black with subtle elevation tiers).
- **Single accent color**: mint/green. Used for:
  - Primary buttons (`Download`, `Upgrade`).
  - Active state on toggles/chips.
  - Positive price deltas.
  - "BEAT" pills.
- **Red**: negative price deltas, "MISS" pills, misses on charts.
- **Grey**: neutral / forward / not-yet-reported.
- **Numbers** feel monospaced (or tabular figures) for column alignment; labels are sans-serif.

### 4.2 Component vocabulary

| Component                | Where it appears                                                                                      | Behavior                                  |
| ------------------------ | ----------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| Toggle pill group        | `% Chg.`, `Standardized/As Reported`, `K/M/B`, `Annual/Quarterly`, `USD/Local`, `Perpetuity/Multiple` | Single-select, visible state.             |
| Chip with `×`            | Selected metrics, peers, date filters                                                                 | Removable selections.                     |
| Range chip row           | Chart ranges `1D … MAX`                                                                               | Single-select.                            |
| Horizontal period slider | Financials, Estimates                                                                                 | Dot per period; drag handles for min/max. |
| Editable cell            | Modeling forward years, Industry table                                                                | Darker outlined box; type to change.      |
| Pill badge               | Price delta, BEAT/MISS, filing type                                                                   | Background tinted, small radius.          |
| Side panel (right)       | AI Summary / Custom Summary                                                                           | Slide-in from right.                      |
| Bottom dock              | Quartr audio player                                                                                   | Persistent across navigation.             |
| Inline upgrade overlay   | Estimates restricted years                                                                            | Greyed-out gradient with lock icon + CTA. |

### 4.3 Table conventions

- Row label left, values right-aligned.
- Drill-down chevron on parent rows.
- _Italic_ rows for derivative metrics (% Chg, Margin, CAGR).
- Em-dash `—` for missing values.
- Currency symbol only on first numeric column in dense tables; subsequent columns implied.

### 4.4 URL & routing scheme

```
/dashboard/
/screener/
/fundamental-charting/
/document-search/
/company/<exchange>-<ticker>/                              ← Overview
/company/<exchange>-<ticker>/financials/<statement>/<granularity>/
/company/<exchange>-<ticker>/investor-relations/[<event>]/
/company/<exchange>-<ticker>/research/
/company/<exchange>-<ticker>/estimates/<metric>/
/company/<exchange>-<ticker>/news/
/company/<exchange>-<ticker>/insiders/
/company/<exchange>-<ticker>/industry/
/company/<exchange>-<ticker>/financial-modeling/
/company/<exchange>-<ticker>/filings/
```

Deep-linkable, semantic, and consistent across companies.

---

## 5. Data Model Implications

To support these views, the backend needs (at minimum):

- **Company master** — ticker, exchange, name, description, sector/industry, CEO, founded year, website, employee count, logo URL.
- **Quote feed** — last price, change, % change, timestamp (with delay flag).
- **Statistics snapshot** — pre-computed Profile / Margins / Returns / Valuation TTM / Valuation NTM / Financial Health / Growth (CAGR) / Dividends. Keyed by company + as-of date.
- **Financial statements** — standardized + as-reported variants, line-item codes, parent/child hierarchy, period granularity, currency, unit.
  - Each line item should expose: absolute value, % change vs. prior period, % of revenue (common-size).
- **Estimates store** — per metric per fiscal period: mean, median, high, low, std dev, count of estimates, plus per-revision history for the LT trends chart.
- **Price targets** — analyst, target, date, rating.
- **Insider holdings** — person, title(s), filing date, shares, % owned, market value.
- **Institutional holdings** (13F).
- **Insider trades** (Form 4).
- **Peer set** — default per company + user-overrides; metric library shared with the Industry tab.
- **Transcripts** — event metadata, audio URL, transcript segments by speaker, links to Q&A timestamps.
- **Research documents** — PDF URL, page count, source (Morningstar / AI), publish date.
- **Filings** — SEC/exchange filings with category, date, document URL.
- **News** — headline, source, timestamp, URL.
- **Saved models** — per-user DCF scenarios; serialized inputs + outputs.
- **User layer** — bookmarks, custom summaries, watchlists, plan tier (for gating).

---

## 6. Build Order Recommendation

Suggested phasing if cloning the analyst workflow:

| Phase                               | Deliverables                                                                                                                              |
| ----------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| **P0 — Shell**                      | App rail, persistent company header, primary tab strip, deep-link routing, dark theme, design tokens (colors, spacing, typography).       |
| **P1 — Overview**                   | Company description, key facts, statistics grid (8 groups), interactive price chart with range chips. Highest single-page value.          |
| **P2 — Financials**                 | Income statement table with toolbar (granularity, units, % chg, common-size, standardized/as-reported), then Balance Sheet and Cash Flow. |
| **P3 — Estimates**                  | Consensus chart + estimates table for Revenue and EPS first; revision trends.                                                             |
| **P4 — Ownership + Filings + News** | Three list-heavy tabs that share a common table component.                                                                                |
| **P5 — IR Transcripts**             | Three-pane reader + audio dock. AI Summary requires LLM integration.                                                                      |
| **P6 — Research**                   | PDF viewer + analyst report ingestion + AI Summary.                                                                                       |
| **P7 — Industry**                   | Peer-comparison builder (shared metric library with Financials).                                                                          |
| **P8 — Modeling**                   | Editable DCF; biggest engineering lift; reuse cells from Financials.                                                                      |

---

## 7. Specific Patterns to Replicate (cheat sheet)

1. **Header price pill** — `$214.36  -$5.57 (-2.5%)  15min` with color-coded background. Tiny detail, huge polish gain.
2. **Statistics-block group titles** in a slightly muted color, with KPI rows in two columns of label/value beneath. Stack 3 groups side-by-side at desktop, 1 column on mobile.
3. **Italic derivative rows** in tables — saves users mental math.
4. **Horizontal period slider** for ranges — far better than year buttons or pagination.
5. **Beat/Miss dot chart** on earnings — instantly communicates a company's track record.
6. **"Show more" expander** on long prose (description, notes) — keeps the fold tight.
7. **Bulls Say / Bears Say** as a thesis snapshot — borrow this UI even if you generate the content with your own LLM.
8. **AI Summary / Custom Summary** dual buttons — invites users to engage with the model without forcing it.
9. **Skip to Q&A** button on transcript player — analysts will love this.
10. **Editable forward cells visually distinct from historical cells** — establishes that the right side of the table is "yours".
11. **Inline upgrade overlay** — a chart with the future portion locked under a translucent gradient + "Upgrade" CTA. Converts better than hiding sections.
12. **Brand favicons in peer tables** — small but makes the table scannable.

---

## 8. Anti-patterns / things to improve on

A few observations where you could differentiate:

- The icon rail is unlabeled by default; first-time users may not discover Charting/Screener/Query/Resources. Tooltips or labeled mode would help.
- Some tables are wide enough to require horizontal scroll on smaller screens; pinned first column would help.
- The Modeling tab is powerful but lacks scenario presets (bull/base/bear) out of the box — you could ship those.
- AI Summary is hidden behind a click; consider streaming a default summary at the top of any transcript/report.
- No obvious "compare to peer" overlay on the Overview price chart — would be a natural extension.
- News tab (not deeply explored) appears to be a flat feed; clustering by topic / sentiment would be a differentiator.

---

## 9. Open questions for product/design

- Do we want the company workspace to be **single-page (tabs)** like fiscal.ai, or **route-per-page**? (Fiscal.ai routes per page but feels single-page due to a persistent shell.)
- Which currency/unit toggles are global vs. per-table?
- How much of the statistics block is pre-computed server-side vs. derived client-side?
- Do we license third-party reports (Morningstar-style) or rely entirely on LLM-generated research?
- DCF model: build native or embed a third-party engine?
- Where does our LLM live in this UI — only in side panels (AI Summary), or also as an in-line "Explain this row" affordance on financials?

---

## 10. Appendix — Raw observations

- Visited tabs: Overview, Financials (Income Statement / Annual), Estimates (Revenue), Research, Investor Relations, Ownership (Insiders), Industry, Modeling, Filings.
- Example ticker used: `NasdaqGS-NBIS` (Nebius Group N.V.).
- All screenshots and raw text captures available in the originating research session.
- Date of capture: 2026-05-25. Fiscal.ai app version label seen: `v5.6.8`.
