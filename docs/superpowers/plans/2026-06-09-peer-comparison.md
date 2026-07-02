# Peer Comparison Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the buried `peer_comp.py` table builder to a first-class product surface — a Peers tab on `/company/[ticker]` and a standalone `/compare` page — with an expanded deterministic metric set and a persisted, editable peer set per ticker.

**Architecture:** Approach A from the spec (`docs/superpowers/specs/2026-06-09-peer-comparison-design.md`): evolve `services/peer_comp.py` in place as the single shared builder used by the new `/api/peers` router, the `/compare` page, and the workspace differentiation step. Schemas move to `models/peer_comp.py` (re-exported from `workspace_schemas.py`). New `peer_sets` table auto-seeded from filing-extracted competitors ∪ a new FMP stock-peers client method.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic (backend), stdlib `unittest` (tests), Next.js 16 App Router + React 19 + Tailwind v4 (frontend).

---

## Conventions you must follow (this repo is particular)

- Backend imports are **absolute from project root**: `from backend.app.x import y`. Run everything from project root with the venv active: `source backend/venv/bin/activate`.
- Tests: stdlib unittest, **no pytest**. Run: `python -m unittest backend.tests.<module> -v` from project root. API tests set env vars via `os.environ.setdefault(...)` before importing app modules (copy the block from `backend/tests/test_themes_api.py`).
- Every FMP client method returns `tuple[data, Citation]`.
- Ticker path params use `ticker: Ticker = Depends(TickerPath)` from `backend/app/models/ticker.py`.
- Frontend: every backend call goes through `frontend/lib/api.ts` (`apiFetch` helper, `BASE` const). Light-theme CSS variable tokens (`var(--surface)`, `var(--text)`, `var(--text-muted)`, `var(--border)`, `var(--primary)`, `var(--accent-bg)`, `var(--surface-alt)`, `var(--success)`, `var(--error)`) — no hardcoded slate colors.
- **Next.js 16 warning** (from `frontend/AGENTS.md`): before writing any frontend page, read the relevant guide in `frontend/node_modules/next/dist/docs/` — APIs may differ from training data. Specifically check `useSearchParams` + Suspense requirements before Task 11.
- Frequent commits, one per task minimum. Commit messages follow existing style: `feat(peers): ...`, `fix(...): ...`, `test(...): ...`.

## File structure (what gets created/modified)

```
backend/app/models/peer_comp.py            CREATE — PeerCompRow/PeerCompTable/PeerError (moved + widened)
backend/app/models/peer_set.py             CREATE — PeerSet ORM (peer_sets table)
backend/app/models/__init__.py             MODIFY — export PeerSet (alembic metadata)
backend/app/models/workspace_schemas.py    MODIFY — delete 3 classes, re-export from peer_comp
backend/app/services/peer_comp.py          MODIFY — widen METRIC_FIELDS, 4-endpoint _fetch_one
backend/app/services/peer_sets.py          CREATE — seed/update/peers_for_ticker
backend/app/services/workspace_steps.py    MODIFY — _fetch_resolved_peers delegates to peers_for_ticker
backend/app/clients/fmp.py                 MODIFY — add get_stock_peers
backend/app/api/peers.py                   CREATE — /api/peers router
backend/app/main.py                        MODIFY — register router
backend/migrations/versions/<new>.py       CREATE — peer_sets table
backend/tests/test_peer_comp_schemas.py    CREATE
backend/tests/test_peer_comp.py            MODIFY — rewrite with 4-endpoint fake FMP
backend/tests/test_fmp_stock_peers.py      CREATE
backend/tests/test_peer_sets.py            CREATE
backend/tests/test_peers_api.py            CREATE
frontend/lib/api.ts                        MODIFY — widen PeerCompRow, add peersApi
frontend/components/peers/PeerCompTable.tsx CREATE — shared grouped table
frontend/components/peers/PeerSetEditor.tsx CREATE — chip editor
frontend/components/company/TabStrip.tsx   MODIFY — add Peers tab
frontend/app/company/[ticker]/peers/page.tsx CREATE
frontend/app/compare/page.tsx              CREATE
CLAUDE.md, TODO.md                         MODIFY — docs (final task)
```

---

### Task 0: Branch setup

- [ ] **Step 1: Create the feature branch off main**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
git checkout main && git pull
git checkout -b feat/peer-comparison
source backend/venv/bin/activate
```

Expected: on branch `feat/peer-comparison`, clean tree. (If the workspace-robustness-pack branch hasn't merged yet, that's fine — this feature is independent of it.)

- [ ] **Step 2: Baseline test run**

```bash
python -m unittest backend.tests.test_peer_comp backend.tests.test_step_differentiation backend.tests.test_workspace_schemas -v
```

Expected: all PASS. If not, stop and report — don't build on a red baseline.

---

### Task 1: Move + widen the peer-comp schemas

**Files:**
- Create: `backend/app/models/peer_comp.py`
- Modify: `backend/app/models/workspace_schemas.py` (delete the 3 class defs in the "Step 5" section, add re-export import)
- Test: `backend/tests/test_peer_comp_schemas.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_peer_comp_schemas.py`:

```python
"""Pins the schema move (models/peer_comp.py) + backward compatibility:
old persisted DifferentiationOutput JSON (pre-widening, no new fields)
must still validate, and workspace_schemas must re-export the names."""

import unittest


class SchemaMoveTests(unittest.TestCase):
    def test_new_module_exports(self):
        from backend.app.models.peer_comp import (  # noqa: F401
            PeerCompRow,
            PeerCompTable,
            PeerError,
        )

    def test_workspace_schemas_reexports_same_classes(self):
        from backend.app.models import peer_comp, workspace_schemas

        self.assertIs(workspace_schemas.PeerCompRow, peer_comp.PeerCompRow)
        self.assertIs(workspace_schemas.PeerCompTable, peer_comp.PeerCompTable)
        self.assertIs(workspace_schemas.PeerError, peer_comp.PeerError)

    def test_old_persisted_differentiation_output_still_validates(self):
        """A step_outputs payload persisted before the widening (only the
        original 10 metric fields) must round-trip through the schema."""
        from backend.app.models.workspace_schemas import DifferentiationOutput

        old_row = {
            "ticker": "NVDA", "pe": 30.0, "ev_ebitda": 25.0, "p_b": 12.0,
            "p_fcf": 28.0, "p_s": 20.0, "roe": 0.5, "revenue_yoy": 0.6,
            "eps_yoy": 0.8, "gross_margin": None, "ebitda_margin": None,
        }
        old_payload = {
            "peer_comp": {
                "focus_ticker": "NVDA",
                "rows": [old_row],
                "median": {"ticker": "__median__"},
                "delta_vs_median_pct": {"ticker": "__delta__"},
            },
            "read_throughs": [],
            "per_peer_errors": [],
        }
        out = DifferentiationOutput.model_validate(old_payload)
        self.assertEqual(out.peer_comp.focus_ticker, "NVDA")
        # New fields default to None on old data
        self.assertIsNone(out.peer_comp.rows[0].peg)
        self.assertIsNone(out.peer_comp.rows[0].market_cap)

    def test_new_fields_accept_values(self):
        from backend.app.models.peer_comp import PeerCompRow

        row = PeerCompRow(
            ticker="NVDA", peg=1.2, operating_margin=0.35, fcf_margin=0.30,
            roic=0.4, roa=0.3, market_cap=2.5e12,
        )
        self.assertEqual(row.peg, 1.2)
        self.assertEqual(row.market_cap, 2.5e12)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest backend.tests.test_peer_comp_schemas -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.models.peer_comp'`

- [ ] **Step 3: Create `backend/app/models/peer_comp.py`**

```python
"""Peer comparison schemas — shared by the peers API, /compare, and the
workspace differentiation step.

Moved out of workspace_schemas.py (2026-06-09) so the product surface and
the workspace step share one source of truth. workspace_schemas re-exports
these names for backward compatibility — old persisted step_outputs JSONB
(without the post-move optional fields) still validates because every new
field defaults to None.

Margin / growth / return values are ratios (0.46 = 46%), matching the FMP
wire format. market_cap is absolute USD.
"""
from pydantic import BaseModel, Field


class PeerCompRow(BaseModel):
    """A single row in the peer comparison table."""

    ticker: str = Field(
        description="The peer ticker (or focus ticker for the highlighted row)."
    )
    # Valuation
    pe: float | None = Field(default=None, description="Price-to-earnings.")
    ev_ebitda: float | None = Field(default=None, description="EV/EBITDA.")
    p_b: float | None = Field(default=None, description="Price-to-book.")
    p_fcf: float | None = Field(default=None, description="Price-to-FCF.")
    p_s: float | None = Field(default=None, description="Price-to-sales.")
    peg: float | None = Field(default=None, description="PEG ratio.")
    # Growth
    revenue_yoy: float | None = Field(
        default=None, description="Revenue YoY growth %."
    )
    eps_yoy: float | None = Field(
        default=None, description="EPS YoY growth %."
    )
    # Margins
    gross_margin: float | None = Field(
        default=None, description="Gross margin %."
    )
    operating_margin: float | None = Field(
        default=None, description="Operating margin %."
    )
    ebitda_margin: float | None = Field(
        default=None, description="EBITDA margin %."
    )
    fcf_margin: float | None = Field(
        default=None, description="Free-cash-flow margin %."
    )
    # Returns
    roe: float | None = Field(default=None, description="Return on equity.")
    roic: float | None = Field(
        default=None, description="Return on invested capital."
    )
    roa: float | None = Field(
        default=None, description="Return on (tangible) assets."
    )
    # Context
    market_cap: float | None = Field(
        default=None, description="Market capitalization, USD."
    )


class PeerCompTable(BaseModel):
    """The full peer comparison table."""

    focus_ticker: str = Field(description="Focus company ticker.")
    rows: list[PeerCompRow] = Field(
        default_factory=list, description="Peer rows (focus row first)."
    )
    median: PeerCompRow = Field(
        description="Computed peer median (focus excluded)."
    )
    delta_vs_median_pct: PeerCompRow = Field(
        description="Focus row deltas vs. median (all metrics in %)."
    )


class PeerError(BaseModel):
    """Error during peer resolution or data fetch."""

    peer_ticker: str = Field(description="Peer ticker that failed.")
    error_message: str = Field(description="Error detail.")
```

- [ ] **Step 4: Edit `backend/app/models/workspace_schemas.py`**

Delete the three class definitions `PeerCompRow`, `PeerCompTable`, `PeerError` (they sit under the `# ── Step 5: Differentiation (Peer Comp + Read-Throughs) ──` comment, roughly lines 267–312). In their place, directly under that section comment, put:

```python
# PeerCompRow / PeerCompTable / PeerError moved to models/peer_comp.py
# (2026-06-09) — re-exported here so existing imports keep working.
from backend.app.models.peer_comp import (  # noqa: F401, E402
    PeerCompRow,
    PeerCompTable,
    PeerError,
)
```

Leave `DifferentiationOutput` untouched — it references `PeerCompTable` and `PeerError` by name, which now resolve via the re-export.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m unittest backend.tests.test_peer_comp_schemas backend.tests.test_workspace_schemas backend.tests.test_step_differentiation backend.tests.test_workspace_step_outputs_validation -v
```

Expected: all PASS (the move is invisible to existing consumers).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/peer_comp.py backend/app/models/workspace_schemas.py backend/tests/test_peer_comp_schemas.py
git commit -m "refactor(peers): move PeerComp schemas to models/peer_comp.py with widened optional fields"
```

---

### Task 2: Widen the table builder to 4 FMP endpoints

**Files:**
- Modify: `backend/app/services/peer_comp.py`
- Test: `backend/tests/test_peer_comp.py` (full rewrite — existing tests must mock the two new endpoints)

- [ ] **Step 1: Rewrite the test file (failing first)**

Replace the entire contents of `backend/tests/test_peer_comp.py` with:

```python
import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.peer_comp import build_peer_comp_table

# Per-ticker fake payloads for the four endpoints _fetch_one now hits.
KM = {
    "NVDA": {"peRatioTTM": 30.0, "enterpriseValueOverEBITDATTM": 25.0,
             "priceToBookRatioTTM": 12.0, "priceToFreeCashFlowsRatioTTM": 28.0,
             "priceToSalesRatioTTM": 20.0, "pegRatioTTM": 1.1, "roeTTM": 0.5,
             "roicTTM": 0.4, "returnOnTangibleAssetsTTM": 0.3},
    "AMD":  {"peRatioTTM": 40.0, "enterpriseValueOverEBITDATTM": 28.0,
             "priceToBookRatioTTM": 5.0, "priceToFreeCashFlowsRatioTTM": 35.0,
             "priceToSalesRatioTTM": 8.0, "pegRatioTTM": 1.5, "roeTTM": 0.2,
             "roicTTM": 0.15, "returnOnTangibleAssetsTTM": 0.1},
    "INTC": {"peRatioTTM": 18.0, "enterpriseValueOverEBITDATTM": 10.0,
             "priceToBookRatioTTM": 1.5, "priceToFreeCashFlowsRatioTTM": 15.0,
             "priceToSalesRatioTTM": 2.5, "pegRatioTTM": 2.0, "roeTTM": 0.05,
             "roicTTM": 0.04, "returnOnTangibleAssetsTTM": 0.03},
    "MU":   {"peRatioTTM": 22.0, "enterpriseValueOverEBITDATTM": 12.0,
             "priceToBookRatioTTM": 2.0, "priceToFreeCashFlowsRatioTTM": 18.0,
             "priceToSalesRatioTTM": 3.0, "pegRatioTTM": 1.8, "roeTTM": 0.1,
             "roicTTM": 0.08, "returnOnTangibleAssetsTTM": 0.06},
}
RATIOS = {
    "NVDA": {"grossProfitMarginTTM": 0.75, "operatingProfitMarginTTM": 0.60,
             "ebitdaMarginTTM": 0.62, "freeCashFlowMarginTTM": 0.45},
    "AMD":  {"grossProfitMarginTTM": 0.50, "operatingProfitMarginTTM": 0.20,
             "ebitdaMarginTTM": 0.25, "freeCashFlowMarginTTM": 0.15},
    "INTC": {"grossProfitMarginTTM": 0.40, "operatingProfitMarginTTM": 0.05,
             "ebitdaMarginTTM": 0.15, "freeCashFlowMarginTTM": -0.05},
    "MU":   {"grossProfitMarginTTM": 0.35, "operatingProfitMarginTTM": 0.18,
             "ebitdaMarginTTM": 0.40, "freeCashFlowMarginTTM": 0.10},
}
GROWTH = {
    "NVDA": [{"revenueGrowth": 0.6, "epsGrowth": 0.8}],
    "AMD":  [{"revenueGrowth": 0.2, "epsGrowth": 0.3}],
    "INTC": [{"revenueGrowth": -0.1, "epsGrowth": -0.2}],
    "MU":   [{"revenueGrowth": 0.3, "epsGrowth": 0.4}],
}
PROFILE = {
    "NVDA": {"marketCap": 2.5e12},
    "AMD":  {"marketCap": 3.0e11},
    "INTC": {"marketCap": 1.5e11},
    "MU":   {"marketCap": 1.2e11},
}


def make_fake_fmp(fail: set[str] | None = None) -> AsyncMock:
    """Fake FMP client serving the four endpoints from the dicts above.
    Tickers in `fail` raise on key-metrics (simulating an FMP error)."""
    fail = fail or set()
    fmp = AsyncMock()

    async def km(ticker):
        if ticker in fail:
            raise RuntimeError("FMP 404")
        return KM.get(ticker, {}), MagicMock()

    async def ratios(ticker):
        return RATIOS.get(ticker, {}), MagicMock()

    async def fg(ticker):
        return GROWTH.get(ticker, []), MagicMock()

    async def profile(ticker):
        return PROFILE.get(ticker, {}), MagicMock()

    fmp.get_key_metrics_ttm = km
    fmp.get_ratios_ttm = ratios
    fmp.get_financial_growth = fg
    fmp.get_company_profile = profile
    return fmp


class TestPeerComp(unittest.IsolatedAsyncioTestCase):
    async def test_builds_table_and_median(self):
        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD", "INTC", "MU"],
            fmp=make_fake_fmp(),
        )
        self.assertEqual(table.focus_ticker, "NVDA")
        self.assertEqual(len(table.rows), 4)
        # Median PE of peers (AMD, INTC, MU) = 22.0 (sorted: 18, 22, 40)
        self.assertEqual(table.median.pe, 22.0)
        self.assertEqual(errors, [])

    async def test_new_fields_mapped(self):
        table, _ = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD"], fmp=make_fake_fmp(),
        )
        focus = next(r for r in table.rows if r.ticker == "NVDA")
        self.assertEqual(focus.peg, 1.1)
        self.assertEqual(focus.gross_margin, 0.75)
        self.assertEqual(focus.operating_margin, 0.60)
        self.assertEqual(focus.ebitda_margin, 0.62)
        self.assertEqual(focus.fcf_margin, 0.45)
        self.assertEqual(focus.roic, 0.4)
        self.assertEqual(focus.roa, 0.3)
        self.assertEqual(focus.market_cap, 2.5e12)

    async def test_median_over_new_fields(self):
        table, _ = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD", "INTC", "MU"],
            fmp=make_fake_fmp(),
        )
        # Median gross margin of peers (0.50, 0.40, 0.35) = 0.40
        self.assertEqual(table.median.gross_margin, 0.40)
        # Median market cap of peers (3.0e11, 1.5e11, 1.2e11) = 1.5e11
        self.assertEqual(table.median.market_cap, 1.5e11)

    async def test_missing_wire_fields_become_none(self):
        """A ticker absent from the fake payload dicts maps to all-None metrics."""
        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["ZZZQ"], fmp=make_fake_fmp(),
        )
        self.assertEqual(errors, [])
        zzzq = next(r for r in table.rows if r.ticker == "ZZZQ")
        self.assertIsNone(zzzq.pe)
        self.assertIsNone(zzzq.gross_margin)
        self.assertIsNone(zzzq.market_cap)

    async def test_per_peer_failure_recorded(self):
        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD", "BADCO"],
            fmp=make_fake_fmp(fail={"BADCO"}),
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].peer_ticker, "BADCO")
        self.assertEqual(len(table.rows), 2)  # focus + AMD

    async def test_focus_failure_raises(self):
        with self.assertRaises(RuntimeError):
            await build_peer_comp_table(
                focus_ticker="BADCO", peer_tickers=["AMD"],
                fmp=make_fake_fmp(fail={"BADCO"}),
            )

    async def test_zero_peers_returns_none(self):
        table, errors = await build_peer_comp_table(
            focus_ticker="X", peer_tickers=[], fmp=AsyncMock(),
        )
        self.assertIsNone(table)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest backend.tests.test_peer_comp -v`
Expected: `test_new_fields_mapped`, `test_median_over_new_fields` FAIL (new fields are None — `_fetch_one` doesn't fetch ratios/profile yet). `test_focus_failure_raises` may also fail. The original-shape tests pass.

- [ ] **Step 3: Update `backend/app/services/peer_comp.py`**

Replace `METRIC_FIELDS` and `_fetch_one`, add `_first`, and update the import (schemas now come from `models.peer_comp` — keep importing via `workspace_schemas` OR switch to the new module; switch, it's the source of truth):

```python
"""Peer comparison table builder — fetches FMP data and computes median/delta metrics.

Shared by three consumers: the /api/peers router, the /compare page (via that
router), and workspace step 5 (differentiation). One builder, one set of
numbers everywhere.
"""
from __future__ import annotations

import asyncio
from statistics import median
from typing import Any

from backend.app.models.peer_comp import PeerCompTable, PeerCompRow, PeerError

METRIC_FIELDS = (
    "pe",
    "ev_ebitda",
    "p_b",
    "p_fcf",
    "p_s",
    "peg",
    "revenue_yoy",
    "eps_yoy",
    "gross_margin",
    "operating_margin",
    "ebitda_margin",
    "fcf_margin",
    "roe",
    "roic",
    "roa",
    "market_cap",
)
```

`build_peer_comp_table`, `_compute_median`, `_compute_delta`, `_safe` are unchanged (they iterate `METRIC_FIELDS`). Replace `_fetch_one` and add `_first`:

```python
async def _fetch_one(ticker: str, fmp) -> PeerCompRow:
    """Fetch key-metrics, ratios, growth, and profile for one ticker.

    Wire-name notes: the key-metrics-ttm names below are production-proven
    (same names consumed by graph/nodes.py for the deep-dive valuation
    tables). ratios-ttm names carry fallbacks because the /stable/ API has
    shifted fields between endpoints before — see get_ratios_ttm docstring.
    """
    (km, _), (ratios, _), (fg, _), (profile, _) = await asyncio.gather(
        fmp.get_key_metrics_ttm(ticker),
        fmp.get_ratios_ttm(ticker),
        fmp.get_financial_growth(ticker),
        fmp.get_company_profile(ticker),
    )
    fg_row = fg[0] if isinstance(fg, list) and fg else {}

    return PeerCompRow(
        ticker=ticker,
        pe=_first((km, "peRatioTTM"), (ratios, "priceToEarningsRatioTTM")),
        ev_ebitda=_first(
            (km, "enterpriseValueOverEBITDATTM"),
            (ratios, "enterpriseValueMultipleTTM"),
        ),
        p_b=_first((km, "priceToBookRatioTTM"), (ratios, "priceToBookRatioTTM")),
        p_fcf=_first(
            (km, "priceToFreeCashFlowsRatioTTM"),
            (ratios, "priceToFreeCashFlowRatioTTM"),
        ),
        p_s=_first((km, "priceToSalesRatioTTM"), (ratios, "priceToSalesRatioTTM")),
        peg=_first((km, "pegRatioTTM"), (ratios, "priceEarningsToGrowthRatioTTM")),
        revenue_yoy=_first((fg_row, "revenueGrowth")),
        eps_yoy=_first((fg_row, "epsGrowth"), (fg_row, "epsgrowth")),
        gross_margin=_first((ratios, "grossProfitMarginTTM")),
        operating_margin=_first((ratios, "operatingProfitMarginTTM")),
        ebitda_margin=_first((ratios, "ebitdaMarginTTM")),
        fcf_margin=_first(
            (ratios, "freeCashFlowMarginTTM"), (ratios, "fcfMarginTTM")
        ),
        roe=_first((km, "roeTTM"), (ratios, "returnOnEquityTTM")),
        roic=_first((km, "roicTTM"), (ratios, "returnOnInvestedCapitalTTM")),
        roa=_first(
            (km, "returnOnTangibleAssetsTTM"), (ratios, "returnOnAssetsTTM")
        ),
        market_cap=_first((profile, "marketCap"), (profile, "mktCap")),
    )


def _first(*candidates: tuple[Any, str]) -> float | None:
    """First non-None value across (dict, key) candidates.

    Distinct from `x or y` — a legitimate 0.0 value short-circuits correctly.
    """
    for d, key in candidates:
        v = _safe(d, key)
        if v is not None:
            return v
    return None
```

Delete the old `_fetch_one` body (the `metrics_dict` version with the two `None` margin comments).

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m unittest backend.tests.test_peer_comp backend.tests.test_step_differentiation -v
```

Expected: all PASS.

- [ ] **Step 5: Live FMP wire-name verification (requires `.env` with FMP_API_KEY)**

```bash
python - <<'EOF'
import asyncio
from backend.app.clients.fmp import FMPClient

async def main():
    fmp = FMPClient()
    km, _ = await fmp.get_key_metrics_ttm("NVDA")
    ratios, _ = await fmp.get_ratios_ttm("NVDA")
    profile, _ = await fmp.get_company_profile("NVDA")
    print("KM keys:", sorted(km.keys()) if isinstance(km, dict) else km)
    print("RATIOS keys:", sorted(ratios.keys()) if isinstance(ratios, dict) else ratios)
    print("PROFILE marketCap:", profile.get("marketCap"), "| mktCap:", profile.get("mktCap"))

asyncio.run(main())
EOF
```

Compare the printed key lists against the names used in `_fetch_one`. Rules: (a) the key-metrics-ttm primaries from `graph/nodes.py` stay primary; (b) if a ratios-ttm fallback name doesn't exist in the printed list, replace it with the closest real key (e.g. if `freeCashFlowMarginTTM` is absent but the list has another fcf-margin spelling, use that); (c) if a metric exists on neither endpoint, leave the mapping as-is — it degrades to None, which the UI renders as an em-dash. Then build a row for a real ticker and eyeball it:

```bash
python - <<'EOF'
import asyncio
from backend.app.clients.fmp import FMPClient
from backend.app.services.peer_comp import _fetch_one

async def main():
    row = await _fetch_one("NVDA", FMPClient())
    print(row.model_dump_json(indent=2))

asyncio.run(main())
EOF
```

Expected: pe / ev_ebitda / margins / roic / market_cap all populated (non-None) for NVDA. If any are None, adjust fallback keys per the printed key lists and re-run.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/peer_comp.py backend/tests/test_peer_comp.py
git commit -m "feat(peers): widen peer-comp builder to 16 metrics across 4 FMP endpoints"
```

---

### Task 3: `FMPClient.get_stock_peers`

**Files:**
- Modify: `backend/app/clients/fmp.py` (add method after `get_company_profile`, ~line 333)
- Test: `backend/tests/test_fmp_stock_peers.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_fmp_stock_peers.py`:

```python
import os
import unittest
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.clients.fmp import FMPClient
from backend.app.models.citation import Citation


class StockPeersTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_symbols_excluding_self(self):
        client = FMPClient()
        client._request = AsyncMock(return_value=[
            {"symbol": "AMD", "companyName": "Advanced Micro Devices"},
            {"symbol": "nvda", "companyName": "NVIDIA (self, lowercase)"},
            {"symbol": "INTC", "companyName": "Intel"},
            {"companyName": "no symbol key — skipped"},
        ])
        peers, citation = await client.get_stock_peers("NVDA")
        self.assertEqual(peers, ["AMD", "INTC"])
        self.assertIsInstance(citation, Citation)

    async def test_non_list_payload_returns_empty(self):
        client = FMPClient()
        client._request = AsyncMock(return_value={"error": "not found"})
        peers, _ = await client.get_stock_peers("ZZZQ")
        self.assertEqual(peers, [])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest backend.tests.test_fmp_stock_peers -v`
Expected: FAIL with `AttributeError: 'FMPClient' object has no attribute 'get_stock_peers'`

- [ ] **Step 3: Add the method to `backend/app/clients/fmp.py`** (insert directly after `get_company_profile`)

```python
    async def get_stock_peers(self, ticker: str) -> tuple[list[str], Citation]:
        """Peer tickers from FMP's stock-peers endpoint.

        GET /stable/stock-peers?symbol=X → list of {symbol, companyName, ...}.
        Returns uppercased peer symbols, excluding the input ticker itself.
        """
        params = {"symbol": ticker}
        data = await self._request("stock-peers", params, ttl=TTL_FUNDAMENTAL)
        peers = [
            str(d["symbol"]).upper()
            for d in (data if isinstance(data, list) else [])
            if isinstance(d, dict)
            and d.get("symbol")
            and str(d["symbol"]).upper() != ticker.upper()
        ]
        citation = self._make_citation("stock-peers", "Stock Peers", ticker, params)
        return peers, citation
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest backend.tests.test_fmp_stock_peers -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/fmp.py backend/tests/test_fmp_stock_peers.py
git commit -m "feat(fmp): add get_stock_peers client method"
```

---

### Task 4: `PeerSet` ORM + migration

**Files:**
- Create: `backend/app/models/peer_set.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/migrations/versions/<generated>_peer_sets.py`

- [ ] **Step 1: Create `backend/app/models/peer_set.py`**

```python
"""PeerSet — persisted, user-curated peer list per ticker.

Auto-seeded on first read from filing-extracted competitors
(competitor_landscape) + FMP stock-peers; user edits replace the list.
No FKs by design: peer sets are independent of themes/runs and survive
their deletion.
"""

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class PeerSet(Base, TimestampMixin):
    __tablename__ = "peer_sets"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    peers: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
```

- [ ] **Step 2: Register in `backend/app/models/__init__.py`**

Add (alphabetical placement next to the other imports):

```python
from backend.app.models.peer_set import PeerSet  # noqa: F401
```

and add `"PeerSet",` to `__all__`.

- [ ] **Step 3: Generate + fill the migration**

```bash
cd backend && alembic revision -m "peer_sets"
```

This stamps the correct `down_revision` (current head) automatically. Open the generated file in `backend/migrations/versions/` and fill in:

```python
def upgrade() -> None:
    op.create_table(
        "peer_sets",
        sa.Column("ticker", sa.String(length=16), primary_key=True),
        sa.Column("peers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("peer_sets")
```

Make sure the file imports `from sqlalchemy.dialects import postgresql` (add it if the template didn't).

- [ ] **Step 4: Run the migration and verify**

```bash
cd backend && alembic upgrade head && cd ..
python - <<'EOF'
import asyncio
from sqlalchemy import text
from backend.app.db import async_session

async def main():
    async with async_session() as db:
        cols = (await db.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='peer_sets'"
        ))).scalars().all()
        print(sorted(cols))

asyncio.run(main())
EOF
```

Expected output: `['created_at', 'peers', 'ticker', 'updated_at']`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/peer_set.py backend/app/models/__init__.py backend/migrations/versions/
git commit -m "feat(peers): peer_sets table + PeerSet ORM"
```

---

### Task 5: `services/peer_sets.py` (seed / update / shared derivation)

**Files:**
- Create: `backend/app/services/peer_sets.py`
- Test: `backend/tests/test_peer_sets.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_peer_sets.py`:

```python
"""Pins peer-set seeding (competitor_landscape ∪ stock-peers, capped, deduped),
update normalization, and the curated-first/fallback derivation used by
workspace step 5."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services import peer_sets
from backend.app.models.peer_set import PeerSet


def _db_returning(*rows):
    """Mock AsyncSession whose successive execute() calls return the given
    scalar_one_or_none / scalars().all() payloads in order."""
    db = MagicMock()
    results = []
    for row in rows:
        r = MagicMock()
        r.scalar_one_or_none.return_value = row
        scalars = MagicMock()
        scalars.all.return_value = row if isinstance(row, list) else []
        r.scalars.return_value = scalars
        results.append(r)
    db.execute = AsyncMock(side_effect=results)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _landscape_row(competitors):
    row = MagicMock()
    row.competitors = competitors
    return row


class GetOrSeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_row_returned_without_seeding(self):
        existing = PeerSet(ticker="NVDA", peers=["AMD", "INTC"])
        db = _db_returning(existing)
        fmp = AsyncMock()
        peers, seeded = await peer_sets.get_or_seed_peer_set("NVDA", db, fmp)
        self.assertEqual(peers, ["AMD", "INTC"])
        self.assertFalse(seeded)
        db.add.assert_not_called()
        fmp.get_stock_peers.assert_not_called()

    async def test_seed_unions_landscape_then_fmp_capped_deduped(self):
        # execute #1: PeerSet miss; execute #2: competitor_landscape rows
        landscape = [_landscape_row([
            {"resolved_to_ticker": "AMD"},
            {"resolved_to_ticker": "INTC"},
            {"resolved_to_ticker": "NVDA"},   # self — dropped
            {"resolved_to_ticker": None},      # unresolved — dropped
        ])]
        db = _db_returning(None, landscape)
        fmp = AsyncMock()
        fmp.get_stock_peers = AsyncMock(return_value=(
            ["INTC", "AVGO", "QCOM", "TSM", "MU", "ARM", "TXN", "ADI", "MRVL"],
            MagicMock(),
        ))
        peers, seeded = await peer_sets.get_or_seed_peer_set("NVDA", db, fmp)
        self.assertTrue(seeded)
        # landscape first, then fmp fill (INTC deduped), capped at 8
        self.assertEqual(peers, ["AMD", "INTC", "AVGO", "QCOM", "TSM", "MU", "ARM", "TXN"])
        db.add.assert_called_once()
        db.commit.assert_awaited()

    async def test_seed_tolerates_fmp_failure(self):
        landscape = [_landscape_row([{"resolved_to_ticker": "AMD"}])]
        db = _db_returning(None, landscape)
        fmp = AsyncMock()
        fmp.get_stock_peers = AsyncMock(side_effect=RuntimeError("FMP down"))
        peers, seeded = await peer_sets.get_or_seed_peer_set("NVDA", db, fmp)
        self.assertEqual(peers, ["AMD"])
        self.assertTrue(seeded)

    async def test_zero_sources_persists_empty_row(self):
        db = _db_returning(None, [])
        fmp = AsyncMock()
        fmp.get_stock_peers = AsyncMock(return_value=([], MagicMock()))
        peers, seeded = await peer_sets.get_or_seed_peer_set("ZZZQ", db, fmp)
        self.assertEqual(peers, [])
        self.assertTrue(seeded)
        db.add.assert_called_once()  # empty row persisted — no re-seed next visit


class UpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalizes_dedupes_drops_self(self):
        db = _db_returning(None)
        peers = await peer_sets.update_peer_set(
            "NVDA", ["amd ", "AMD", "nvda", "intc"], db
        )
        self.assertEqual(peers, ["AMD", "INTC"])
        db.add.assert_called_once()
        db.commit.assert_awaited()

    async def test_replaces_existing_row(self):
        existing = PeerSet(ticker="NVDA", peers=["OLD"])
        db = _db_returning(existing)
        peers = await peer_sets.update_peer_set("NVDA", ["AMD"], db)
        self.assertEqual(peers, ["AMD"])
        self.assertEqual(existing.peers, ["AMD"])
        db.add.assert_not_called()

    async def test_empty_list_clears(self):
        existing = PeerSet(ticker="NVDA", peers=["AMD"])
        db = _db_returning(existing)
        peers = await peer_sets.update_peer_set("NVDA", [], db)
        self.assertEqual(peers, [])
        self.assertEqual(existing.peers, [])

    async def test_invalid_ticker_raises_value_error(self):
        db = _db_returning(None)
        with self.assertRaises(ValueError):
            await peer_sets.update_peer_set("NVDA", ["NOT A TICKER!!"], db)

    async def test_over_cap_raises_value_error(self):
        db = _db_returning(None)
        thirteen = [f"T{i}" for i in range(13)]
        with self.assertRaises(ValueError):
            await peer_sets.update_peer_set("NVDA", thirteen, db)


class PeersForTickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_curated_set_preferred(self):
        existing = PeerSet(ticker="NVDA", peers=["AMD", "INTC"])
        db = _db_returning(existing)
        peers = await peer_sets.peers_for_ticker("NVDA", db)
        self.assertEqual(peers, ["AMD", "INTC"])

    async def test_empty_curated_falls_back_to_landscape(self):
        existing = PeerSet(ticker="NVDA", peers=[])
        db = _db_returning(existing)
        with patch.object(
            peer_sets, "resolved_competitor_peers",
            new=AsyncMock(return_value=["AMD"]),
        ) as fallback:
            peers = await peer_sets.peers_for_ticker("NVDA", db)
        self.assertEqual(peers, ["AMD"])
        fallback.assert_awaited_once()

    async def test_missing_row_falls_back_to_landscape(self):
        db = _db_returning(None)
        with patch.object(
            peer_sets, "resolved_competitor_peers",
            new=AsyncMock(return_value=["AMD"]),
        ):
            peers = await peer_sets.peers_for_ticker("NVDA", db)
        self.assertEqual(peers, ["AMD"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest backend.tests.test_peer_sets -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.services.peer_sets'`

- [ ] **Step 3: Create `backend/app/services/peer_sets.py`**

```python
"""Peer-set persistence + seeding, and the shared peer derivation used by
both the peers API and workspace step 5 (differentiation).

Seeding priority: filing-extracted competitors (competitor_landscape,
resolved tickers only) first, then FMP stock-peers to fill remaining
slots, capped at PEER_CAP. Zero-source seeds persist an empty row so we
don't re-derive on every visit.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filing import CompetitorLandscape
from backend.app.models.peer_set import PeerSet
from backend.app.models.ticker import normalize_ticker

log = logging.getLogger(__name__)

PEER_CAP = 8          # auto-seed size
MAX_PEERS = 12        # hard cap on a curated set (matches /compare cap)


async def resolved_competitor_peers(
    ticker: str, db: AsyncSession, cap: int = PEER_CAP
) -> list[str]:
    """Resolved competitor tickers from competitor_landscape. De-duped,
    capped, excludes the focus ticker. (Moved from
    workspace_steps._fetch_resolved_peers, which now delegates here.)"""
    focus = ticker.upper()
    rows = (await db.execute(
        select(CompetitorLandscape).where(CompetitorLandscape.ticker == focus)
    )).scalars().all()

    seen: set[str] = set()
    peers: list[str] = []
    for row in rows:
        for c in (row.competitors or []):
            t = (c.get("resolved_to_ticker") or "").upper()
            if t and t != focus and t not in seen:
                seen.add(t)
                peers.append(t)
                if len(peers) >= cap:
                    return peers
    return peers


async def get_or_seed_peer_set(
    ticker: str, db: AsyncSession, fmp
) -> tuple[list[str], bool]:
    """Return (peers, seeded). Seeds + persists on first call for a ticker.
    Commits on the seed path."""
    focus = ticker.upper()
    row = (
        await db.execute(select(PeerSet).where(PeerSet.ticker == focus))
    ).scalar_one_or_none()
    if row is not None:
        return list(row.peers or []), False

    peers = await resolved_competitor_peers(focus, db, cap=PEER_CAP)
    if len(peers) < PEER_CAP:
        try:
            fmp_peers, _ = await fmp.get_stock_peers(focus)
        except Exception:  # noqa: BLE001 — seed-time best effort
            log.warning("stock-peers fetch failed during seed for %s", focus)
            fmp_peers = []
        seen = set(peers)
        for t in fmp_peers:
            if t and t != focus and t not in seen:
                seen.add(t)
                peers.append(t)
                if len(peers) >= PEER_CAP:
                    break

    db.add(PeerSet(ticker=focus, peers=peers))
    await db.commit()
    return peers, True


async def update_peer_set(
    ticker: str, peers: list[str], db: AsyncSession
) -> list[str]:
    """Replace the persisted peer list. Normalizes + de-dupes, drops the
    set's own ticker, allows [] (clears). Raises ValueError on an invalid
    ticker or an over-cap list (API maps both to 400). Commits."""
    focus = ticker.upper()
    seen: set[str] = set()
    cleaned: list[str] = []
    for raw in peers:
        t = normalize_ticker(raw)  # raises ValueError on garbage
        if t != focus and t not in seen:
            seen.add(t)
            cleaned.append(t)
    if len(cleaned) > MAX_PEERS:
        raise ValueError(f"peer set capped at {MAX_PEERS} tickers")

    row = (
        await db.execute(select(PeerSet).where(PeerSet.ticker == focus))
    ).scalar_one_or_none()
    if row is None:
        db.add(PeerSet(ticker=focus, peers=cleaned))
    else:
        row.peers = cleaned
    await db.commit()
    return cleaned


async def peers_for_ticker(
    ticker: str, db: AsyncSession, cap: int = PEER_CAP
) -> list[str]:
    """Peer list for downstream consumers (workspace step 5): the curated
    set when present and non-empty, else filing-derived competitors."""
    focus = ticker.upper()
    row = (
        await db.execute(select(PeerSet).where(PeerSet.ticker == focus))
    ).scalar_one_or_none()
    if row is not None and row.peers:
        return list(row.peers)[:cap]
    return await resolved_competitor_peers(focus, db, cap=cap)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest backend.tests.test_peer_sets -v`
Expected: PASS (12 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/peer_sets.py backend/tests/test_peer_sets.py
git commit -m "feat(peers): peer_sets service — seed, update, curated-first derivation"
```

---

### Task 6: Workspace step 5 prefers the curated set

**Files:**
- Modify: `backend/app/services/workspace_steps.py` (`_fetch_resolved_peers`, ~line 658)

- [ ] **Step 1: Replace `_fetch_resolved_peers` with a delegation**

In `backend/app/services/workspace_steps.py`, replace the entire `_fetch_resolved_peers` function (keep the module-level `PEER_CAP = 8` — it documents the step's cap and is passed explicitly):

```python
async def _fetch_resolved_peers(ctx: WorkspaceContext) -> list[str]:
    """Peer list for differentiation: the user-curated peer_sets row when
    present and non-empty, else resolved competitor tickers from
    competitor_landscape (the original derivation, now shared via
    services/peer_sets.py)."""
    from backend.app.services.peer_sets import peers_for_ticker

    return await peers_for_ticker(ctx.ticker, ctx.db, cap=PEER_CAP)
```

(The old body — the `CompetitorLandscape` query loop — moved verbatim into `peer_sets.resolved_competitor_peers` in Task 5.)

- [ ] **Step 2: Run the workspace test suites**

```bash
python -m unittest backend.tests.test_step_differentiation backend.tests.test_workspace_steps_contracts backend.tests.test_workspace_service -v
```

Expected: all PASS — `test_step_differentiation` patches `_fetch_resolved_peers` itself, so the delegation is invisible to it. The curated-first behavior is already pinned by `PeersForTickerTests` in Task 5.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/workspace_steps.py
git commit -m "feat(workspace): differentiation step prefers curated peer set"
```

---

### Task 7: `/api/peers` router

**Files:**
- Create: `backend/app/api/peers.py`
- Modify: `backend/app/main.py` (import + register)
- Test: `backend/tests/test_peers_api.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_peers_api.py`:

```python
"""Pins the /api/peers contract: route ordering (/compare is NOT swallowed
by /{ticker} — 'compare' parses as a valid ticker symbol!), param
validation, seed-on-GET, PUT error mapping, and empty-set comp shape."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.peers import router
from backend.app.db import get_db
from backend.app.models.peer_comp import PeerCompRow, PeerCompTable


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    app.state.fmp = AsyncMock()
    return TestClient(app)


def _fake_table(focus="NVDA", peers=("AMD",)):
    rows = [PeerCompRow(ticker=focus)] + [PeerCompRow(ticker=p) for p in peers]
    return PeerCompTable(
        focus_ticker=focus,
        rows=rows,
        median=PeerCompRow(ticker="__median__"),
        delta_vs_median_pct=PeerCompRow(ticker="__delta__"),
    )


class CompareRouteTests(unittest.TestCase):
    def test_compare_not_shadowed_by_ticker_route(self):
        """'compare' is a valid-looking ticker — without correct route
        ordering, GET /api/peers/compare would hit /{ticker} and return a
        peer-set payload instead of a 422 for the missing tickers param."""
        client = make_client()
        resp = client.get("/api/peers/compare")
        self.assertEqual(resp.status_code, 422)  # missing required ?tickers=

    def test_compare_builds_table_with_default_focus(self):
        client = make_client()
        with patch(
            "backend.app.api.peers.build_peer_comp_table",
            new=AsyncMock(return_value=(_fake_table(), [])),
        ) as build:
            resp = client.get("/api/peers/compare?tickers=nvda,AMD")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["table"]["focus_ticker"], "NVDA")
        self.assertEqual(body["errors"], [])
        # default focus = first ticker, normalized; peers exclude focus
        kwargs = build.await_args.kwargs
        self.assertEqual(kwargs["focus_ticker"], "NVDA")
        self.assertEqual(kwargs["peer_tickers"], ["AMD"])

    def test_compare_rejects_invalid_ticker(self):
        client = make_client()
        resp = client.get("/api/peers/compare?tickers=NVDA,NOT%20A%20TICKER")
        self.assertEqual(resp.status_code, 400)

    def test_compare_rejects_over_cap(self):
        client = make_client()
        tickers = ",".join(f"T{i}" for i in range(13))
        resp = client.get(f"/api/peers/compare?tickers={tickers}")
        self.assertEqual(resp.status_code, 400)

    def test_compare_rejects_focus_not_in_tickers(self):
        client = make_client()
        resp = client.get("/api/peers/compare?tickers=NVDA,AMD&focus=INTC")
        self.assertEqual(resp.status_code, 400)

    def test_compare_focus_failure_maps_to_502(self):
        client = make_client()
        with patch(
            "backend.app.api.peers.build_peer_comp_table",
            new=AsyncMock(side_effect=RuntimeError("FMP down")),
        ):
            resp = client.get("/api/peers/compare?tickers=NVDA,AMD")
        self.assertEqual(resp.status_code, 502)


class PeerSetRouteTests(unittest.TestCase):
    def test_get_seeds_and_returns(self):
        client = make_client()
        with patch(
            "backend.app.api.peers.get_or_seed_peer_set",
            new=AsyncMock(return_value=(["AMD", "INTC"], True)),
        ):
            resp = client.get("/api/peers/nvda")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(), {"ticker": "NVDA", "peers": ["AMD", "INTC"], "seeded": True}
        )

    def test_get_rejects_garbage_ticker(self):
        client = make_client()
        resp = client.get("/api/peers/NOT%20A%20TICKER")
        self.assertEqual(resp.status_code, 400)

    def test_put_replaces(self):
        client = make_client()
        with patch(
            "backend.app.api.peers.update_peer_set",
            new=AsyncMock(return_value=["AMD"]),
        ):
            resp = client.put("/api/peers/NVDA", json={"peers": ["amd"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["peers"], ["AMD"])

    def test_put_maps_value_error_to_400(self):
        client = make_client()
        with patch(
            "backend.app.api.peers.update_peer_set",
            new=AsyncMock(side_effect=ValueError("invalid ticker symbol")),
        ):
            resp = client.put("/api/peers/NVDA", json={"peers": ["bad!!"]})
        self.assertEqual(resp.status_code, 400)

    def test_comp_empty_set_returns_null_table(self):
        client = make_client()
        with patch(
            "backend.app.api.peers.get_or_seed_peer_set",
            new=AsyncMock(return_value=([], True)),
        ):
            resp = client.get("/api/peers/NVDA/comp")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"table": None, "errors": []})

    def test_comp_builds_from_persisted_set(self):
        client = make_client()
        with patch(
            "backend.app.api.peers.get_or_seed_peer_set",
            new=AsyncMock(return_value=(["AMD"], False)),
        ), patch(
            "backend.app.api.peers.build_peer_comp_table",
            new=AsyncMock(return_value=(_fake_table(), [])),
        ):
            resp = client.get("/api/peers/NVDA/comp")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["table"]["focus_ticker"], "NVDA")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest backend.tests.test_peers_api -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.app.api.peers'`

- [ ] **Step 3: Create `backend/app/api/peers.py`**

```python
"""Peer-set CRUD + peer-comparison tables.

ROUTE ORDERING MATTERS: the literal /compare route is declared BEFORE the
/{ticker} routes. "compare" itself parses as a valid ticker symbol
("COMPARE"), so if /{ticker} were declared first it would silently swallow
/compare requests and return a peer set for ticker COMPARE. Pinned by
test_peers_api.CompareRouteTests.test_compare_not_shadowed_by_ticker_route.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.peer_comp import PeerCompTable, PeerError
from backend.app.models.ticker import Ticker, TickerPath, normalize_ticker
from backend.app.services.peer_comp import build_peer_comp_table
from backend.app.services.peer_sets import get_or_seed_peer_set, update_peer_set

router = APIRouter(prefix="/api/peers", tags=["peers"])

MAX_COMPARE_TICKERS = 12


class PeersPayload(BaseModel):
    peers: list[str]


class PeerSetResponse(BaseModel):
    ticker: str
    peers: list[str]
    seeded: bool = False


class PeerCompResponse(BaseModel):
    table: PeerCompTable | None
    errors: list[PeerError]


async def _build_table(focus: str, peers: list[str], fmp) -> PeerCompResponse:
    try:
        table, errors = await build_peer_comp_table(
            focus_ticker=focus, peer_tickers=peers, fmp=fmp
        )
    except Exception as e:  # noqa: BLE001 — focus-ticker fetch failure
        raise HTTPException(
            status_code=502, detail=f"failed to fetch data for {focus}: {e}"
        )
    return PeerCompResponse(table=table, errors=errors)


@router.get("/compare")
async def compare(
    request: Request,
    tickers: str = Query(
        ..., description="Comma-separated tickers; first is the default focus."
    ),
    focus: str | None = None,
) -> PeerCompResponse:
    try:
        parsed = [normalize_ticker(t) for t in tickers.split(",") if t.strip()]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not parsed:
        raise HTTPException(
            status_code=400, detail="tickers must contain at least one symbol"
        )
    seen: set[str] = set()
    parsed = [t for t in parsed if not (t in seen or seen.add(t))]
    if len(parsed) > MAX_COMPARE_TICKERS:
        raise HTTPException(
            status_code=400,
            detail=f"at most {MAX_COMPARE_TICKERS} tickers per comparison",
        )
    try:
        focus_t = normalize_ticker(focus) if focus else parsed[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if focus_t not in parsed:
        raise HTTPException(status_code=400, detail="focus must be one of tickers")
    peers = [t for t in parsed if t != focus_t]
    return await _build_table(focus_t, peers, request.app.state.fmp)


@router.get("/{ticker}")
async def get_peer_set(
    request: Request,
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> PeerSetResponse:
    peers, seeded = await get_or_seed_peer_set(ticker, db, request.app.state.fmp)
    return PeerSetResponse(ticker=ticker, peers=peers, seeded=seeded)


@router.put("/{ticker}")
async def put_peer_set(
    payload: PeersPayload,
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> PeerSetResponse:
    try:
        peers = await update_peer_set(ticker, payload.peers, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return PeerSetResponse(ticker=ticker, peers=peers)


@router.get("/{ticker}/comp")
async def peer_comp(
    request: Request,
    ticker: Ticker = Depends(TickerPath),
    db: AsyncSession = Depends(get_db),
) -> PeerCompResponse:
    peers, _ = await get_or_seed_peer_set(ticker, db, request.app.state.fmp)
    if not peers:
        return PeerCompResponse(table=None, errors=[])
    return await _build_table(ticker, peers, request.app.state.fmp)
```

- [ ] **Step 4: Register in `backend/app/main.py`**

Add to the api import block:

```python
from backend.app.api import peers as peers_api
```

Add to the router block (after `app.include_router(prospectus_api.router)`):

```python
app.include_router(peers_api.router)
```

(`peers.py` carries its own `/api/peers` prefix — register without a second prefix, same as `models_router`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest backend.tests.test_peers_api -v`
Expected: PASS (12 tests).

- [ ] **Step 6: Full backend suite + live smoke**

```bash
python -m unittest discover -s backend/tests -t . -v 2>&1 | tail -5
```

Expected: all green. Then with the backend running (`uvicorn backend.app.main:app --reload`):

```bash
curl -s "http://127.0.0.1:8000/api/peers/NVDA" | python -m json.tool
curl -s "http://127.0.0.1:8000/api/peers/NVDA/comp" | python -m json.tool | head -40
curl -s "http://127.0.0.1:8000/api/peers/compare?tickers=NVDA,AMD,INTC" | python -m json.tool | head -40
```

Expected: first call seeds + returns a peer list (`"seeded": true` on first run); comp/compare return populated tables.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/peers.py backend/app/main.py backend/tests/test_peers_api.py
git commit -m "feat(peers): /api/peers router — set CRUD, comp, ad-hoc compare"
```

---

### Task 8: Frontend types + client (`lib/api.ts`)

**Files:**
- Modify: `frontend/lib/api.ts` (widen `PeerCompRow` at ~line 1529; add `peersApi` + response types near it)

- [ ] **Step 1: Widen the `PeerCompRow` interface**

Replace the existing interface (line ~1529):

```ts
export interface PeerCompRow {
  ticker: string;
  pe: number | null; ev_ebitda: number | null; p_b: number | null;
  p_fcf: number | null; p_s: number | null; peg: number | null;
  revenue_yoy: number | null; eps_yoy: number | null;
  gross_margin: number | null; operating_margin: number | null;
  ebitda_margin: number | null; fcf_margin: number | null;
  roe: number | null; roic: number | null; roa: number | null;
  market_cap: number | null;
}
```

- [ ] **Step 2: Add response types + client below the `DifferentiationOutput` interface**

```ts
export interface PeerSetResponse {
  ticker: string;
  peers: string[];
  seeded: boolean;
}
export interface PeerCompResponse {
  table: PeerCompTable | null;
  errors: { peer_ticker: string; error_message: string }[];
}

export const peersApi = {
  get: (ticker: string) =>
    apiFetch<PeerSetResponse>(`/api/peers/${encodeURIComponent(ticker)}`),
  update: (ticker: string, peers: string[]) =>
    apiFetch<PeerSetResponse>(`/api/peers/${encodeURIComponent(ticker)}`, {
      method: "PUT",
      body: JSON.stringify({ peers }),
    }),
  comp: (ticker: string) =>
    apiFetch<PeerCompResponse>(`/api/peers/${encodeURIComponent(ticker)}/comp`),
  compare: (tickers: string[], focus?: string) =>
    apiFetch<PeerCompResponse>(
      `/api/peers/compare?tickers=${encodeURIComponent(tickers.join(","))}${
        focus ? `&focus=${encodeURIComponent(focus)}` : ""
      }`
    ),
};
```

- [ ] **Step 3: Verify the build still typechecks**

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Expected: clean. (`DifferentiationCard.tsx` only reads the original 10 keys, so widening is additive.)

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(peers): typed peersApi client + widened PeerCompRow"
```

---

### Task 9: Shared `PeerCompTable` component

**Files:**
- Create: `frontend/components/peers/PeerCompTable.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import type { PeerCompTable as PeerCompTableData, PeerCompRow } from "@/lib/api";
import { fmtMarketCap } from "@/lib/api";

type MetricKey = Exclude<keyof PeerCompRow, "ticker">;
type Kind = "multiple" | "pct" | "money";
type Better = "low" | "high" | null;

interface MetricDef { key: MetricKey; label: string; kind: Kind; better: Better }

const GROUPS: { label: string; metrics: MetricDef[] }[] = [
  {
    label: "Valuation",
    metrics: [
      { key: "pe", label: "P/E", kind: "multiple", better: "low" },
      { key: "ev_ebitda", label: "EV/EBITDA", kind: "multiple", better: "low" },
      { key: "p_b", label: "P/B", kind: "multiple", better: "low" },
      { key: "p_fcf", label: "P/FCF", kind: "multiple", better: "low" },
      { key: "p_s", label: "P/S", kind: "multiple", better: "low" },
      { key: "peg", label: "PEG", kind: "multiple", better: "low" },
    ],
  },
  {
    label: "Growth",
    metrics: [
      { key: "revenue_yoy", label: "Rev YoY", kind: "pct", better: "high" },
      { key: "eps_yoy", label: "EPS YoY", kind: "pct", better: "high" },
    ],
  },
  {
    label: "Margins",
    metrics: [
      { key: "gross_margin", label: "Gross", kind: "pct", better: "high" },
      { key: "operating_margin", label: "Oper", kind: "pct", better: "high" },
      { key: "ebitda_margin", label: "EBITDA", kind: "pct", better: "high" },
      { key: "fcf_margin", label: "FCF", kind: "pct", better: "high" },
    ],
  },
  {
    label: "Returns",
    metrics: [
      { key: "roe", label: "ROE", kind: "pct", better: "high" },
      { key: "roic", label: "ROIC", kind: "pct", better: "high" },
      { key: "roa", label: "ROA", kind: "pct", better: "high" },
    ],
  },
  {
    label: "",
    metrics: [
      // Context only — no best-in-class judgment on size.
      { key: "market_cap", label: "Mkt Cap", kind: "money", better: null },
    ],
  },
];

const ALL_METRICS: MetricDef[] = GROUPS.flatMap((g) => g.metrics);

function fmtValue(v: number | null, kind: Kind): string {
  if (v == null || Number.isNaN(v)) return "—";
  if (kind === "pct") return `${(v * 100).toFixed(1)}%`;
  if (kind === "money") return fmtMarketCap(v);
  return `${v.toFixed(1)}x`;
}

/** Per-metric best value across the displayed company rows (focus + peers). */
function bestValues(rows: PeerCompRow[]): Partial<Record<MetricKey, number>> {
  const best: Partial<Record<MetricKey, number>> = {};
  for (const m of ALL_METRICS) {
    if (!m.better) continue;
    const vals = rows.map((r) => r[m.key]).filter((v): v is number => v != null);
    if (vals.length === 0) continue;
    best[m.key] = m.better === "low" ? Math.min(...vals) : Math.max(...vals);
  }
  return best;
}

export function PeerCompTable({ table }: { table: PeerCompTableData }) {
  const focus = table.focus_ticker;
  const companyRows = [
    ...table.rows.filter((r) => r.ticker === focus),
    ...table.rows.filter((r) => r.ticker !== focus),
  ];
  const best = bestValues(companyRows);

  const cell = (row: PeerCompRow, m: MetricDef) => {
    const v = row[m.key];
    const isBest = m.better != null && v != null && v === best[m.key];
    return (
      <td
        key={m.key}
        className={`text-right py-1.5 px-2 tabular-nums ${
          isBest ? "text-[var(--success)] font-semibold" : "text-[var(--text)]"
        }`}
      >
        {fmtValue(v, m.kind)}
      </td>
    );
  };

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b border-[var(--border)]">
            <th className="sticky left-0 bg-[var(--surface)] z-10" />
            {GROUPS.map((g) => (
              <th
                key={g.label || "context"}
                colSpan={g.metrics.length}
                className="py-1 px-2 text-center text-[10px] uppercase tracking-wide text-[var(--text-muted)] border-l border-[var(--border)]"
              >
                {g.label}
              </th>
            ))}
          </tr>
          <tr className="border-b border-[var(--border)]">
            <th className="sticky left-0 bg-[var(--surface)] text-left py-1.5 px-2 font-semibold text-[var(--text-muted)] z-10">
              Ticker
            </th>
            {GROUPS.map((g) =>
              g.metrics.map((m, i) => (
                <th
                  key={m.key}
                  className={`text-right py-1.5 px-2 font-semibold text-[var(--text-muted)] whitespace-nowrap ${
                    i === 0 ? "border-l border-[var(--border)]" : ""
                  }`}
                >
                  {m.label}
                </th>
              ))
            )}
          </tr>
        </thead>
        <tbody>
          {companyRows.map((row) => {
            const isFocus = row.ticker === focus;
            return (
              <tr
                key={row.ticker}
                className={`border-b border-[var(--border)] ${
                  isFocus ? "bg-[var(--accent-bg)] font-semibold" : ""
                }`}
              >
                <td
                  className={`sticky left-0 z-10 text-left py-1.5 px-2 ${
                    isFocus
                      ? "bg-[var(--accent-bg)] text-[var(--primary)]"
                      : "bg-[var(--surface)] text-[var(--text)]"
                  }`}
                >
                  {row.ticker}
                </td>
                {ALL_METRICS.map((m) => cell(row, m))}
              </tr>
            );
          })}

          {/* Median footer */}
          <tr className="border-b border-[var(--border)] bg-[var(--surface-alt)]">
            <td className="sticky left-0 bg-[var(--surface-alt)] z-10 text-left py-1.5 px-2 font-medium text-[var(--text-muted)]">
              Peer median
            </td>
            {ALL_METRICS.map((m) => (
              <td
                key={m.key}
                className="text-right py-1.5 px-2 tabular-nums text-[var(--text-muted)]"
              >
                {fmtValue(table.median[m.key], m.kind)}
              </td>
            ))}
          </tr>

          {/* Delta footer */}
          <tr>
            <td className="sticky left-0 bg-[var(--surface)] z-10 text-left py-1.5 px-2 font-medium text-[var(--text-muted)]">
              Δ vs median
            </td>
            {ALL_METRICS.map((m) => {
              const d = table.delta_vs_median_pct[m.key];
              const color =
                d == null
                  ? "text-[var(--text-muted)]"
                  : d > 0
                    ? "text-[var(--success)]"
                    : "text-[var(--error)]";
              return (
                <td key={m.key} className={`text-right py-1.5 px-2 tabular-nums ${color}`}>
                  {d == null ? "—" : `${d > 0 ? "+" : ""}${d.toFixed(1)}%`}
                </td>
              );
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
```

Note: the Δ row is a *relative* delta vs the median (computed backend-side) — green/red only signals direction, not good/bad (a +33% P/E delta isn't "good"); the best-in-class tint on the company rows is the judgment layer.

- [ ] **Step 2: Lint**

```bash
cd frontend && npm run lint
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/peers/PeerCompTable.tsx
git commit -m "feat(peers): shared grouped PeerCompTable component"
```

---

### Task 10: Peers tab on the company workspace

**Files:**
- Modify: `frontend/components/company/TabStrip.tsx` (add tab entry)
- Create: `frontend/components/peers/PeerSetEditor.tsx`
- Create: `frontend/app/company/[ticker]/peers/page.tsx`

- [ ] **Step 1: Add the tab to `TabStrip.tsx`**

In the `TABS` array, insert after the `financials` entry:

```ts
  { seg: "peers", label: "Peers" },
```

- [ ] **Step 2: Create `frontend/components/peers/PeerSetEditor.tsx`**

```tsx
"use client";

import { useState } from "react";

export function PeerSetEditor({
  focus,
  peers,
  busy,
  onChange,
}: {
  focus: string;
  peers: string[];
  busy: boolean;
  onChange: (next: string[]) => void;
}) {
  const [draft, setDraft] = useState("");

  function handleAdd() {
    const candidates = draft
      .split(/[\s,]+/)
      .map((t) => t.trim().toUpperCase())
      .filter((t) => t && t !== focus && !peers.includes(t));
    setDraft("");
    if (candidates.length > 0) onChange([...peers, ...candidates]);
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {peers.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface-alt)] px-2 py-0.5 text-xs text-[var(--text)]"
        >
          {t}
          <button
            type="button"
            disabled={busy}
            onClick={() => onChange(peers.filter((p) => p !== t))}
            aria-label={`Remove ${t}`}
            className="text-[var(--text-muted)] hover:text-[var(--error)] disabled:opacity-50"
          >
            ✕
          </button>
        </span>
      ))}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleAdd();
        }}
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Add tickers…"
          disabled={busy}
          className="w-28 rounded-md border border-[var(--border)] bg-[var(--surface)] px-2 py-1 text-xs text-[var(--text)] placeholder:text-[var(--text-muted)] disabled:opacity-50"
          aria-label="Add peer tickers"
        />
      </form>
    </div>
  );
}
```

- [ ] **Step 3: Create `frontend/app/company/[ticker]/peers/page.tsx`**

```tsx
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { peersApi } from "@/lib/api";
import type { PeerCompResponse } from "@/lib/api";
import { PeerCompTable } from "@/components/peers/PeerCompTable";
import { PeerSetEditor } from "@/components/peers/PeerSetEditor";

export default function PeersPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();

  const [peers, setPeers] = useState<string[] | null>(null);
  // null = loading, undefined = error
  const [comp, setComp] = useState<PeerCompResponse | null | undefined>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!ticker) return;
    let alive = true;
    // Sequential on purpose: GET /{ticker} seeds the row; firing comp in
    // parallel could double-seed (PK violation on the second insert).
    (async () => {
      try {
        const set = await peersApi.get(ticker);
        if (!alive) return;
        setPeers(set.peers);
        const c = await peersApi.comp(ticker);
        if (alive) setComp(c);
      } catch {
        if (alive) setComp(undefined);
      }
    })();
    return () => { alive = false; };
  }, [ticker]);

  async function handleChange(next: string[]) {
    if (peers == null) return;
    const prev = peers;
    setBusy(true);
    setError(null);
    setPeers(next);
    try {
      const saved = await peersApi.update(ticker, next);
      setPeers(saved.peers);
      setComp(saved.peers.length > 0 ? await peersApi.comp(ticker) : { table: null, errors: [] });
    } catch (e) {
      setPeers(prev);
      setError(e instanceof Error ? e.message : "Failed to update peers");
    } finally {
      setBusy(false);
    }
  }

  if (comp === undefined) {
    return <div className="text-sm text-[var(--error)]">Failed to load peer data.</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-[var(--text)]">Peer set</h2>
        {peers != null && peers.length > 0 && (
          <Link
            href={`/compare?tickers=${encodeURIComponent([ticker, ...peers].join(","))}&focus=${ticker}`}
            className="text-xs text-[var(--primary)] hover:underline"
          >
            Open in compare →
          </Link>
        )}
      </div>

      {peers == null ? (
        <div className="text-sm text-[var(--text-muted)]">Loading…</div>
      ) : (
        <PeerSetEditor focus={ticker} peers={peers} busy={busy} onChange={handleChange} />
      )}
      {error && <div className="text-xs text-[var(--error)]">{error}</div>}

      {comp?.errors && comp.errors.length > 0 && (
        <div className="text-xs text-[var(--text-muted)]">
          Couldn&apos;t load: {comp.errors.map((e) => e.peer_ticker).join(", ")}
        </div>
      )}

      {peers != null && peers.length === 0 ? (
        <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
          No peers yet — add tickers above to build the comparison.
        </div>
      ) : comp?.table ? (
        <PeerCompTable table={comp.table} />
      ) : comp === null ? (
        <div className="text-sm text-[var(--text-muted)]">Loading comparison…</div>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 4: Lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Expected: clean build, `/company/[ticker]/peers` appears in the route list.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/company/TabStrip.tsx frontend/components/peers/PeerSetEditor.tsx "frontend/app/company/[ticker]/peers/page.tsx"
git commit -m "feat(peers): Peers tab on company workspace with editable peer set"
```

---

### Task 11: Standalone `/compare` page

**Files:**
- Create: `frontend/app/compare/page.tsx`

- [ ] **Step 1: Check Next.js 16 docs for `useSearchParams`**

```bash
ls frontend/node_modules/next/dist/docs/ | grep -i -E "search-params|use-search"
```

Read the matching doc. Confirm: (a) `useSearchParams` import path, (b) whether a `<Suspense>` boundary is required around components using it. Adjust the code below if the API changed.

- [ ] **Step 2: Create `frontend/app/compare/page.tsx`**

```tsx
"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { peersApi } from "@/lib/api";
import type { PeerCompResponse } from "@/lib/api";
import { PeerCompTable } from "@/components/peers/PeerCompTable";
import { PeerSetEditor } from "@/components/peers/PeerSetEditor";

function CompareInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const tickers = (searchParams.get("tickers") ?? "")
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);
  const focus = (searchParams.get("focus") ?? tickers[0] ?? "").toUpperCase();

  const [comp, setComp] = useState<PeerCompResponse | null | undefined>(null);
  const [error, setError] = useState<string | null>(null);

  const key = tickers.join(",") + "|" + focus;
  useEffect(() => {
    if (tickers.length === 0) { setComp(null); return; }
    let alive = true;
    setComp(null);
    setError(null);
    peersApi
      .compare(tickers, focus || undefined)
      .then((c) => { if (alive) setComp(c); })
      .catch((e) => {
        if (alive) {
          setComp(undefined);
          setError(e instanceof Error ? e.message : "Failed to compare");
        }
      });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  function setUrl(nextTickers: string[], nextFocus: string) {
    if (nextTickers.length === 0) {
      router.replace("/compare");
      return;
    }
    const f = nextTickers.includes(nextFocus) ? nextFocus : nextTickers[0];
    router.replace(
      `/compare?tickers=${encodeURIComponent(nextTickers.join(","))}&focus=${f}`
    );
  }

  // The editor treats the focus as "self"; on /compare the focus is just
  // the first chip, so pass an empty focus and manage the full list here.
  return (
    <main className="mx-auto max-w-[1400px] space-y-4 px-6 py-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--text)]">Compare</h1>
        <p className="text-xs text-[var(--text-muted)]">
          The first ticker is the focus row. The URL is shareable.
        </p>
      </div>

      <PeerSetEditor
        focus=""
        peers={tickers}
        busy={false}
        onChange={(next) => setUrl(next, focus)}
      />

      {tickers.length === 0 && (
        <div className="rounded-lg border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
          Add tickers to build a comparison, e.g. NVDA AMD INTC.
        </div>
      )}

      {error && <div className="text-xs text-[var(--error)]">{error}</div>}

      {comp?.errors && comp.errors.length > 0 && (
        <div className="text-xs text-[var(--text-muted)]">
          Couldn&apos;t load: {comp.errors.map((e) => e.peer_ticker).join(", ")}
        </div>
      )}

      {tickers.length > 0 && comp === null && (
        <div className="text-sm text-[var(--text-muted)]">Loading…</div>
      )}
      {comp?.table && <PeerCompTable table={comp.table} />}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={null}>
      <CompareInner />
    </Suspense>
  );
}
```

- [ ] **Step 3: Lint + build**

```bash
cd frontend && npm run lint && npm run build
```

Expected: clean; `/compare` in the route list.

- [ ] **Step 4: Manual smoke (backend + frontend running)**

With `uvicorn backend.app.main:app --reload` and `npm run dev` up, walk through in a browser (or via the Playwright MCP tools):

1. `http://localhost:3000/company/NVDA/peers` — peer set auto-seeds, table renders, focus row highlighted, best-in-class cells tinted.
2. Add a ticker chip (e.g. `TSM`) — table refreshes with the new row; remove it — row disappears. Reload — edits persisted.
3. Click "Open in compare →" — `/compare` opens with the same tickers; edit chips — URL updates; reload the URL — same table (state is in the URL).
4. Enter a bogus ticker on the company tab (e.g. `ZZZZZZ`) — appears as a row of em-dashes or in the "Couldn't load" notice, no crash.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/compare/page.tsx
git commit -m "feat(peers): standalone /compare page with URL-state tickers"
```

---

### Task 12: Docs + wrap-up

**Files:**
- Modify: `CLAUDE.md` (two small insertions)
- Modify: `TODO.md` (Done entry)

- [ ] **Step 1: Update `CLAUDE.md`**

(a) In the **frontend layout** section's `components/` listing, add:

```markdown
- `components/peers/` — `PeerCompTable` (grouped comparison table shared by the company Peers tab and `/compare`), `PeerSetEditor` (chip editor)
```

(b) After the "Workspace loop" section (or near the model section), add a short block:

```markdown
### Peer comparison (read this before touching `backend/app/services/peer_comp.py` or `peer_sets.py`)

`services/peer_comp.py` is the single peer-table builder shared by three consumers: `GET /api/peers/{ticker}/comp`, `GET /api/peers/compare?tickers=`, and workspace step 5 (differentiation). Schemas live in `models/peer_comp.py` (re-exported from `workspace_schemas.py` for old persisted `step_outputs`). 16 metrics from 4 FMP endpoints (key-metrics-ttm, ratios-ttm, financial-growth, profile); km wire names match the ones `graph/nodes.py` uses. Peer sets persist in `peer_sets` (ticker PK, JSONB peers) — auto-seeded from resolved `competitor_landscape` tickers ∪ `FMPClient.get_stock_peers`, capped at 8 (manual edits capped at 12); `services/peer_sets.peers_for_ticker` is the curated-first/fallback derivation the workspace step consumes. **Route-ordering footgun:** in `api/peers.py`, `/compare` must stay declared before `/{ticker}` — "compare" parses as a valid ticker. Frontend surfaces: `/company/[ticker]/peers` tab + `/compare` (URL is the state, no nav link by design).
```

- [ ] **Step 2: Update `TODO.md`**

Add at the top of **Done (recent)**:

```markdown
- **Peer comparison surface (2026-06-09)**. First sub-project of the investor-portal track (spec: `docs/superpowers/specs/2026-06-09-peer-comparison-design.md`, local-only). `peer_comp.py` promoted from workspace-internal to the single shared table builder: schemas moved to `models/peer_comp.py` (re-exported from `workspace_schemas` — old persisted `step_outputs` still validate, pinned by test), `METRIC_FIELDS` widened to 16 (valuation + growth + margins + returns + market cap) across 4 FMP endpoints with fallback wire-keys (`_first` helper). New `peer_sets` table (ticker PK, JSONB peers) + `services/peer_sets.py` (seed = resolved `competitor_landscape` ∪ new `FMPClient.get_stock_peers`, cap 8; manual edits normalized/deduped, cap 12); workspace `_fetch_resolved_peers` now delegates to `peers_for_ticker` (curated-first, landscape fallback). New `/api/peers` router (set GET/PUT, `/{ticker}/comp`, ad-hoc `/compare?tickers=` — declared before `/{ticker}` because "compare" parses as a ticker; pinned by test). Frontend: Peers tab on `/company/[ticker]` (chip editor, optimistic update with rollback) + standalone `/compare` (URL-state, shareable) sharing `components/peers/PeerCompTable` (grouped headers, best-in-class tint via direction map, median + Δ footers).
```

- [ ] **Step 3: Full verification pass**

```bash
python -m unittest discover -s backend/tests -t . 2>&1 | tail -3
cd frontend && npm run lint && npm run build && cd ..
```

Expected: backend suite fully green; frontend lint + build clean.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md TODO.md
git commit -m "docs: record peer comparison surface in CLAUDE.md + TODO.md"
```

- [ ] **Step 5: Finish the branch**

Use the superpowers:finishing-a-development-branch skill — typically: push `feat/peer-comparison`, open a PR against `main` with a summary of the above, or merge per the user's preference.

---

## Self-review notes (already applied)

- Spec coverage: schemas/move (Task 1), widened builder + live wire-name verification (Task 2), stock-peers client (Task 3), `peer_sets` table (Task 4), seed/update/derivation service incl. zero-source empty-row + fmp-failure tolerance (Task 5), workspace curated-first integration (Task 6), all four API routes + ordering pin + 502 mapping + empty-set null table (Task 7), frontend types/client (Task 8), shared grouped table with direction map (Task 9), Peers tab + editor + error/empty states (Task 10), `/compare` URL-state page (Task 11), docs (Task 12).
- Deviation from spec, intentional: manual peer sets are capped at 12 (`MAX_PEERS`, matching the `/compare` cap) so `/{ticker}/comp` can't fan out unboundedly; the spec left manual size unspecified.
- The spec's "no caching in v1" concern is softened in practice: `FMPClient` already caches fundamentals for 24h per ticker+endpoint, so repeat table renders are cheap.
```
