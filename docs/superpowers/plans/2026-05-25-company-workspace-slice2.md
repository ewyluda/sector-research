# Company Workspace — Slice 2 Implementation Plan (Overview tab)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Overview tab of the company workspace — an 8-group statistics grid, a 1M–5Y price line chart, and a pipeline-derived Bulls/Bears card — replacing the slice-1 placeholder.

**Architecture:** A new `GET /api/company/{ticker}/overview` endpoint (fmp-only) returns the statistics grid + a 5-year daily close series, built in `company_snapshot.py` from `profile` + `key-metrics-ttm` + a new `ratios-ttm` fetch + `financial-growth`. The frontend renders a `StatisticsGrid`, a Recharts `PriceChart` (range chips slice the 5y series client-side), and a `BullsBears` card that reuses the existing `pipeline.list`/`pipeline.report` endpoints (no new backend) to pull the latest completed run's `bull_case`/`bear_case`.

**Tech Stack:** FastAPI + Pydantic + the shared `FMPClient`; Next.js 16 client components + Recharts; stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-05-25-company-workspace-design.md` (Overview = slice 2).

**Scope notes / deviations (decided during planning, with the user):**
- **Beat/miss widget is DEFERRED** to a fast-follow. The live FMP `analyst-estimates` response carries only consensus avg/high/low — **no `actual` fields** — so beat/miss has no data there; the only actuals source is the `earnings_prints` table, which needs a separate refresh/index step. Not bolting that onto the Overview now.
- **Lens-aware discovery-rank badge is DEFERRED.** Fetching a ticker's theme rank requires `GET /api/themes/{id}/discover`, which runs the full discovery engine (FMP screener) on demand — too heavy for an Overview load. The lens still reframes the Overview via Bulls/Bears run selection.
- **Valuation ratios come from `ratios-ttm`, not `key-metrics-ttm`.** Verified against the live API: `key-metrics-ttm` lacks P/E, P/B, P/S, PEG, dividend yield (those are in `ratios-ttm`). This plan adds a `get_ratios_ttm` client method. (The existing `_build_curated_financials` reads PE/PB keys from `key-metrics-ttm` where they don't exist — a pre-existing latent issue; **do not** touch it here.)

**Conventions (from CLAUDE.md):** backend absolute imports rooted at project root; run from project root with `backend/venv` active; every endpoint normalizes `ticker = ticker.upper()`; FMP client methods return `tuple[data, Citation]`; frontend pages/components are `"use client"` using `useParams`/`useSearchParams`. Per `frontend/AGENTS.md`, check `node_modules/next/dist/docs/` before writing Next routing code. Known pre-existing tsc errors live in three `.mts` test files — ignore those when checking `tsc`.

---

## File Structure

**Backend:**
- Modify `backend/app/clients/fmp.py` — add `get_ratios_ttm`.
- Modify `backend/app/services/company_snapshot.py` — add `StatItem`, `StatGroup`, `PricePoint`, `CompanyOverview` models + `build_company_overview`.
- Modify `backend/app/api/company.py` — add `GET /{ticker}/overview`.
- Create `backend/tests/test_company_overview.py` — unit tests for `build_company_overview` with a stub FMP.

**Frontend:**
- Modify `frontend/lib/api.ts` — `StatItem`/`StatGroup`/`PricePoint`/`CompanyOverview` types + `getCompanyOverview`.
- Create `frontend/components/company/formatStat.ts` — value formatter by unit.
- Create `frontend/components/company/StatisticsGrid.tsx` — the 8-group grid.
- Create `frontend/components/company/PriceChart.tsx` — Recharts line + range chips.
- Create `frontend/components/company/BullsBears.tsx` — pipeline-derived bull/bear card.
- Modify `frontend/app/company/[ticker]/page.tsx` — compose the three into the Overview tab.

---

## Task 1: Backend — overview endpoint (ratios-ttm fetch + stats grid + price series)

**Files:**
- Modify: `backend/app/clients/fmp.py`
- Modify: `backend/app/services/company_snapshot.py`
- Modify: `backend/app/api/company.py`
- Create: `backend/tests/test_company_overview.py`

- [ ] **Step 1: Add `get_ratios_ttm` to the FMP client.**

In `backend/app/clients/fmp.py`, directly after the existing `get_key_metrics_ttm` method, add (mirrors its exact pattern — the existing method uses `data[0] if isinstance(data, list) and data else data` and `self._make_citation(...)`, `ttl=TTL_FUNDAMENTAL`):

```python
    async def get_ratios_ttm(self, ticker: str) -> tuple[dict, Citation]:
        """Trailing-twelve-month valuation/profitability ratios.

        Source for P/E, P/B, P/S, P/FCF, PEG, dividend yield, and margins —
        these live on /stable/ratios-ttm, NOT key-metrics-ttm.
        """
        params = {"symbol": ticker}
        data = await self._request("ratios-ttm", params, ttl=TTL_FUNDAMENTAL)
        result = data[0] if isinstance(data, list) and data else data
        citation = self._make_citation(
            "ratios-ttm", "Ratios TTM", ticker, params
        )
        return result, citation
```

- [ ] **Step 2: Write the failing test.** Create `backend/tests/test_company_overview.py`:

```python
"""Unit tests for build_company_overview.

Stubs the FMP client (each method returns tuple[data, Citation]) — no network.
Verifies the 8-group statistics grid maps real FMP TTM field names, missing
keys degrade to None (em-dash), and the price series is oldest-first.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_snapshot import build_company_overview


class _StubFMP:
    def __init__(self, profile, km, ratios, growth, prices):
        self._profile, self._km, self._ratios, self._growth, self._prices = (
            profile, km, ratios, growth, prices,
        )

    async def get_company_profile(self, ticker):
        return self._profile, None

    async def get_key_metrics_ttm(self, ticker):
        return self._km, None

    async def get_ratios_ttm(self, ticker):
        return self._ratios, None

    async def get_financial_growth(self, ticker, period="annual", limit=1):
        return self._growth, None

    async def get_historical_price(self, ticker, from_date, to_date):
        return self._prices, None


def _full_stub():
    return _StubFMP(
        profile={"companyName": "Apple Inc.", "sector": "Technology",
                 "industry": "Consumer Electronics", "marketCap": 3.4e12,
                 "beta": 1.25, "fullTimeEmployees": 161000},
        km={"enterpriseValueTTM": 3.5e12, "evToEBITDATTM": 25.1,
            "evToSalesTTM": 8.2, "returnOnEquityTTM": 1.47,
            "returnOnAssetsTTM": 0.28, "returnOnInvestedCapitalTTM": 0.55,
            "returnOnCapitalEmployedTTM": 0.6, "returnOnTangibleAssetsTTM": 0.3,
            "currentRatioTTM": 0.87, "netDebtToEBITDATTM": 0.4,
            "workingCapitalTTM": -1.0e9, "earningsYieldTTM": 0.03,
            "freeCashFlowYieldTTM": 0.035},
        ratios={"priceToEarningsRatioTTM": 35.2, "priceToBookRatioTTM": 48.0,
                "priceToSalesRatioTTM": 8.5, "priceToFreeCashFlowRatioTTM": 30.0,
                "priceToEarningsGrowthRatioTTM": 2.1,
                "forwardPriceToEarningsGrowthRatioTTM": 1.9,
                "priceToFairValueTTM": 1.1, "grossProfitMarginTTM": 0.46,
                "ebitdaMarginTTM": 0.34, "operatingProfitMarginTTM": 0.30,
                "pretaxProfitMarginTTM": 0.29, "netProfitMarginTTM": 0.25,
                "dividendYieldTTM": 0.005, "dividendPayoutRatioTTM": 0.15,
                "dividendPerShareTTM": 0.96, "cashPerShareTTM": 4.0},
        growth={"revenueGrowth": 0.08, "epsgrowth": 0.10,
                "freeCashFlowGrowth": 0.05, "ebitdaGrowth": 0.07,
                "fiveYRevenueGrowthPerShare": 0.12,
                "tenYRevenueGrowthPerShare": 0.15,
                "fiveYDividendperShareGrowthPerShare": 0.06},
        prices=[
            {"date": "2025-01-03", "close": 240.0},
            {"date": "2025-01-02", "close": 243.0},  # newest-first from FMP
        ],
    )


class BuildCompanyOverviewTest(unittest.IsolatedAsyncioTestCase):
    async def test_eight_groups_present(self):
        ov = await build_company_overview(_full_stub(), "aapl")
        self.assertEqual(ov.ticker, "AAPL")
        self.assertEqual(ov.sector, "Technology")
        titles = [g.title for g in ov.stats]
        self.assertEqual(titles, [
            "Profile", "Margins", "Returns (TTM)", "Valuation (TTM)",
            "Valuation (Forward)", "Financial Health", "Growth", "Dividends",
        ])

    async def test_maps_real_field_names(self):
        ov = await build_company_overview(_full_stub(), "AAPL")
        groups = {g.title: {i.label: i for i in g.items} for g in ov.stats}
        # ROE from key-metrics-ttm returnOnEquityTTM
        self.assertAlmostEqual(groups["Returns (TTM)"]["ROE"].value, 1.47)
        self.assertEqual(groups["Returns (TTM)"]["ROE"].unit, "pct")
        # P/E from ratios-ttm priceToEarningsRatioTTM
        self.assertAlmostEqual(groups["Valuation (TTM)"]["P/E"].value, 35.2)
        self.assertEqual(groups["Valuation (TTM)"]["P/E"].unit, "x")
        # Gross margin from ratios-ttm
        self.assertAlmostEqual(groups["Margins"]["Gross"].value, 0.46)
        # Market cap from profile
        self.assertAlmostEqual(groups["Profile"]["Market Cap"].value, 3.4e12)
        self.assertEqual(groups["Profile"]["Market Cap"].unit, "money")
        # Employees int
        self.assertEqual(groups["Profile"]["Employees"].value, 161000)
        self.assertEqual(groups["Profile"]["Employees"].unit, "int")

    async def test_missing_keys_degrade_to_none(self):
        stub = _StubFMP(profile={"companyName": "X"}, km={}, ratios={},
                        growth={}, prices=[])
        ov = await build_company_overview(stub, "X")
        groups = {g.title: {i.label: i for i in g.items} for g in ov.stats}
        self.assertIsNone(groups["Valuation (TTM)"]["P/E"].value)
        self.assertIsNone(groups["Returns (TTM)"]["ROE"].value)
        self.assertEqual(ov.prices, [])

    async def test_prices_sorted_oldest_first(self):
        ov = await build_company_overview(_full_stub(), "AAPL")
        self.assertEqual([p.date for p in ov.prices], ["2025-01-02", "2025-01-03"])
        self.assertEqual(ov.prices[0].close, 243.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails.**

```bash
source backend/venv/bin/activate
python -m unittest backend.tests.test_company_overview -v
```
Expected: FAIL — `ImportError: cannot import name 'build_company_overview'`.

- [ ] **Step 4: Implement the models + builder.** Append to `backend/app/services/company_snapshot.py` (it already imports `Optional`, `BaseModel`, and defines `_as_dict`; add `from datetime import date, timedelta` and `import asyncio` at the top if not present):

```python
class StatItem(BaseModel):
    label: str
    value: Optional[float] = None
    unit: str  # "pct" | "x" | "money" | "num" | "int"


class StatGroup(BaseModel):
    title: str
    items: list[StatItem]


class PricePoint(BaseModel):
    date: str
    close: float


class CompanyOverview(BaseModel):
    ticker: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    stats: list[StatGroup]
    prices: list[PricePoint]


def _f(d: dict, key: str) -> Optional[float]:
    """Safe float read: None if absent or non-numeric."""
    v = d.get(key)
    if isinstance(v, (int, float)):
        return float(v)
    return None


async def build_company_overview(fmp, ticker: str) -> CompanyOverview:
    """Assemble the Overview-tab payload from five FMP endpoints (fmp-only).

    Valuation ratios + margins come from ratios-ttm; EV multiples + returns
    from key-metrics-ttm; growth/CAGR from financial-growth; identity + market
    cap from profile; 5y daily closes from historical-price. Any missing field
    degrades to None (rendered em-dash).
    """
    ticker = ticker.upper()
    today = date.today()
    five_y_ago = today - timedelta(days=365 * 5 + 2)

    async def _safe(coro, default):
        try:
            data, _ = await coro
            return data
        except Exception:
            return default

    profile, km, ratios, growth_list, prices_raw = await asyncio.gather(
        _safe(fmp.get_company_profile(ticker), {}),
        _safe(fmp.get_key_metrics_ttm(ticker), {}),
        _safe(fmp.get_ratios_ttm(ticker), {}),
        _safe(fmp.get_financial_growth(ticker, period="annual", limit=1), []),
        _safe(fmp.get_historical_price(ticker, five_y_ago.isoformat(), today.isoformat()), []),
    )

    pr = _as_dict(profile)
    km = _as_dict(km)
    ra = _as_dict(ratios)
    fg = growth_list[0] if isinstance(growth_list, list) and growth_list else {}
    fg = _as_dict(fg)

    market_cap = _f(pr, "marketCap")
    if market_cap is None:
        market_cap = _f(km, "marketCap")

    stats = [
        StatGroup(title="Profile", items=[
            StatItem(label="Market Cap", value=market_cap, unit="money"),
            StatItem(label="Enterprise Value", value=_f(km, "enterpriseValueTTM"), unit="money"),
            StatItem(label="Beta", value=_f(pr, "beta"), unit="num"),
            StatItem(label="Employees", value=_f(pr, "fullTimeEmployees"), unit="int"),
        ]),
        StatGroup(title="Margins", items=[
            StatItem(label="Gross", value=_f(ra, "grossProfitMarginTTM"), unit="pct"),
            StatItem(label="EBITDA", value=_f(ra, "ebitdaMarginTTM"), unit="pct"),
            StatItem(label="Operating", value=_f(ra, "operatingProfitMarginTTM"), unit="pct"),
            StatItem(label="Pre-Tax", value=_f(ra, "pretaxProfitMarginTTM"), unit="pct"),
            StatItem(label="Net", value=_f(ra, "netProfitMarginTTM"), unit="pct"),
        ]),
        StatGroup(title="Returns (TTM)", items=[
            StatItem(label="ROE", value=_f(km, "returnOnEquityTTM"), unit="pct"),
            StatItem(label="ROA", value=_f(km, "returnOnAssetsTTM"), unit="pct"),
            StatItem(label="ROIC", value=_f(km, "returnOnInvestedCapitalTTM"), unit="pct"),
            StatItem(label="ROCE", value=_f(km, "returnOnCapitalEmployedTTM"), unit="pct"),
            StatItem(label="ROTA", value=_f(km, "returnOnTangibleAssetsTTM"), unit="pct"),
        ]),
        StatGroup(title="Valuation (TTM)", items=[
            StatItem(label="P/E", value=_f(ra, "priceToEarningsRatioTTM"), unit="x"),
            StatItem(label="P/B", value=_f(ra, "priceToBookRatioTTM"), unit="x"),
            StatItem(label="P/S", value=_f(ra, "priceToSalesRatioTTM"), unit="x"),
            StatItem(label="P/FCF", value=_f(ra, "priceToFreeCashFlowRatioTTM"), unit="x"),
            StatItem(label="EV/EBITDA", value=_f(km, "evToEBITDATTM"), unit="x"),
            StatItem(label="EV/Sales", value=_f(km, "evToSalesTTM"), unit="x"),
            StatItem(label="PEG", value=_f(ra, "priceToEarningsGrowthRatioTTM"), unit="x"),
        ]),
        StatGroup(title="Valuation (Forward)", items=[
            StatItem(label="Fwd PEG", value=_f(ra, "forwardPriceToEarningsGrowthRatioTTM"), unit="x"),
            StatItem(label="Price/Fair Value", value=_f(ra, "priceToFairValueTTM"), unit="x"),
            StatItem(label="Earnings Yield", value=_f(km, "earningsYieldTTM"), unit="pct"),
            StatItem(label="FCF Yield", value=_f(km, "freeCashFlowYieldTTM"), unit="pct"),
        ]),
        StatGroup(title="Financial Health", items=[
            StatItem(label="Current Ratio", value=_f(km, "currentRatioTTM"), unit="x"),
            StatItem(label="Net Debt/EBITDA", value=_f(km, "netDebtToEBITDATTM"), unit="x"),
            StatItem(label="Cash/Share", value=_f(ra, "cashPerShareTTM"), unit="money"),
            StatItem(label="Working Capital", value=_f(km, "workingCapitalTTM"), unit="money"),
        ]),
        StatGroup(title="Growth", items=[
            StatItem(label="Revenue", value=_f(fg, "revenueGrowth"), unit="pct"),
            StatItem(label="EPS", value=_f(fg, "epsgrowth"), unit="pct"),
            StatItem(label="FCF", value=_f(fg, "freeCashFlowGrowth"), unit="pct"),
            StatItem(label="EBITDA", value=_f(fg, "ebitdaGrowth"), unit="pct"),
            StatItem(label="Rev 5Y CAGR", value=_f(fg, "fiveYRevenueGrowthPerShare"), unit="pct"),
            StatItem(label="Rev 10Y CAGR", value=_f(fg, "tenYRevenueGrowthPerShare"), unit="pct"),
        ]),
        StatGroup(title="Dividends", items=[
            StatItem(label="Yield", value=_f(ra, "dividendYieldTTM"), unit="pct"),
            StatItem(label="Payout", value=_f(ra, "dividendPayoutRatioTTM"), unit="pct"),
            StatItem(label="DPS", value=_f(ra, "dividendPerShareTTM"), unit="money"),
            StatItem(label="DPS 5Y Growth", value=_f(fg, "fiveYDividendperShareGrowthPerShare"), unit="pct"),
        ]),
    ]

    prices: list[PricePoint] = []
    if isinstance(prices_raw, list):
        for row in prices_raw:
            if isinstance(row, dict) and row.get("date") and isinstance(row.get("close"), (int, float)):
                prices.append(PricePoint(date=row["date"], close=float(row["close"])))
        prices.sort(key=lambda p: p.date)  # FMP returns newest-first; chart wants oldest-first

    return CompanyOverview(
        ticker=ticker,
        sector=pr.get("sector"),
        industry=pr.get("industry"),
        stats=stats,
        prices=prices,
    )
```

- [ ] **Step 5: Run test to verify it passes.**

```bash
python -m unittest backend.tests.test_company_overview -v
```
Expected: PASS (4 tests OK).

- [ ] **Step 6: Add the endpoint.** In `backend/app/api/company.py`, update the import line and add the route:

Change:
```python
from backend.app.services.company_snapshot import CompanyHeader, build_company_header
```
to:
```python
from backend.app.services.company_snapshot import (
    CompanyHeader,
    CompanyOverview,
    build_company_header,
    build_company_overview,
)
```
Then add after the existing `get_company_header` route:
```python
@router.get("/{ticker}/overview", response_model=CompanyOverview)
async def get_company_overview(ticker: str, request: Request) -> CompanyOverview:
    return await build_company_overview(request.app.state.fmp, ticker)
```

- [ ] **Step 7: Verify the route is wired.**

```bash
python -c "from backend.app.main import app; print(sorted(r.path for r in app.routes if 'company' in r.path))"
```
Expected: `['/api/company/{ticker}/header', '/api/company/{ticker}/overview']`

- [ ] **Step 8: Commit.**

```bash
git add backend/app/clients/fmp.py backend/app/services/company_snapshot.py backend/app/api/company.py backend/tests/test_company_overview.py
git commit -m "feat(company): overview endpoint — 8-group stats grid + 5y price series"
```

---

## Task 2: Frontend — overview API client

**Files:** Modify `frontend/lib/api.ts` (in the "Company workspace" section added in slice 1, after `getCompanyHeader`).

- [ ] **Step 1: Add types + fetch fn.** Append in the Company workspace section:

```ts
export interface StatItem {
  label: string;
  value: number | null;
  unit: "pct" | "x" | "money" | "num" | "int";
}

export interface StatGroup {
  title: string;
  items: StatItem[];
}

export interface PricePoint {
  date: string;
  close: number;
}

export interface CompanyOverview {
  ticker: string;
  sector: string | null;
  industry: string | null;
  stats: StatGroup[];
  prices: PricePoint[];
}

export async function getCompanyOverview(ticker: string): Promise<CompanyOverview> {
  return apiFetch<CompanyOverview>(`/api/company/${encodeURIComponent(ticker)}/overview`);
}
```

- [ ] **Step 2: Type-check.**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no new errors (only the 3 pre-existing `.mts` errors).

- [ ] **Step 3: Commit.**

```bash
git add frontend/lib/api.ts
git commit -m "feat(company): typed getCompanyOverview client"
```

---

## Task 3: Frontend — formatStat + StatisticsGrid

**Files:**
- Create: `frontend/components/company/formatStat.ts`
- Create: `frontend/components/company/StatisticsGrid.tsx`

- [ ] **Step 1: `frontend/components/company/formatStat.ts`:**

```ts
import type { StatItem } from "@/lib/api";

/** Format a stat value by unit. Null → em-dash. */
export function formatStat(value: number | null, unit: StatItem["unit"]): string {
  if (value == null || Number.isNaN(value)) return "—";
  switch (unit) {
    case "pct":
      return `${(value * 100).toFixed(1)}%`;
    case "x":
      return `${value.toFixed(1)}x`;
    case "int":
      return Math.round(value).toLocaleString();
    case "num":
      return value.toFixed(2);
    case "money": {
      const a = Math.abs(value);
      if (a >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
      if (a >= 1e9) return `$${(value / 1e9).toFixed(1)}B`;
      if (a >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
      return `$${value.toFixed(2)}`;
    }
    default:
      return String(value);
  }
}
```

- [ ] **Step 2: `frontend/components/company/StatisticsGrid.tsx`:**

```tsx
import type { StatGroup } from "@/lib/api";
import { formatStat } from "./formatStat";

export function StatisticsGrid({ groups }: { groups: StatGroup[] }) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {groups.map((g) => (
        <div key={g.title} className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
          <h3 className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            {g.title}
          </h3>
          <dl className="space-y-1">
            {g.items.map((it) => (
              <div key={it.label} className="flex items-baseline justify-between gap-2">
                <dt className="text-xs text-[var(--text-muted)]">{it.label}</dt>
                <dd className="font-mono text-sm tabular-nums text-[var(--text)]">
                  {formatStat(it.value, it.unit)}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Type-check + lint.**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no new errors; clean lint.

- [ ] **Step 4: Commit.**

```bash
git add frontend/components/company/formatStat.ts frontend/components/company/StatisticsGrid.tsx
git commit -m "feat(company): statistics grid + stat formatter"
```

---

## Task 4: Frontend — PriceChart (Recharts line + range chips)

**Files:** Create `frontend/components/company/PriceChart.tsx`.

Context: Recharts is already a dependency (used across `components/deep-dive/charts/`). The chart receives the full 5-year `PricePoint[]` (oldest-first) and slices it client-side per the selected range.

- [ ] **Step 1: `frontend/components/company/PriceChart.tsx`:**

```tsx
"use client";

import { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import type { PricePoint } from "@/lib/api";

const RANGES = ["1M", "3M", "6M", "YTD", "1Y", "5Y"] as const;
type Range = (typeof RANGES)[number];

function cutoff(range: Range): Date {
  const now = new Date();
  switch (range) {
    case "1M": return new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
    case "3M": return new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
    case "6M": return new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
    case "YTD": return new Date(now.getFullYear(), 0, 1);
    case "1Y": return new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
    case "5Y": return new Date(now.getFullYear() - 5, now.getMonth(), now.getDate());
  }
}

export function PriceChart({ prices }: { prices: PricePoint[] }) {
  const [range, setRange] = useState<Range>("1Y");

  const data = useMemo(() => {
    const from = cutoff(range).toISOString().slice(0, 10);
    return prices.filter((p) => p.date >= from);
  }, [prices, range]);

  const first = data[0]?.close;
  const last = data[data.length - 1]?.close;
  const delta = first != null && last != null ? last - first : null;
  const pct = delta != null && first ? (delta / first) * 100 : null;
  const up = (delta ?? 0) >= 0;
  const stroke = up ? "var(--success,#16a34a)" : "var(--error,#dc2626)";

  if (prices.length === 0) {
    return (
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--text-muted)]">
        No price history available.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-baseline gap-2">
          {last != null && (
            <span className="font-mono text-lg font-semibold text-[var(--text)]">
              ${last.toFixed(2)}
            </span>
          )}
          {delta != null && pct != null && (
            <span className="font-mono text-xs" style={{ color: stroke }}>
              {up ? "+" : ""}{delta.toFixed(2)} ({up ? "+" : ""}{pct.toFixed(2)}%) · {range}
            </span>
          )}
        </div>
        <div className="flex gap-1">
          {RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`rounded px-2 py-0.5 text-xs transition-colors ${
                r === range
                  ? "bg-[var(--accent-bg)] font-medium text-[var(--text)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text)]"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={data} margin={{ top: 5, right: 8, bottom: 5, left: 8 }}>
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: "var(--text-muted)" }}
            minTickGap={40}
            tickFormatter={(d: string) => d.slice(0, 7)}
          />
          <YAxis
            domain={["auto", "auto"]}
            tick={{ fontSize: 10, fill: "var(--text-muted)" }}
            width={48}
            tickFormatter={(v: number) => `$${v.toFixed(0)}`}
          />
          <Tooltip
            contentStyle={{ fontSize: 12, background: "var(--surface)", border: "1px solid var(--border)" }}
            formatter={(v: number) => [`$${v.toFixed(2)}`, "Close"]}
          />
          <Line type="monotone" dataKey="close" stroke={stroke} dot={false} strokeWidth={1.5} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Type-check + lint.**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no new errors; clean lint. (If Recharts' `Tooltip`/`tickFormatter` types complain about the `number`/`string` param, match the existing usage in `frontend/components/deep-dive/charts/TrendLineChart.tsx` — read it for the exact typing idiom — but do NOT loosen with `any`.)

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/company/PriceChart.tsx
git commit -m "feat(company): price chart with 1M-5Y range chips"
```

---

## Task 5: Frontend — BullsBears (pipeline-derived, lens-aware)

**Files:** Create `frontend/components/company/BullsBears.tsx`.

Context: reuses the same latest-run resolver pattern as `components/company/ResearchTab.tsx` (fetch completed runs filtered by ticker via `pipeline.list({ status: "completed", ticker, limit: 50 })`, prefer the run matching `?lens=`, else most recent; then `pipeline.report(runId)`). It reads `report.phases.thesis?.structured` as `ThesisStructured` (`bull_case` / `bear_case`, each `ThesisPoint { title; evidence }`). These types already exist in `lib/api.ts`.

- [ ] **Step 1: `frontend/components/company/BullsBears.tsx`:**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { pipeline } from "@/lib/api";
import type { RunSummary, ReportResponse, ThesisStructured, ThesisPoint } from "@/lib/api";
import { EmptyState } from "./EmptyState";

export function BullsBears({ ticker }: { ticker: string }) {
  const lens = useSearchParams().get("lens");
  const [hasRun, setHasRun] = useState<boolean | null>(null);
  const [thesis, setThesis] = useState<ThesisStructured | null>(null);

  useEffect(() => {
    let alive = true;
    pipeline
      .list({ status: "completed", ticker, limit: 50 })
      .then((runs: RunSummary[]) => {
        if (!alive) return;
        const preferred = (lens && runs.find((r) => r.theme_id === lens)) || runs[0];
        if (!preferred) {
          setHasRun(false);
          setThesis(null);
          return;
        }
        setHasRun(true);
        return pipeline.report(preferred.id).then((rep: ReportResponse) => {
          if (alive) setThesis((rep.phases.thesis?.structured as ThesisStructured) ?? null);
        });
      })
      .catch(() => {
        if (alive) { setHasRun(false); setThesis(null); }
      });
    return () => {
      alive = false;
    };
  }, [ticker, lens]);

  if (hasRun === null) {
    return <div className="p-4 text-sm text-[var(--text-muted)]">Loading thesis…</div>;
  }
  if (!hasRun) {
    return (
      <EmptyState
        title="No thesis yet"
        message="Run the due-diligence pipeline to generate the bull and bear case."
        cta={{ href: `/pipeline/new?ticker=${ticker}`, label: "Run pipeline →" }}
      />
    );
  }

  const bulls: ThesisPoint[] = thesis?.bull_case ?? [];
  const bears: ThesisPoint[] = thesis?.bear_case ?? [];

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      <Column title="Bulls say" tone="var(--success,#16a34a)" points={bulls} />
      <Column title="Bears say" tone="var(--error,#dc2626)" points={bears} />
    </div>
  );
}

function Column({ title, tone, points }: { title: string; tone: string; points: ThesisPoint[] }) {
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
      <h3 className="mb-2 text-sm font-semibold" style={{ color: tone }}>{title}</h3>
      {points.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">—</p>
      ) : (
        <ul className="space-y-2">
          {points.map((p, i) => (
            <li key={i} className="text-sm">
              <span className="font-medium text-[var(--text)]">{p.title}</span>
              {p.evidence && <span className="text-[var(--text-muted)]"> — {p.evidence}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Type-check + lint.**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no new errors; clean lint. (Confirm `ThesisStructured` and `ThesisPoint` are exported from `lib/api.ts` — they are. If `rep.phases.thesis` is typed without `structured`, mirror the cast used in `app/pipeline/[runId]/page.tsx`: `as ThesisStructured`.)

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/company/BullsBears.tsx
git commit -m "feat(company): pipeline-derived Bulls/Bears card (lens-aware)"
```

---

## Task 6: Frontend — wire the Overview page

**Files:** Modify `frontend/app/company/[ticker]/page.tsx` (currently the slice-1 placeholder).

- [ ] **Step 1: Replace the placeholder.** Overwrite `frontend/app/company/[ticker]/page.tsx` with:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getCompanyOverview } from "@/lib/api";
import type { CompanyOverview } from "@/lib/api";
import { StatisticsGrid } from "@/components/company/StatisticsGrid";
import { PriceChart } from "@/components/company/PriceChart";
import { BullsBears } from "@/components/company/BullsBears";

export default function OverviewPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  const [overview, setOverview] = useState<CompanyOverview | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    setLoading(true);
    getCompanyOverview(ticker)
      .then((o) => alive && setOverview(o))
      .catch(() => alive && setOverview(null))
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, [ticker]);

  return (
    <div className="space-y-4">
      {overview?.sector && (
        <p className="text-xs text-[var(--text-muted)]">
          {overview.sector}
          {overview.industry ? ` · ${overview.industry}` : ""}
        </p>
      )}
      {loading ? (
        <div className="p-6 text-sm text-[var(--text-muted)]">Loading overview…</div>
      ) : (
        <>
          {overview && <PriceChart prices={overview.prices} />}
          {overview && <StatisticsGrid groups={overview.stats} />}
        </>
      )}
      <BullsBears ticker={ticker} />
    </div>
  );
}
```

- [ ] **Step 2: Type-check + lint.**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```
Expected: no new errors; clean lint.

- [ ] **Step 3: Build.**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
Expected: "Compiled successfully", `/company/[ticker]` still listed as a dynamic route.

- [ ] **Step 4: Manual smoke.** With backend (`uvicorn backend.app.main:app --reload` from project root) + frontend (`npm run dev`) running and `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`:
  - Open `/company/AAPL`. Expected: sector·industry caption, a price chart defaulting to 1Y with working range chips (1M…5Y), the 8-group statistics grid populated (em-dashes only for genuinely-absent KPIs), and a Bulls/Bears card (populated if AAPL has a completed run, else "Run pipeline →" CTA).
  - Click a range chip → chart reslices; header price-delta updates.

- [ ] **Step 5: Commit.**

```bash
git add frontend/app/company/[ticker]/page.tsx
git commit -m "feat(company): wire Overview tab — stats grid + price chart + Bulls/Bears"
```

---

## Full-slice verification

- [ ] Backend: `python -m unittest backend.tests.test_company_overview -v` → OK (4 tests).
- [ ] Backend: route wiring prints both `/header` and `/overview`.
- [ ] Frontend: `npx tsc --noEmit` clean (only pre-existing `.mts`), `npm run lint` clean, `npm run build` succeeds.
- [ ] Manual: `/company/<TICKER>` renders price chart + stats grid + Bulls/Bears; range chips work; lens (`?lens=`) changes which run feeds Bulls/Bears.

## Out of scope (fast-follows)
- **Beat/miss earnings widget** (needs `earnings_prints` actuals — separate refresh dependency).
- **Lens-aware discovery-rank badge** on the Overview (triggers a full discovery run).
- **Multi-ticker price overlay**, intraday (1D/5D) ranges, NTM price target / NTM P/E (need analyst price targets + forward EPS aggregation).
