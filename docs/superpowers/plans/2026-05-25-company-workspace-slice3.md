# Company Workspace — Slice 3 Implementation Plan (Financials tab)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Financials tab — Income Statement / Balance Sheet / Cash Flow tables with a granularity toggle (Annual/Quarterly), a period-count window, units (K/M/B), and `% Chg` / Common-Size derivative views — replacing the slice-1 placeholder.

**Architecture:** A new `GET /api/company/{ticker}/financials?period=annual|quarter` endpoint (fmp-only) reshapes the three FMP statements into period-aligned `{lineKey: values[]}` columns. A shared frontend row-spec (`statementRows.ts`) owns the display order, labels, and common-size base per statement. A `StatementTable` renders rows × periods and computes `% Chg` (period-over-period) and common-size (÷ base) client-side; the granularity toggle triggers a refetch, everything else is a client-side transform.

**Tech Stack:** FastAPI + Pydantic + the shared `FMPClient` (existing `get_income_statement`/`get_balance_sheet`/`get_cash_flow`); Next.js 16 client components; stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-05-25-company-workspace-design.md` (Financials = slice 3).

**Scope (decided with the user):** 3 core statements (IS/BS/CF); granularity toggle + period-count window (NOT a draggable slider); units K/M/B; `% Chg` toggle; Common-Size toggle (IS ÷ revenue, BS ÷ totalAssets; disabled on CF). Deferred: Ratios/Segments/Adjusted/Custom sub-tabs, decimal-precision toggle, standardized/as-reported, reverse-dates, deep-linkable per-statement routes.

**Conventions:** backend absolute imports from project root; run from project root with `backend/venv` active; `ticker.upper()` at entry; FMP methods return `tuple[data, Citation]`; frontend `"use client"` + `useParams`. Known pre-existing tsc errors in three `.mts` files — ignore. The service module `backend/app/services/company_snapshot.py` already has a module-level `async def _safe_fetch(coro, default)` and `_as_dict` helper (from slice 2) — reuse them.

**Verified FMP statement field names (live /stable API):**
- income-statement: `revenue, costOfRevenue, grossProfit, researchAndDevelopmentExpenses, sellingGeneralAndAdministrativeExpenses, operatingExpenses, operatingIncome, interestExpense, incomeBeforeTax, incomeTaxExpense, netIncome, ebitda, eps, epsDiluted, weightedAverageShsOutDil`; each row also has `date, period, fiscalYear`.
- balance-sheet-statement: `cashAndCashEquivalents, shortTermInvestments, netReceivables, inventory, totalCurrentAssets, propertyPlantEquipmentNet, goodwillAndIntangibleAssets, totalAssets, accountPayables, shortTermDebt, totalCurrentLiabilities, longTermDebt, totalLiabilities, retainedEarnings, totalStockholdersEquity, totalDebt, netDebt`.
- cash-flow-statement: `netIncome, depreciationAndAmortization, stockBasedCompensation, changeInWorkingCapital, netCashProvidedByOperatingActivities, capitalExpenditure, freeCashFlow, acquisitionsNet, netCashProvidedByInvestingActivities, netDividendsPaid, commonStockRepurchased, netDebtIssuance, netCashProvidedByFinancingActivities, netChangeInCash`.

---

## File Structure

**Backend:**
- Modify `backend/app/services/company_snapshot.py` — add `CompanyFinancials` model + `_period_label`, `_columnize`, `build_company_financials`.
- Modify `backend/app/api/company.py` — add `GET /{ticker}/financials`.
- Create `backend/tests/test_company_financials.py`.

**Frontend:**
- Modify `frontend/lib/api.ts` — `CompanyFinancials` type + `getCompanyFinancials`.
- Create `frontend/components/company/fmtFinancial.ts` — units (K/M/B) + %/× formatter.
- Create `frontend/components/company/statementRows.ts` — ordered row specs per statement.
- Create `frontend/components/company/StatementTable.tsx` — one statement table with %chg / common-size / units.
- Modify `frontend/app/company/[ticker]/financials/page.tsx` — statement sub-tabs + toolbar + table.

---

## Task 1: Backend — financials endpoint

**Files:**
- Modify: `backend/app/services/company_snapshot.py`
- Modify: `backend/app/api/company.py`
- Create: `backend/tests/test_company_financials.py`

- [ ] **Step 1: Write the failing test.** Create `backend/tests/test_company_financials.py`:

```python
"""Unit tests for build_company_financials.

Stubs the FMP client (each method returns tuple[data, Citation]) — no network.
Verifies the three statements are reshaped into period-aligned column dicts,
numeric-only, with period labels from fiscalYear/period, BS/CF aligned by index.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_snapshot import build_company_financials


class _StubFMP:
    def __init__(self, inc, bal, cf):
        self._inc, self._bal, self._cf = inc, bal, cf

    async def get_income_statement(self, ticker, period="annual", limit=4):
        return self._inc, None

    async def get_balance_sheet(self, ticker, period="annual", limit=4):
        return self._bal, None

    async def get_cash_flow(self, ticker, period="annual", limit=4):
        return self._cf, None


def _stub():
    return _StubFMP(
        inc=[
            {"date": "2025-06-28", "period": "Q3", "fiscalYear": 2025, "symbol": "AAPL",
             "revenue": 100.0, "grossProfit": 46.0, "netIncome": 25.0},
            {"date": "2025-03-29", "period": "Q2", "fiscalYear": 2025, "symbol": "AAPL",
             "revenue": 90.0, "grossProfit": 40.0, "netIncome": 20.0},
        ],
        bal=[
            {"date": "2025-06-28", "period": "Q3", "fiscalYear": 2025, "totalAssets": 350.0},
            {"date": "2025-03-29", "period": "Q2", "fiscalYear": 2025, "totalAssets": 340.0},
        ],
        cf=[
            {"date": "2025-06-28", "period": "Q3", "fiscalYear": 2025, "freeCashFlow": 22.0},
            {"date": "2025-03-29", "period": "Q2", "fiscalYear": 2025, "freeCashFlow": 18.0},
        ],
    )


class BuildCompanyFinancialsTest(unittest.IsolatedAsyncioTestCase):
    async def test_quarter_period_labels_and_alignment(self):
        fin = await build_company_financials(_stub(), "aapl", period="quarter")
        self.assertEqual(fin.ticker, "AAPL")
        self.assertEqual(fin.period, "quarter")
        self.assertEqual(fin.periods, ["Q3 2025", "Q2 2025"])
        # income columns aligned newest-first
        self.assertEqual(fin.income["revenue"], [100.0, 90.0])
        self.assertEqual(fin.income["netIncome"], [25.0, 20.0])
        # balance + cashflow aligned by index to the same periods
        self.assertEqual(fin.balance["totalAssets"], [350.0, 340.0])
        self.assertEqual(fin.cashflow["freeCashFlow"], [22.0, 18.0])

    async def test_numeric_only_no_string_keys(self):
        fin = await build_company_financials(_stub(), "AAPL", period="quarter")
        self.assertNotIn("symbol", fin.income)
        self.assertNotIn("date", fin.income)
        self.assertNotIn("period", fin.income)

    async def test_annual_labels_use_fiscal_year(self):
        fin = await build_company_financials(_stub(), "AAPL", period="annual")
        self.assertEqual(fin.periods, ["2025", "2025"])

    async def test_empty_statements_degrade(self):
        fin = await build_company_financials(_StubFMP([], [], []), "X", period="quarter")
        self.assertEqual(fin.periods, [])
        self.assertEqual(fin.income, {})
        self.assertEqual(fin.balance, {})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it, confirm it FAILS** (ImportError for `build_company_financials`).

```bash
source backend/venv/bin/activate
python -m unittest backend.tests.test_company_financials -v
```

- [ ] **Step 3: Implement in `backend/app/services/company_snapshot.py`.** Append after the slice-2 code (it already imports `asyncio`, `Optional`, `BaseModel`, and defines `_safe_fetch`):

```python
class CompanyFinancials(BaseModel):
    ticker: str
    period: str
    periods: list[str]
    income: dict[str, list[Optional[float]]]
    balance: dict[str, list[Optional[float]]]
    cashflow: dict[str, list[Optional[float]]]


def _period_label(row: dict, period: str) -> str:
    fy = row.get("fiscalYear")
    if fy is None:
        fy = str(row.get("date", ""))[:4]
    if period == "annual":
        return str(fy)
    p = row.get("period", "")
    return f"{p} {fy}".strip()


def _columnize(rows: list, n: int) -> dict[str, list[Optional[float]]]:
    """Reshape up to n statement rows (newest-first) into {key: [values]} columns,
    aligned by index, numeric values only (bool excluded). Trailing slots are None
    when a statement returns fewer periods than the income statement."""
    out: dict[str, list[Optional[float]]] = {}
    for i in range(min(n, len(rows))):
        row = rows[i]
        if not isinstance(row, dict):
            continue
        for k, v in row.items():
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                out.setdefault(k, [None] * n)[i] = float(v)
    return out


async def build_company_financials(
    fmp, ticker: str, period: str = "quarter", limit: int = 12
) -> CompanyFinancials:
    """Reshape the three FMP statements into period-aligned column dicts (fmp-only).

    Periods are derived from the income statement (newest-first, as FMP returns);
    balance sheet and cash flow are aligned to those periods by index. Only numeric
    fields are kept. The frontend row-spec selects/orders/labels the keys.
    """
    ticker = ticker.upper()
    inc, bal, cf = await asyncio.gather(
        _safe_fetch(fmp.get_income_statement(ticker, period=period, limit=limit), []),
        _safe_fetch(fmp.get_balance_sheet(ticker, period=period, limit=limit), []),
        _safe_fetch(fmp.get_cash_flow(ticker, period=period, limit=limit), []),
    )
    inc = inc if isinstance(inc, list) else []
    bal = bal if isinstance(bal, list) else []
    cf = cf if isinstance(cf, list) else []

    periods = [_period_label(r, period) for r in inc if isinstance(r, dict)]
    n = len(periods)

    return CompanyFinancials(
        ticker=ticker,
        period=period,
        periods=periods,
        income=_columnize(inc, n),
        balance=_columnize(bal, n),
        cashflow=_columnize(cf, n),
    )
```

- [ ] **Step 4: Run the test, confirm 4 PASS.**

- [ ] **Step 5: Add the endpoint in `backend/app/api/company.py`.** Extend the import and add the route:

```python
from backend.app.services.company_snapshot import (
    CompanyFinancials,
    CompanyHeader,
    CompanyOverview,
    build_company_financials,
    build_company_header,
    build_company_overview,
)
```
Add after `get_company_overview`:
```python
@router.get("/{ticker}/financials", response_model=CompanyFinancials)
async def get_company_financials(
    ticker: str, request: Request, period: str = "quarter"
) -> CompanyFinancials:
    period = "annual" if period == "annual" else "quarter"
    return await build_company_financials(request.app.state.fmp, ticker, period=period)
```

- [ ] **Step 6: Verify route wiring.**

```bash
python -c "from backend.app.main import app; print(sorted(r.path for r in app.routes if 'company' in r.path))"
```
Expected includes `/api/company/{ticker}/financials`.

- [ ] **Step 7: Commit.**

```bash
git add backend/app/services/company_snapshot.py backend/app/api/company.py backend/tests/test_company_financials.py
git commit -m "feat(company): financials endpoint — period-aligned IS/BS/CF columns"
```

---

## Task 2: Frontend — financials API client

**Files:** Modify `frontend/lib/api.ts` (Company workspace section).

- [ ] **Step 1: Add type + fetch fn** after `getCompanyOverview`:

```ts
export interface CompanyFinancials {
  ticker: string;
  period: "annual" | "quarter";
  periods: string[];
  income: Record<string, (number | null)[]>;
  balance: Record<string, (number | null)[]>;
  cashflow: Record<string, (number | null)[]>;
}

export async function getCompanyFinancials(
  ticker: string,
  period: "annual" | "quarter",
): Promise<CompanyFinancials> {
  return apiFetch<CompanyFinancials>(
    `/api/company/${encodeURIComponent(ticker)}/financials?period=${period}`,
  );
}
```

- [ ] **Step 2: Type-check.** `cd frontend && npx tsc --noEmit` → no new errors.

- [ ] **Step 3: Commit.**

```bash
git add frontend/lib/api.ts
git commit -m "feat(company): typed getCompanyFinancials client"
```

---

## Task 3: Frontend — fmtFinancial + statementRows

**Files:**
- Create: `frontend/components/company/fmtFinancial.ts`
- Create: `frontend/components/company/statementRows.ts`

- [ ] **Step 1: `frontend/components/company/fmtFinancial.ts`:**

```ts
export type Unit = "K" | "M" | "B";

/** Format an absolute money value scaled to the chosen unit. Null → em-dash. */
export function fmtMoney(value: number | null, unit: Unit): string {
  if (value == null || Number.isNaN(value)) return "—";
  const div = unit === "B" ? 1e9 : unit === "M" ? 1e6 : 1e3;
  const scaled = value / div;
  return scaled.toLocaleString("en-US", { maximumFractionDigits: scaled >= 100 || scaled <= -100 ? 0 : 1 });
}

/** Format a percentage (value is already a ratio, e.g. 0.46 → "46.0%"). Null → em-dash. */
export function fmtPct(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

/** Per-share / raw numeric value (EPS etc.). Null → em-dash. */
export function fmtNum(value: number | null): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toFixed(2);
}
```

- [ ] **Step 2: `frontend/components/company/statementRows.ts`** (ordered display rows per statement, using the verified FMP keys; `kind` drives formatting; `baseKey` is the common-size denominator):

```ts
export interface StatementRow {
  label: string;
  key: string;
  kind: "money" | "num"; // money → unit-scaled + common-size eligible; num → raw (EPS, shares)
  bold?: boolean;
}

export interface StatementSpec {
  rows: StatementRow[];
  baseKey: string | null; // common-size denominator; null disables common-size
}

export const INCOME_SPEC: StatementSpec = {
  baseKey: "revenue",
  rows: [
    { label: "Revenue", key: "revenue", kind: "money", bold: true },
    { label: "Cost of Revenue", key: "costOfRevenue", kind: "money" },
    { label: "Gross Profit", key: "grossProfit", kind: "money", bold: true },
    { label: "R&D", key: "researchAndDevelopmentExpenses", kind: "money" },
    { label: "SG&A", key: "sellingGeneralAndAdministrativeExpenses", kind: "money" },
    { label: "Operating Expenses", key: "operatingExpenses", kind: "money" },
    { label: "Operating Income", key: "operatingIncome", kind: "money", bold: true },
    { label: "Interest Expense", key: "interestExpense", kind: "money" },
    { label: "Income Before Tax", key: "incomeBeforeTax", kind: "money" },
    { label: "Income Tax", key: "incomeTaxExpense", kind: "money" },
    { label: "Net Income", key: "netIncome", kind: "money", bold: true },
    { label: "EBITDA", key: "ebitda", kind: "money" },
    { label: "EPS", key: "eps", kind: "num" },
    { label: "EPS (Diluted)", key: "epsDiluted", kind: "num" },
    { label: "Shares (Diluted)", key: "weightedAverageShsOutDil", kind: "money" },
  ],
};

export const BALANCE_SPEC: StatementSpec = {
  baseKey: "totalAssets",
  rows: [
    { label: "Cash & Equivalents", key: "cashAndCashEquivalents", kind: "money" },
    { label: "Short-Term Investments", key: "shortTermInvestments", kind: "money" },
    { label: "Receivables", key: "netReceivables", kind: "money" },
    { label: "Inventory", key: "inventory", kind: "money" },
    { label: "Total Current Assets", key: "totalCurrentAssets", kind: "money", bold: true },
    { label: "PP&E (net)", key: "propertyPlantEquipmentNet", kind: "money" },
    { label: "Goodwill & Intangibles", key: "goodwillAndIntangibleAssets", kind: "money" },
    { label: "Total Assets", key: "totalAssets", kind: "money", bold: true },
    { label: "Accounts Payable", key: "accountPayables", kind: "money" },
    { label: "Short-Term Debt", key: "shortTermDebt", kind: "money" },
    { label: "Total Current Liabilities", key: "totalCurrentLiabilities", kind: "money", bold: true },
    { label: "Long-Term Debt", key: "longTermDebt", kind: "money" },
    { label: "Total Liabilities", key: "totalLiabilities", kind: "money", bold: true },
    { label: "Retained Earnings", key: "retainedEarnings", kind: "money" },
    { label: "Total Equity", key: "totalStockholdersEquity", kind: "money", bold: true },
    { label: "Total Debt", key: "totalDebt", kind: "money" },
    { label: "Net Debt", key: "netDebt", kind: "money" },
  ],
};

export const CASHFLOW_SPEC: StatementSpec = {
  baseKey: null,
  rows: [
    { label: "Net Income", key: "netIncome", kind: "money" },
    { label: "D&A", key: "depreciationAndAmortization", kind: "money" },
    { label: "Stock-Based Comp", key: "stockBasedCompensation", kind: "money" },
    { label: "Change in Working Capital", key: "changeInWorkingCapital", kind: "money" },
    { label: "Operating Cash Flow", key: "netCashProvidedByOperatingActivities", kind: "money", bold: true },
    { label: "CapEx", key: "capitalExpenditure", kind: "money" },
    { label: "Free Cash Flow", key: "freeCashFlow", kind: "money", bold: true },
    { label: "Acquisitions", key: "acquisitionsNet", kind: "money" },
    { label: "Investing Cash Flow", key: "netCashProvidedByInvestingActivities", kind: "money", bold: true },
    { label: "Dividends Paid", key: "netDividendsPaid", kind: "money" },
    { label: "Stock Repurchased", key: "commonStockRepurchased", kind: "money" },
    { label: "Debt Issuance (net)", key: "netDebtIssuance", kind: "money" },
    { label: "Financing Cash Flow", key: "netCashProvidedByFinancingActivities", kind: "money", bold: true },
    { label: "Net Change in Cash", key: "netChangeInCash", kind: "money", bold: true },
  ],
};
```

- [ ] **Step 2 (verify): Type-check + lint.** `cd frontend && npx tsc --noEmit && npm run lint` → clean.

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/company/fmtFinancial.ts frontend/components/company/statementRows.ts
git commit -m "feat(company): financial statement row specs + value formatters"
```

---

## Task 4: Frontend — StatementTable

**Files:** Create `frontend/components/company/StatementTable.tsx`.

Renders one statement: a sticky left label column + one column per period. Supports units (K/M/B), a `% Chg` toggle (interleaves an italic period-over-period change row under each money row), and a Common-Size toggle (shows each money cell as % of `spec.baseKey` for that period; no-op when `baseKey` is null). Periods are newest-first (index 0 = newest), so `%chg[i] = (v[i]-v[i+1])/|v[i+1]|`.

- [ ] **Step 1: `frontend/components/company/StatementTable.tsx`:**

```tsx
import type { StatementSpec } from "./statementRows";
import { fmtMoney, fmtNum, fmtPct, type Unit } from "./fmtFinancial";

interface Props {
  periods: string[];
  data: Record<string, (number | null)[]>;
  spec: StatementSpec;
  unit: Unit;
  pctChg: boolean;
  commonSize: boolean;
}

function pctChange(curr: number | null, prev: number | null): number | null {
  if (curr == null || prev == null || prev === 0) return null;
  return (curr - prev) / Math.abs(prev);
}

export function StatementTable({ periods, data, spec, unit, pctChg, commonSize }: Props) {
  if (periods.length === 0) {
    return <div className="p-6 text-sm text-[var(--text-muted)]">No statement data available.</div>;
  }
  const base = spec.baseKey ? data[spec.baseKey] : null;
  const useCommonSize = commonSize && !!base;

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] bg-[var(--surface)]">
            <th className="sticky left-0 z-10 bg-[var(--surface)] px-3 py-2 text-left text-xs font-semibold text-[var(--text-muted)]">
              {useCommonSize ? "% of base" : `Units: ${unit}`}
            </th>
            {periods.map((p) => (
              <th key={p} className="px-3 py-2 text-right text-xs font-semibold text-[var(--text-muted)] whitespace-nowrap">
                {p}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {spec.rows.map((row) => {
            const values = data[row.key] ?? [];
            return (
              <RowGroup
                key={row.key}
                label={row.label}
                bold={row.bold}
                kind={row.kind}
                values={values}
                periodsLen={periods.length}
                unit={unit}
                pctChg={pctChg}
                useCommonSize={useCommonSize && row.kind === "money"}
                base={base}
              />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RowGroup(props: {
  label: string;
  bold?: boolean;
  kind: "money" | "num";
  values: (number | null)[];
  periodsLen: number;
  unit: Unit;
  pctChg: boolean;
  useCommonSize: boolean;
  base: (number | null)[] | null;
}) {
  const { label, bold, kind, values, periodsLen, unit, pctChg, useCommonSize, base } = props;
  const idx = Array.from({ length: periodsLen }, (_, i) => i);

  function cell(i: number): string {
    const v = values[i] ?? null;
    if (useCommonSize && base) {
      const b = base[i] ?? null;
      if (v == null || b == null || b === 0) return "—";
      return fmtPct(v / b);
    }
    return kind === "money" ? fmtMoney(v, unit) : fmtNum(v);
  }

  return (
    <>
      <tr className="border-b border-[var(--border)]/40 hover:bg-[var(--surface-alt)]">
        <td className={`sticky left-0 z-10 bg-[var(--surface)] px-3 py-1.5 text-left ${bold ? "font-semibold text-[var(--text)]" : "text-[var(--text-muted)]"}`}>
          {label}
        </td>
        {idx.map((i) => (
          <td key={i} className={`px-3 py-1.5 text-right font-mono tabular-nums ${bold ? "font-semibold text-[var(--text)]" : "text-[var(--text)]"}`}>
            {cell(i)}
          </td>
        ))}
      </tr>
      {pctChg && kind === "money" && !useCommonSize && (
        <tr className="border-b border-[var(--border)]/40 text-[var(--text-muted)]">
          <td className="sticky left-0 z-10 bg-[var(--surface)] px-3 py-1 pl-6 text-left text-xs italic">% Chg</td>
          {idx.map((i) => {
            const chg = pctChange(values[i] ?? null, values[i + 1] ?? null);
            return (
              <td key={i} className="px-3 py-1 text-right font-mono text-xs italic tabular-nums">
                {chg == null ? "—" : `${chg >= 0 ? "+" : ""}${(chg * 100).toFixed(1)}%`}
              </td>
            );
          })}
        </tr>
      )}
    </>
  );
}
```

- [ ] **Step 2: Type-check + lint.** `cd frontend && npx tsc --noEmit && npm run lint` → clean.

- [ ] **Step 3: Commit.**

```bash
git add frontend/components/company/StatementTable.tsx
git commit -m "feat(company): StatementTable with %chg, common-size, unit scaling"
```

---

## Task 5: Frontend — wire the Financials page

**Files:** Modify `frontend/app/company/[ticker]/financials/page.tsx` (slice-1 placeholder).

Statement sub-tabs (Income / Balance / Cash Flow) + a toolbar (granularity Annual/Quarterly, units K/M/B, `% Chg` toggle, Common-Size toggle) above the table. Granularity changes refetch; the rest are client-side. Common-Size toggle is disabled when the active statement's `baseKey` is null (Cash Flow).

- [ ] **Step 1: Overwrite `frontend/app/company/[ticker]/financials/page.tsx`:**

```tsx
"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getCompanyFinancials } from "@/lib/api";
import type { CompanyFinancials } from "@/lib/api";
import { StatementTable } from "@/components/company/StatementTable";
import { INCOME_SPEC, BALANCE_SPEC, CASHFLOW_SPEC } from "@/components/company/statementRows";
import type { Unit } from "@/components/company/fmtFinancial";

type StmtKey = "income" | "balance" | "cashflow";
const STATEMENTS: { key: StmtKey; label: string }[] = [
  { key: "income", label: "Income Statement" },
  { key: "balance", label: "Balance Sheet" },
  { key: "cashflow", label: "Cash Flow" },
];
const SPECS = { income: INCOME_SPEC, balance: BALANCE_SPEC, cashflow: CASHFLOW_SPEC };

export default function FinancialsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();

  const [period, setPeriod] = useState<"annual" | "quarter">("quarter");
  const [stmt, setStmt] = useState<StmtKey>("income");
  const [unit, setUnit] = useState<Unit>("M");
  const [pctChg, setPctChg] = useState(false);
  const [commonSize, setCommonSize] = useState(false);
  const [fin, setFin] = useState<CompanyFinancials | null | undefined>(null);

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    setFin(null);
    getCompanyFinancials(ticker, period)
      .then((f) => { if (alive) setFin(f); })
      .catch(() => { if (alive) setFin(undefined); });
    return () => { alive = false; };
  }, [ticker, period]);

  const spec = SPECS[stmt];
  const commonSizeDisabled = spec.baseKey == null;

  return (
    <div className="space-y-3">
      {/* Statement sub-tabs */}
      <div className="flex gap-1 border-b border-[var(--border)]">
        {STATEMENTS.map((s) => (
          <button
            key={s.key}
            onClick={() => setStmt(s.key)}
            className={`px-3 py-2 text-sm transition-colors ${
              stmt === s.key
                ? "border-b-2 border-[var(--primary)] font-medium text-[var(--text)]"
                : "text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <Toggle options={[["quarter", "Quarterly"], ["annual", "Annual"]]} value={period} onChange={(v) => setPeriod(v as "annual" | "quarter")} />
        <Toggle options={[["K", "K"], ["M", "M"], ["B", "B"]]} value={unit} onChange={(v) => setUnit(v as Unit)} />
        <label className="flex items-center gap-1 text-[var(--text-muted)]">
          <input type="checkbox" checked={pctChg} onChange={(e) => setPctChg(e.target.checked)} /> % Chg
        </label>
        <label className={`flex items-center gap-1 ${commonSizeDisabled ? "opacity-40" : "text-[var(--text-muted)]"}`}>
          <input type="checkbox" checked={commonSize && !commonSizeDisabled} disabled={commonSizeDisabled} onChange={(e) => setCommonSize(e.target.checked)} /> Common Size
        </label>
      </div>

      {/* Table */}
      {fin === null ? (
        <div className="p-6 text-sm text-[var(--text-muted)]">Loading financials…</div>
      ) : fin === undefined ? (
        <div className="p-6 text-sm text-[var(--text-muted)]">Could not load financials.</div>
      ) : (
        <StatementTable
          periods={fin.periods}
          data={fin[stmt]}
          spec={spec}
          unit={unit}
          pctChg={pctChg}
          commonSize={commonSize && !commonSizeDisabled}
        />
      )}
    </div>
  );
}

function Toggle({ options, value, onChange }: { options: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex gap-0.5 rounded-md border border-[var(--border)] p-0.5">
      {options.map(([val, label]) => (
        <button
          key={val}
          onClick={() => onChange(val)}
          className={`rounded px-2 py-0.5 transition-colors ${
            value === val ? "bg-[var(--accent-bg)] font-medium text-[var(--text)]" : "text-[var(--text-muted)] hover:text-[var(--text)]"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Type-check + lint + build.**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build 2>&1 | tail -6
```
Expected: zero new tsc errors; clean lint; "Compiled successfully"; `/company/[ticker]/financials` listed.

- [ ] **Step 3: Manual smoke.** Backend + frontend running, `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`. Open `/company/AAPL/financials`:
  - Three sub-tabs switch statements; default Income Statement, Quarterly, units M.
  - Toggling Annual refetches (columns change to fiscal years).
  - `% Chg` interleaves italic period-over-period rows under money rows.
  - Common Size shows % of revenue (Income) / total assets (Balance); is disabled (greyed) on Cash Flow.
  - Units K/M/B rescale the absolute figures.

- [ ] **Step 4: Commit.**

```bash
git add frontend/app/company/[ticker]/financials/page.tsx
git commit -m "feat(company): wire Financials tab — statement sub-tabs + toolbar + tables"
```

---

## Full-slice verification
- [ ] Backend: `python -m unittest backend.tests.test_company_financials -v` → 4 OK.
- [ ] Route wiring lists `/api/company/{ticker}/financials`.
- [ ] Frontend: `tsc` clean (only pre-existing `.mts`), `lint` clean, `next build` succeeds.
- [ ] Manual: statements/toggles/granularity all behave per Task 5 Step 3.

## Out of scope (fast-follows)
- Ratios / Segments & KPIs / Adjusted / Custom-Metrics sub-tabs.
- Draggable period slider, decimal-precision toggle, standardized vs as-reported, reverse-dates, deep-linkable per-statement routes.
- Row drill-down chevrons / add-to-chart checkboxes.
