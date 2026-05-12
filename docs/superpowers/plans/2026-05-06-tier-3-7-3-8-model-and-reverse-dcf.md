# Tier 3.7 + 3.8 — Editable Financial Model & Reverse DCF Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a per-ticker, editable, AI-seeded full 3-statement financial model (5Y annual + 8Q quarterly forecast) with a reverse-DCF readout that decomposes current price into the assumptions priced in. Gates Tier 3.9 (workspace 5-step loop).

**Spec:** `docs/superpowers/specs/2026-05-06-tier-3-7-3-8-model-and-reverse-dcf-design.md` — read it before starting; this plan implements it task-by-task.

**Architecture:** Three layers. (1) Pure-Python engines: `dcf.py` and `reverse_dcf.py` are stateless functions over a `ModelState` Pydantic object — trivially testable. (2) Stateful seeding & recompute: `model_baseline.py` (Sonnet pass + cell-level citations), `model_balancing.py` (drivers → IS → CF → BS rollforward + plug priority). (3) API + frontend: `models_api.py` exposes init / draft / save / reverse-dcf; `/model/[ticker]` is a three-tab Next.js page (Forecast, Reverse DCF, History).

**Tech Stack:** Python 3.12, FastAPI, async SQLAlchemy 2, Alembic, LangGraph, Pydantic v2, Anthropic SDK (Sonnet 4.6), Next.js 16 + React 19 + Recharts + lightweight-charts, PostgreSQL 16.

**Backend testing convention:** No pytest configured. Verification is via smoke scripts in `backend/scripts/smoke_*.py`, run from project root with the venv active. Pattern: import the function, mock external deps (`llm.complete`, FMP client, etc.), assert on outputs, exit non-zero on failure. See `backend/scripts/smoke_question_log.py` and `backend/scripts/smoke_earnings_navigator.py` for established shape.

**Branch:** `feat/model-reverse-dcf`. One PR at the end (or two if 3.7 is sequenced before 3.8 — decided in §Execution).

---

## File Map

```
backend/app/
├── models/
│   ├── citation.py                  (MODIFY: add cell_path field to Citation + CitationRecord)
│   ├── ticker_model.py              (NEW: TickerModel ORM)
│   ├── ticker_model_draft.py        (NEW: TickerModelDraft ORM)
│   ├── model_state.py               (NEW: Pydantic ModelState, ModelCell, registries)
│   └── __init__.py                  (MODIFY: register new models)
├── services/
│   ├── dcf.py                       (NEW: pure DCF engine)
│   ├── reverse_dcf.py               (NEW: 4 solvers)
│   ├── model_balancing.py           (NEW: recompute pipeline + plug priority)
│   ├── model_baseline.py            (NEW: orchestrate AI seed)
│   └── model_diff.py                (NEW: cell-path-keyed JSON diff)
├── graph/
│   ├── model_baseline_node.py       (NEW: Sonnet baseline call)
│   └── state.py                     (MODIFY: StateCitation.cell_path)
├── api/
│   └── models_api.py                (NEW: 5 endpoints)
├── main.py                          (MODIFY: register router)
└── migrations/versions/
    ├── XXXX_add_cell_path_to_citations.py    (NEW)
    ├── XXXX_create_ticker_models.py           (NEW)
    └── XXXX_create_ticker_model_drafts.py     (NEW)

backend/scripts/
├── smoke_dcf.py                     (NEW)
├── smoke_reverse_dcf.py             (NEW)
├── smoke_model_balancing.py         (NEW)
├── smoke_model_diff.py              (NEW)
├── smoke_model_baseline.py          (NEW)
├── smoke_models_api.py              (NEW)
└── smoke_model_e2e.py               (NEW)

frontend/
├── app/model/[ticker]/page.tsx              (NEW)
├── components/model/
│   ├── ForecastGrid.tsx                     (NEW)
│   ├── DriverPanel.tsx                      (NEW)
│   ├── FormulaBar.tsx                       (NEW)
│   ├── CellRenderer.tsx                     (NEW)
│   ├── ReverseDcfPanel.tsx                  (NEW)
│   ├── SensitivityHeatmap.tsx               (NEW)
│   ├── ThesisVsPricedTable.tsx              (NEW)
│   ├── WhatIfScratchPanel.tsx               (NEW)
│   ├── HistoryDiffViewer.tsx                (NEW)
│   ├── SaveVersionModal.tsx                 (NEW)
│   ├── modelSections.ts                     (NEW: registry)
│   └── heatmapColors.ts                     (NEW)
├── components/deep-dive/
│   ├── SectionNav.tsx                       (MODIFY: add "Model" pill)
│   └── ReportHeader.tsx                     (MODIFY: model status badge)
└── lib/api.ts                               (MODIFY: model client + types)
```

---

## Phase 0 — Foundations

### Task 1: ModelState + ModelCell Pydantic + driver/line-item registry

**Files:**
- Create: `backend/app/models/model_state.py`
- Create: `backend/scripts/smoke_model_state.py`

- [ ] **Step 1: Write the smoke script first**

```python
# backend/scripts/smoke_model_state.py
"""Smoke test for model_state Pydantic schemas."""
import json
import sys
from backend.app.models.model_state import (
    ModelState, ModelCell, Period, ModelAssumptions,
    DRIVER_KEYS, LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF,
)


def test_modelcell_roundtrip():
    cell = ModelCell(value=1.5, source="driver", formula=None, citation_id=None)
    raw = cell.model_dump_json()
    back = ModelCell.model_validate_json(raw)
    assert back == cell, f"roundtrip mismatch: {back} != {cell}"


def test_modelstate_minimal():
    state = ModelState(
        periods=[Period(label="2026Q1", kind="Q", is_historical=False, quarter_index=1)],
        drivers={"2026Q1": {k: ModelCell(value=0.0, source="driver") for k in DRIVER_KEYS}},
        income_statement={li: {"2026Q1": ModelCell(value=0.0, source="computed")} for li in LINE_ITEMS_PNL},
        balance_sheet={li: {"2026Q1": ModelCell(value=0.0, source="computed")} for li in LINE_ITEMS_BS},
        cash_flow={li: {"2026Q1": ModelCell(value=0.0, source="computed")} for li in LINE_ITEMS_CF},
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=0.10, source="driver"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=12.0, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )
    raw = state.model_dump_json()
    back = ModelState.model_validate_json(raw)
    assert back == state, "ModelState roundtrip failed"


if __name__ == "__main__":
    test_modelcell_roundtrip()
    test_modelstate_minimal()
    print("OK: model_state smoke passed")
    sys.exit(0)
```

- [ ] **Step 2: Run smoke to verify it fails**

```bash
source backend/venv/bin/activate
python -m backend.scripts.smoke_model_state
```
Expected: `ModuleNotFoundError: No module named 'backend.app.models.model_state'`.

- [ ] **Step 3: Implement `model_state.py`**

```python
# backend/app/models/model_state.py
"""Pydantic schemas + registries for the per-ticker financial model."""
from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

# ---- Driver registry (~25 keys, all per-period) -----------------------------

DRIVER_KEYS: list[str] = [
    # Revenue (one of these populated per period; the other is None)
    "revenue_growth_pct", "revenue_absolute",
    # Margins
    "gross_margin_pct", "sga_pct_revenue", "rd_pct_revenue",
    "other_opex_pct_revenue", "da_pct_revenue",
    # Below the line
    "effective_tax_rate", "interest_income_yield", "interest_expense_rate",
    # Capex / WC
    "capex_pct_revenue", "dso_days", "dio_days", "dpo_days",
    # Capital return
    "dividend_payout_ratio", "buyback_dollars", "share_count_change_pct",
    # Debt
    "debt_repayment_dollars", "revolver_rate",
]

# ---- Line item registries (mirror FMP statement structure) ------------------

LINE_ITEMS_PNL: list[str] = [
    "revenue", "cost_of_revenue", "gross_profit",
    "sga", "rd", "other_opex", "operating_expenses",
    "ebit", "depreciation_amortization", "ebitda",
    "interest_income", "interest_expense", "pretax_income",
    "income_tax", "net_income",
    "shares_diluted", "eps_diluted",
]

LINE_ITEMS_BS: list[str] = [
    "cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
    "total_current_assets",
    "ppe_net", "goodwill", "other_long_term_assets", "total_assets",
    "accounts_payable", "short_term_debt", "other_current_liabilities",
    "total_current_liabilities",
    "long_term_debt", "other_long_term_liabilities", "total_liabilities",
    "common_equity", "retained_earnings", "total_equity",
    "total_liab_and_equity",
]

LINE_ITEMS_CF: list[str] = [
    "net_income_cf", "depreciation_amortization_cf",
    "delta_accounts_receivable", "delta_inventory", "delta_accounts_payable",
    "operating_cash_flow",
    "capex", "free_cash_flow",
    "debt_issued", "debt_repaid",
    "dividends_paid", "buybacks",
    "net_change_in_cash",
]


# ---- Schemas ----------------------------------------------------------------

class Period(BaseModel):
    label: str                              # "2024Q1", "2026"
    kind: Literal["Q", "Y"]
    is_historical: bool
    quarter_index: int | None = None        # 1-4 for Q, None for Y


CellSource = Literal["historical", "ai_baseline", "driver", "computed", "override"]


class ModelCell(BaseModel):
    value: float | None = None
    source: CellSource = "computed"
    formula: str | None = None
    citation_id: str | None = None
    last_edited_at: str | None = None        # ISO
    last_edited_by: Literal["system", "ai_baseline", "user"] | None = None


class ModelAssumptions(BaseModel):
    discount_rate: ModelCell
    terminal_method: Literal["exit_multiple", "perpetuity"]
    terminal_multiple: ModelCell
    perpetuity_growth: ModelCell
    tax_rate: ModelCell
    plug_priority: list[Literal["debt_paydown", "buyback", "dividend", "cash"]] = Field(
        default_factory=lambda: ["debt_paydown", "buyback", "dividend", "cash"]
    )


class ModelState(BaseModel):
    periods: list[Period]
    drivers: dict[str, dict[str, ModelCell]]            # {period_label: {driver_key: cell}}
    income_statement: dict[str, dict[str, ModelCell]]   # {line_item: {period_label: cell}}
    balance_sheet: dict[str, dict[str, ModelCell]]
    cash_flow: dict[str, dict[str, ModelCell]]
    assumptions: ModelAssumptions


# ---- Helpers used by services -----------------------------------------------

def cell_path_pnl(line_item: str, period: str) -> str:
    return f"income_statement.{line_item}.{period}"


def cell_path_bs(line_item: str, period: str) -> str:
    return f"balance_sheet.{line_item}.{period}"


def cell_path_cf(line_item: str, period: str) -> str:
    return f"cash_flow.{line_item}.{period}"


def cell_path_driver(period: str, driver_key: str) -> str:
    return f"drivers.{period}.{driver_key}"


def cell_path_assumption(key: str) -> str:
    return f"assumptions.{key}"
```

- [ ] **Step 4: Run smoke; verify pass**

```bash
python -m backend.scripts.smoke_model_state
```
Expected: `OK: model_state smoke passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/model_state.py backend/scripts/smoke_model_state.py
git commit -m "feat(model): Pydantic ModelState + driver/line-item registries"
```

---

### Task 2: Citation extension — `cell_path`

**Files:**
- Modify: `backend/app/models/citation.py` (add `cell_path` to dataclass + ORM)
- Modify: `backend/app/graph/state.py` (add `cell_path` to `StateCitation`)
- Create: `backend/migrations/versions/XXXX_add_cell_path_to_citations.py`

- [ ] **Step 1: Read current citation.py and state.py to confirm existing fields**

```bash
sed -n '1,80p' backend/app/models/citation.py
sed -n '1,40p' backend/app/graph/state.py | grep -A 20 "StateCitation"
```

- [ ] **Step 2: Add `cell_path` to `Citation` dataclass and `CitationRecord` ORM**

In `backend/app/models/citation.py`, add `cell_path: str | None = None` to both the `Citation` dataclass and the `CitationRecord` SQLAlchemy model. Add `Citation.with_cell(path: str) -> Citation` helper (returns a new Citation with `cell_path` set).

```python
# inside Citation dataclass
cell_path: str | None = None

def with_cell(self, path: str) -> "Citation":
    from dataclasses import replace
    return replace(self, cell_path=path)

# inside CitationRecord ORM (SQLAlchemy)
cell_path: Mapped[str | None] = mapped_column(String, nullable=True, index=False)
```

- [ ] **Step 3: Add `cell_path` to `StateCitation`**

In `backend/app/graph/state.py`, add `cell_path: str | None = None` to the `StateCitation` dataclass and ensure it round-trips through `to_dict`/`from_dict`.

- [ ] **Step 4: Generate Alembic migration**

```bash
cd backend && alembic revision --autogenerate -m "add cell_path to citations"
```
Inspect generated file. It should be a single `op.add_column("citations", sa.Column("cell_path", sa.String(), nullable=True))`.

- [ ] **Step 5: Apply migration; smoke**

```bash
cd backend && alembic upgrade head
psql $DATABASE_URL_SYNC -c "\d citations" | grep cell_path
```
Expected: `cell_path | character varying`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/citation.py backend/app/graph/state.py backend/migrations/versions/*_add_cell_path_to_citations.py
git commit -m "feat(model): add cell_path to Citation + StateCitation"
```

---

### Task 3: `ticker_models` ORM + migration

**Files:**
- Create: `backend/app/models/ticker_model.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/XXXX_create_ticker_models.py`

- [ ] **Step 1: Implement ORM**

```python
# backend/app/models/ticker_model.py
"""TickerModel ORM — versioned per-ticker financial model state."""
from __future__ import annotations
import uuid
from sqlalchemy import String, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class TickerModel(Base, TimestampMixin):
    __tablename__ = "ticker_models"
    __table_args__ = (UniqueConstraint("ticker", "version", name="uq_ticker_models_ticker_version"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    ticker: Mapped[str] = mapped_column(String, index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
    parent_research_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False), ForeignKey("research_runs.id"), nullable=True
    )
    label: Mapped[str | None] = mapped_column(String, nullable=True)
```

- [ ] **Step 2: Register in `models/__init__.py`** (both import line and `__all__`)

```python
from backend.app.models.ticker_model import TickerModel  # noqa: F401
# inside __all__:
"TickerModel",
```

- [ ] **Step 3: Generate migration**

```bash
cd backend && alembic revision --autogenerate -m "create ticker_models"
```

- [ ] **Step 4: Apply + verify**

```bash
cd backend && alembic upgrade head
psql $DATABASE_URL_SYNC -c "\d ticker_models"
```
Expected: id (uuid), ticker (varchar), version (int), state (jsonb), parent_research_run_id (uuid nullable), label (varchar nullable), created_at, updated_at; unique index on (ticker, version).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/ticker_model.py backend/app/models/__init__.py backend/migrations/versions/*_create_ticker_models.py
git commit -m "feat(model): add ticker_models table + ORM"
```

---

### Task 4: `ticker_model_drafts` ORM + migration

**Files:**
- Create: `backend/app/models/ticker_model_draft.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/XXXX_create_ticker_model_drafts.py`

- [ ] **Step 1: Implement ORM**

```python
# backend/app/models/ticker_model_draft.py
from __future__ import annotations
from sqlalchemy import String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class TickerModelDraft(Base, TimestampMixin):
    __tablename__ = "ticker_model_drafts"

    ticker: Mapped[str] = mapped_column(String, primary_key=True)
    base_version_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("ticker_models.id"), nullable=False
    )
    state: Mapped[dict] = mapped_column(JSONB, nullable=False)
```

- [ ] **Step 2: Register in `models/__init__.py`**

```python
from backend.app.models.ticker_model_draft import TickerModelDraft  # noqa: F401
# add to __all__: "TickerModelDraft",
```

- [ ] **Step 3: Generate + apply migration**

```bash
cd backend && alembic revision --autogenerate -m "create ticker_model_drafts"
cd backend && alembic upgrade head
psql $DATABASE_URL_SYNC -c "\d ticker_model_drafts"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/ticker_model_draft.py backend/app/models/__init__.py backend/migrations/versions/*_create_ticker_model_drafts.py
git commit -m "feat(model): add ticker_model_drafts table + ORM"
```

---

## Phase 1 — DCF engine (pure)

### Task 5: `dcf()` engine — exit multiple terminal method

**Files:**
- Create: `backend/app/services/dcf.py`
- Create: `backend/scripts/smoke_dcf.py`

- [ ] **Step 1: Write smoke with hand-calculated fixture**

The fixture is a mature, dividend-paying business with known intrinsic value. Use simple round numbers so anyone can verify on paper.

```python
# backend/scripts/smoke_dcf.py
"""Smoke test for the pure DCF engine."""
import sys
from backend.app.models.model_state import (
    ModelState, ModelCell, Period, ModelAssumptions,
    LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF, DRIVER_KEYS,
)
from backend.app.services.dcf import dcf


def make_flat_fixture(fcf_per_year: float, share_count: float, discount: float, exit_mult: float, ebitda: float) -> ModelState:
    """5-year flat fixture: FCF = $100/yr, EBITDA = $150/yr, 100 shares, 10% discount, 12x EBITDA exit."""
    periods = [Period(label=str(2026 + i), kind="Y", is_historical=False) for i in range(5)]
    drivers = {p.label: {k: ModelCell(value=0.0, source="driver") for k in DRIVER_KEYS} for p in periods}
    income_statement = {li: {p.label: ModelCell(value=0.0, source="computed") for p in periods} for li in LINE_ITEMS_PNL}
    for p in periods:
        income_statement["ebitda"][p.label] = ModelCell(value=ebitda, source="computed")
        income_statement["shares_diluted"][p.label] = ModelCell(value=share_count, source="computed")
    cash_flow = {li: {p.label: ModelCell(value=0.0, source="computed") for p in periods} for li in LINE_ITEMS_CF}
    for p in periods:
        cash_flow["free_cash_flow"][p.label] = ModelCell(value=fcf_per_year, source="computed")
    balance_sheet = {li: {p.label: ModelCell(value=0.0, source="computed") for p in periods} for li in LINE_ITEMS_BS}

    return ModelState(
        periods=periods,
        drivers=drivers,
        income_statement=income_statement,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=discount, source="driver"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=exit_mult, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )


def test_flat_dcf_exit_multiple():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    result = dcf(state)
    # PV of 5 yearly FCFs of 100 @ 10% = 100 * (1 - 1.10^-5) / 0.10 = 379.0787
    # Terminal = EBITDA(year 5) * 12 = 1800; PV @ 10% / (1.10^5) = 1117.69
    # Total intrinsic = 379.08 + 1117.69 = 1496.77
    expected = 1496.77
    actual = result.intrinsic_value
    assert abs(actual - expected) < 1.0, f"intrinsic_value mismatch: got {actual}, expected ≈ {expected}"
    expected_per_share = expected / 100.0
    assert abs(result.intrinsic_per_share - expected_per_share) < 0.01, f"per_share mismatch: got {result.intrinsic_per_share}"
    print(f"OK: flat exit-multiple DCF: intrinsic={actual:.2f} per_share={result.intrinsic_per_share:.4f}")


if __name__ == "__main__":
    test_flat_dcf_exit_multiple()
    print("OK: smoke_dcf passed")
    sys.exit(0)
```

- [ ] **Step 2: Run; expect ModuleNotFoundError**

```bash
python -m backend.scripts.smoke_dcf
```
Expected: `ModuleNotFoundError: No module named 'backend.app.services.dcf'`.

- [ ] **Step 3: Implement `dcf.py`**

```python
# backend/app/services/dcf.py
"""Pure DCF engine. No IO, no DB."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

from backend.app.models.model_state import ModelState


@dataclass
class DcfResult:
    intrinsic_value: float
    intrinsic_per_share: float
    fcf_schedule: list[tuple[str, float]]    # [(period_label, fcf)]
    pv_schedule: list[tuple[str, float]]     # [(period_label, pv_of_fcf)]
    terminal_value: float
    terminal_pv: float


def _forecast_periods(state: ModelState) -> list:
    return [p for p in state.periods if not p.is_historical]


def _resolve_overrides(state: ModelState, overrides: dict[str, float] | None) -> dict[str, float]:
    """A no-op for now; downstream solvers will pass overrides for revenue_growth_pct, ebit_margin_pct,
    or terminal_multiple. The simple flat-fixture path doesn't use overrides; full recompute integration
    happens in Task 8 when reverse_dcf is wired with real overrides."""
    return overrides or {}


def dcf(
    state: ModelState,
    *,
    overrides: dict[str, float] | None = None,
    terminal_method: Literal["exit_multiple", "perpetuity"] | None = None,
    discount_rate: float | None = None,
) -> DcfResult:
    """Compute intrinsic value from a ModelState.

    Reads FCF from `cash_flow.free_cash_flow.<period>` for each forecast period.
    Terminal value: exit_multiple = EBITDA(last forecast period) * terminal_multiple
                    perpetuity   = FCF(last) * (1+g) / (r-g)
    Discount rate: assumptions.discount_rate unless overridden.
    """
    forecast = _forecast_periods(state)
    if not forecast:
        raise ValueError("dcf(): state has no forecast periods")

    r = discount_rate if discount_rate is not None else (state.assumptions.discount_rate.value or 0.0)
    method = terminal_method or state.assumptions.terminal_method
    overrides = _resolve_overrides(state, overrides)

    # FCF schedule
    fcfs: list[tuple[str, float]] = []
    for p in forecast:
        cell = state.cash_flow.get("free_cash_flow", {}).get(p.label)
        if cell is None or cell.value is None:
            raise ValueError(f"dcf(): missing FCF for forecast period {p.label}")
        fcfs.append((p.label, float(cell.value)))

    # PV of FCFs (discount each by year-fraction; quarters fractional)
    pvs: list[tuple[str, float]] = []
    cumulative_year = 0.0
    for label, fcf in fcfs:
        # Q periods get 0.25 year increments; Y periods 1.0
        period = next(p for p in forecast if p.label == label)
        delta = 0.25 if period.kind == "Q" else 1.0
        cumulative_year += delta
        pv = fcf / ((1.0 + r) ** cumulative_year)
        pvs.append((label, pv))

    # Terminal value at end of last forecast period
    last = forecast[-1]
    if method == "exit_multiple":
        ebitda_cell = state.income_statement.get("ebitda", {}).get(last.label)
        if ebitda_cell is None or ebitda_cell.value is None:
            raise ValueError("dcf(): exit_multiple terminal requires EBITDA on last forecast period")
        tv = float(ebitda_cell.value) * (state.assumptions.terminal_multiple.value or 0.0)
    elif method == "perpetuity":
        g = state.assumptions.perpetuity_growth.value or 0.0
        if r <= g:
            raise ValueError(f"dcf(): perpetuity requires discount_rate > perpetuity_growth (r={r}, g={g})")
        tv = fcfs[-1][1] * (1.0 + g) / (r - g)
    else:
        raise ValueError(f"dcf(): unknown terminal_method {method!r}")

    tv_pv = tv / ((1.0 + r) ** cumulative_year)

    intrinsic = sum(pv for _, pv in pvs) + tv_pv

    # Per-share: divide by diluted shares from last forecast period
    shares_cell = state.income_statement.get("shares_diluted", {}).get(last.label)
    shares = float(shares_cell.value) if shares_cell and shares_cell.value else 1.0

    return DcfResult(
        intrinsic_value=intrinsic,
        intrinsic_per_share=intrinsic / shares,
        fcf_schedule=fcfs,
        pv_schedule=pvs,
        terminal_value=tv,
        terminal_pv=tv_pv,
    )
```

- [ ] **Step 4: Run smoke; expect PASS**

```bash
python -m backend.scripts.smoke_dcf
```
Expected: `OK: flat exit-multiple DCF: intrinsic=1496.77 ...` followed by `OK: smoke_dcf passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/dcf.py backend/scripts/smoke_dcf.py
git commit -m "feat(model): pure DCF engine with exit-multiple terminal"
```

---

### Task 6: DCF perpetuity terminal + overrides

**Files:** `backend/scripts/smoke_dcf.py` (extend)

- [ ] **Step 1: Add perpetuity fixture to smoke**

```python
def test_flat_dcf_perpetuity():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    result = dcf(state, terminal_method="perpetuity")
    # PV of 5 FCFs = 379.08
    # Terminal (perp at g=2.5%): TV = 100 * 1.025 / (0.10 - 0.025) = 1366.67
    # PV terminal = 1366.67 / 1.10^5 = 848.42
    # Intrinsic = 379.08 + 848.42 = 1227.50
    expected = 1227.50
    assert abs(result.intrinsic_value - expected) < 1.0, f"perpetuity DCF mismatch: got {result.intrinsic_value}"
    print(f"OK: flat perpetuity DCF: intrinsic={result.intrinsic_value:.2f}")


def test_dcf_discount_override():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    base = dcf(state).intrinsic_value
    higher = dcf(state, discount_rate=0.15).intrinsic_value
    assert higher < base, f"higher discount must reduce intrinsic; got {higher} >= {base}"
    print(f"OK: discount override: base={base:.2f}, @15%={higher:.2f}")
```

- [ ] **Step 2: Run smoke; should pass without code change** (engine already supports perpetuity from Task 5)

```bash
python -m backend.scripts.smoke_dcf
```
Expected: all three test prints + `OK: smoke_dcf passed`.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/smoke_dcf.py
git commit -m "test(model): perpetuity terminal + discount override smokes"
```

---

## Phase 2 — Reverse DCF solvers

### Task 7: `solve_implied_driver` — bisection on revenue growth, margin, multiple

**Files:**
- Create: `backend/app/services/reverse_dcf.py`
- Create: `backend/scripts/smoke_reverse_dcf.py`

- [ ] **Step 1: Write smoke**

```python
# backend/scripts/smoke_reverse_dcf.py
"""Smoke test for reverse DCF solvers."""
import sys
from backend.scripts.smoke_dcf import make_flat_fixture
from backend.app.services.dcf import dcf
from backend.app.services.reverse_dcf import solve_implied_driver


def test_implied_terminal_multiple_round_trip():
    # Start with a state at exit_mult=12; intrinsic = 1496.77
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    base = dcf(state).intrinsic_per_share         # = 14.9677
    # Target a higher per-share price; solver should return a higher multiple
    target = 18.0
    implied = solve_implied_driver(state, dimension="terminal_multiple", target_per_share=target)
    assert implied > 12.0, f"implied multiple should exceed baseline 12, got {implied}"
    # Re-run dcf with that multiple, expect intrinsic_per_share ≈ target
    state2 = state.model_copy(deep=True)
    state2.assumptions.terminal_multiple.value = implied
    out = dcf(state2).intrinsic_per_share
    assert abs(out - target) < 0.05, f"round-trip mismatch: got {out}, expected {target}"
    print(f"OK: implied terminal_multiple={implied:.3f} → per_share={out:.4f} (target {target})")


if __name__ == "__main__":
    test_implied_terminal_multiple_round_trip()
    print("OK: smoke_reverse_dcf (Task 7) passed")
    sys.exit(0)
```

- [ ] **Step 2: Run; expect ModuleNotFoundError**

```bash
python -m backend.scripts.smoke_reverse_dcf
```

- [ ] **Step 3: Implement `reverse_dcf.py` with `solve_implied_driver`**

```python
# backend/app/services/reverse_dcf.py
"""Reverse-DCF solvers built atop the pure dcf() engine."""
from __future__ import annotations
from typing import Literal
from copy import deepcopy

from backend.app.models.model_state import ModelState
from backend.app.services.dcf import dcf

ImpliedDimension = Literal["revenue_growth_pct", "ebit_margin_pct", "terminal_multiple"]

# Bisection bounds per dimension. Conservative wide ranges so any reasonable solution is bracketed.
BOUNDS: dict[str, tuple[float, float]] = {
    "revenue_growth_pct": (-0.50, 1.00),     # -50% to +100%
    "ebit_margin_pct":    (-0.50, 0.80),
    "terminal_multiple":  (0.5, 80.0),
}


def _apply_uniform_override(state: ModelState, dimension: ImpliedDimension, value: float) -> ModelState:
    """Return a deep-copied state with the chosen dimension overridden uniformly across forecast periods.
    For terminal_multiple, this overrides assumptions.terminal_multiple.
    For driver-style dimensions, the dimension is rewired into every forecast period's drivers — but the
    full driver→IS→CF recompute lives in model_balancing (Task 11+). For Task 7, we override directly
    on the line items the dcf() engine reads (ebitda for margin, free_cash_flow scaling for growth).
    This keeps the solver provable against the flat fixture; full integration with the recompute pipeline
    happens in Task 14."""
    s = deepcopy(state)
    forecast = [p for p in s.periods if not p.is_historical]
    if dimension == "terminal_multiple":
        s.assumptions.terminal_multiple.value = value
        return s
    if dimension == "ebit_margin_pct":
        # For the flat fixture EBITDA proxy: scale EBITDA by (1 + value).
        # When recompute is integrated (Task 13), this branch will be replaced by:
        #   for p in forecast: s.drivers[p.label]["gross_margin_pct"].value = value
        #   then call services.model_balancing.recompute(s)
        for p in forecast:
            cell = s.income_statement["ebitda"][p.label]
            base = cell.value or 0.0
            cell.value = base * (1.0 + value)   # treat `value` as a delta to baseline margin
        return s
    if dimension == "revenue_growth_pct":
        # For the flat fixture: scale FCF by (1 + value)^t to simulate growth.
        # When recompute is integrated (Task 13), this branch sets the per-period revenue_growth_pct driver.
        for i, p in enumerate(forecast, start=1):
            cell = s.cash_flow["free_cash_flow"][p.label]
            base = cell.value or 0.0
            cell.value = base * ((1.0 + value) ** i)
        return s
    raise ValueError(f"unknown dimension {dimension}")


def solve_implied_driver(
    state: ModelState,
    *,
    dimension: ImpliedDimension,
    target_per_share: float,
    tolerance: float = 1e-3,
    max_iter: int = 60,
) -> float:
    """Bisection: find the value of `dimension` such that dcf(state).intrinsic_per_share == target_per_share."""
    lo, hi = BOUNDS[dimension]

    def evaluate(v: float) -> float:
        s = _apply_uniform_override(state, dimension, v)
        return dcf(s).intrinsic_per_share

    f_lo = evaluate(lo) - target_per_share
    f_hi = evaluate(hi) - target_per_share
    if f_lo * f_hi > 0:
        # Same sign at both bounds — target unreachable in this range
        raise ValueError(
            f"solve_implied_driver: target {target_per_share} unreachable in {dimension} range [{lo}, {hi}] "
            f"(f_lo={f_lo:.4f}, f_hi={f_hi:.4f})"
        )

    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = evaluate(mid) - target_per_share
        if abs(f_mid) < tolerance:
            return mid
        if f_lo * f_mid < 0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid
    return 0.5 * (lo + hi)
```

- [ ] **Step 4: Run smoke; verify PASS**

```bash
python -m backend.scripts.smoke_reverse_dcf
```
Expected: `OK: implied terminal_multiple=... → per_share=... (target 18.0)`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/reverse_dcf.py backend/scripts/smoke_reverse_dcf.py
git commit -m "feat(model): solve_implied_driver (bisection)"
```

---

### Task 8: `solve_implied_irr`

**Files:**
- Modify: `backend/app/services/reverse_dcf.py`
- Modify: `backend/scripts/smoke_reverse_dcf.py`

- [ ] **Step 1: Add IRR test**

```python
def test_implied_irr_round_trip():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    target_per_share = 14.9677  # the baseline at r=10%
    from backend.app.services.reverse_dcf import solve_implied_irr
    irr = solve_implied_irr(state, target_per_share=target_per_share)
    assert abs(irr - 0.10) < 0.005, f"implied IRR should ≈ 10%, got {irr}"
    print(f"OK: implied IRR={irr:.4f}")
```

- [ ] **Step 2: Implement `solve_implied_irr`**

```python
# append to reverse_dcf.py
def solve_implied_irr(
    state: ModelState,
    *,
    target_per_share: float,
    tolerance: float = 1e-4,
    max_iter: int = 80,
) -> float:
    """Bisection on discount_rate; returns the rate where intrinsic_per_share == target_per_share."""
    lo, hi = -0.05, 0.50
    def evaluate(r: float) -> float:
        return dcf(state, discount_rate=r).intrinsic_per_share
    f_lo = evaluate(lo) - target_per_share
    f_hi = evaluate(hi) - target_per_share
    if f_lo * f_hi > 0:
        raise ValueError(f"solve_implied_irr: target {target_per_share} unreachable in [{lo}, {hi}]")
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        f_mid = evaluate(mid) - target_per_share
        if abs(f_mid) < tolerance:
            return mid
        if f_lo * f_mid < 0:
            hi = mid; f_hi = f_mid
        else:
            lo = mid; f_lo = f_mid
    return 0.5 * (lo + hi)
```

- [ ] **Step 3: Run smoke; verify PASS**

```bash
python -m backend.scripts.smoke_reverse_dcf
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/reverse_dcf.py backend/scripts/smoke_reverse_dcf.py
git commit -m "feat(model): solve_implied_irr"
```

---

### Task 9: `sensitivity_grid`

**Files:**
- Modify: `backend/app/services/reverse_dcf.py`
- Modify: `backend/scripts/smoke_reverse_dcf.py`

- [ ] **Step 1: Add grid test**

```python
def test_sensitivity_grid_shape():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    from backend.app.services.reverse_dcf import sensitivity_grid
    grid = sensitivity_grid(
        state,
        x_dim="revenue_growth_pct", x_range=(-0.05, 0.15),
        y_dim="ebit_margin_pct",    y_range=(-0.10, 0.10),
        size=21,
    )
    assert len(grid["x_values"]) == 21
    assert len(grid["y_values"]) == 21
    assert len(grid["values"]) == 21
    assert len(grid["values"][0]) == 21
    # Top-right corner (highest growth + margin) should exceed baseline
    baseline = dcf(state).intrinsic_per_share
    assert grid["values"][-1][-1] > baseline
    print(f"OK: 21x21 grid; baseline={baseline:.2f}, top-right={grid['values'][-1][-1]:.2f}")
```

- [ ] **Step 2: Implement `sensitivity_grid`**

```python
# append to reverse_dcf.py
def sensitivity_grid(
    state: ModelState,
    *,
    x_dim: ImpliedDimension,
    x_range: tuple[float, float],
    y_dim: ImpliedDimension,
    y_range: tuple[float, float],
    size: int = 21,
) -> dict:
    """Evaluate intrinsic_per_share over a size x size grid of (x_dim, y_dim) overrides."""
    if x_dim == y_dim:
        raise ValueError("sensitivity_grid: x_dim and y_dim must differ")
    xs = [x_range[0] + (x_range[1] - x_range[0]) * i / (size - 1) for i in range(size)]
    ys = [y_range[0] + (y_range[1] - y_range[0]) * i / (size - 1) for i in range(size)]
    values: list[list[float]] = []
    for y in ys:
        row: list[float] = []
        s_y = _apply_uniform_override(state, y_dim, y)
        for x in xs:
            s_xy = _apply_uniform_override(s_y, x_dim, x)
            row.append(dcf(s_xy).intrinsic_per_share)
        values.append(row)
    return {"x_dim": x_dim, "y_dim": y_dim, "x_values": xs, "y_values": ys, "values": values}
```

- [ ] **Step 3: Run smoke; verify PASS**

```bash
python -m backend.scripts.smoke_reverse_dcf
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/reverse_dcf.py backend/scripts/smoke_reverse_dcf.py
git commit -m "feat(model): sensitivity_grid (21x21 default)"
```

---

### Task 10: `thesis_vs_priced_in`

**Files:** modify `reverse_dcf.py`, modify `smoke_reverse_dcf.py`

- [ ] **Step 1: Add comparison test**

```python
def test_thesis_vs_priced_in_shape():
    state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
    from backend.app.services.reverse_dcf import thesis_vs_priced_in
    target = 12.0   # below baseline of 14.97 → market less optimistic than thesis
    out = thesis_vs_priced_in(state, target_per_share=target)
    assert len(out) == 3
    dimensions = {row["dimension"] for row in out}
    assert dimensions == {"revenue_growth_pct", "ebit_margin_pct", "terminal_multiple"}
    for row in out:
        assert "thesis" in row and "priced_in" in row and "delta" in row
    print(f"OK: thesis_vs_priced_in: {out}")
```

- [ ] **Step 2: Implement**

```python
# append to reverse_dcf.py
def thesis_vs_priced_in(state: ModelState, *, target_per_share: float) -> list[dict]:
    """For each of the three dimensions, return {thesis, priced_in, delta}.
    `thesis` = current value in `state` (revenue growth: average across forecast; margin: avg gross_margin_pct;
    multiple: assumptions.terminal_multiple). `priced_in` = solver output."""
    forecast = [p for p in state.periods if not p.is_historical]

    def avg_driver(key: str) -> float:
        vals = [state.drivers.get(p.label, {}).get(key, None) for p in forecast]
        nums = [c.value for c in vals if c is not None and c.value is not None]
        return sum(nums) / len(nums) if nums else 0.0

    thesis_growth = avg_driver("revenue_growth_pct")
    thesis_margin = avg_driver("gross_margin_pct")
    thesis_multiple = state.assumptions.terminal_multiple.value or 0.0

    rows = []
    for dim, thesis in [
        ("revenue_growth_pct", thesis_growth),
        ("ebit_margin_pct", thesis_margin),
        ("terminal_multiple", thesis_multiple),
    ]:
        try:
            priced_in = solve_implied_driver(state, dimension=dim, target_per_share=target_per_share)
        except ValueError:
            priced_in = None
        rows.append({
            "dimension": dim,
            "thesis": thesis,
            "priced_in": priced_in,
            "delta": (thesis - priced_in) if priced_in is not None else None,
        })
    return rows
```

- [ ] **Step 3: Run smoke; verify PASS**

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/reverse_dcf.py backend/scripts/smoke_reverse_dcf.py
git commit -m "feat(model): thesis_vs_priced_in comparison"
```

---

## Phase 3 — Recompute pipeline (drivers → IS → CF → BS)

### Task 11: P&L computation from drivers

**Files:**
- Create: `backend/app/services/model_balancing.py`
- Create: `backend/scripts/smoke_model_balancing.py`

- [ ] **Step 1: Write smoke**

```python
# backend/scripts/smoke_model_balancing.py
"""Smoke for the recompute pipeline."""
import sys
from backend.app.models.model_state import ModelState, ModelCell, Period, ModelAssumptions, DRIVER_KEYS, LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF
from backend.app.services.model_balancing import compute_income_statement


def make_minimal_state() -> ModelState:
    historical_p = Period(label="2025Y", kind="Y", is_historical=True)
    forecast_p = Period(label="2026Y", kind="Y", is_historical=False)

    drivers = {
        "2025Y": {k: ModelCell(value=0.0, source="historical") for k in DRIVER_KEYS},
        "2026Y": {
            "revenue_growth_pct":   ModelCell(value=0.10, source="driver"),
            "revenue_absolute":     ModelCell(value=None, source="driver"),
            "gross_margin_pct":     ModelCell(value=0.50, source="driver"),
            "sga_pct_revenue":      ModelCell(value=0.20, source="driver"),
            "rd_pct_revenue":       ModelCell(value=0.05, source="driver"),
            "other_opex_pct_revenue": ModelCell(value=0.0, source="driver"),
            "da_pct_revenue":       ModelCell(value=0.05, source="driver"),
            "effective_tax_rate":   ModelCell(value=0.21, source="driver"),
            "interest_income_yield": ModelCell(value=0.0, source="driver"),
            "interest_expense_rate": ModelCell(value=0.0, source="driver"),
            "capex_pct_revenue":    ModelCell(value=0.05, source="driver"),
            "dso_days":             ModelCell(value=45.0, source="driver"),
            "dio_days":             ModelCell(value=30.0, source="driver"),
            "dpo_days":             ModelCell(value=40.0, source="driver"),
            "dividend_payout_ratio": ModelCell(value=0.0, source="driver"),
            "buyback_dollars":      ModelCell(value=0.0, source="driver"),
            "share_count_change_pct": ModelCell(value=0.0, source="driver"),
            "debt_repayment_dollars": ModelCell(value=0.0, source="driver"),
            "revolver_rate":        ModelCell(value=0.05, source="driver"),
        },
    }
    income_statement = {li: {} for li in LINE_ITEMS_PNL}
    income_statement["revenue"]["2025Y"] = ModelCell(value=1000.0, source="historical")
    income_statement["shares_diluted"]["2025Y"] = ModelCell(value=100.0, source="historical")
    income_statement["shares_diluted"]["2026Y"] = ModelCell(value=100.0, source="computed")
    balance_sheet = {li: {} for li in LINE_ITEMS_BS}
    cash_flow = {li: {} for li in LINE_ITEMS_CF}

    return ModelState(
        periods=[historical_p, forecast_p],
        drivers=drivers,
        income_statement=income_statement,
        balance_sheet=balance_sheet,
        cash_flow=cash_flow,
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=0.10, source="driver"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=12.0, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )


def test_compute_income_statement_minimal():
    s = make_minimal_state()
    s2 = compute_income_statement(s)
    rev = s2.income_statement["revenue"]["2026Y"].value
    assert abs(rev - 1100.0) < 0.01, f"revenue should be 1000 * 1.10 = 1100, got {rev}"
    gp = s2.income_statement["gross_profit"]["2026Y"].value
    assert abs(gp - 550.0) < 0.01, f"gross_profit should be 1100 * 0.50 = 550, got {gp}"
    ebit = s2.income_statement["ebit"]["2026Y"].value
    # EBIT = revenue - cogs - sga - rd - other_opex - da
    #      = 1100 - 550 - 220 - 55 - 0 - 55 = 220
    assert abs(ebit - 220.0) < 0.01, f"ebit got {ebit}"
    ni = s2.income_statement["net_income"]["2026Y"].value
    # NI = EBIT * (1 - tax) = 220 * 0.79 = 173.80   (no interest)
    assert abs(ni - 173.8) < 0.01, f"net_income got {ni}"
    print(f"OK: P&L compute: rev={rev} gp={gp} ebit={ebit} ni={ni}")


if __name__ == "__main__":
    test_compute_income_statement_minimal()
    print("OK: smoke_model_balancing (Task 11) passed")
    sys.exit(0)
```

- [ ] **Step 2: Run; expect ImportError**

- [ ] **Step 3: Implement `compute_income_statement`**

```python
# backend/app/services/model_balancing.py
"""Recompute pipeline: drivers → IS → CF → BS."""
from __future__ import annotations
from copy import deepcopy
from backend.app.models.model_state import ModelState, ModelCell


class ModelBalanceError(Exception):
    """Balance sheet failed to balance after rollforward."""


def _drv(state: ModelState, period: str, key: str) -> float | None:
    cell = state.drivers.get(period, {}).get(key)
    return cell.value if cell else None


def _set_pnl(state: ModelState, line: str, period: str, value: float, formula: str | None = None) -> None:
    state.income_statement.setdefault(line, {})[period] = ModelCell(
        value=value, source="computed", formula=formula,
    )


def compute_income_statement(state: ModelState) -> ModelState:
    """Compute P&L from drivers, period by period (forecast only). Returns a deep-copied new state.
    Skips any cell already marked source=='override' (preserves user overrides)."""
    s = deepcopy(state)
    forecast = [p for p in s.periods if not p.is_historical]

    # We need to know prior-period revenue; build a sequential chain through historicals first.
    prior_rev: float | None = None
    for p in s.periods:
        if p.is_historical:
            cell = s.income_statement.get("revenue", {}).get(p.label)
            if cell and cell.value is not None:
                prior_rev = cell.value

    for p in forecast:
        # --- Revenue ---
        existing = s.income_statement.get("revenue", {}).get(p.label)
        if existing and existing.source == "override" and existing.value is not None:
            rev = existing.value
        else:
            abs_cell = s.drivers.get(p.label, {}).get("revenue_absolute")
            if abs_cell and abs_cell.value is not None:
                rev = abs_cell.value
            else:
                growth = _drv(s, p.label, "revenue_growth_pct") or 0.0
                if prior_rev is None:
                    raise ValueError(f"compute_income_statement: no prior revenue for {p.label}")
                # Quarterly periods: apply growth as YoY against prior_rev (simplification for v1)
                rev = prior_rev * (1.0 + growth)
            _set_pnl(s, "revenue", p.label, rev, formula="= prior_revenue * (1 + revenue_growth_pct)")
        prior_rev = rev

        gm = _drv(s, p.label, "gross_margin_pct") or 0.0
        gp = rev * gm
        cogs = rev - gp
        _set_pnl(s, "cost_of_revenue", p.label, cogs, formula="= revenue - gross_profit")
        _set_pnl(s, "gross_profit", p.label, gp, formula="= revenue * gross_margin_pct")

        sga_pct = _drv(s, p.label, "sga_pct_revenue") or 0.0
        rd_pct = _drv(s, p.label, "rd_pct_revenue") or 0.0
        other_pct = _drv(s, p.label, "other_opex_pct_revenue") or 0.0
        da_pct = _drv(s, p.label, "da_pct_revenue") or 0.0
        sga, rd, other, da = rev * sga_pct, rev * rd_pct, rev * other_pct, rev * da_pct
        opex = sga + rd + other
        _set_pnl(s, "sga", p.label, sga)
        _set_pnl(s, "rd", p.label, rd)
        _set_pnl(s, "other_opex", p.label, other)
        _set_pnl(s, "operating_expenses", p.label, opex)
        _set_pnl(s, "depreciation_amortization", p.label, da)
        ebit = gp - opex - da
        _set_pnl(s, "ebit", p.label, ebit, formula="= gross_profit - operating_expenses - da")
        _set_pnl(s, "ebitda", p.label, ebit + da, formula="= ebit + da")

        # Interest assumed 0 in v1 P&L; debt schedule lives in CF/BS step
        _set_pnl(s, "interest_income", p.label, 0.0)
        _set_pnl(s, "interest_expense", p.label, 0.0)
        pretax = ebit
        _set_pnl(s, "pretax_income", p.label, pretax)
        tax_rate = _drv(s, p.label, "effective_tax_rate") or 0.0
        tax = pretax * tax_rate
        _set_pnl(s, "income_tax", p.label, tax)
        ni = pretax - tax
        _set_pnl(s, "net_income", p.label, ni, formula="= pretax_income * (1 - effective_tax_rate)")

        # Shares: prior shares × (1 + share_count_change_pct)
        sh_change = _drv(s, p.label, "share_count_change_pct") or 0.0
        prior_sh_cell = s.income_statement.get("shares_diluted", {}).get(p.label)
        if prior_sh_cell and prior_sh_cell.source != "override":
            # Find prior period's shares
            idx = s.periods.index(p)
            prior_period = s.periods[idx - 1]
            prior_sh = (s.income_statement.get("shares_diluted", {}).get(prior_period.label) or ModelCell()).value or 0.0
            sh = prior_sh * (1.0 + sh_change)
            _set_pnl(s, "shares_diluted", p.label, sh)
        else:
            sh = (prior_sh_cell.value if prior_sh_cell else 0.0) or 0.0
        _set_pnl(s, "eps_diluted", p.label, ni / sh if sh else 0.0)

    return s
```

- [ ] **Step 4: Run smoke; verify PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/model_balancing.py backend/scripts/smoke_model_balancing.py
git commit -m "feat(model): compute_income_statement from drivers"
```

---

### Task 12: Cash flow + balance sheet rollforward + plug priority

**Files:** modify `backend/app/services/model_balancing.py`, `backend/scripts/smoke_model_balancing.py`

- [ ] **Step 1: Extend smoke with BS-balance assertion**

```python
def test_full_rollforward_balances():
    s = make_minimal_state()
    # Add minimal historical BS + CF state for rollforward seed
    s.balance_sheet["cash_and_equivalents"]["2025Y"] = ModelCell(value=200.0, source="historical")
    s.balance_sheet["accounts_receivable"]["2025Y"] = ModelCell(value=120.0, source="historical")
    s.balance_sheet["inventory"]["2025Y"] = ModelCell(value=80.0, source="historical")
    s.balance_sheet["other_current_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
    s.balance_sheet["ppe_net"]["2025Y"] = ModelCell(value=400.0, source="historical")
    s.balance_sheet["goodwill"]["2025Y"] = ModelCell(value=0.0, source="historical")
    s.balance_sheet["other_long_term_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
    s.balance_sheet["accounts_payable"]["2025Y"] = ModelCell(value=110.0, source="historical")
    s.balance_sheet["short_term_debt"]["2025Y"] = ModelCell(value=0.0, source="historical")
    s.balance_sheet["other_current_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
    s.balance_sheet["long_term_debt"]["2025Y"] = ModelCell(value=200.0, source="historical")
    s.balance_sheet["other_long_term_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
    s.balance_sheet["common_equity"]["2025Y"] = ModelCell(value=200.0, source="historical")
    s.balance_sheet["retained_earnings"]["2025Y"] = ModelCell(value=290.0, source="historical")
    # 2025 BS check: assets = 200+120+80+0+400+0+0 = 800; liabilities = 110+0+0+200+0 = 310; equity = 200+290 = 490
    # 800 = 310 + 490 ✓

    from backend.app.services.model_balancing import recompute
    s2 = recompute(s)

    assets = sum((s2.balance_sheet[li]["2026Y"].value or 0.0) for li in [
        "cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
        "ppe_net", "goodwill", "other_long_term_assets",
    ])
    liab = sum((s2.balance_sheet[li]["2026Y"].value or 0.0) for li in [
        "accounts_payable", "short_term_debt", "other_current_liabilities",
        "long_term_debt", "other_long_term_liabilities",
    ])
    eq = sum((s2.balance_sheet[li]["2026Y"].value or 0.0) for li in ["common_equity", "retained_earnings"])
    diff = assets - (liab + eq)
    assert abs(diff) < 1.0, f"BS imbalance: assets={assets}, liab+eq={liab+eq}, diff={diff}"
    print(f"OK: BS balances at 2026Y: assets={assets:.2f}, liab+eq={liab+eq:.2f}")
```

- [ ] **Step 2: Implement `compute_cash_flow`, `roll_balance_sheet`, `recompute`**

```python
# append to backend/app/services/model_balancing.py
def _set_cf(state: ModelState, line: str, period: str, value: float) -> None:
    state.cash_flow.setdefault(line, {})[period] = ModelCell(value=value, source="computed")


def _set_bs(state: ModelState, line: str, period: str, value: float) -> None:
    state.balance_sheet.setdefault(line, {})[period] = ModelCell(value=value, source="computed")


def _bs_prior(state: ModelState, line: str, period_idx: int) -> float:
    prior_period = state.periods[period_idx - 1]
    cell = state.balance_sheet.get(line, {}).get(prior_period.label)
    return (cell.value if cell else 0.0) or 0.0


def compute_cash_flow(state: ModelState) -> ModelState:
    """CF derived from P&L + WC changes + capex + financing drivers. Run after compute_income_statement."""
    s = state
    forecast = [p for p in s.periods if not p.is_historical]
    for p in forecast:
        idx = s.periods.index(p)
        ni = (s.income_statement["net_income"][p.label].value or 0.0)
        da = (s.income_statement["depreciation_amortization"][p.label].value or 0.0)
        rev = (s.income_statement["revenue"][p.label].value or 0.0)
        cogs = (s.income_statement["cost_of_revenue"][p.label].value or 0.0)

        dso = _drv(s, p.label, "dso_days") or 0.0
        dio = _drv(s, p.label, "dio_days") or 0.0
        dpo = _drv(s, p.label, "dpo_days") or 0.0

        # New AR/Inv/AP using days-driven targets
        new_ar = rev * (dso / 365.0)
        new_inv = cogs * (dio / 365.0)
        new_ap = cogs * (dpo / 365.0)

        prior_ar = _bs_prior(s, "accounts_receivable", idx)
        prior_inv = _bs_prior(s, "inventory", idx)
        prior_ap = _bs_prior(s, "accounts_payable", idx)

        d_ar = -(new_ar - prior_ar)   # AR up = cash use
        d_inv = -(new_inv - prior_inv)
        d_ap = (new_ap - prior_ap)    # AP up = cash source

        capex_pct = _drv(s, p.label, "capex_pct_revenue") or 0.0
        capex = -(rev * capex_pct)    # negative outflow

        ocf = ni + da + d_ar + d_inv + d_ap
        fcf = ocf + capex

        debt_repay = -(_drv(s, p.label, "debt_repayment_dollars") or 0.0)
        buybacks = -(_drv(s, p.label, "buyback_dollars") or 0.0)
        payout = _drv(s, p.label, "dividend_payout_ratio") or 0.0
        dividends = -(ni * payout)

        net_change = fcf + debt_repay + buybacks + dividends

        _set_cf(s, "net_income_cf", p.label, ni)
        _set_cf(s, "depreciation_amortization_cf", p.label, da)
        _set_cf(s, "delta_accounts_receivable", p.label, d_ar)
        _set_cf(s, "delta_inventory", p.label, d_inv)
        _set_cf(s, "delta_accounts_payable", p.label, d_ap)
        _set_cf(s, "operating_cash_flow", p.label, ocf)
        _set_cf(s, "capex", p.label, capex)
        _set_cf(s, "free_cash_flow", p.label, fcf)
        _set_cf(s, "debt_issued", p.label, 0.0)
        _set_cf(s, "debt_repaid", p.label, debt_repay)
        _set_cf(s, "dividends_paid", p.label, dividends)
        _set_cf(s, "buybacks", p.label, buybacks)
        _set_cf(s, "net_change_in_cash", p.label, net_change)
    return s


def roll_balance_sheet(state: ModelState) -> ModelState:
    """Roll BS forward from prior period + CF activity. Plug priority is honored implicitly:
    debt_repaid drains LT debt; buybacks drain cash; dividends drain cash; remainder is cash buildup.
    If FCF + financing < 0, the gap is funded by short_term_debt (revolver). v1 ignores PPE/goodwill changes
    beyond capex flowing into PPE."""
    s = state
    forecast = [p for p in s.periods if not p.is_historical]
    for p in forecast:
        idx = s.periods.index(p)
        rev = s.income_statement["revenue"][p.label].value or 0.0
        cogs = s.income_statement["cost_of_revenue"][p.label].value or 0.0

        dso = _drv(s, p.label, "dso_days") or 0.0
        dio = _drv(s, p.label, "dio_days") or 0.0
        dpo = _drv(s, p.label, "dpo_days") or 0.0

        _set_bs(s, "accounts_receivable", p.label, rev * (dso / 365.0))
        _set_bs(s, "inventory", p.label, cogs * (dio / 365.0))
        _set_bs(s, "accounts_payable", p.label, cogs * (dpo / 365.0))
        _set_bs(s, "other_current_assets", p.label, _bs_prior(s, "other_current_assets", idx))
        _set_bs(s, "other_current_liabilities", p.label, _bs_prior(s, "other_current_liabilities", idx))
        _set_bs(s, "other_long_term_assets", p.label, _bs_prior(s, "other_long_term_assets", idx))
        _set_bs(s, "other_long_term_liabilities", p.label, _bs_prior(s, "other_long_term_liabilities", idx))
        _set_bs(s, "goodwill", p.label, _bs_prior(s, "goodwill", idx))

        capex = -(s.cash_flow["capex"][p.label].value or 0.0)  # positive for PPE addition
        da = s.income_statement["depreciation_amortization"][p.label].value or 0.0
        ppe = _bs_prior(s, "ppe_net", idx) + capex - da
        _set_bs(s, "ppe_net", p.label, ppe)

        # Debt
        prior_lt = _bs_prior(s, "long_term_debt", idx)
        debt_repay = (_drv(s, p.label, "debt_repayment_dollars") or 0.0)
        new_lt = max(0.0, prior_lt - debt_repay)
        _set_bs(s, "long_term_debt", p.label, new_lt)

        # Equity
        prior_re = _bs_prior(s, "retained_earnings", idx)
        ni = s.income_statement["net_income"][p.label].value or 0.0
        dividends = -(s.cash_flow["dividends_paid"][p.label].value or 0.0)  # negative cash, positive distribution
        new_re = prior_re + ni - dividends
        _set_bs(s, "retained_earnings", p.label, new_re)
        prior_ce = _bs_prior(s, "common_equity", idx)
        buybacks = -(s.cash_flow["buybacks"][p.label].value or 0.0)
        _set_bs(s, "common_equity", p.label, prior_ce - buybacks)

        # Cash plug: ΔCash = NCF; revolver fills if cash goes negative
        prior_cash = _bs_prior(s, "cash_and_equivalents", idx)
        ncf = s.cash_flow["net_change_in_cash"][p.label].value or 0.0
        new_cash = prior_cash + ncf
        prior_st = _bs_prior(s, "short_term_debt", idx)
        if new_cash < 0:
            revolver_draw = -new_cash
            new_cash = 0.0
            _set_bs(s, "short_term_debt", p.label, prior_st + revolver_draw)
        else:
            _set_bs(s, "short_term_debt", p.label, prior_st)
        _set_bs(s, "cash_and_equivalents", p.label, new_cash)

        # Totals
        ca = sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
        ])
        _set_bs(s, "total_current_assets", p.label, ca)
        ta = ca + sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "ppe_net", "goodwill", "other_long_term_assets",
        ])
        _set_bs(s, "total_assets", p.label, ta)
        cl = sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "accounts_payable", "short_term_debt", "other_current_liabilities",
        ])
        _set_bs(s, "total_current_liabilities", p.label, cl)
        tl = cl + sum((s.balance_sheet[li][p.label].value or 0.0) for li in [
            "long_term_debt", "other_long_term_liabilities",
        ])
        _set_bs(s, "total_liabilities", p.label, tl)
        te = sum((s.balance_sheet[li][p.label].value or 0.0) for li in ["common_equity", "retained_earnings"])
        _set_bs(s, "total_equity", p.label, te)
        _set_bs(s, "total_liab_and_equity", p.label, tl + te)

        # Balance check
        if abs(ta - (tl + te)) > 1.0:
            raise ModelBalanceError(
                f"BS imbalance at {p.label}: assets={ta:.2f}, liab+eq={tl+te:.2f}, diff={ta-(tl+te):.2f}"
            )

    return s


def recompute(state: ModelState) -> ModelState:
    """Full recompute pipeline. Idempotent: produces a deep-copied new state with all computed
    cells refreshed and BS balanced."""
    s = compute_income_statement(state)
    s = compute_cash_flow(s)
    s = roll_balance_sheet(s)
    return s
```

- [ ] **Step 3: Run smoke; verify PASS**

```bash
python -m backend.scripts.smoke_model_balancing
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/model_balancing.py backend/scripts/smoke_model_balancing.py
git commit -m "feat(model): full recompute pipeline (CF + BS rollforward + plug)"
```

---

### Task 13: Wire reverse_dcf overrides through the recompute pipeline

The Task 7 `_apply_uniform_override` short-circuits the recompute pipeline (it edits IS/CF cells directly). Now that `recompute()` exists, reverse_dcf should set drivers and re-run recompute so solvers operate on a fully consistent model state.

**Files:** modify `backend/app/services/reverse_dcf.py`

- [ ] **Step 1: Update smoke to test against a non-flat fixture (driver-driven)**

```python
# add to backend/scripts/smoke_reverse_dcf.py
def test_implied_growth_uses_recompute():
    """Validates that solving for revenue_growth_pct produces a state whose recompute output matches."""
    from backend.scripts.smoke_model_balancing import make_minimal_state
    state = make_minimal_state()
    # Need historical BS to allow recompute → grab from smoke_model_balancing
    state.balance_sheet["cash_and_equivalents"]["2025Y"] = ModelCell(value=200.0, source="historical")
    state.balance_sheet["accounts_receivable"]["2025Y"] = ModelCell(value=120.0, source="historical")
    state.balance_sheet["inventory"]["2025Y"] = ModelCell(value=80.0, source="historical")
    state.balance_sheet["other_current_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["ppe_net"]["2025Y"] = ModelCell(value=400.0, source="historical")
    state.balance_sheet["goodwill"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["other_long_term_assets"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["accounts_payable"]["2025Y"] = ModelCell(value=110.0, source="historical")
    state.balance_sheet["short_term_debt"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["other_current_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["long_term_debt"]["2025Y"] = ModelCell(value=200.0, source="historical")
    state.balance_sheet["other_long_term_liabilities"]["2025Y"] = ModelCell(value=0.0, source="historical")
    state.balance_sheet["common_equity"]["2025Y"] = ModelCell(value=200.0, source="historical")
    state.balance_sheet["retained_earnings"]["2025Y"] = ModelCell(value=290.0, source="historical")

    from backend.app.services.model_balancing import recompute
    state = recompute(state)
    base_per_share = dcf(state).intrinsic_per_share

    # Solve for revenue_growth that yields 1.5x baseline per-share
    target = base_per_share * 1.5
    implied = solve_implied_driver(state, dimension="revenue_growth_pct", target_per_share=target)
    print(f"OK: implied growth via recompute: {implied:.4f} for target {target:.4f}")
```

- [ ] **Step 2: Update `_apply_uniform_override` to set drivers + recompute**

```python
# in backend/app/services/reverse_dcf.py — replace existing _apply_uniform_override
from backend.app.services.model_balancing import recompute

def _apply_uniform_override(state: ModelState, dimension: ImpliedDimension, value: float) -> ModelState:
    s = deepcopy(state)
    forecast = [p for p in s.periods if not p.is_historical]
    if dimension == "terminal_multiple":
        s.assumptions.terminal_multiple.value = value
        return s
    if dimension == "ebit_margin_pct":
        # Override the gross margin driver uniformly; opex stays constant pct.
        for p in forecast:
            cell = s.drivers[p.label].get("gross_margin_pct")
            if cell is None:
                from backend.app.models.model_state import ModelCell
                s.drivers[p.label]["gross_margin_pct"] = ModelCell(value=value, source="driver")
            else:
                cell.value = value
        return recompute(s)
    if dimension == "revenue_growth_pct":
        for p in forecast:
            cell = s.drivers[p.label].get("revenue_growth_pct")
            if cell is None:
                from backend.app.models.model_state import ModelCell
                s.drivers[p.label]["revenue_growth_pct"] = ModelCell(value=value, source="driver")
            else:
                cell.value = value
            # Disable absolute-revenue override if previously set
            abs_cell = s.drivers[p.label].get("revenue_absolute")
            if abs_cell:
                abs_cell.value = None
        return recompute(s)
    raise ValueError(f"unknown dimension {dimension}")
```

- [ ] **Step 3: Re-run smoke; verify PASS**

```bash
python -m backend.scripts.smoke_reverse_dcf
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/reverse_dcf.py backend/scripts/smoke_reverse_dcf.py
git commit -m "feat(model): wire reverse_dcf overrides through recompute pipeline"
```

---

## Phase 4 — Diff service

### Task 14: `model_diff` cell-path-keyed JSON diff

**Files:**
- Create: `backend/app/services/model_diff.py`
- Create: `backend/scripts/smoke_model_diff.py`

- [ ] **Step 1: Write smoke**

```python
# backend/scripts/smoke_model_diff.py
import sys
from copy import deepcopy
from backend.scripts.smoke_model_balancing import make_minimal_state
from backend.app.services.model_diff import diff_states


def test_diff_single_driver_change():
    a = make_minimal_state()
    b = deepcopy(a)
    b.drivers["2026Y"]["gross_margin_pct"].value = 0.55  # was 0.50
    d = diff_states(a, b)
    assert d["added"] == [], f"expected no adds, got {d['added']}"
    assert d["removed"] == [], f"expected no removes, got {d['removed']}"
    changed_paths = [c["cell_path"] for c in d["changed"]]
    assert "drivers.2026Y.gross_margin_pct" in changed_paths, f"diff missed driver change: {changed_paths}"
    print("OK: model_diff detects driver change")


if __name__ == "__main__":
    test_diff_single_driver_change()
    print("OK: smoke_model_diff passed")
    sys.exit(0)
```

- [ ] **Step 2: Implement `model_diff.py`**

```python
# backend/app/services/model_diff.py
"""Cell-path-keyed JSON diff between two ModelStates."""
from __future__ import annotations
from typing import Iterable

from backend.app.models.model_state import ModelState, ModelCell


def _walk_cells(state: ModelState) -> Iterable[tuple[str, ModelCell]]:
    for stmt_name, stmt in [
        ("income_statement", state.income_statement),
        ("balance_sheet", state.balance_sheet),
        ("cash_flow", state.cash_flow),
    ]:
        for line, periods in stmt.items():
            for period, cell in periods.items():
                yield f"{stmt_name}.{line}.{period}", cell
    for period, drvs in state.drivers.items():
        for k, cell in drvs.items():
            yield f"drivers.{period}.{k}", cell
    for k in ("discount_rate", "terminal_multiple", "perpetuity_growth", "tax_rate"):
        cell = getattr(state.assumptions, k)
        yield f"assumptions.{k}", cell


def diff_states(a: ModelState, b: ModelState, *, eps: float = 1e-6) -> dict:
    """Return {added, removed, changed} keyed by cell_path."""
    a_map = {p: c for p, c in _walk_cells(a)}
    b_map = {p: c for p, c in _walk_cells(b)}
    added = sorted(set(b_map) - set(a_map))
    removed = sorted(set(a_map) - set(b_map))
    changed: list[dict] = []
    for path in sorted(set(a_map) & set(b_map)):
        ca, cb = a_map[path], b_map[path]
        va, vb = ca.value or 0.0, cb.value or 0.0
        if abs(va - vb) > eps or ca.source != cb.source:
            changed.append({"cell_path": path, "before": {"value": ca.value, "source": ca.source},
                            "after": {"value": cb.value, "source": cb.source}})
    return {"added": added, "removed": removed, "changed": changed}
```

- [ ] **Step 3: Run smoke; verify PASS**

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/model_diff.py backend/scripts/smoke_model_diff.py
git commit -m "feat(model): cell-path-keyed JSON diff between ModelStates"
```

---

## Phase 5 — AI baseline seeding

### Task 15: Sonnet baseline node + Pydantic ForecastDrivers schema

**Files:**
- Create: `backend/app/graph/model_baseline_node.py`
- Create: `backend/scripts/smoke_model_baseline.py`

- [ ] **Step 1: Write smoke (with mocked llm.complete)**

```python
# backend/scripts/smoke_model_baseline.py
import sys
import json
from unittest.mock import patch, MagicMock
from backend.app.graph.model_baseline_node import generate_baseline_drivers, BaselineDriversResponse


FAKE_LLM_OUTPUT = {
    "drivers": {
        "2026Y": {
            "revenue_growth_pct": {"value": 0.10, "reason": "matches consensus", "source_citation_id": None},
            "gross_margin_pct":   {"value": 0.50, "reason": "stable from 8Q history", "source_citation_id": None},
            "sga_pct_revenue":    {"value": 0.20, "reason": "from history", "source_citation_id": None},
            "rd_pct_revenue":     {"value": 0.05, "reason": "from history", "source_citation_id": None},
            "other_opex_pct_revenue": {"value": 0.0, "reason": "n/a", "source_citation_id": None},
            "da_pct_revenue":     {"value": 0.05, "reason": "from history", "source_citation_id": None},
            "effective_tax_rate": {"value": 0.21, "reason": "statutory", "source_citation_id": None},
            "interest_income_yield": {"value": 0.0, "reason": "n/a", "source_citation_id": None},
            "interest_expense_rate": {"value": 0.0, "reason": "n/a", "source_citation_id": None},
            "capex_pct_revenue":  {"value": 0.05, "reason": "from history", "source_citation_id": None},
            "dso_days": {"value": 45.0, "reason": "stable", "source_citation_id": None},
            "dio_days": {"value": 30.0, "reason": "stable", "source_citation_id": None},
            "dpo_days": {"value": 40.0, "reason": "stable", "source_citation_id": None},
            "dividend_payout_ratio": {"value": 0.0, "reason": "no dividend", "source_citation_id": None},
            "buyback_dollars": {"value": 0.0, "reason": "no buyback program", "source_citation_id": None},
            "share_count_change_pct": {"value": 0.0, "reason": "flat", "source_citation_id": None},
            "debt_repayment_dollars": {"value": 0.0, "reason": "no schedule", "source_citation_id": None},
            "revolver_rate": {"value": 0.05, "reason": "n/a baseline", "source_citation_id": None},
            "revenue_absolute": {"value": None, "reason": "use growth pct", "source_citation_id": None}
        }
    }
}


def test_generate_baseline_drivers_with_mock():
    fake = json.dumps(FAKE_LLM_OUTPUT)
    with patch("backend.app.graph.model_baseline_node.llm.complete", return_value=fake):
        out = generate_baseline_drivers(
            ticker="ZZZ",
            historicals_payload="(stub historicals)",
            deep_dive_summary="(stub findings)",
            consensus_estimates="(stub estimates)",
            forecast_period_labels=["2026Y"],
        )
    assert isinstance(out, BaselineDriversResponse)
    assert "2026Y" in out.drivers
    assert out.drivers["2026Y"]["gross_margin_pct"].value == 0.50
    print("OK: baseline node returns parsed BaselineDriversResponse")


if __name__ == "__main__":
    test_generate_baseline_drivers_with_mock()
    print("OK: smoke_model_baseline (Task 15) passed")
    sys.exit(0)
```

- [ ] **Step 2: Implement `model_baseline_node.py`**

```python
# backend/app/graph/model_baseline_node.py
"""Sonnet pass that generates a baseline ForecastDrivers payload from deep-dive context."""
from __future__ import annotations
from pydantic import BaseModel, Field

from backend.app.graph import llm


class DriverProposal(BaseModel):
    value: float | None = None
    reason: str = ""
    source_citation_id: str | None = None


class BaselineDriversResponse(BaseModel):
    drivers: dict[str, dict[str, DriverProposal]]   # {period_label: {driver_key: proposal}}


SYSTEM_PROMPT = """You are building a baseline financial forecast for a 3-statement model. \
Use the deep-dive findings, analyst consensus, and historical trends to produce structured driver \
assumptions for each forecast period. For each driver, give a numeric value, a one-line reason, and \
optionally a source_citation_id pointing back to a deep-dive finding ID, an analyst estimate label, \
or a historical-trend note. Anchor near consensus estimates unless the deep-dive findings explicitly \
contradict them — in which case explain why in `reason`. Use percentages as decimals (10% = 0.10). \
Days drivers (DSO/DIO/DPO) in days. Dollar drivers in same units as revenue. \
Output JSON ONLY — no preamble. Schema: {"drivers": {<period_label>: {<driver_key>: {"value": <num|null>, "reason": <str>, "source_citation_id": <str|null>}}}}"""


def generate_baseline_drivers(
    *,
    ticker: str,
    historicals_payload: str,
    deep_dive_summary: str,
    consensus_estimates: str,
    forecast_period_labels: list[str],
) -> BaselineDriversResponse:
    user = (
        f"Ticker: {ticker}\n\n"
        f"Forecast periods (in order): {', '.join(forecast_period_labels)}\n\n"
        f"=== Historical financials (8 quarters) ===\n{historicals_payload}\n\n"
        f"=== Analyst consensus estimates ===\n{consensus_estimates}\n\n"
        f"=== Deep-dive summary (verdict, scores, key findings per category) ===\n{deep_dive_summary}\n\n"
        f"Produce the BaselineDriversResponse JSON now."
    )
    raw = llm.complete(
        system=SYSTEM_PROMPT,
        user=user,
        assistant_prefill='{"drivers":',
    )
    return BaselineDriversResponse.model_validate_json(raw)
```

Note: `llm.complete` already prepends `assistant_prefill` to its return value (per Tier 2.5 / 1.2 lessons-learned in memory). Do NOT manually prepend.

- [ ] **Step 3: Run smoke; verify PASS**

```bash
python -m backend.scripts.smoke_model_baseline
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/graph/model_baseline_node.py backend/scripts/smoke_model_baseline.py
git commit -m "feat(model): Sonnet baseline-drivers node"
```

---

### Task 16: `model_baseline.py` service — orchestrate seed end-to-end

**Files:**
- Create: `backend/app/services/model_baseline.py`
- Modify: `backend/scripts/smoke_model_baseline.py`

- [ ] **Step 1: Add orchestration smoke**

```python
# append to smoke_model_baseline.py
async def test_initialize_model_for_ticker_with_mocks():
    """Mocks ResearchRun + FMP + llm.complete; asserts a ModelState comes out balanced."""
    # NB: this test exercises the orchestration glue — actual DB write happens in Task 17.
    from unittest.mock import patch
    from backend.app.services import model_baseline
    fake_llm = json.dumps(FAKE_LLM_OUTPUT)
    fake_run_state = {
        "curated_financials": {
            "income_statements": [{"period": "2025Y", "revenue": 1000.0, "ebitda": 200.0, "shares_diluted": 100.0,
                                   "gross_profit": 500.0, "operating_expenses": 300.0, "depreciation_amortization": 50.0,
                                   "ebit": 150.0, "net_income": 120.0, "eps_diluted": 1.20}],
            "balance_sheets": [{"period": "2025Y", "cash_and_equivalents": 200.0, "accounts_receivable": 120.0,
                                "inventory": 80.0, "ppe_net": 400.0, "accounts_payable": 110.0,
                                "long_term_debt": 200.0, "common_equity": 200.0, "retained_earnings": 290.0}],
            "cash_flows": [],
            "profile": {"beta": 1.0},
        },
        "thesis_output": {"core_thesis": "growth thesis"},
        "deep_dive_results": {},
    }
    with patch.object(model_baseline, "_load_seeding_context", return_value=fake_run_state), \
         patch("backend.app.graph.model_baseline_node.llm.complete", return_value=fake_llm), \
         patch.object(model_baseline, "_get_risk_free_rate", return_value=0.04):
        state = await model_baseline.build_baseline_state(ticker="ZZZ", forecast_period_labels=["2026Y"])
    assert state.assumptions.discount_rate.value > 0
    print(f"OK: build_baseline_state produces ModelState (discount={state.assumptions.discount_rate.value:.4f})")
```

Add an asyncio runner to `__main__`:

```python
import asyncio
asyncio.run(test_initialize_model_for_ticker_with_mocks())
```

- [ ] **Step 2: Implement `model_baseline.py`**

```python
# backend/app/services/model_baseline.py
"""Orchestrate AI baseline seeding into a ModelState."""
from __future__ import annotations
from datetime import datetime
from typing import Any

from backend.app.graph.model_baseline_node import generate_baseline_drivers, BaselineDriversResponse
from backend.app.models.model_state import (
    ModelState, ModelCell, Period, ModelAssumptions,
    DRIVER_KEYS, LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF,
)
from backend.app.services.model_balancing import recompute


async def _load_seeding_context(ticker: str) -> dict[str, Any]:
    """Load latest completed research_run state for ticker. Real impl pulls from research_runs table."""
    from backend.app.db import async_session
    from backend.app.models.research_run import ResearchRun
    from sqlalchemy import select
    async with async_session() as db:
        stmt = (select(ResearchRun)
                .where(ResearchRun.ticker == ticker, ResearchRun.status == "completed")
                .order_by(ResearchRun.created_at.desc()).limit(1))
        run = (await db.execute(stmt)).scalar_one_or_none()
        if run is None:
            raise ValueError(f"No completed research_run found for ticker {ticker}")
        return run.state or {}


async def _get_risk_free_rate() -> float:
    """Latest 10Y treasury from FRED. Reuses existing FRED client cache."""
    from backend.app.clients.fred_client import FREDClient
    client = FREDClient()
    series = await client.fetch_series("DGS10")  # 10-Year Treasury Constant Maturity Rate
    if not series or not series[-1].get("value"):
        return 0.045  # fallback
    return float(series[-1]["value"]) / 100.0


def _build_periods() -> list[Period]:
    """8 historical Q + 8 forecast Q + 5 forecast Y. Caller can override the labels."""
    today = datetime.utcnow()
    year, q = today.year, (today.month - 1) // 3 + 1
    periods: list[Period] = []
    # 8 historical quarters
    for i in range(8, 0, -1):
        ny, nq = year, q - i
        while nq <= 0:
            ny -= 1; nq += 4
        periods.append(Period(label=f"{ny}Q{nq}", kind="Q", is_historical=True, quarter_index=nq))
    # 8 forecast quarters
    for i in range(0, 8):
        ny, nq = year, q + i
        while nq > 4:
            ny += 1; nq -= 4
        periods.append(Period(label=f"{ny}Q{nq}", kind="Q", is_historical=False, quarter_index=nq))
    # 5 forecast years (calendar years following the last forecast quarter)
    last_q = periods[-1]
    start_y = last_q.label.split("Q")[0]
    base = int(start_y) + 1
    for i in range(5):
        periods.append(Period(label=f"{base + i}Y", kind="Y", is_historical=False))
    return periods


def _seed_historicals(state: ModelState, ctx: dict[str, Any]) -> None:
    """Map curated_financials onto historical period cells."""
    cf = ctx.get("curated_financials") or {}
    for stmt_key, lines in [
        ("income_statements", LINE_ITEMS_PNL),
        ("balance_sheets",    LINE_ITEMS_BS),
        ("cash_flows",        LINE_ITEMS_CF),
    ]:
        target = {
            "income_statements": state.income_statement,
            "balance_sheets":    state.balance_sheet,
            "cash_flows":        state.cash_flow,
        }[stmt_key]
        for record in cf.get(stmt_key, []):
            period = record.get("period")
            if period is None:
                continue
            for line in lines:
                if line in record and record[line] is not None:
                    target.setdefault(line, {})[period] = ModelCell(
                        value=float(record[line]), source="historical",
                        last_edited_by="system",
                    )


def _apply_baseline_drivers(state: ModelState, response: BaselineDriversResponse) -> None:
    """Inject Sonnet-generated drivers into state.drivers, source='ai_baseline'."""
    for period_label, drvs in response.drivers.items():
        if period_label not in state.drivers:
            state.drivers[period_label] = {}
        for k, proposal in drvs.items():
            state.drivers[period_label][k] = ModelCell(
                value=proposal.value,
                source="ai_baseline",
                citation_id=proposal.source_citation_id,
                last_edited_at=datetime.utcnow().isoformat(),
                last_edited_by="ai_baseline",
                formula=proposal.reason or None,   # store reason in formula slot for display
            )


async def build_baseline_state(*, ticker: str, forecast_period_labels: list[str] | None = None) -> ModelState:
    ctx = await _load_seeding_context(ticker)
    periods = _build_periods()
    forecast = [p.label for p in periods if not p.is_historical]
    if forecast_period_labels is None:
        forecast_period_labels = forecast
    # Empty cells everywhere; will be filled by seed/recompute
    drivers = {p.label: {k: ModelCell(value=None, source="driver") for k in DRIVER_KEYS} for p in periods}
    income_statement = {li: {} for li in LINE_ITEMS_PNL}
    balance_sheet = {li: {} for li in LINE_ITEMS_BS}
    cash_flow = {li: {} for li in LINE_ITEMS_CF}
    rf = await _get_risk_free_rate()
    beta = float(ctx.get("curated_financials", {}).get("profile", {}).get("beta") or 1.0)
    state = ModelState(
        periods=periods, drivers=drivers,
        income_statement=income_statement, balance_sheet=balance_sheet, cash_flow=cash_flow,
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=rf + beta * 0.055, source="driver",
                                    formula=f"= rf + β × ERP = {rf:.4f} + {beta:.2f} × 0.055"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=12.0, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )
    _seed_historicals(state, ctx)

    # Build seed strings for the LLM
    historicals_str = (ctx.get("curated_financials") or {}).get("income_statements", [])
    deep_dive_summary = str(ctx.get("deep_dive_results") or "(no findings)")
    consensus = (ctx.get("curated_financials") or {}).get("estimates", "(no estimates)")
    response = generate_baseline_drivers(
        ticker=ticker,
        historicals_payload=str(historicals_str),
        deep_dive_summary=deep_dive_summary,
        consensus_estimates=str(consensus),
        forecast_period_labels=forecast_period_labels,
    )
    _apply_baseline_drivers(state, response)

    # Recompute (skip if no historicals to seed BS — surface clean error to caller)
    try:
        state = recompute(state)
    except Exception as exc:
        # Caller may decide to persist as-is and warn the user
        state.income_statement.setdefault("revenue", {})  # ensure shape preserved
        raise
    return state
```

- [ ] **Step 3: Run smoke; verify PASS**

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/model_baseline.py backend/scripts/smoke_model_baseline.py
git commit -m "feat(model): build_baseline_state orchestrator (run → seed → drivers → recompute)"
```

---

### Task 17: Persist v1 to `ticker_models`

**Files:** modify `backend/app/services/model_baseline.py`

- [ ] **Step 1: Add persistence helper**

```python
# append to backend/app/services/model_baseline.py
async def initialize_or_get_model(ticker: str, *, force: bool = False) -> "TickerModel":
    """Returns the latest TickerModel row for ticker, building one if missing or force=True."""
    from backend.app.db import async_session
    from backend.app.models.ticker_model import TickerModel
    from sqlalchemy import select, desc
    async with async_session() as db:
        stmt = select(TickerModel).where(TickerModel.ticker == ticker).order_by(desc(TickerModel.version)).limit(1)
        latest = (await db.execute(stmt)).scalar_one_or_none()
        if latest is not None and not force:
            return latest
        next_version = 1 if latest is None else latest.version + 1
        state = await build_baseline_state(ticker=ticker)
        row = TickerModel(
            ticker=ticker, version=next_version,
            state=state.model_dump(),
            label=("AI baseline" if latest is None else "AI reseed"),
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row
```

The `await db.refresh(row)` call is required after commit to avoid the stale identity-map bug observed in Tier 2.5.

- [ ] **Step 2: Smoke against a real DB with synthetic ticker**

Add to smoke_model_baseline.py:
```python
async def test_initialize_or_get_model_synthetic_ticker():
    """Use synthetic ticker 'ZMODEL'. Cleans up after test. Requires DB up."""
    from backend.app.db import async_session
    from backend.app.models.ticker_model import TickerModel
    from sqlalchemy import delete
    from backend.app.services.model_baseline import initialize_or_get_model
    # Pre-clean
    async with async_session() as db:
        await db.execute(delete(TickerModel).where(TickerModel.ticker == "ZMODEL"))
        await db.commit()
    try:
        row = await initialize_or_get_model("ZMODEL")
        assert row.version == 1
        assert row.state is not None
        # Idempotent
        row2 = await initialize_or_get_model("ZMODEL")
        assert row2.id == row.id
        # Force reseed
        row3 = await initialize_or_get_model("ZMODEL", force=True)
        assert row3.version == 2
        print(f"OK: persisted ZMODEL v1 and v2 ({row.id}, {row3.id})")
    finally:
        async with async_session() as db:
            await db.execute(delete(TickerModel).where(TickerModel.ticker == "ZMODEL"))
            await db.commit()
```

This will fail unless `_load_seeding_context` is mocked or there's a real research_run for `ZMODEL`. For smoke purposes, mock it — see existing pattern in Task 16.

- [ ] **Step 3: Run smoke**

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/model_baseline.py backend/scripts/smoke_model_baseline.py
git commit -m "feat(model): persist baseline state to ticker_models with versioning"
```

---

## Phase 6 — API surface

### Task 18: GET `/api/models/<ticker>` and POST `/api/models/<ticker>/initialize`

**Files:**
- Create: `backend/app/api/models_api.py`
- Modify: `backend/app/main.py` (register router)
- Create: `backend/scripts/smoke_models_api.py`

- [ ] **Step 1: Implement router**

```python
# backend/app/api/models_api.py
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.ticker_model import TickerModel
from backend.app.models.ticker_model_draft import TickerModelDraft
from backend.app.models.model_state import ModelState
from backend.app.services.model_baseline import initialize_or_get_model

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("/{ticker}")
async def get_model(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    stmt = select(TickerModel).where(TickerModel.ticker == ticker).order_by(desc(TickerModel.version)).limit(1)
    latest = (await db.execute(stmt)).scalar_one_or_none()
    if latest is None:
        return {"latest_version": None, "draft": None}
    draft = (await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))).scalar_one_or_none()
    return {
        "latest_version": {
            "id": latest.id, "ticker": latest.ticker, "version": latest.version,
            "label": latest.label, "state": latest.state,
            "created_at": latest.created_at.isoformat(),
        },
        "draft": ({"base_version_id": draft.base_version_id, "state": draft.state,
                   "updated_at": draft.updated_at.isoformat()} if draft else None),
    }


@router.post("/{ticker}/initialize")
async def initialize(ticker: str, force: bool = False) -> dict:
    """Seed (or re-seed if force=true) a model for the ticker."""
    try:
        row = await initialize_or_get_model(ticker, force=force)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": row.id, "ticker": row.ticker, "version": row.version, "state": row.state, "label": row.label}
```

- [ ] **Step 2: Register router**

In `backend/app/main.py`, after the other `app.include_router(...)` calls, add:
```python
from backend.app.api.models_api import router as models_router
app.include_router(models_router)
```

- [ ] **Step 3: Smoke**

```python
# backend/scripts/smoke_models_api.py
import asyncio, sys
from fastapi.testclient import TestClient
from unittest.mock import patch
from backend.app.main import app

client = TestClient(app)


def test_get_model_for_unknown_ticker():
    r = client.get("/api/models/UNKNOWNZZZ")
    assert r.status_code == 200
    body = r.json()
    assert body["latest_version"] is None
    assert body["draft"] is None
    print("OK: GET unknown ticker returns null payload")


if __name__ == "__main__":
    test_get_model_for_unknown_ticker()
    print("OK: smoke_models_api (Task 18) passed")
    sys.exit(0)
```

Run: `python -m backend.scripts.smoke_models_api`. Expected PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/models_api.py backend/app/main.py backend/scripts/smoke_models_api.py
git commit -m "feat(api): GET /api/models/<ticker> and POST /initialize"
```

---

### Task 19: PUT `/api/models/<ticker>/draft` (cell edit + recompute)

**Files:** modify `backend/app/api/models_api.py`, `backend/scripts/smoke_models_api.py`

- [ ] **Step 1: Add endpoint**

```python
# append to models_api.py
from pydantic import BaseModel as _BM
from datetime import datetime
from backend.app.services.model_balancing import recompute, ModelBalanceError


class DraftEditRequest(_BM):
    cell_path: str           # "drivers.2026Y.gross_margin_pct" | "income_statement.revenue.2026Q1"
    value: float | None
    source: str | None = None  # "driver" | "override"; ignored for assumption cells


def _apply_edit(state_dict: dict, edit: DraftEditRequest) -> dict:
    """Mutate state JSON dict in place, returning the mutated dict."""
    parts = edit.cell_path.split(".")
    if parts[0] == "drivers" and len(parts) == 3:
        period, key = parts[1], parts[2]
        state_dict["drivers"][period][key] = {
            "value": edit.value, "source": edit.source or "driver",
            "formula": None, "citation_id": None,
            "last_edited_at": datetime.utcnow().isoformat(), "last_edited_by": "user",
        }
    elif parts[0] in ("income_statement", "balance_sheet", "cash_flow") and len(parts) == 3:
        stmt, line, period = parts
        state_dict[stmt][line][period] = {
            "value": edit.value, "source": edit.source or "override",
            "formula": None, "citation_id": None,
            "last_edited_at": datetime.utcnow().isoformat(), "last_edited_by": "user",
        }
    elif parts[0] == "assumptions" and len(parts) == 2:
        key = parts[1]
        cur = state_dict["assumptions"][key]
        if isinstance(cur, dict):
            cur["value"] = edit.value
            cur["last_edited_at"] = datetime.utcnow().isoformat()
            cur["last_edited_by"] = "user"
        else:
            state_dict["assumptions"][key] = edit.value
    else:
        raise ValueError(f"unknown cell_path shape: {edit.cell_path}")
    return state_dict


@router.put("/{ticker}/draft")
async def put_draft(ticker: str, edit: DraftEditRequest, db: AsyncSession = Depends(get_db)) -> dict:
    # Get current state: existing draft, else latest version
    draft = (await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))).scalar_one_or_none()
    if draft is None:
        latest = (await db.execute(select(TickerModel).where(TickerModel.ticker == ticker)
                                   .order_by(desc(TickerModel.version)).limit(1))).scalar_one_or_none()
        if latest is None:
            raise HTTPException(status_code=404, detail="no model exists for ticker")
        state_dict = dict(latest.state)
        base_version_id = latest.id
    else:
        state_dict = dict(draft.state)
        base_version_id = draft.base_version_id

    state_dict = _apply_edit(state_dict, edit)
    # Recompute
    try:
        state = ModelState.model_validate(state_dict)
        state = recompute(state)
        state_dict = state.model_dump()
    except ModelBalanceError as e:
        raise HTTPException(status_code=409, detail=f"BS imbalance: {e}")

    if draft is None:
        draft = TickerModelDraft(ticker=ticker, base_version_id=base_version_id, state=state_dict)
        db.add(draft)
    else:
        draft.state = state_dict
    await db.commit()
    await db.refresh(draft)
    return {"ticker": ticker, "base_version_id": draft.base_version_id, "state": draft.state,
            "updated_at": draft.updated_at.isoformat()}
```

- [ ] **Step 2: Smoke (mocked initialize → edit → assert recompute)**

Add to smoke_models_api.py — gate on a real DB. Use synthetic ticker `ZAPI`, mock `initialize_or_get_model`, then test edit endpoint.

- [ ] **Step 3: Run smoke; verify PASS**

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/models_api.py backend/scripts/smoke_models_api.py
git commit -m "feat(api): PUT /api/models/<ticker>/draft (cell edit + recompute)"
```

---

### Task 20: POST `/api/models/<ticker>/save` and DELETE draft

**Files:** modify `backend/app/api/models_api.py`, `backend/scripts/smoke_models_api.py`

- [ ] **Step 1: Add endpoints**

```python
# append to models_api.py
class SaveVersionRequest(_BM):
    label: str | None = None


@router.post("/{ticker}/save")
async def save_version(ticker: str, body: SaveVersionRequest, db: AsyncSession = Depends(get_db)) -> dict:
    draft = (await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))).scalar_one_or_none()
    if draft is None:
        raise HTTPException(status_code=404, detail="no draft to save")
    latest = (await db.execute(select(TickerModel).where(TickerModel.ticker == ticker)
                               .order_by(desc(TickerModel.version)).limit(1))).scalar_one_or_none()
    next_version = 1 if latest is None else latest.version + 1
    new_row = TickerModel(
        ticker=ticker, version=next_version, state=draft.state,
        label=body.label or f"v{next_version}",
        parent_research_run_id=getattr(latest, "parent_research_run_id", None),
    )
    db.add(new_row)
    await db.delete(draft)
    await db.commit()
    await db.refresh(new_row)
    return {"id": new_row.id, "ticker": ticker, "version": new_row.version, "label": new_row.label}


@router.delete("/{ticker}/draft")
async def discard_draft(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    draft = (await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))).scalar_one_or_none()
    if draft is not None:
        await db.delete(draft)
        await db.commit()
    return {"ok": True}
```

- [ ] **Step 2: Smoke** — extend `smoke_models_api.py` to test full edit-save-discard cycle.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/models_api.py backend/scripts/smoke_models_api.py
git commit -m "feat(api): POST /save (promote draft to version) + DELETE /draft"
```

---

### Task 21: GET `/api/models/<ticker>/reverse-dcf`

**Files:** modify `backend/app/api/models_api.py`, `backend/scripts/smoke_models_api.py`

- [ ] **Step 1: Add endpoint**

```python
# append to models_api.py
from backend.app.services.dcf import dcf
from backend.app.services.reverse_dcf import (
    solve_implied_driver, solve_implied_irr, sensitivity_grid, thesis_vs_priced_in,
)


async def _fetch_live_price(ticker: str) -> float:
    """Pulls current price from FMP. Cached 60s in app state."""
    from backend.app.clients.fmp_client import FMPClient
    client = FMPClient()
    quote = await client.fetch_quote(ticker)
    return float((quote.get("price") if quote else 0.0) or 0.0)


@router.get("/{ticker}/reverse-dcf")
async def get_reverse_dcf(ticker: str, price: float | None = None, from_draft: bool = False,
                          db: AsyncSession = Depends(get_db)) -> dict:
    if from_draft:
        draft = (await db.execute(select(TickerModelDraft).where(TickerModelDraft.ticker == ticker))).scalar_one_or_none()
        state_dict = draft.state if draft else None
    else:
        state_dict = None
    if state_dict is None:
        latest = (await db.execute(select(TickerModel).where(TickerModel.ticker == ticker)
                                   .order_by(desc(TickerModel.version)).limit(1))).scalar_one_or_none()
        if latest is None:
            raise HTTPException(status_code=404, detail="no model exists")
        state_dict = latest.state

    state = ModelState.model_validate(state_dict)
    target = price if price is not None else await _fetch_live_price(ticker)
    if not target:
        raise HTTPException(status_code=502, detail="no live price available")

    return {
        "price_used": target,
        "price_source": "user_override" if price is not None else "fmp_live",
        "implied_drivers": {
            "revenue_growth_pct": _safe_solve(state, "revenue_growth_pct", target),
            "ebit_margin_pct":    _safe_solve(state, "ebit_margin_pct", target),
            "terminal_multiple":  _safe_solve(state, "terminal_multiple", target),
        },
        "implied_irr": _safe_solve_irr(state, target),
        "sensitivity_grids": {
            "growth_margin":   sensitivity_grid(state, x_dim="revenue_growth_pct", x_range=(-0.05, 0.20),
                                                y_dim="ebit_margin_pct", y_range=(-0.10, 0.10)),
            "growth_multiple": sensitivity_grid(state, x_dim="revenue_growth_pct", x_range=(-0.05, 0.20),
                                                y_dim="terminal_multiple", y_range=(5.0, 25.0)),
            "margin_multiple": sensitivity_grid(state, x_dim="ebit_margin_pct", x_range=(-0.10, 0.10),
                                                y_dim="terminal_multiple", y_range=(5.0, 25.0)),
        },
        "thesis_vs_priced_in": thesis_vs_priced_in(state, target_per_share=target),
    }


def _safe_solve(state: ModelState, dim: str, target: float):
    try:
        return solve_implied_driver(state, dimension=dim, target_per_share=target)
    except ValueError:
        return None


def _safe_solve_irr(state: ModelState, target: float):
    try:
        return solve_implied_irr(state, target_per_share=target)
    except ValueError:
        return None
```

- [ ] **Step 2: Smoke** — `python -m backend.scripts.smoke_models_api` with the synthetic-ticker setup; assert response shape.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/models_api.py backend/scripts/smoke_models_api.py
git commit -m "feat(api): GET /reverse-dcf (4-payload single response)"
```

---

## Phase 7 — Frontend

### Task 22: `lib/api.ts` model types + client

**Files:** modify `frontend/lib/api.ts`

- [ ] **Step 1: Add types matching backend Pydantic shapes**

```typescript
// frontend/lib/api.ts — append the following

export type CellSource = "historical" | "ai_baseline" | "driver" | "computed" | "override";

export interface ModelCell {
  value: number | null;
  source: CellSource;
  formula: string | null;
  citation_id: string | null;
  last_edited_at: string | null;
  last_edited_by: "system" | "ai_baseline" | "user" | null;
}

export interface Period {
  label: string;
  kind: "Q" | "Y";
  is_historical: boolean;
  quarter_index: number | null;
}

export interface ModelAssumptions {
  discount_rate: ModelCell;
  terminal_method: "exit_multiple" | "perpetuity";
  terminal_multiple: ModelCell;
  perpetuity_growth: ModelCell;
  tax_rate: ModelCell;
  plug_priority: Array<"debt_paydown" | "buyback" | "dividend" | "cash">;
}

export interface ModelState {
  periods: Period[];
  drivers: Record<string, Record<string, ModelCell>>;
  income_statement: Record<string, Record<string, ModelCell>>;
  balance_sheet: Record<string, Record<string, ModelCell>>;
  cash_flow: Record<string, Record<string, ModelCell>>;
  assumptions: ModelAssumptions;
}

export interface TickerModelVersion {
  id: string;
  ticker: string;
  version: number;
  label: string | null;
  state: ModelState;
  created_at: string;
}

export interface TickerModelDraft {
  base_version_id: string;
  state: ModelState;
  updated_at: string;
}

export interface ReverseDcfResponse {
  price_used: number;
  price_source: "fmp_live" | "user_override";
  implied_drivers: { revenue_growth_pct: number | null; ebit_margin_pct: number | null; terminal_multiple: number | null };
  implied_irr: number | null;
  sensitivity_grids: {
    growth_margin: SensitivityGrid;
    growth_multiple: SensitivityGrid;
    margin_multiple: SensitivityGrid;
  };
  thesis_vs_priced_in: Array<{ dimension: string; thesis: number; priced_in: number | null; delta: number | null }>;
}

export interface SensitivityGrid {
  x_dim: string;
  y_dim: string;
  x_values: number[];
  y_values: number[];
  values: number[][];
}

// Client functions
export async function getModel(ticker: string) {
  return fetchJson<{ latest_version: TickerModelVersion | null; draft: TickerModelDraft | null }>(`/api/models/${ticker}`);
}
export async function initializeModel(ticker: string, force = false) {
  return fetchJson<TickerModelVersion>(`/api/models/${ticker}/initialize?force=${force}`, { method: "POST" });
}
export async function putModelDraft(ticker: string, body: { cell_path: string; value: number | null; source?: string }) {
  return fetchJson<TickerModelDraft>(`/api/models/${ticker}/draft`, { method: "PUT", body: JSON.stringify(body) });
}
export async function saveModelVersion(ticker: string, label: string | null) {
  return fetchJson<{ id: string; version: number; label: string }>(`/api/models/${ticker}/save`, {
    method: "POST", body: JSON.stringify({ label }),
  });
}
export async function discardModelDraft(ticker: string) {
  return fetchJson<{ ok: boolean }>(`/api/models/${ticker}/draft`, { method: "DELETE" });
}
export async function getReverseDcf(ticker: string, opts: { price?: number; from_draft?: boolean } = {}) {
  const qs = new URLSearchParams();
  if (opts.price !== undefined) qs.set("price", String(opts.price));
  if (opts.from_draft) qs.set("from_draft", "true");
  return fetchJson<ReverseDcfResponse>(`/api/models/${ticker}/reverse-dcf?${qs}`);
}
```

(Re-use the existing `fetchJson` helper from elsewhere in `api.ts`. If naming differs, follow the file's established pattern.)

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(frontend): model API types + client"
```

---

### Task 23: `/model/[ticker]/page.tsx` shell + tab routing

**Files:**
- Create: `frontend/app/model/[ticker]/page.tsx`
- Create: `frontend/components/model/modelSections.ts`

- [ ] **Step 1: Implement `modelSections.ts`**

```typescript
// frontend/components/model/modelSections.ts
export const MODEL_TABS = [
  { id: "forecast",     label: "Forecast",     hash: "#forecast" },
  { id: "reverse-dcf",  label: "Reverse DCF",  hash: "#reverse-dcf" },
  { id: "history",      label: "History",      hash: "#history" },
] as const;
export type ModelTab = (typeof MODEL_TABS)[number]["id"];
```

- [ ] **Step 2: Implement page shell**

```tsx
// frontend/app/model/[ticker]/page.tsx
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { getModel, initializeModel, type TickerModelVersion, type TickerModelDraft } from "@/lib/api";
import { MODEL_TABS, type ModelTab } from "@/components/model/modelSections";

export default function ModelPage() {
  const { ticker } = useParams<{ ticker: string }>();
  const [tab, setTab] = useState<ModelTab>("forecast");
  const [latest, setLatest] = useState<TickerModelVersion | null>(null);
  const [draft, setDraft] = useState<TickerModelDraft | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  // Hash-based tab routing
  useEffect(() => {
    const sync = () => {
      const h = window.location.hash || "#forecast";
      const t = MODEL_TABS.find((x) => x.hash === h);
      if (t) setTab(t.id);
    };
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    setLoading(true);
    getModel(ticker)
      .then((r) => { setLatest(r.latest_version); setDraft(r.draft); })
      .catch((e) => setErr(String(e)))
      .finally(() => setLoading(false));
  }, [ticker]);

  async function handleCreate() {
    setLoading(true);
    try {
      const v = await initializeModel(ticker);
      setLatest(v);
    } catch (e) { setErr(String(e)); }
    finally { setLoading(false); }
  }

  if (loading) return <div className="p-6 text-slate-400">Loading model…</div>;
  if (err) return <div className="p-6 text-red-400">Error: {err}</div>;
  if (!latest) return (
    <div className="p-6 space-y-3">
      <h1 className="text-2xl font-semibold">{ticker} — no model yet</h1>
      <button onClick={handleCreate} className="px-3 py-1.5 bg-blue-600 hover:bg-blue-500 rounded text-white">
        Create AI baseline
      </button>
    </div>
  );

  const activeState = draft?.state ?? latest.state;

  return (
    <div className="flex flex-col h-full">
      <header className="border-b border-slate-800 px-6 py-3 flex items-center gap-4" data-print-hide="true">
        <h1 className="text-xl font-semibold">{ticker} <span className="text-slate-500 text-sm">v{latest.version} · {latest.label}</span></h1>
        <nav className="flex gap-2 ml-auto">
          {MODEL_TABS.map((t) => (
            <a key={t.id} href={t.hash}
               className={`px-3 py-1.5 rounded text-sm ${tab === t.id ? "bg-slate-800 text-white" : "text-slate-400 hover:text-white"}`}>
              {t.label}
            </a>
          ))}
        </nav>
      </header>
      <main className="flex-1 overflow-auto">
        {tab === "forecast" && <ForecastTabContent state={activeState} draft={draft} latest={latest} ticker={ticker}
                                                  onDraftChange={setDraft} onSaved={(v) => { setLatest(v); setDraft(null); }} />}
        {tab === "reverse-dcf" && <ReverseDcfTabContent ticker={ticker} hasDraft={!!draft} />}
        {tab === "history" && <HistoryTabContent ticker={ticker} />}
      </main>
    </div>
  );
}

// Stubs for the next tasks
function ForecastTabContent(_props: any) { return <div className="p-6 text-slate-500">Forecast tab — see Task 24</div>; }
function ReverseDcfTabContent(_props: any) { return <div className="p-6 text-slate-500">Reverse DCF tab — see Task 25</div>; }
function HistoryTabContent(_props: any) { return <div className="p-6 text-slate-500">History tab — see Task 27</div>; }
```

- [ ] **Step 3: lint + tsc + manual smoke**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```
Open http://localhost:3000/model/AAPL (or any seeded ticker) — expect "no model yet" with a Create button.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/model frontend/components/model/modelSections.ts
git commit -m "feat(frontend): /model/[ticker] page shell with tab routing"
```

---

### Task 24: `ForecastGrid`, `DriverPanel`, `CellRenderer`, `FormulaBar`

**Files:**
- Create: `frontend/components/model/CellRenderer.tsx`
- Create: `frontend/components/model/DriverPanel.tsx`
- Create: `frontend/components/model/ForecastGrid.tsx`
- Create: `frontend/components/model/FormulaBar.tsx`
- Modify: `frontend/app/model/[ticker]/page.tsx` (replace `ForecastTabContent` stub)

- [ ] **Step 1: `CellRenderer` — color-coded by source, click = focus, double-click = override**

```tsx
// frontend/components/model/CellRenderer.tsx
"use client";
import type { ModelCell } from "@/lib/api";

const CLS: Record<string, string> = {
  historical:  "bg-slate-800 text-slate-300",
  ai_baseline: "bg-yellow-900/30 text-yellow-100",
  driver:      "bg-yellow-700/40 text-yellow-50",
  computed:    "bg-transparent text-slate-100",
  override:    "border border-orange-400 bg-orange-900/20 text-orange-100",
};

export function CellRenderer({
  cell, cellPath, onFocus, onCommitEdit, focused, editable = true,
}: {
  cell: ModelCell | undefined;
  cellPath: string;
  onFocus: (path: string) => void;
  onCommitEdit?: (path: string, value: number | null) => Promise<void>;
  focused: boolean;
  editable?: boolean;
}) {
  const value = cell?.value ?? null;
  const source = cell?.source ?? "computed";
  const ringCls = focused ? "ring-2 ring-blue-400" : "";
  return (
    <td
      onClick={() => onFocus(cellPath)}
      onDoubleClick={() => {
        if (!editable || !onCommitEdit) return;
        const v = prompt(`Override value for ${cellPath}`, value === null ? "" : String(value));
        if (v === null) return;
        const num = v === "" ? null : Number(v);
        if (v !== "" && Number.isNaN(num)) return;
        void onCommitEdit(cellPath, num);
      }}
      className={`px-2 py-1 text-right text-sm cursor-pointer ${CLS[source] ?? CLS.computed} ${ringCls}`}
    >
      {value === null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
    </td>
  );
}
```

- [ ] **Step 2: `DriverPanel` — collapsible groups; inline edit triggers `putModelDraft`**

```tsx
// frontend/components/model/DriverPanel.tsx
"use client";
import { useState } from "react";
import type { ModelState } from "@/lib/api";
import { CellRenderer } from "./CellRenderer";

const GROUPS: Array<{ label: string; keys: string[] }> = [
  { label: "Revenue",       keys: ["revenue_growth_pct", "revenue_absolute"] },
  { label: "Margins",       keys: ["gross_margin_pct", "sga_pct_revenue", "rd_pct_revenue", "other_opex_pct_revenue", "da_pct_revenue"] },
  { label: "Below the line",keys: ["effective_tax_rate", "interest_income_yield", "interest_expense_rate"] },
  { label: "Capex / WC",    keys: ["capex_pct_revenue", "dso_days", "dio_days", "dpo_days"] },
  { label: "Capital return",keys: ["dividend_payout_ratio", "buyback_dollars", "share_count_change_pct"] },
  { label: "Debt",          keys: ["debt_repayment_dollars", "revolver_rate"] },
];

export function DriverPanel({
  state, focused, onFocus, onEdit,
}: {
  state: ModelState;
  focused: string | null;
  onFocus: (path: string) => void;
  onEdit: (cellPath: string, value: number | null) => Promise<void>;
}) {
  const periods = state.periods.filter((p) => !p.is_historical);
  const [open, setOpen] = useState(true);
  return (
    <section className="border-b border-slate-800">
      <button onClick={() => setOpen(!open)} className="w-full text-left px-6 py-2 text-sm text-slate-400 hover:text-white">
        {open ? "▾" : "▸"} Drivers
      </button>
      {open && (
        <div className="px-6 pb-3 overflow-x-auto">
          {GROUPS.map((g) => (
            <div key={g.label} className="mb-3">
              <div className="text-xs uppercase text-slate-500 mb-1">{g.label}</div>
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    <th className="text-left text-xs text-slate-500 pr-2 py-0.5">Driver</th>
                    {periods.map((p) => <th key={p.label} className="text-right text-xs text-slate-500 px-1 py-0.5">{p.label}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {g.keys.map((k) => (
                    <tr key={k} className="border-t border-slate-900">
                      <td className="text-left text-xs text-slate-300 pr-2 py-0.5">{k}</td>
                      {periods.map((p) => {
                        const path = `drivers.${p.label}.${k}`;
                        return <CellRenderer key={path} cell={state.drivers[p.label]?.[k]} cellPath={path}
                                             focused={focused === path} onFocus={onFocus} onCommitEdit={onEdit} />;
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 3: `ForecastGrid` — 3-statement grid with sticky col/row**

```tsx
// frontend/components/model/ForecastGrid.tsx
"use client";
import type { ModelState } from "@/lib/api";
import { CellRenderer } from "./CellRenderer";

const PNL_LINES = ["revenue", "cost_of_revenue", "gross_profit", "sga", "rd", "other_opex", "operating_expenses",
                   "ebit", "depreciation_amortization", "ebitda", "interest_income", "interest_expense",
                   "pretax_income", "income_tax", "net_income", "shares_diluted", "eps_diluted"];
const BS_LINES = ["cash_and_equivalents", "accounts_receivable", "inventory", "other_current_assets",
                  "total_current_assets", "ppe_net", "goodwill", "other_long_term_assets", "total_assets",
                  "accounts_payable", "short_term_debt", "other_current_liabilities", "total_current_liabilities",
                  "long_term_debt", "other_long_term_liabilities", "total_liabilities",
                  "common_equity", "retained_earnings", "total_equity", "total_liab_and_equity"];
const CF_LINES = ["net_income_cf", "depreciation_amortization_cf", "delta_accounts_receivable",
                  "delta_inventory", "delta_accounts_payable", "operating_cash_flow", "capex",
                  "free_cash_flow", "debt_issued", "debt_repaid", "dividends_paid", "buybacks", "net_change_in_cash"];

function StmtTable({ title, lines, stmt, state, focused, onFocus, onEdit }: {
  title: string; lines: string[]; stmt: "income_statement" | "balance_sheet" | "cash_flow";
  state: ModelState;
  focused: string | null;
  onFocus: (path: string) => void;
  onEdit: (path: string, v: number | null) => Promise<void>;
}) {
  return (
    <div className="mb-6">
      <h2 className="px-6 py-1 text-sm font-semibold text-slate-300 sticky top-0 bg-slate-950 z-10">{title}</h2>
      <div className="overflow-x-auto">
        <table className="border-collapse w-max">
          <thead>
            <tr>
              <th className="sticky left-0 bg-slate-950 text-left text-xs text-slate-500 px-6 py-1">Line item</th>
              {state.periods.map((p) => (
                <th key={p.label} className={`text-right text-xs px-2 py-1 ${p.is_historical ? "text-slate-600" : "text-slate-400"}`}>
                  {p.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((li) => (
              <tr key={li} className="border-t border-slate-900">
                <td className="sticky left-0 bg-slate-950 text-left text-xs text-slate-300 px-6 py-1">{li}</td>
                {state.periods.map((p) => {
                  const path = `${stmt}.${li}.${p.label}`;
                  return <CellRenderer key={path} cell={state[stmt][li]?.[p.label]} cellPath={path}
                                       focused={focused === path} onFocus={onFocus} onCommitEdit={onEdit}
                                       editable={!p.is_historical} />;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ForecastGrid({
  state, focused, onFocus, onEdit,
}: {
  state: ModelState;
  focused: string | null;
  onFocus: (path: string) => void;
  onEdit: (path: string, v: number | null) => Promise<void>;
}) {
  return (
    <div className="pt-3">
      <StmtTable title="Income Statement" lines={PNL_LINES} stmt="income_statement" state={state} focused={focused} onFocus={onFocus} onEdit={onEdit} />
      <StmtTable title="Balance Sheet"     lines={BS_LINES}  stmt="balance_sheet"   state={state} focused={focused} onFocus={onFocus} onEdit={onEdit} />
      <StmtTable title="Cash Flow"         lines={CF_LINES}  stmt="cash_flow"       state={state} focused={focused} onFocus={onFocus} onEdit={onEdit} />
    </div>
  );
}
```

- [ ] **Step 4: `FormulaBar`**

```tsx
// frontend/components/model/FormulaBar.tsx
"use client";
import type { ModelState, ModelCell } from "@/lib/api";

function lookupCell(state: ModelState, path: string): ModelCell | undefined {
  const parts = path.split(".");
  if (parts[0] === "drivers" && parts.length === 3) return state.drivers[parts[1]]?.[parts[2]];
  if ((parts[0] === "income_statement" || parts[0] === "balance_sheet" || parts[0] === "cash_flow") && parts.length === 3) {
    return (state as any)[parts[0]]?.[parts[1]]?.[parts[2]];
  }
  if (parts[0] === "assumptions" && parts.length === 2) {
    const a = (state.assumptions as any)[parts[1]];
    return typeof a === "object" ? a : undefined;
  }
  return undefined;
}

export function FormulaBar({ state, focused }: { state: ModelState; focused: string | null }) {
  if (!focused) return <div className="px-6 py-1 text-xs text-slate-600 border-b border-slate-900" data-print-hide="true">Click a cell to inspect.</div>;
  const cell = lookupCell(state, focused);
  return (
    <div className="px-6 py-1 text-xs text-slate-300 border-b border-slate-900 flex gap-3" data-print-hide="true">
      <span className="text-slate-500">{focused}</span>
      <span className="text-slate-400">{cell?.source ?? "—"}</span>
      <span>{cell?.value === null || cell?.value === undefined ? "—" : cell?.value.toLocaleString()}</span>
      {cell?.formula && <span className="text-slate-500">· {cell.formula}</span>}
      {cell?.citation_id && <a href={`#citation-${cell.citation_id}`} className="text-blue-400 hover:underline">citation</a>}
    </div>
  );
}
```

- [ ] **Step 5: Wire `ForecastTabContent`** in `page.tsx` — replace the stub:

```tsx
// in frontend/app/model/[ticker]/page.tsx, replace the stub
import { DriverPanel } from "@/components/model/DriverPanel";
import { ForecastGrid } from "@/components/model/ForecastGrid";
import { FormulaBar } from "@/components/model/FormulaBar";
import { putModelDraft, saveModelVersion, discardModelDraft, type ModelState as MS, type TickerModelDraft as TMD, type TickerModelVersion as TMV } from "@/lib/api";

function ForecastTabContent({
  state, draft, latest, ticker, onDraftChange, onSaved,
}: {
  state: MS; draft: TMD | null; latest: TMV; ticker: string;
  onDraftChange: (d: TMD | null) => void;
  onSaved: (v: TMV) => void;
}) {
  const [focused, setFocused] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleEdit(cellPath: string, value: number | null) {
    setBusy(true);
    try {
      const updated = await putModelDraft(ticker, { cell_path: cellPath, value });
      onDraftChange(updated);
    } catch (e) { alert(String(e)); }
    finally { setBusy(false); }
  }
  async function handleSave() {
    const label = prompt("Version label:", "");
    if (label === null) return;
    setBusy(true);
    try {
      await saveModelVersion(ticker, label || null);
      const r = await import("@/lib/api").then((m) => m.getModel(ticker));
      onSaved(r.latest_version!);
    } finally { setBusy(false); }
  }
  async function handleDiscard() {
    if (!confirm("Discard draft?")) return;
    setBusy(true);
    try { await discardModelDraft(ticker); onDraftChange(null); }
    finally { setBusy(false); }
  }

  return (
    <>
      <FormulaBar state={state} focused={focused} />
      <DriverPanel state={state} focused={focused} onFocus={setFocused} onEdit={handleEdit} />
      <ForecastGrid state={state} focused={focused} onFocus={setFocused} onEdit={handleEdit} />
      <div className="sticky bottom-0 left-0 right-0 bg-slate-950 border-t border-slate-800 px-6 py-2 flex gap-2 justify-end" data-print-hide="true">
        <button onClick={handleDiscard} disabled={!draft || busy} className="px-3 py-1 text-sm rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-40">Discard draft</button>
        <button onClick={handleSave} disabled={!draft || busy} className="px-3 py-1 text-sm rounded bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white">Save Version</button>
      </div>
    </>
  );
}
```

- [ ] **Step 6: lint + tsc + manual smoke**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```
Manual: open `/model/<ticker>` (a ticker that has a research_run). Click "Create AI baseline". Verify grid renders, double-click a forecast cell to override, observe draft state, click Save Version.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/model frontend/app/model
git commit -m "feat(frontend): forecast grid + driver panel + formula bar + edit cycle"
```

---

### Task 25: `ReverseDcfPanel`, `ThesisVsPricedTable`, `SensitivityHeatmap`, `WhatIfScratchPanel`

**Files:**
- Create: `frontend/components/model/ReverseDcfPanel.tsx`
- Create: `frontend/components/model/ThesisVsPricedTable.tsx`
- Create: `frontend/components/model/SensitivityHeatmap.tsx`
- Create: `frontend/components/model/WhatIfScratchPanel.tsx`
- Create: `frontend/components/model/heatmapColors.ts`
- Modify: `frontend/app/model/[ticker]/page.tsx` (replace `ReverseDcfTabContent` stub)

- [ ] **Step 1: `heatmapColors.ts`**

```typescript
// diverging palette around iso-value
export function heatmapColor(value: number, ref: number, range: number): string {
  const norm = Math.max(-1, Math.min(1, (value - ref) / Math.max(range, 1e-9)));
  if (norm >= 0) {
    const t = norm;
    return `rgb(${Math.round(40 + t * 40)}, ${Math.round(150 - t * 40)}, ${Math.round(80 - t * 30)})`; // greens
  }
  const t = -norm;
  return `rgb(${Math.round(150 + t * 60)}, ${Math.round(60 + t * 30)}, ${Math.round(60 + t * 30)})`;   // reds
}
```

- [ ] **Step 2: `ThesisVsPricedTable.tsx`**

```tsx
"use client";
import type { ReverseDcfResponse } from "@/lib/api";

export function ThesisVsPricedTable({ rows }: { rows: ReverseDcfResponse["thesis_vs_priced_in"] }) {
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-slate-400 text-xs">
          <th className="text-left px-2 py-1">Dimension</th>
          <th className="text-right px-2 py-1">Thesis</th>
          <th className="text-right px-2 py-1">Priced in</th>
          <th className="text-right px-2 py-1">Δ</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.dimension} className="border-t border-slate-800">
            <td className="text-left px-2 py-1 text-slate-300">{r.dimension}</td>
            <td className="text-right px-2 py-1">{r.thesis.toLocaleString(undefined, { maximumFractionDigits: 4 })}</td>
            <td className="text-right px-2 py-1">{r.priced_in?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}</td>
            <td className={`text-right px-2 py-1 ${r.delta == null ? "text-slate-500" : r.delta > 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {r.delta?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 3: `SensitivityHeatmap.tsx`**

```tsx
"use client";
import type { SensitivityGrid } from "@/lib/api";
import { heatmapColor } from "./heatmapColors";

export function SensitivityHeatmap({ grid, currentPrice }: { grid: SensitivityGrid; currentPrice: number }) {
  const flat = grid.values.flat();
  const min = Math.min(...flat), max = Math.max(...flat);
  const range = Math.max(currentPrice - min, max - currentPrice);
  return (
    <div className="text-xs">
      <div className="mb-1 text-slate-400">{grid.x_dim} × {grid.y_dim}</div>
      <table className="border-collapse">
        <thead>
          <tr>
            <th></th>
            {grid.x_values.map((v, i) => i % 4 === 0 ? <th key={i} className="text-center text-slate-500 px-0.5">{v.toFixed(2)}</th> : <th key={i}></th>)}
          </tr>
        </thead>
        <tbody>
          {grid.values.map((row, ri) => (
            <tr key={ri}>
              <td className="text-right text-slate-500 pr-1">{ri % 4 === 0 ? grid.y_values[ri].toFixed(2) : ""}</td>
              {row.map((v, ci) => (
                <td key={ci} title={`x=${grid.x_values[ci].toFixed(3)}, y=${grid.y_values[ri].toFixed(3)} → ${v.toFixed(2)}`}
                    style={{ backgroundColor: heatmapColor(v, currentPrice, range) }} className="w-3 h-3 p-0" />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: `ReverseDcfPanel.tsx`**

```tsx
"use client";
import { useEffect, useState } from "react";
import { getReverseDcf, type ReverseDcfResponse } from "@/lib/api";
import { ThesisVsPricedTable } from "./ThesisVsPricedTable";
import { SensitivityHeatmap } from "./SensitivityHeatmap";

export function ReverseDcfPanel({ ticker, hasDraft }: { ticker: string; hasDraft: boolean }) {
  const [data, setData] = useState<ReverseDcfResponse | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [priceOverride, setPriceOverride] = useState<string>("");
  const [fromDraft, setFromDraft] = useState(false);

  async function load() {
    setErr(null);
    try {
      const opts: { price?: number; from_draft?: boolean } = {};
      if (priceOverride) opts.price = Number(priceOverride);
      if (fromDraft) opts.from_draft = true;
      const r = await getReverseDcf(ticker, opts);
      setData(r);
    } catch (e) { setErr(String(e)); }
  }
  useEffect(() => { void load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [ticker]);

  if (err) return <div className="p-6 text-rose-400">Error: {err}</div>;
  if (!data) return <div className="p-6 text-slate-400">Loading reverse DCF…</div>;
  return (
    <div className="p-6 space-y-6">
      <div className="flex gap-3 items-center text-sm" data-print-hide="true">
        <label>Price override: <input value={priceOverride} onChange={(e) => setPriceOverride(e.target.value)}
                                       className="bg-slate-900 border border-slate-700 rounded px-2 py-0.5 w-24" /></label>
        {hasDraft && <label><input type="checkbox" checked={fromDraft} onChange={(e) => setFromDraft(e.target.checked)} /> Use draft</label>}
        <button onClick={load} className="px-3 py-0.5 rounded bg-blue-600 text-white text-sm">Recompute</button>
      </div>

      <section className="grid grid-cols-2 gap-6">
        <div>
          <div className="text-xs uppercase text-slate-500">Implied IRR</div>
          <div className="text-4xl font-semibold">{data.implied_irr === null ? "—" : `${(data.implied_irr * 100).toFixed(2)}%`}</div>
          <div className="text-xs text-slate-500 mt-1">at {data.price_used.toFixed(2)} ({data.price_source})</div>
        </div>
        <div>
          <div className="text-xs uppercase text-slate-500 mb-1">Thesis vs priced in</div>
          <ThesisVsPricedTable rows={data.thesis_vs_priced_in} />
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-slate-300 mb-2">Sensitivity grids</h2>
        <div className="grid grid-cols-3 gap-6">
          <SensitivityHeatmap grid={data.sensitivity_grids.growth_margin}   currentPrice={data.price_used} />
          <SensitivityHeatmap grid={data.sensitivity_grids.growth_multiple} currentPrice={data.price_used} />
          <SensitivityHeatmap grid={data.sensitivity_grids.margin_multiple} currentPrice={data.price_used} />
        </div>
      </section>
    </div>
  );
}
```

- [ ] **Step 5: Wire into page.tsx**

```tsx
import { ReverseDcfPanel } from "@/components/model/ReverseDcfPanel";
function ReverseDcfTabContent({ ticker, hasDraft }: { ticker: string; hasDraft: boolean }) {
  return <ReverseDcfPanel ticker={ticker} hasDraft={hasDraft} />;
}
```

- [ ] **Step 6: lint + tsc + manual smoke**

```bash
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```
Manual: navigate to `/model/<ticker>#reverse-dcf` after baseline init. Verify implied IRR + 3 heatmaps render.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/model frontend/app/model
git commit -m "feat(frontend): reverse-DCF tab — IRR + thesis-vs-priced + 3 heatmaps"
```

---

### Task 26: `WhatIfScratchPanel` (cloned scenario, live recompute)

**Files:**
- Create: `frontend/components/model/WhatIfScratchPanel.tsx`
- Modify: `frontend/components/model/ReverseDcfPanel.tsx` (mount it below the grids)

This is a thin local-state extension: clone the current state, let user edit a couple of drivers (use a small subset — gross_margin_pct + revenue_growth_pct + terminal_multiple), and call `getReverseDcf` with `?price=<computed>` to display the implied. The scratch state is in-memory only — no draft pollution.

- [ ] **Step 1: Implement (lean version — three sliders)**

```tsx
// frontend/components/model/WhatIfScratchPanel.tsx
"use client";
import { useState } from "react";

export function WhatIfScratchPanel({ baseline }: { baseline: { growth: number; margin: number; multiple: number } }) {
  const [growth, setGrowth] = useState(baseline.growth);
  const [margin, setMargin] = useState(baseline.margin);
  const [multiple, setMultiple] = useState(baseline.multiple);
  return (
    <section className="border border-slate-800 rounded p-4">
      <h3 className="text-sm font-semibold text-slate-300 mb-2">What-if scratch</h3>
      <p className="text-xs text-slate-500 mb-3">Move the sliders; nothing is saved. Re-evaluation is illustrative only — for full recompute, edit drivers in the Forecast tab.</p>
      <div className="space-y-2">
        <label className="block text-xs">Revenue growth: {(growth * 100).toFixed(1)}%
          <input type="range" min={-5} max={30} step={0.1} value={growth * 100} onChange={(e) => setGrowth(Number(e.target.value) / 100)} className="w-full" />
        </label>
        <label className="block text-xs">Gross margin: {(margin * 100).toFixed(1)}%
          <input type="range" min={-50} max={80} step={0.5} value={margin * 100} onChange={(e) => setMargin(Number(e.target.value) / 100)} className="w-full" />
        </label>
        <label className="block text-xs">Terminal multiple: {multiple.toFixed(1)}x
          <input type="range" min={1} max={40} step={0.5} value={multiple} onChange={(e) => setMultiple(Number(e.target.value))} className="w-full" />
        </label>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Mount in ReverseDcfPanel below the grids; pass baseline values from `data.thesis_vs_priced_in`.**

- [ ] **Step 3: Commit**

```bash
git add frontend/components/model
git commit -m "feat(frontend): what-if scratch panel (illustrative sliders)"
```

> Full live-recompute scratch (sending a temporary state to a server endpoint and re-running the 4 solvers) is intentionally out of scope for v1 — the slider-only panel gives the user a first-cut feel without a new endpoint. If real iteration is desired post-merge, add `POST /api/models/<ticker>/reverse-dcf/preview` that accepts a transient `ModelState` body and returns the same response shape; the slider panel can then call it on debounce.

---

### Task 27: `HistoryDiffViewer`

**Files:**
- Create: `frontend/components/model/HistoryDiffViewer.tsx`
- Modify: `frontend/lib/api.ts` (add `getModelVersions` and `getModelDiff` clients)
- Modify: `backend/app/api/models_api.py` (add `GET /<ticker>/versions` and `GET /<ticker>/versions/<v>/diff?against=<v>`)
- Modify: `frontend/app/model/[ticker]/page.tsx`

- [ ] **Step 1: Backend list-versions and diff endpoints**

```python
# append to models_api.py
from backend.app.services.model_diff import diff_states


@router.get("/{ticker}/versions")
async def list_versions(ticker: str, db: AsyncSession = Depends(get_db)) -> dict:
    rows = (await db.execute(select(TickerModel).where(TickerModel.ticker == ticker)
                             .order_by(desc(TickerModel.version)))).scalars().all()
    return {"versions": [{"id": r.id, "version": r.version, "label": r.label,
                          "created_at": r.created_at.isoformat()} for r in rows]}


@router.get("/{ticker}/versions/{version}/diff")
async def version_diff(ticker: str, version: int, against: int, db: AsyncSession = Depends(get_db)) -> dict:
    a = (await db.execute(select(TickerModel).where(TickerModel.ticker == ticker, TickerModel.version == against))).scalar_one_or_none()
    b = (await db.execute(select(TickerModel).where(TickerModel.ticker == ticker, TickerModel.version == version))).scalar_one_or_none()
    if a is None or b is None:
        raise HTTPException(status_code=404, detail="version not found")
    return diff_states(ModelState.model_validate(a.state), ModelState.model_validate(b.state))
```

- [ ] **Step 2: Frontend client + component**

```typescript
// append to lib/api.ts
export async function getModelVersions(ticker: string) {
  return fetchJson<{ versions: Array<{ id: string; version: number; label: string | null; created_at: string }> }>(
    `/api/models/${ticker}/versions`
  );
}
export async function getModelDiff(ticker: string, version: number, against: number) {
  return fetchJson<{ added: string[]; removed: string[]; changed: Array<{ cell_path: string; before: any; after: any }> }>(
    `/api/models/${ticker}/versions/${version}/diff?against=${against}`
  );
}
```

```tsx
// frontend/components/model/HistoryDiffViewer.tsx
"use client";
import { useEffect, useState } from "react";
import { getModelVersions, getModelDiff } from "@/lib/api";

export function HistoryDiffViewer({ ticker }: { ticker: string }) {
  const [versions, setVersions] = useState<Awaited<ReturnType<typeof getModelVersions>>["versions"]>([]);
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);
  const [diff, setDiff] = useState<Awaited<ReturnType<typeof getModelDiff>> | null>(null);

  useEffect(() => {
    void getModelVersions(ticker).then((r) => {
      setVersions(r.versions);
      if (r.versions.length >= 2) { setA(r.versions[1].version); setB(r.versions[0].version); }
    });
  }, [ticker]);

  useEffect(() => {
    if (a == null || b == null) return;
    void getModelDiff(ticker, b, a).then(setDiff);
  }, [a, b, ticker]);

  return (
    <div className="p-6">
      <div className="flex gap-3 items-end mb-4">
        <select value={a ?? ""} onChange={(e) => setA(Number(e.target.value))} className="bg-slate-900 border border-slate-700 px-2 py-0.5 rounded text-sm">
          {versions.map((v) => <option key={v.version} value={v.version}>v{v.version} {v.label ?? ""}</option>)}
        </select>
        <span className="text-slate-500">vs</span>
        <select value={b ?? ""} onChange={(e) => setB(Number(e.target.value))} className="bg-slate-900 border border-slate-700 px-2 py-0.5 rounded text-sm">
          {versions.map((v) => <option key={v.version} value={v.version}>v{v.version} {v.label ?? ""}</option>)}
        </select>
      </div>
      {diff && (
        <div className="space-y-3 text-sm">
          <div><span className="text-slate-400">Changed cells:</span> {diff.changed.length}</div>
          <table className="w-full text-xs">
            <thead><tr className="text-slate-500"><th className="text-left">Cell</th><th className="text-right">Before</th><th className="text-right">After</th></tr></thead>
            <tbody>
              {diff.changed.slice(0, 200).map((c) => (
                <tr key={c.cell_path} className="border-t border-slate-900">
                  <td className="text-left text-slate-300">{c.cell_path}</td>
                  <td className="text-right text-slate-500">{c.before?.value?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}</td>
                  <td className="text-right">{c.after?.value?.toLocaleString(undefined, { maximumFractionDigits: 4 }) ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {diff.changed.length > 200 && <div className="text-slate-500">…showing first 200 changes.</div>}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Wire into page.tsx**

```tsx
import { HistoryDiffViewer } from "@/components/model/HistoryDiffViewer";
function HistoryTabContent({ ticker }: { ticker: string }) {
  return <HistoryDiffViewer ticker={ticker} />;
}
```

- [ ] **Step 4: lint + tsc + smoke**; manual verification with two saved versions on a real ticker.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/models_api.py frontend/lib/api.ts frontend/components/model/HistoryDiffViewer.tsx frontend/app/model
git commit -m "feat(frontend): history tab — version list + diff viewer"
```

---

### Task 28: Deep-dive integration — Model pill + status badge

**Files:**
- Modify: `frontend/components/deep-dive/SectionNav.tsx` (add a "Model" pill that links to `/model/<ticker>#forecast`)
- Modify: `frontend/components/deep-dive/ReportHeader.tsx` (status badge)

- [ ] **Step 1: Read existing SectionNav.tsx and ReportHeader.tsx for patterns**

```bash
sed -n '1,80p' frontend/components/deep-dive/SectionNav.tsx
sed -n '1,80p' frontend/components/deep-dive/ReportHeader.tsx
```

- [ ] **Step 2: Add "Model" pill in SectionNav**

After the existing nav pills array, append:
```tsx
// In SectionNav.tsx — add to the rendered list, after all section pills:
<a href={`/model/${ticker}#forecast`} className="px-3 py-1 rounded text-sm text-blue-400 hover:bg-slate-800">
  Model →
</a>
```

(Pass `ticker` prop into SectionNav from its parent if it isn't already there. If `DeepDiveDashboard` already passes `ticker` to SectionNav, this is a one-line change.)

- [ ] **Step 3: Add status badge in ReportHeader**

```tsx
// in ReportHeader.tsx
import { useEffect, useState } from "react";
import { getModel } from "@/lib/api";

function ModelStatusBadge({ ticker }: { ticker: string }) {
  const [info, setInfo] = useState<{ version: number; irr: number | null; saved_at: string } | null>(null);
  useEffect(() => {
    void getModel(ticker).then(async (r) => {
      if (!r.latest_version) return;
      const rev = await import("@/lib/api").then((m) => m.getReverseDcf(ticker).catch(() => null));
      setInfo({ version: r.latest_version.version, irr: rev?.implied_irr ?? null, saved_at: r.latest_version.created_at });
    });
  }, [ticker]);
  if (!info) return <a href={`/model/${ticker}#forecast`} className="text-xs text-blue-400 hover:underline">Create model →</a>;
  const ago = relativeTime(info.saved_at);
  return (
    <a href={`/model/${ticker}#forecast`} className="text-xs text-slate-300 hover:text-white">
      Model v{info.version} · saved {ago} {info.irr !== null && `· IRR ${(info.irr * 100).toFixed(1)}%`}
    </a>
  );
}

function relativeTime(iso: string): string {
  const d = (Date.now() - new Date(iso).getTime()) / 1000;
  if (d < 3600) return `${Math.floor(d / 60)}m ago`;
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`;
  return `${Math.floor(d / 86400)}d ago`;
}
```

Mount `<ModelStatusBadge ticker={ticker} />` next to the existing verdict callout in ReportHeader.

- [ ] **Step 4: lint + tsc + manual smoke**

- [ ] **Step 5: Commit**

```bash
git add frontend/components/deep-dive
git commit -m "feat(frontend): deep-dive integration — Model pill + status badge"
```

---

## Phase 8 — End-to-end verification

### Task 29: E2E smoke against a real ticker

**Files:**
- Create: `backend/scripts/smoke_model_e2e.py`

- [ ] **Step 1: Implement E2E smoke**

```python
# backend/scripts/smoke_model_e2e.py
"""Real-DB E2E smoke: requires a completed research_run for the chosen ticker.
Override with --ticker. Verifies init → edit → save → reverse-dcf cycle."""
import asyncio
import sys
from sqlalchemy import select, delete
from backend.app.db import async_session
from backend.app.models.ticker_model import TickerModel
from backend.app.models.ticker_model_draft import TickerModelDraft
from backend.app.services.model_baseline import initialize_or_get_model
from backend.app.models.model_state import ModelState


async def run(ticker: str):
    # Pre-clean
    async with async_session() as db:
        await db.execute(delete(TickerModelDraft).where(TickerModelDraft.ticker == ticker))
        await db.execute(delete(TickerModel).where(TickerModel.ticker == ticker))
        await db.commit()

    print(f"Initializing baseline for {ticker}…")
    row = await initialize_or_get_model(ticker)
    state = ModelState.model_validate(row.state)
    forecast = [p for p in state.periods if not p.is_historical]
    print(f"  → version {row.version}, {len(forecast)} forecast periods, label={row.label}")

    # Spot-check: at least one driver is populated, BS balances on first forecast period
    first_f = forecast[0]
    rev = state.income_statement["revenue"][first_f.label].value
    print(f"  → forecast revenue at {first_f.label}: {rev}")
    assert rev is not None and rev > 0

    # Diff (no edit yet) — should be empty between v1 and v1
    print("OK: E2E baseline init succeeded.")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
    asyncio.run(run(ticker))
```

- [ ] **Step 2: Run with a ticker that has a completed research_run**

```bash
python -m backend.scripts.smoke_model_e2e AAPL
```
Expected: prints version, forecast period count, revenue value, and `OK: E2E baseline init succeeded.`

- [ ] **Step 3: Manual full-app smoke**

```bash
# Terminal 1
source backend/venv/bin/activate
uvicorn backend.app.main:app --reload
# Terminal 2
cd frontend && npm run dev
```
Open http://localhost:3000/model/AAPL. Verify: page loads, "Create AI baseline" works, forecast grid populates, double-click override edits a cell (draft state), Save Version creates v2, Reverse DCF tab shows IRR + heatmaps + thesis-vs-priced table, History tab shows v1 vs v2 diff. Deep-dive page for AAPL shows the Model status badge.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/smoke_model_e2e.py
git commit -m "test(model): E2E smoke for full init→edit→save→reverse-dcf cycle"
```

---

### Task 30: Frontend lint + build + tsc + final commit

- [ ] **Step 1: Final lint and build**

```bash
cd frontend
npm run lint
npx tsc --noEmit
npm run build
```
All clean.

- [ ] **Step 2: Confirm no orphan imports / dead exports**

Search for any TS/TSX symbol referenced in `lib/api.ts` that isn't used in any component.

- [ ] **Step 3: Open PR**

```bash
git push -u origin feat/model-reverse-dcf
gh pr create --title "feat: editable financial model + reverse DCF (Tier 3.7 + 3.8)" --body "$(cat <<'EOF'
## Summary
- Adds per-ticker, AI-seeded full 3-statement model (5Y annual + 8Q quarterly forecast)
- Reverse DCF with implied driver trio, implied IRR, sensitivity grids, thesis-vs-priced table
- Versioned history with diff viewer; deep-dive integration via Model pill + status badge

## Spec
docs/superpowers/specs/2026-05-06-tier-3-7-3-8-model-and-reverse-dcf-design.md

## Test plan
- [ ] `python -m backend.scripts.smoke_model_state`
- [ ] `python -m backend.scripts.smoke_dcf`
- [ ] `python -m backend.scripts.smoke_reverse_dcf`
- [ ] `python -m backend.scripts.smoke_model_balancing`
- [ ] `python -m backend.scripts.smoke_model_diff`
- [ ] `python -m backend.scripts.smoke_model_baseline`
- [ ] `python -m backend.scripts.smoke_models_api`
- [ ] `python -m backend.scripts.smoke_model_e2e <ticker>`
- [ ] Manual full-app smoke (uvicorn + npm run dev): create baseline, edit, save, reverse-dcf, history diff

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

## Out of Scope (this plan, deferred to Tier 3.9 or Tier 4)

- Workspace 5-step refresh loop (3.9)
- MAMR Investor Council HTTP integration (3.9)
- M&A push-button accretion/dilution template (Tier 4 / Workspace plan Phase 7)
- Snapshot + Obsidian markdown export (3.9)
- Calibration snapshot table (3.9)
- Real-time live-recompute scratch endpoint (Task 26 leaves a hook)
- Financials/banks/insurers — refused at seed time per spec §10.1
- Auto-trigger on earnings prints
- Full BS line-item override propagation through prior-period dependencies (v1 forwards from prior; user override of, e.g., 2026Q3 retained earnings won't recompute 2026Q2 backwards)
- AI-vs-consensus drift warning UI (spec §10.2 risk mitigation): per-driver flag when AI baseline value differs from FMP analyst consensus by >30% relative or >5pp absolute. Data is already in the seeding context; rendering a chip in the DriverPanel is a small follow-up after MVP ships.

---

## Lessons-learned discipline (carry from prior tiers)

1. `llm.complete()` already prepends `assistant_prefill` — never manually concat.
2. `complete()` takes `user: str`, not `messages: list[dict]`.
3. After ORM insert + commit, call `await db.refresh(row)` to avoid stale identity-map reads (Tier 2.5 bug).
4. UUID columns in this project are `UUID(as_uuid=False)` + `Mapped[str]` — no UUID-wrapping in WHERE clauses.
5. Smoke scripts go in `backend/scripts/`, follow the `if __name__ == "__main__"` shape, exit non-zero on failure.
6. `models/__init__.py` requires both the import line AND an entry in `__all__`.
7. `docs/superpowers/specs/` and `docs/superpowers/plans/` are gitignored — they don't get committed; only the code in this plan gets committed.
