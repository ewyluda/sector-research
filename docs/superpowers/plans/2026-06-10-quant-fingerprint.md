# Quant Fingerprint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic quant layer (Piotroski F, Altman Z, Beneish M, accruals, FCF conversion, SBC dilution, margin slopes) computed in pure Python from the 8 quarters already fetched in `node_deep_dive`, injected into routed deep-dive prompts as established facts, rendered as a "Quant Fingerprint" card.

**Architecture:** New pure module `backend/app/services/quant_fingerprint.py` (the `model_balancing.py` pattern — synchronous, no I/O, fixture-testable). Result attached to `CuratedFinancials.quant_fingerprint` (the `macro_indicators` precedent) inside `_build_curated_financials`, so the report API (`backend/app/api/pipeline.py:374`) and `deep_dive_start` SSE carry it with zero new endpoints. Prompt injection via a new `{quant_data}` slot + `QUANT_ROUTING` table + `build_quant_context` builder. One new frontend card in the Financials cluster.

**Tech Stack:** Python 3 stdlib only (no new deps), stdlib `unittest`; Next.js 16 + React 19 + Tailwind v4 frontend.

**Spec:** `docs/superpowers/specs/2026-06-10-quant-fingerprint-design.md` — read it first; formulas, conventions, and routing live there.

---

## Conventions the engineer must know

- Run backend tests **from repo root**: `backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint -v`
- FMP statements arrive **newest first**. TTM = quarters `[0:4]` summed; prior TTM = `[4:8]`. Balance point-in-time: index 0 vs index 4. No partial sums — missing key anywhere in a window ⇒ `None`.
- Every metric independently nullable. Beneish M: all 8 ratios or null + `inputs_missing`.
- Sector gate: `profile["sector"] == "Financial Services"` ⇒ Altman/Beneish `not_applicable` (live-verified, see Task 3).
- Commit prefix: `feat(quant):` / `test(quant):` / `docs:`.
- Frontend: read `node_modules/next/dist/docs/` before editing anything under `frontend/` (Next 16 ≠ training data).

### File map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/services/quant_fingerprint.py` | Create | All quant math (pure) + `QuantFingerprint` dataclass |
| `backend/tests/test_quant_fingerprint.py` | Create | Fixture-driven math tests + prompt-slot smoke tests |
| `backend/app/graph/state.py` | Modify | `CuratedFinancials.quant_fingerprint` field + (de)serialization |
| `backend/app/graph/nodes.py` | Modify | Attach fingerprint in `_build_curated_financials`; thread `quant_context` through `_run_one_category` + targeted-context builder |
| `backend/app/graph/deep_dive_routing.py` | Modify | `QUANT_ROUTING` + `CategoryRouting.quant_metrics` |
| `backend/app/graph/deep_dive_context.py` | Modify | `build_quant_context` + `build_all_contexts` `"quant"` kind |
| `backend/app/graph/prompts.py` | Modify | `{quant_data}` slot in `DEEP_DIVE_USER` |
| `backend/tests/test_deep_dive_routing.py` | Modify | Pin quant routing |
| `backend/tests/test_deep_dive_context.py` | Modify | Pin quant context builder |
| `frontend/lib/api.ts` | Modify | `QuantFingerprint` types + `CuratedFinancials` field |
| `frontend/components/deep-dive/sections/QuantFingerprint.tsx` | Create | The card |
| `frontend/components/deep-dive/DeepDiveDashboard.tsx` | Modify | Mount card after `CrossCategoryCorrelation` |
| `frontend/components/deep-dive/sections.ts` | Modify | Registry entry (`quant_fingerprint`) |

---

### Task 1: Branch + module skeleton (helpers, dataclass, meta)

**Files:**
- Create: `backend/app/services/quant_fingerprint.py`
- Test: `backend/tests/test_quant_fingerprint.py`

- [ ] **Step 1: Create branch**

```bash
git checkout -b feat/quant-fingerprint
```

- [ ] **Step 2: Write the failing tests (helpers + meta + shared fixture)**

Create `backend/tests/test_quant_fingerprint.py`. The fixture is shared by every later task — hand-computed expected values are documented inline.

```python
"""Deterministic quant fingerprint — pure-math tests on synthetic fixtures.

Fixture design: the 4 current-TTM quarters are identical, the 4 prior-TTM
quarters are identical, so every TTM aggregate is 4x a round number and all
expected values below are hand-computable. Statements are NEWEST FIRST
(FMP order). Hand-computed expectations:

  TTM:   rev=400 gp=240 ni=80 ebit=120 sga=40 cfo=120 fcf=100 da=20 sbc=16 shares(avg)=102
  Prior: rev=360 gp=200 ni=60 ebit=100 sga=40 cfo=80          da=20        shares(avg)=100
  Balance[0]: ta=400 ca=200 cl=100 ltd=50 re=120 rec=40 ppe=100 lti=20 tl=180
  Balance[4]: ta=380 ca=180 cl=100 ltd=60 re=100 rec=45 ppe=95  lti=20 tl=190
  Profile: marketCap=2000, sector=Technology
"""
import unittest

from backend.app.services.quant_fingerprint import (
    _div,
    _ols_slope,
    _ttm,
    _prior_ttm,
    build_quant_fingerprint,
)


def _iq(rev, gp, ni, ebit, sga, shares, op_inc=None):
    return {
        "revenue": rev,
        "grossProfit": gp,
        "netIncome": ni,
        "ebit": ebit,
        "sellingGeneralAndAdministrativeExpenses": sga,
        "weightedAverageShsOutDil": shares,
        "operatingIncome": op_inc if op_inc is not None else ebit,
    }


def _bq(ta, ca, cl, ltd, re, rec, ppe, lti, tl):
    return {
        "totalAssets": ta,
        "totalCurrentAssets": ca,
        "totalCurrentLiabilities": cl,
        "longTermDebt": ltd,
        "retainedEarnings": re,
        "netReceivables": rec,
        "propertyPlantEquipmentNet": ppe,
        "longTermInvestments": lti,
        "totalLiabilities": tl,
    }


def _cq(cfo, fcf, da, sbc, ni):
    return {
        "operatingCashFlow": cfo,
        "freeCashFlow": fcf,
        "depreciationAndAmortization": da,
        "stockBasedCompensation": sbc,
        "netIncome": ni,
    }


# Newest first: 4 current quarters then 4 prior quarters.
INCOME = [_iq(100, 60, 20, 30, 10, 102)] * 4 + [_iq(90, 50, 15, 25, 10, 100)] * 4
BALANCE = [_bq(400, 200, 100, 50, 120, 40, 100, 20, 180)] * 4 + \
          [_bq(380, 180, 100, 60, 100, 45, 95, 20, 190)] * 4
CASHFLOW = [_cq(30, 25, 5, 4, 20)] * 4 + [_cq(20, 18, 5, 3, 15)] * 4
PROFILE = {"marketCap": 2000, "sector": "Technology"}


def fingerprint(income=INCOME, balance=BALANCE, cashflow=CASHFLOW, profile=PROFILE):
    return build_quant_fingerprint(income, balance, cashflow, profile).to_dict()


class HelperTests(unittest.TestCase):
    def test_ttm_sums_first_four_quarters(self):
        self.assertEqual(_ttm(INCOME, "revenue"), 400)
        self.assertEqual(_prior_ttm(INCOME, "revenue"), 360)

    def test_ttm_none_when_any_quarter_missing_key(self):
        broken = [dict(q) for q in INCOME]
        del broken[2]["revenue"]
        self.assertIsNone(_ttm(broken, "revenue"))
        self.assertEqual(_prior_ttm(broken, "revenue"), 360)

    def test_ttm_none_when_window_short(self):
        self.assertIsNone(_ttm(INCOME[:3], "revenue"))
        self.assertIsNone(_prior_ttm(INCOME[:6], "revenue"))

    def test_div_guards_none_and_zero(self):
        self.assertIsNone(_div(1.0, 0))
        self.assertIsNone(_div(None, 2.0))
        self.assertIsNone(_div(1.0, None))
        self.assertEqual(_div(1.0, 2.0), 0.5)

    def test_ols_slope_linear_series(self):
        self.assertAlmostEqual(_ols_slope([1.0, 2.0, 3.0, 4.0]), 1.0)
        self.assertAlmostEqual(_ols_slope([4.0, 3.0, 2.0, 1.0]), -1.0)

    def test_ols_slope_needs_four_points(self):
        self.assertIsNone(_ols_slope([1.0, 2.0, 3.0]))


class MetaTests(unittest.TestCase):
    def test_meta_block(self):
        meta = fingerprint()["meta"]
        self.assertEqual(meta["quarters_available"], 8)
        self.assertEqual(meta["basis"], "ttm_vs_prior_ttm")
        self.assertEqual(meta["sector"], "Technology")

    def test_to_dict_is_json_safe(self):
        import json
        json.dumps(fingerprint())  # must not raise


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint -v
```
Expected: `ModuleNotFoundError: No module named 'backend.app.services.quant_fingerprint'`

- [ ] **Step 4: Write the skeleton implementation**

Create `backend/app/services/quant_fingerprint.py`:

```python
"""Deterministic quant fingerprint — pure functions over the FMP statement
payloads already fetched in `node_deep_dive`.

Pattern: `services/model_balancing.py` — synchronous, no I/O, unit-testable
on JSON fixtures. Every metric is independently nullable; a missing input
nulls that metric without affecting the others.

Conventions (see docs/superpowers/specs/2026-06-10-quant-fingerprint-design.md):
  - Statements arrive newest-first (FMP order).
  - Flow metrics: TTM = sum(quarters[0:4]); prior TTM = sum(quarters[4:8]).
    No partial sums — a missing key anywhere in a window yields None.
  - Point-in-time balance items compare index 0 vs index 4 (year-ago).
  - End-of-window total assets are used for ROA / asset turnover in both
    windows (the beginning-of-window variant would need a 9th quarter).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

FINANCIAL_SECTOR = "Financial Services"


# ── Low-level helpers ────────────────────────────────────────────────────────

def _f(stmt: dict | None, key: str) -> float | None:
    if not stmt:
        return None
    v = stmt.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _window(stmts: list[dict], key: str, start: int) -> float | None:
    """Sum a 4-quarter window; None unless all four quarters carry the key."""
    if len(stmts) < start + 4:
        return None
    vals = [_f(s, key) for s in stmts[start:start + 4]]
    if any(v is None for v in vals):
        return None
    return sum(vals)


def _ttm(stmts: list[dict], key: str) -> float | None:
    return _window(stmts, key, 0)


def _prior_ttm(stmts: list[dict], key: str) -> float | None:
    return _window(stmts, key, 4)


def _avg_window(stmts: list[dict], key: str, start: int) -> float | None:
    total = _window(stmts, key, start)
    return total / 4 if total is not None else None


def _div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def _ols_slope(values: list[float]) -> float | None:
    """Least-squares slope over x = 0..n-1. None with < 4 points."""
    n = len(values)
    if n < 4:
        return None
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    sxx = sum((i - x_mean) ** 2 for i in range(n))
    sxy = sum((i - x_mean) * (values[i] - y_mean) for i in range(n))
    return sxy / sxx if sxx else None


def _round(v: float | None, places: int = 4) -> float | None:
    return round(v, places) if v is not None else None


def _is_financial(profile: dict) -> bool:
    return (profile or {}).get("sector") == FINANCIAL_SECTOR


# ── Top-level ────────────────────────────────────────────────────────────────

@dataclass
class QuantFingerprint:
    """JSON-safe payload stored on CuratedFinancials.quant_fingerprint.

    No from_dict — nothing rehydrates it; the raw dict round-trips through
    CuratedFinancials the same way macro_indicators does.
    """
    piotroski: dict
    altman_z: dict
    beneish_m: dict
    accruals_ratio: float | None
    fcf_conversion: float | None
    sbc: dict
    margin_slopes: dict
    meta: dict

    def to_dict(self) -> dict:
        return asdict(self)


def build_quant_fingerprint(
    income: list[dict],
    balance: list[dict],
    cashflow: list[dict],
    profile: dict,
) -> QuantFingerprint:
    income = income or []
    balance = balance or []
    cashflow = cashflow or []
    profile = profile or {}

    return QuantFingerprint(
        piotroski={"score": 0, "components_evaluated": 0, "components": []},
        altman_z={"z": None, "zone": None, "not_applicable_reason": None},
        beneish_m={"m": None, "zone": None, "ratios": {},
                   "inputs_missing": [], "not_applicable_reason": None},
        accruals_ratio=None,
        fcf_conversion=None,
        sbc={"sbc_pct_revenue": None, "share_growth_yoy_pct": None},
        margin_slopes={},
        meta={
            "quarters_available": min(len(income), len(balance), len(cashflow)),
            "basis": "ttm_vs_prior_ttm",
            "sector": profile.get("sector") or "",
        },
    )
```

(The placeholder sub-blocks are replaced by real builders in Tasks 2–5.)

- [ ] **Step 5: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint -v
```
Expected: all `HelperTests` + `MetaTests` PASS (9 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/quant_fingerprint.py backend/tests/test_quant_fingerprint.py
git commit -m "feat(quant): quant fingerprint module skeleton — TTM helpers, OLS slope, meta"
```

---

### Task 2: Piotroski F-score

**Files:**
- Modify: `backend/app/services/quant_fingerprint.py`
- Test: `backend/tests/test_quant_fingerprint.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_quant_fingerprint.py`:

```python
class PiotroskiTests(unittest.TestCase):
    """Fixture passes 8 of 9 checks. no_dilution fails: avg diluted shares
    rose 100 -> 102. Hand-checks: ROA .2 > .1579; CFO 120 > NI 80;
    leverage .125 <= .1579; CR 2.0 > 1.8; GM .6 > .5556; ATO 1.0 > .9474."""

    def test_score_and_evaluated(self):
        p = fingerprint()["piotroski"]
        self.assertEqual(p["score"], 8)
        self.assertEqual(p["components_evaluated"], 9)

    def test_component_keys_and_failure(self):
        p = fingerprint()["piotroski"]
        by_key = {c["key"]: c for c in p["components"]}
        self.assertEqual(
            list(by_key),
            ["roa_positive", "cfo_positive", "roa_delta", "accruals_quality",
             "leverage_delta", "current_ratio_delta", "no_dilution",
             "gross_margin_delta", "asset_turnover_delta"],
        )
        self.assertFalse(by_key["no_dilution"]["passed"])
        self.assertTrue(by_key["roa_positive"]["passed"])
        self.assertTrue(by_key["leverage_delta"]["passed"])

    def test_zero_debt_stays_zero_passes_leverage(self):
        bal = [dict(b, longTermDebt=0) for b in BALANCE]
        p = fingerprint(balance=bal)["piotroski"]
        by_key = {c["key"]: c for c in p["components"]}
        self.assertTrue(by_key["leverage_delta"]["passed"])

    def test_four_quarters_degrades_to_three_evaluated(self):
        p = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])["piotroski"]
        self.assertEqual(p["components_evaluated"], 3)
        self.assertEqual(p["score"], 3)  # roa_positive, cfo_positive, accruals_quality
        by_key = {c["key"]: c for c in p["components"]}
        self.assertIsNone(by_key["roa_delta"]["passed"])
        self.assertIsNone(by_key["no_dilution"]["passed"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint.PiotroskiTests -v
```
Expected: FAIL (`score` is 0, `components` empty).

- [ ] **Step 3: Implement `build_piotroski`**

Add to `quant_fingerprint.py` (above `QuantFingerprint`), and replace the `piotroski=` placeholder in `build_quant_fingerprint` with `piotroski=build_piotroski(income, balance, cashflow),`:

```python
# ── Piotroski F-score ────────────────────────────────────────────────────────

def build_piotroski(income: list[dict], balance: list[dict], cashflow: list[dict]) -> dict:
    b0 = balance[0] if balance else None
    b4 = balance[4] if len(balance) > 4 else None

    ni_ttm = _ttm(income, "netIncome")
    ni_prior = _prior_ttm(income, "netIncome")
    cfo_ttm = _ttm(cashflow, "operatingCashFlow")
    rev_ttm = _ttm(income, "revenue")
    rev_prior = _prior_ttm(income, "revenue")
    ta0 = _f(b0, "totalAssets")
    ta4 = _f(b4, "totalAssets")

    roa_now = _div(ni_ttm, ta0)
    roa_prior = _div(ni_prior, ta4)
    lev_now = _div(_f(b0, "longTermDebt"), ta0)
    lev_prior = _div(_f(b4, "longTermDebt"), ta4)
    cr_now = _div(_f(b0, "totalCurrentAssets"), _f(b0, "totalCurrentLiabilities"))
    cr_prior = _div(_f(b4, "totalCurrentAssets"), _f(b4, "totalCurrentLiabilities"))
    shares_now = _avg_window(income, "weightedAverageShsOutDil", 0)
    shares_prior = _avg_window(income, "weightedAverageShsOutDil", 4)
    gm_now = _div(_ttm(income, "grossProfit"), rev_ttm)
    gm_prior = _div(_prior_ttm(income, "grossProfit"), rev_prior)
    ato_now = _div(rev_ttm, ta0)
    ato_prior = _div(rev_prior, ta4)

    def gt(a, b):
        return None if a is None or b is None else a > b

    def lte(a, b):
        return None if a is None or b is None else a <= b

    def detail(now, prior):
        if now is None or prior is None:
            return "insufficient data"
        return f"{now:.4g} now vs {prior:.4g} prior"

    components = [
        {"key": "roa_positive", "label": "ROA positive (TTM)",
         "passed": None if roa_now is None else roa_now > 0,
         "detail": "insufficient data" if roa_now is None else f"ROA {roa_now:.4g}"},
        {"key": "cfo_positive", "label": "Operating cash flow positive (TTM)",
         "passed": None if cfo_ttm is None else cfo_ttm > 0,
         "detail": "insufficient data" if cfo_ttm is None else f"CFO {cfo_ttm:.4g}"},
        {"key": "roa_delta", "label": "ROA improved YoY",
         "passed": gt(roa_now, roa_prior), "detail": detail(roa_now, roa_prior)},
        {"key": "accruals_quality", "label": "CFO exceeds net income (TTM)",
         "passed": None if cfo_ttm is None or ni_ttm is None else cfo_ttm > ni_ttm,
         "detail": detail(cfo_ttm, ni_ttm)},
        {"key": "leverage_delta", "label": "Long-term leverage flat or lower YoY",
         "passed": lte(lev_now, lev_prior), "detail": detail(lev_now, lev_prior)},
        {"key": "current_ratio_delta", "label": "Current ratio improved YoY",
         "passed": gt(cr_now, cr_prior), "detail": detail(cr_now, cr_prior)},
        {"key": "no_dilution", "label": "No net share issuance YoY",
         "passed": lte(shares_now, shares_prior), "detail": detail(shares_now, shares_prior)},
        {"key": "gross_margin_delta", "label": "Gross margin improved YoY",
         "passed": gt(gm_now, gm_prior), "detail": detail(gm_now, gm_prior)},
        {"key": "asset_turnover_delta", "label": "Asset turnover improved YoY",
         "passed": gt(ato_now, ato_prior), "detail": detail(ato_now, ato_prior)},
    ]
    return {
        "score": sum(1 for c in components if c["passed"] is True),
        "components_evaluated": sum(1 for c in components if c["passed"] is not None),
        "components": components,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quant_fingerprint.py backend/tests/test_quant_fingerprint.py
git commit -m "feat(quant): Piotroski F-score with per-component pass/fail"
```

---

### Task 3: Altman Z-score (+ live sector-string verification)

**Files:**
- Modify: `backend/app/services/quant_fingerprint.py`
- Test: `backend/tests/test_quant_fingerprint.py`

- [ ] **Step 1: Live-verify the financial-sector string (FMP-gotcha discipline)**

```bash
backend/venv/bin/python -c "
import asyncio
from backend.app.clients.fmp import FMPClient
async def main():
    p, _ = await FMPClient().get_company_profile('JPM')
    prof = p[0] if isinstance(p, list) and p else p
    print(repr(prof.get('sector')))
asyncio.run(main())
"
```
Expected: `'Financial Services'`. **If it prints anything else, update `FINANCIAL_SECTOR` in `quant_fingerprint.py` to the live string and note it in the commit message.**

- [ ] **Step 2: Write the failing tests**

Append to `backend/tests/test_quant_fingerprint.py`:

```python
class AltmanZTests(unittest.TestCase):
    """Hand-computed: A=(200-100)/400=.25, B=120/400=.3, C=120/400=.3,
    D=2000/180=11.1111, E=400/400=1.0
    Z = 1.2(.25)+1.4(.3)+3.3(.3)+0.6(11.1111)+1.0 = 9.3767 -> safe."""

    def test_z_value_and_zone(self):
        a = fingerprint()["altman_z"]
        self.assertAlmostEqual(a["z"], 9.3767, places=3)
        self.assertEqual(a["zone"], "safe")
        self.assertIsNone(a["not_applicable_reason"])

    def test_zones(self):
        # Shrink market cap so D collapses: mcap=100 -> D=0.5556, 0.6D=0.3333
        # Z = .3+.42+.99+.3333+1.0 = 3.0433 -> still safe (>2.99).
        a = fingerprint(profile={"marketCap": 100, "sector": "Technology"})["altman_z"]
        self.assertEqual(a["zone"], "safe")
        # mcap=50 -> 0.6D=0.1667, Z=2.8767 -> grey
        a = fingerprint(profile={"marketCap": 50, "sector": "Technology"})["altman_z"]
        self.assertEqual(a["zone"], "grey")
        # mcap=1 + gut EBIT/revenue via zero-revenue income would null Z;
        # instead drop retained earnings & ebit through balance/income edits:
        income = [_iq(100, 60, 20, -200, 10, 102)] * 4 + [_iq(90, 50, 15, 25, 10, 100)] * 4
        a = fingerprint(income=income, profile={"marketCap": 1, "sector": "Technology"})["altman_z"]
        self.assertEqual(a["zone"], "distress")

    def test_financial_sector_not_applicable(self):
        a = fingerprint(profile={"marketCap": 2000, "sector": "Financial Services"})["altman_z"]
        self.assertIsNone(a["z"])
        self.assertIsNone(a["zone"])
        self.assertIn("financial", a["not_applicable_reason"].lower())

    def test_missing_inputs_null_z_without_reason(self):
        bal = [{k: v for k, v in b.items() if k != "retainedEarnings"} for b in BALANCE]
        a = fingerprint(balance=bal)["altman_z"]
        self.assertIsNone(a["z"])
        self.assertIsNone(a["not_applicable_reason"])

    def test_mktcap_legacy_fallback(self):
        a = fingerprint(profile={"mktCap": 2000, "sector": "Technology"})["altman_z"]
        self.assertAlmostEqual(a["z"], 9.3767, places=3)
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint.AltmanZTests -v
```
Expected: FAIL (`z` is None).

- [ ] **Step 4: Implement `build_altman_z`**

Add to `quant_fingerprint.py`, and replace the `altman_z=` placeholder in `build_quant_fingerprint` with `altman_z=build_altman_z(income, balance, profile),`:

```python
# ── Altman Z-score (original 1968 formula; non-financials only) ──────────────

def build_altman_z(income: list[dict], balance: list[dict], profile: dict) -> dict:
    if _is_financial(profile):
        return {"z": None, "zone": None,
                "not_applicable_reason": "Altman Z is not meaningful for financial-sector companies"}
    b0 = balance[0] if balance else None
    ta0 = _f(b0, "totalAssets")
    ca0 = _f(b0, "totalCurrentAssets")
    cl0 = _f(b0, "totalCurrentLiabilities")
    mcap = _f(profile, "marketCap")
    if mcap is None:
        mcap = _f(profile, "mktCap")

    a = _div(None if ca0 is None or cl0 is None else ca0 - cl0, ta0)
    b = _div(_f(b0, "retainedEarnings"), ta0)
    c = _div(_ttm(income, "ebit"), ta0)
    d = _div(mcap, _f(b0, "totalLiabilities"))
    e = _div(_ttm(income, "revenue"), ta0)
    if any(v is None for v in (a, b, c, d, e)):
        return {"z": None, "zone": None, "not_applicable_reason": None}
    z = 1.2 * a + 1.4 * b + 3.3 * c + 0.6 * d + 1.0 * e
    zone = "safe" if z > 2.99 else ("grey" if z >= 1.81 else "distress")
    return {"z": round(z, 4), "zone": zone, "not_applicable_reason": None}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint -v
```
Expected: all PASS. (If the distress-zone fixture math surprises you: EBIT_TTM = 4×(−200) = −800, C = −2, 3.3C = −6.6 ⇒ Z ≈ −4.88.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/quant_fingerprint.py backend/tests/test_quant_fingerprint.py
git commit -m "feat(quant): Altman Z with zone banding and financial-sector gate"
```

---

### Task 4: Beneish M-score

**Files:**
- Modify: `backend/app/services/quant_fingerprint.py`
- Test: `backend/tests/test_quant_fingerprint.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_quant_fingerprint.py`:

```python
class BeneishMTests(unittest.TestCase):
    """Hand-computed ratios for the fixture:
    DSRI=(40/400)/(45/360)=0.8        GMI=(200/360)/(240/400)=0.9259
    AQI=(1-320/400)/(1-295/380)=0.8941  SGI=400/360=1.1111
    DEPI=(20/115)/(20/120)=1.0435     SGAI=(40/400)/(40/360)=0.9
    LVGI=(150/400)/(160/380)=0.8906   TATA=(80-120)/400=-0.1
    M = -4.84 + .92(.8)+.528(.9259)+.404(.8941)+.892(1.1111)
        +.115(1.0435)-.172(.9)+4.679(-.1)-.327(.8906) = -3.0567 -> unlikely"""

    def test_m_value_zone_and_ratios(self):
        b = fingerprint()["beneish_m"]
        self.assertAlmostEqual(b["m"], -3.0567, places=3)
        self.assertEqual(b["zone"], "unlikely")
        self.assertEqual(b["inputs_missing"], [])
        self.assertAlmostEqual(b["ratios"]["dsri"], 0.8, places=4)
        self.assertAlmostEqual(b["ratios"]["tata"], -0.1, places=4)
        self.assertAlmostEqual(b["ratios"]["lvgi"], 0.8906, places=3)

    def test_missing_sga_nulls_m_with_reason(self):
        income = [{k: v for k, v in q.items()
                   if k != "sellingGeneralAndAdministrativeExpenses"} for q in INCOME]
        b = fingerprint(income=income)["beneish_m"]
        self.assertIsNone(b["m"])
        self.assertIsNone(b["zone"])
        self.assertIn("sgai", b["inputs_missing"])

    def test_four_quarters_nulls_m(self):
        b = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])["beneish_m"]
        self.assertIsNone(b["m"])
        # TATA is current-window-only and stays computable.
        self.assertNotIn("tata", b["inputs_missing"])
        self.assertIn("dsri", b["inputs_missing"])

    def test_financial_sector_not_applicable(self):
        b = fingerprint(profile={"marketCap": 2000, "sector": "Financial Services"})["beneish_m"]
        self.assertIsNone(b["m"])
        self.assertIn("financial", b["not_applicable_reason"].lower())
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint.BeneishMTests -v
```
Expected: FAIL (`m` is None, `ratios` empty).

- [ ] **Step 3: Implement `build_beneish_m`**

Add to `quant_fingerprint.py`, and replace the `beneish_m=` placeholder in `build_quant_fingerprint` with `beneish_m=build_beneish_m(income, balance, cashflow, profile),`:

```python
# ── Beneish M-score (8-ratio; non-financials only) ───────────────────────────

def build_beneish_m(income: list[dict], balance: list[dict],
                    cashflow: list[dict], profile: dict) -> dict:
    base = {"m": None, "zone": None, "ratios": {},
            "inputs_missing": [], "not_applicable_reason": None}
    if _is_financial(profile):
        base["not_applicable_reason"] = "Beneish M is not meaningful for financial-sector companies"
        return base

    b0 = balance[0] if balance else None
    b4 = balance[4] if len(balance) > 4 else None
    ta0, ta4 = _f(b0, "totalAssets"), _f(b4, "totalAssets")
    rev_ttm, rev_prior = _ttm(income, "revenue"), _prior_ttm(income, "revenue")
    ni_ttm = _ttm(income, "netIncome")
    cfo_ttm = _ttm(cashflow, "operatingCashFlow")
    da_ttm = _ttm(cashflow, "depreciationAndAmortization")
    da_prior = _prior_ttm(cashflow, "depreciationAndAmortization")
    sga_ttm = _ttm(income, "sellingGeneralAndAdministrativeExpenses")
    sga_prior = _prior_ttm(income, "sellingGeneralAndAdministrativeExpenses")
    gm_now = _div(_ttm(income, "grossProfit"), rev_ttm)
    gm_prior = _div(_prior_ttm(income, "grossProfit"), rev_prior)

    def asset_quality(b: dict | None, ta: float | None) -> float | None:
        # AQ = 1 - (CA + PPE + securities)/TA. longTermInvestments is the
        # securities term; short-term investments already sit inside CA.
        ca, ppe, lti = (_f(b, "totalCurrentAssets"),
                        _f(b, "propertyPlantEquipmentNet"),
                        _f(b, "longTermInvestments"))
        if None in (ca, ppe, lti) or not ta:
            return None
        return 1 - (ca + ppe + lti) / ta

    def leverage(b: dict | None, ta: float | None) -> float | None:
        ltd, cl = _f(b, "longTermDebt"), _f(b, "totalCurrentLiabilities")
        if None in (ltd, cl) or not ta:
            return None
        return (ltd + cl) / ta

    def dep_rate(da: float | None, b: dict | None) -> float | None:
        ppe = _f(b, "propertyPlantEquipmentNet")
        if da is None or ppe is None or (da + ppe) == 0:
            return None
        return da / (da + ppe)

    ratios = {
        "dsri": _div(_div(_f(b0, "netReceivables"), rev_ttm),
                     _div(_f(b4, "netReceivables"), rev_prior)),
        "gmi": _div(gm_prior, gm_now),
        "aqi": _div(asset_quality(b0, ta0), asset_quality(b4, ta4)),
        "sgi": _div(rev_ttm, rev_prior),
        "depi": _div(dep_rate(da_prior, b4), dep_rate(da_ttm, b0)),
        "sgai": _div(_div(sga_ttm, rev_ttm), _div(sga_prior, rev_prior)),
        "lvgi": _div(leverage(b0, ta0), leverage(b4, ta4)),
        "tata": _div(None if ni_ttm is None or cfo_ttm is None else ni_ttm - cfo_ttm, ta0),
    }
    base["ratios"] = {k: _round(v) for k, v in ratios.items()}
    missing = [k for k, v in ratios.items() if v is None]
    if missing:
        base["inputs_missing"] = missing
        return base

    m = (-4.84 + 0.92 * ratios["dsri"] + 0.528 * ratios["gmi"]
         + 0.404 * ratios["aqi"] + 0.892 * ratios["sgi"] + 0.115 * ratios["depi"]
         - 0.172 * ratios["sgai"] + 4.679 * ratios["tata"] - 0.327 * ratios["lvgi"])
    base["m"] = round(m, 4)
    base["zone"] = "flag" if m > -1.78 else ("caution" if m >= -2.22 else "unlikely")
    return base
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quant_fingerprint.py backend/tests/test_quant_fingerprint.py
git commit -m "feat(quant): Beneish M-score — 8 ratios, zone banding, all-or-null"
```

---

### Task 5: Accruals, FCF conversion, SBC dilution, margin slopes

**Files:**
- Modify: `backend/app/services/quant_fingerprint.py`
- Test: `backend/tests/test_quant_fingerprint.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_quant_fingerprint.py`:

```python
class ScalarMetricTests(unittest.TestCase):
    def test_accruals_ratio_avg_ta(self):
        # (80-120)/((400+380)/2) = -40/390 = -0.1026
        self.assertAlmostEqual(fingerprint()["accruals_ratio"], -0.1026, places=3)

    def test_accruals_falls_back_to_ta0_with_four_quarters(self):
        fp = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])
        self.assertAlmostEqual(fp["accruals_ratio"], -0.1, places=4)  # -40/400

    def test_fcf_conversion(self):
        self.assertAlmostEqual(fingerprint()["fcf_conversion"], 1.25, places=4)  # 100/80

    def test_fcf_conversion_null_on_negative_ni(self):
        income = [_iq(100, 60, -20, 30, 10, 102)] * 4 + [_iq(90, 50, 15, 25, 10, 100)] * 4
        self.assertIsNone(fingerprint(income=income)["fcf_conversion"])

    def test_sbc_block(self):
        sbc = fingerprint()["sbc"]
        self.assertAlmostEqual(sbc["sbc_pct_revenue"], 4.0, places=2)        # 16/400
        self.assertAlmostEqual(sbc["share_growth_yoy_pct"], 2.0, places=2)   # 102/100 - 1

    def test_sbc_share_growth_null_with_four_quarters(self):
        sbc = fingerprint(INCOME[:4], BALANCE[:4], CASHFLOW[:4])["sbc"]
        self.assertAlmostEqual(sbc["sbc_pct_revenue"], 4.0, places=2)
        self.assertIsNone(sbc["share_growth_yoy_pct"])


class MarginSlopeTests(unittest.TestCase):
    def test_rising_gross_margin_positive_slope(self):
        # Chronological gross margins: 4x 55.56% then 4x 60% -> positive slope.
        slopes = fingerprint()["margin_slopes"]
        self.assertGreater(slopes["gross"]["slope_pp_per_quarter"], 0)
        self.assertEqual(slopes["gross"]["quarters"], 8)
        self.assertIn("operating", slopes)
        self.assertIn("net", slopes)

    def test_skips_zero_revenue_quarters(self):
        income = list(INCOME)
        income[7] = dict(income[7], revenue=0)
        slopes = fingerprint(income=income)["margin_slopes"]
        self.assertEqual(slopes["gross"]["quarters"], 7)

    def test_under_four_points_null_slope(self):
        slopes = fingerprint(INCOME[:3], BALANCE[:3], CASHFLOW[:3])["margin_slopes"]
        self.assertIsNone(slopes["gross"]["slope_pp_per_quarter"])
        self.assertEqual(slopes["gross"]["quarters"], 3)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint.ScalarMetricTests backend.tests.test_quant_fingerprint.MarginSlopeTests -v
```
Expected: FAIL (nulls everywhere).

- [ ] **Step 3: Implement the remaining builders**

Add to `quant_fingerprint.py`:

```python
# ── SBC dilution + margin slopes ─────────────────────────────────────────────

def build_sbc(income: list[dict], cashflow: list[dict]) -> dict:
    pct = _div(_ttm(cashflow, "stockBasedCompensation"), _ttm(income, "revenue"))
    growth = _div(_avg_window(income, "weightedAverageShsOutDil", 0),
                  _avg_window(income, "weightedAverageShsOutDil", 4))
    return {
        "sbc_pct_revenue": _round(pct * 100, 2) if pct is not None else None,
        "share_growth_yoy_pct": _round((growth - 1) * 100, 2) if growth is not None else None,
    }


def build_margin_slopes(income: list[dict]) -> dict:
    def margin_series(numerator: str) -> list[float]:
        pts = []
        for stmt in reversed(income):  # chronological, oldest first
            rev, num = _f(stmt, "revenue"), _f(stmt, numerator)
            if rev and num is not None:
                pts.append(num / rev * 100)
        return pts

    out = {}
    for label, numerator in (("gross", "grossProfit"),
                             ("operating", "operatingIncome"),
                             ("net", "netIncome")):
        pts = margin_series(numerator)
        out[label] = {
            "slope_pp_per_quarter": _round(_ols_slope(pts)),
            "quarters": len(pts),
        }
    return out
```

Then replace the remaining placeholders in `build_quant_fingerprint` so the full body reads:

```python
    income = income or []
    balance = balance or []
    cashflow = cashflow or []
    profile = profile or {}

    ni_ttm = _ttm(income, "netIncome")
    cfo_ttm = _ttm(cashflow, "operatingCashFlow")
    ta0 = _f(balance[0] if balance else None, "totalAssets")
    ta4 = _f(balance[4] if len(balance) > 4 else None, "totalAssets")
    # Avg of window endpoints when the year-ago balance exists; TA[0] otherwise
    # (meta.quarters_available makes the fallback interpretable downstream).
    accrual_den = (ta0 + ta4) / 2 if ta0 is not None and ta4 is not None else ta0
    accruals = _div(None if ni_ttm is None or cfo_ttm is None else ni_ttm - cfo_ttm,
                    accrual_den)
    fcf_conv = _div(_ttm(cashflow, "freeCashFlow"), ni_ttm) \
        if ni_ttm is not None and ni_ttm > 0 else None

    return QuantFingerprint(
        piotroski=build_piotroski(income, balance, cashflow),
        altman_z=build_altman_z(income, balance, profile),
        beneish_m=build_beneish_m(income, balance, cashflow, profile),
        accruals_ratio=_round(accruals),
        fcf_conversion=_round(fcf_conv),
        sbc=build_sbc(income, cashflow),
        margin_slopes=build_margin_slopes(income),
        meta={
            "quarters_available": min(len(income), len(balance), len(cashflow)),
            "basis": "ttm_vs_prior_ttm",
            "sector": profile.get("sector") or "",
        },
    )
```

- [ ] **Step 4: Run the whole module's tests**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint -v
```
Expected: all PASS (≈27 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/quant_fingerprint.py backend/tests/test_quant_fingerprint.py
git commit -m "feat(quant): accruals, FCF conversion, SBC dilution, margin-trend slopes"
```

---

### Task 6: Attach to CuratedFinancials + node wiring

**Files:**
- Modify: `backend/app/graph/state.py` (CuratedFinancials: field ~line 226, `to_dict` ~line 269, `from_dict` ~line 314)
- Modify: `backend/app/graph/nodes.py` (`_build_curated_financials` return, ~line 674)
- Test: `backend/tests/test_quant_fingerprint.py`

> **Spec refinement:** the spec sketches the attach in `node_deep_dive` right after `_build_curated_financials(...)`. Attach **inside** `_build_curated_financials` instead — it already receives `income/balance/cashflow/profile`, is pure, and is directly unit-tested (`test_deep_dive_valuation_ratios.py` pattern). Same behavior, one edit point, testable without the async node.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_quant_fingerprint.py`:

```python
class CuratedAttachTests(unittest.TestCase):
    def test_build_curated_financials_attaches_fingerprint(self):
        from backend.app.graph.nodes import _build_curated_financials
        curated = _build_curated_financials(
            ticker="TEST", income=INCOME, balance=BALANCE, cashflow=CASHFLOW,
            profile=PROFILE, dcf=None, estimates=[],
        )
        fp = curated.quant_fingerprint
        self.assertIsNotNone(fp)
        self.assertEqual(fp["piotroski"]["score"], 8)
        self.assertEqual(fp["meta"]["quarters_available"], 8)

    def test_empty_payloads_still_attach_null_metrics(self):
        from backend.app.graph.nodes import _build_curated_financials
        curated = _build_curated_financials(
            ticker="TEST", income=[], balance=[], cashflow=[],
            profile={}, dcf=None, estimates=[],
        )
        self.assertIsNotNone(curated.quant_fingerprint)
        self.assertIsNone(curated.quant_fingerprint["altman_z"]["z"])

    def test_curated_financials_round_trip(self):
        from backend.app.graph.state import CuratedFinancials
        cf = CuratedFinancials(ticker="TEST", company_name="T", sector="",
                               industry="", market_cap=0, current_price=0)
        cf.quant_fingerprint = fingerprint()
        rehydrated = CuratedFinancials.from_dict(cf.to_dict())
        self.assertEqual(rehydrated.quant_fingerprint["piotroski"]["score"], 8)

    def test_old_payload_without_key_round_trips_none(self):
        from backend.app.graph.state import CuratedFinancials
        cf = CuratedFinancials(ticker="TEST", company_name="T", sector="",
                               industry="", market_cap=0, current_price=0)
        d = cf.to_dict()
        d.pop("quant_fingerprint", None)  # simulate an old persisted run
        self.assertIsNone(CuratedFinancials.from_dict(d).quant_fingerprint)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint.CuratedAttachTests -v
```
Expected: FAIL (`CuratedFinancials` has no attribute `quant_fingerprint`).

- [ ] **Step 3: Add the field to `CuratedFinancials` (state.py)**

After the `macro_indicators` field (line ~226):

```python
    # Deterministic quant fingerprint (services/quant_fingerprint.py),
    # attached in _build_curated_financials. Raw dict — like macro_indicators.
    quant_fingerprint: dict | None = None
```

In `to_dict()`, after `"macro_indicators": self.macro_indicators,`:

```python
            "quant_fingerprint": self.quant_fingerprint,
```

In `from_dict()`, after `macro_indicators=d.get("macro_indicators"),`:

```python
            quant_fingerprint=d.get("quant_fingerprint"),
```

- [ ] **Step 4: Attach in `_build_curated_financials` (nodes.py)**

Add to the import block at the top of `nodes.py`:

```python
from backend.app.services.quant_fingerprint import build_quant_fingerprint
```

In `_build_curated_financials`, change the single `return CuratedFinancials(...)` expression (line ~674) to assign-then-return, appending after the close of the constructor call:

```python
    curated = CuratedFinancials(
        ...  # existing args unchanged
    )
    # Defensive: a quant bug must not null out the whole curated payload.
    try:
        curated.quant_fingerprint = build_quant_fingerprint(
            income, balance, cashflow, prof
        ).to_dict()
    except Exception as e:
        logger.warning("[%s] quant fingerprint computation failed: %s", ticker, e)
    return curated
```

(`prof` is the already-normalized profile dict from line ~605; `logger` exists at module level.)

- [ ] **Step 5: Run tests + the curated-financials regression module**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint backend.tests.test_deep_dive_valuation_ratios -v
```
Expected: all PASS (the valuation-ratio module pins `_build_curated_financials` with empty statements — Step 4's try/except keeps it green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/state.py backend/app/graph/nodes.py backend/tests/test_quant_fingerprint.py
git commit -m "feat(quant): attach fingerprint to CuratedFinancials in _build_curated_financials"
```

---

### Task 7: QUANT_ROUTING table

**Files:**
- Modify: `backend/app/graph/deep_dive_routing.py`
- Test: `backend/tests/test_deep_dive_routing.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_deep_dive_routing.py` (import `QUANT_ROUTING` in the existing import block):

```python
class QuantRoutingTests(unittest.TestCase):
    def test_financial_health_quant_metrics(self):
        r = routing_for("Financial Health")
        self.assertEqual(r.quant_metrics,
                         ["piotroski", "altman_z", "accruals", "fcf_conversion"])

    def test_risk_assessment_gets_forensic_scores(self):
        r = routing_for("Risk Assessment")
        self.assertEqual(r.quant_metrics, ["altman_z", "beneish_m", "accruals"])

    def test_unrouted_category_empty(self):
        self.assertEqual(routing_for("Technical & Market Structure").quant_metrics, [])
        self.assertEqual(routing_for("Macro & Regime").quant_metrics, [])

    def test_table_uses_known_metric_keys_only(self):
        known = {"piotroski", "altman_z", "beneish_m", "accruals",
                 "fcf_conversion", "sbc", "margin_slopes"}
        for cat, keys in QUANT_ROUTING.items():
            self.assertTrue(set(keys) <= known, f"{cat} routes unknown key")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_deep_dive_routing -v
```
Expected: FAIL (ImportError on `QUANT_ROUTING`).

- [ ] **Step 3: Implement the routing**

In `deep_dive_routing.py`, after `RELATIONSHIP_ROUTING` (line ~101):

```python
# Deterministic quant fingerprint metric groups (services/quant_fingerprint.py).
# Keys are metric-group names inside CuratedFinancials.quant_fingerprint.
QUANT_ROUTING: dict[str, list[str]] = {
    "Financial Health": ["piotroski", "altman_z", "accruals", "fcf_conversion"],
    "Risk Assessment": ["altman_z", "beneish_m", "accruals"],
    "Growth & Earnings": ["margin_slopes", "sbc", "fcf_conversion"],
    "Business Quality": ["margin_slopes", "piotroski"],
    "Management & Governance": ["sbc", "beneish_m"],
}
```

In `CategoryRouting`, after `relationships: bool = False`:

```python
    quant_metrics: list[str] = field(default_factory=list)
```

In `routing_for`, after the `relationships=` line:

```python
        quant_metrics=list(QUANT_ROUTING.get(category, [])),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_deep_dive_routing -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/deep_dive_routing.py backend/tests/test_deep_dive_routing.py
git commit -m "feat(quant): QUANT_ROUTING per-category metric groups"
```

---

### Task 8: build_quant_context builder

**Files:**
- Modify: `backend/app/graph/deep_dive_context.py`
- Test: `backend/tests/test_deep_dive_context.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_deep_dive_context.py` (add `build_quant_context` to the existing import block; the `_ctx` helper already exists at the top of the file):

```python
# ── quant ───────────────────────────────────────────────────────────────────

QUANT_FP = {
    "piotroski": {"score": 8, "components_evaluated": 9, "components": [
        {"key": "roa_positive", "label": "ROA positive (TTM)", "passed": True, "detail": "ROA 0.2"},
        {"key": "no_dilution", "label": "No net share issuance YoY", "passed": False, "detail": "102 now vs 100 prior"},
    ]},
    "altman_z": {"z": 9.3767, "zone": "safe", "not_applicable_reason": None},
    "beneish_m": {"m": -3.0567, "zone": "unlikely", "ratios": {"dsri": 0.8, "tata": -0.1},
                  "inputs_missing": [], "not_applicable_reason": None},
    "accruals_ratio": -0.1026,
    "fcf_conversion": 1.25,
    "sbc": {"sbc_pct_revenue": 4.0, "share_growth_yoy_pct": 2.0},
    "margin_slopes": {"gross": {"slope_pp_per_quarter": 0.85, "quarters": 8},
                      "operating": {"slope_pp_per_quarter": None, "quarters": 3},
                      "net": {"slope_pp_per_quarter": -0.1, "quarters": 8}},
    "meta": {"quarters_available": 8, "basis": "ttm_vs_prior_ttm", "sector": "Technology"},
}


class BuildQuantContextTests(unittest.TestCase):
    def test_empty_when_category_unrouted(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        self.assertEqual(build_quant_context(ctx, "Macro & Regime"), "")

    def test_empty_when_no_fingerprint(self):
        self.assertEqual(build_quant_context(_ctx(), "Financial Health"), "")
        ctx = _ctx(curated_financials={})
        self.assertEqual(build_quant_context(ctx, "Financial Health"), "")

    def test_routed_renders_only_routed_groups(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        out = build_quant_context(ctx, "Risk Assessment")  # altman, beneish, accruals
        self.assertIn("Altman Z: 9.3767 (safe", out)
        self.assertIn("Beneish M: -3.0567 (unlikely", out)
        self.assertIn("Accruals ratio", out)
        self.assertNotIn("Piotroski", out)
        self.assertNotIn("SBC", out)

    def test_header_framing_pinned(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        out = build_quant_context(ctx, "Financial Health")
        self.assertIn("Do NOT recompute these; interpret them", out)
        self.assertIn("Piotroski F-score: 8/9 (9 evaluated)", out)
        self.assertIn("✗ no_dilution", out)

    def test_not_applicable_rendered_as_gap(self):
        fp = dict(QUANT_FP)
        fp["altman_z"] = {"z": None, "zone": None,
                          "not_applicable_reason": "Altman Z is not meaningful for financial-sector companies"}
        ctx = _ctx(curated_financials={"quant_fingerprint": fp})
        out = build_quant_context(ctx, "Risk Assessment")
        self.assertIn("Altman Z: n/a — Altman Z is not meaningful", out)

    def test_margin_slopes_skip_null_entries(self):
        ctx = _ctx(curated_financials={"quant_fingerprint": QUANT_FP})
        out = build_quant_context(ctx, "Growth & Earnings")
        self.assertIn("gross +0.85pp/q over 8q", out)
        self.assertIn("net -0.1pp/q over 8q", out)
        self.assertNotIn("operating", out.split("Margin trend slopes")[1].split("\n")[0])

    def test_build_all_contexts_includes_quant_kind(self):
        ctx = _ctx(categories=["Financial Health"],
                   curated_financials={"quant_fingerprint": QUANT_FP})
        all_ctx = build_all_contexts(ctx)
        self.assertIn("quant", all_ctx["Financial Health"])
        self.assertIn("Piotroski", all_ctx["Financial Health"]["quant"])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_deep_dive_context -v
```
Expected: FAIL (ImportError on `build_quant_context`).

- [ ] **Step 3: Implement the builder**

In `deep_dive_context.py`: add `QUANT_ROUTING` to the `deep_dive_routing` import block, then add before the Dispatcher section:

```python
_QUANT_HEADER = (
    "Deterministic quant metrics (computed in pure Python from the FMP statements "
    "above — Tier 1, established facts. Do NOT recompute these; interpret them. "
    "Where a metric is null or marked not-applicable, treat it as a stated data "
    "gap, not a derivable value.)"
)


def _render_quant_metric(key: str, fp: dict) -> str:
    if key == "piotroski":
        p = fp.get("piotroski") or {}
        comps = p.get("components") or []
        if not comps:
            return ""
        marks = {True: "✓", False: "✗", None: "—"}
        detail = ", ".join(f"{marks[c.get('passed')]} {c.get('key')}" for c in comps)
        return (f"Piotroski F-score: {p.get('score')}/9 "
                f"({p.get('components_evaluated')} evaluated): {detail}")
    if key == "altman_z":
        a = fp.get("altman_z") or {}
        if a.get("not_applicable_reason"):
            return f"Altman Z: n/a — {a['not_applicable_reason']}"
        if a.get("z") is None:
            return "Altman Z: null (insufficient inputs)"
        return (f"Altman Z: {a['z']} ({a['zone']}; "
                ">2.99 safe, 1.81–2.99 grey, <1.81 distress)")
    if key == "beneish_m":
        b = fp.get("beneish_m") or {}
        if b.get("not_applicable_reason"):
            return f"Beneish M: n/a — {b['not_applicable_reason']}"
        if b.get("m") is None:
            missing = ", ".join(b.get("inputs_missing") or []) or "insufficient inputs"
            return f"Beneish M: null (missing: {missing})"
        ratios = b.get("ratios") or {}
        ratio_str = ", ".join(f"{k}={v}" for k, v in ratios.items() if v is not None)
        return (f"Beneish M: {b['m']} ({b['zone']}; >-1.78 flag, "
                f"-2.22..-1.78 caution, <-2.22 unlikely) [{ratio_str}]")
    if key == "accruals":
        v = fp.get("accruals_ratio")
        if v is None:
            return ""
        return (f"Accruals ratio ((NI−CFO)/avg TA, TTM): {v} "
                "(large positive ⇒ earnings outrunning cash)")
    if key == "fcf_conversion":
        v = fp.get("fcf_conversion")
        return "" if v is None else f"FCF conversion (FCF/NI, TTM): {v}"
    if key == "sbc":
        s = fp.get("sbc") or {}
        parts = []
        if s.get("sbc_pct_revenue") is not None:
            parts.append(f"SBC {s['sbc_pct_revenue']}% of revenue (TTM)")
        if s.get("share_growth_yoy_pct") is not None:
            parts.append(f"diluted shares {s['share_growth_yoy_pct']:+g}% YoY")
        return "; ".join(parts)
    if key == "margin_slopes":
        m = fp.get("margin_slopes") or {}
        parts = []
        for label in ("gross", "operating", "net"):
            entry = m.get(label) or {}
            slope = entry.get("slope_pp_per_quarter")
            if slope is not None:
                parts.append(f"{label} {slope:+g}pp/q over {entry.get('quarters')}q")
        return "Margin trend slopes (OLS): " + ", ".join(parts) if parts else ""
    return ""


def build_quant_context(ctx: DeepDiveContext, category: str) -> str:
    metric_keys = QUANT_ROUTING.get(category)
    if not metric_keys:
        return ""
    fp = (ctx.curated_financials or {}).get("quant_fingerprint")
    if not fp or not isinstance(fp, dict):
        return ""
    lines = [_QUANT_HEADER]
    for key in metric_keys:
        rendered = _render_quant_metric(key, fp)
        if rendered:
            lines.append(rendered)
    if len(lines) == 1:
        return ""
    return "\n".join(lines)
```

In `build_all_contexts`, add to the per-category dict after `"counterparty": ...`:

```python
            "quant": build_quant_context(ctx, cat),
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
backend/venv/bin/python -m unittest backend.tests.test_deep_dive_context -v
```
Expected: all PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/deep_dive_context.py backend/tests/test_deep_dive_context.py
git commit -m "feat(quant): build_quant_context prompt builder with routed metric rendering"
```

---

### Task 9: Prompt slot + node threading

**Files:**
- Modify: `backend/app/graph/prompts.py` (`DEEP_DIVE_USER`, lines 88–113)
- Modify: `backend/app/graph/nodes.py` (`_run_one_category` ~line 489; call site ~line 995; `_build_targeted_context_for_category` ~line 969)
- Test: `backend/tests/test_quant_fingerprint.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_quant_fingerprint.py`:

```python
class PromptSlotTests(unittest.TestCase):
    def test_quant_data_slot_present_exactly_once(self):
        from backend.app.graph.prompts import DEEP_DIVE_USER
        self.assertEqual(DEEP_DIVE_USER.count("{quant_data}"), 1)
        # Positioned directly after the fundamentals block.
        self.assertLess(DEEP_DIVE_USER.index("{data}"), DEEP_DIVE_USER.index("{quant_data}"))
        self.assertLess(DEEP_DIVE_USER.index("{quant_data}"), DEEP_DIVE_USER.index("{transcript_data}"))

    def test_template_formats_with_quant_kwarg(self):
        from backend.app.graph.prompts import DEEP_DIVE_USER
        rendered = DEEP_DIVE_USER.format(
            ticker="NVDA", theme="ai", category="Financial Health", data="d",
            quant_data="QUANT-SENTINEL", transcript_data="", macro_data="",
            technical_data="", sentiment_data="", edgar_data="",
            filing_excerpts="", counterparty_context="", prior_questions="",
            loop_context="",
        )
        self.assertIn("QUANT-SENTINEL", rendered)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint.PromptSlotTests -v
```
Expected: FAIL (count is 0).

- [ ] **Step 3: Add the slot to `DEEP_DIVE_USER`**

In `prompts.py`, change:

```
Available data:
{data}

{transcript_data}
```

to:

```
Available data:
{data}

{quant_data}

{transcript_data}
```

- [ ] **Step 4: Thread through `_run_one_category`**

In `nodes.py` `_run_one_category` signature (line ~489), insert after `counterparty_context_text: str = "",`:

```python
    quant_context: str = "",
```

In the `DEEP_DIVE_USER.format(...)` call inside it, add after `counterparty_context=counterparty_context_text,`:

```python
                    quant_data=quant_context,
```

At the call site in `node_deep_dive` (line ~995), the args are positional — insert `category_contexts[cat]["quant"]` after the counterparty arg so positions match the new signature:

```python
        _run_one_category(
            cat, state.ticker, state.theme_id, data_text, loop_ctx_str,
            category_contexts[cat]["transcript"], category_contexts[cat]["macro"],
            category_contexts[cat]["technical"], category_contexts[cat]["sentiment"],
            category_contexts[cat]["edgar"],
            category_contexts[cat]["filing"],
            category_contexts[cat]["counterparty"],
            category_contexts[cat]["quant"],
            _render_prior_questions_slot(prior_q_map[cat]),
        )
```

In `_build_targeted_context_for_category` (line ~969), add to the label/text list after the Counterparty entry:

```python
            ("Quant context", ctx.get("quant", "")),
```

- [ ] **Step 5: Run the focused suite**

```bash
backend/venv/bin/python -m unittest backend.tests.test_quant_fingerprint backend.tests.test_deep_dive_context backend.tests.test_deep_dive_routing -v
```
Expected: all PASS.

- [ ] **Step 6: Run the full backend suite (catches any prompt/format regression elsewhere)**

```bash
backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```
Expected: OK (≈330+ tests, 0 failures). Investigate any failure before proceeding.

- [ ] **Step 7: Commit**

```bash
git add backend/app/graph/prompts.py backend/app/graph/nodes.py backend/tests/test_quant_fingerprint.py
git commit -m "feat(quant): {quant_data} prompt slot threaded through deep-dive categories"
```

---

### Task 10: Frontend — types, card, mount, registry

**Files:**
- Modify: `frontend/lib/api.ts` (CuratedFinancials interface, lines 789–833)
- Create: `frontend/components/deep-dive/sections/QuantFingerprint.tsx`
- Modify: `frontend/components/deep-dive/DeepDiveDashboard.tsx` (mount after `CrossCategoryCorrelation`, line ~76)
- Modify: `frontend/components/deep-dive/sections.ts` (Financials group, lines 25–31)

> Before editing: skim the relevant guide in `frontend/node_modules/next/dist/docs/` (Next 16 conventions). The card is a client component with no data fetching — the pattern to copy is `sections/CrossCategoryCorrelation.tsx`.

- [ ] **Step 1: Add types to `lib/api.ts`**

Insert immediately above `export interface CuratedFinancials` (line 789):

```typescript
export interface PiotroskiComponent {
  key: string;
  label: string;
  passed: boolean | null;
  detail: string;
}

export interface QuantFingerprint {
  piotroski: {
    score: number;
    components_evaluated: number;
    components: PiotroskiComponent[];
  };
  altman_z: {
    z: number | null;
    zone: "safe" | "grey" | "distress" | null;
    not_applicable_reason: string | null;
  };
  beneish_m: {
    m: number | null;
    zone: "unlikely" | "caution" | "flag" | null;
    ratios: Record<string, number | null>;
    inputs_missing: string[];
    not_applicable_reason: string | null;
  };
  accruals_ratio: number | null;
  fcf_conversion: number | null;
  sbc: { sbc_pct_revenue: number | null; share_growth_yoy_pct: number | null };
  margin_slopes: Record<
    "gross" | "operating" | "net",
    { slope_pp_per_quarter: number | null; quarters: number }
  >;
  meta: { quarters_available: number; basis: string; sector: string };
}
```

Then add to the `CuratedFinancials` interface after `macro_indicators: MacroIndicators | null;`:

```typescript
  // Absent on runs persisted before the quant layer shipped.
  quant_fingerprint?: QuantFingerprint | null;
```

- [ ] **Step 2: Create the card**

Create `frontend/components/deep-dive/sections/QuantFingerprint.tsx`:

```tsx
"use client";

import type {
  CuratedFinancials,
  QuantFingerprint as QuantFingerprintData,
  PiotroskiComponent,
} from "@/lib/api";

interface QuantFingerprintProps {
  financials: CuratedFinancials | null;
}

// Zone colors are model-defined thresholds, NOT 0-100 score tiers — do not
// swap in scoreColors.ts here.
const ZONE_STYLES: Record<string, string> = {
  safe: "bg-emerald-500/15 text-emerald-400",
  unlikely: "bg-emerald-500/15 text-emerald-400",
  grey: "bg-amber-500/15 text-amber-400",
  caution: "bg-amber-500/15 text-amber-400",
  distress: "bg-red-500/15 text-red-400",
  flag: "bg-red-500/15 text-red-400",
};

function ZonePill({ zone }: { zone: string | null }) {
  if (!zone) return null;
  return (
    <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase ${ZONE_STYLES[zone] ?? ""}`}>
      {zone}
    </span>
  );
}

function PiotroskiCheck({ component }: { component: PiotroskiComponent }) {
  const mark = component.passed === null ? "—" : component.passed ? "✓" : "✗";
  const color =
    component.passed === null
      ? "text-[var(--color-text-muted)]"
      : component.passed
        ? "text-emerald-400"
        : "text-red-400";
  return (
    <div className="flex items-start gap-1.5" title={component.detail}>
      <span className={`font-mono text-xs ${color}`}>{mark}</span>
      <span className="text-[11px] text-[var(--color-text-secondary)]">{component.label}</span>
    </div>
  );
}

function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">{label}</p>
      <p className="text-sm font-semibold text-[var(--color-text-primary)] mt-0.5">{value}</p>
      {hint && <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">{hint}</p>}
    </div>
  );
}

function fmtPct(v: number | null, digits = 1): string {
  return v === null ? "—" : `${v > 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

function ScoreModel({
  title,
  value,
  zone,
  naReason,
}: {
  title: string;
  value: number | null;
  zone: string | null;
  naReason: string | null;
}) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">{title}</p>
      {naReason ? (
        <p className="text-[11px] text-[var(--color-text-muted)] mt-1">n/a — financial sector</p>
      ) : value === null ? (
        <p className="text-[11px] text-[var(--color-text-muted)] mt-1">insufficient data</p>
      ) : (
        <div className="flex items-center gap-2 mt-0.5">
          <span className="text-sm font-semibold text-[var(--color-text-primary)]">{value.toFixed(2)}</span>
          <ZonePill zone={zone} />
        </div>
      )}
    </div>
  );
}

function SlopeRow({ label, slope, quarters }: { label: string; slope: number | null; quarters: number }) {
  if (slope === null) {
    return (
      <div className="flex items-center justify-between text-[11px]">
        <span className="text-[var(--color-text-secondary)]">{label}</span>
        <span className="text-[var(--color-text-muted)]">— ({quarters}q)</span>
      </div>
    );
  }
  const up = slope > 0;
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span className={up ? "text-emerald-400" : "text-red-400"}>
        {up ? "▲" : "▼"} {slope > 0 ? "+" : ""}
        {slope.toFixed(2)} pp/q <span className="text-[var(--color-text-muted)]">({quarters}q)</span>
      </span>
    </div>
  );
}

export function QuantFingerprint({ financials }: QuantFingerprintProps) {
  const fp: QuantFingerprintData | null | undefined = financials?.quant_fingerprint;
  if (!fp) return null; // old runs have no fingerprint — render nothing

  return (
    <section
      id="quant_fingerprint"
      className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] overflow-hidden"
    >
      <div className="px-5 py-3 border-b border-[var(--color-border)] bg-[var(--color-bg)]/40">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">Quant Fingerprint</h3>
        <p className="text-[10px] text-[var(--color-text-muted)] mt-0.5">
          Computed deterministically from {fp.meta.quarters_available} quarters (TTM vs prior-TTM) — not AI-generated
        </p>
      </div>
      <div className="p-5 space-y-5">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Piotroski */}
          <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
            <div className="flex items-center justify-between">
              <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)]">Piotroski F-Score</p>
              <span className="text-sm font-semibold text-[var(--color-text-primary)]">
                {fp.piotroski.score}/9
                {fp.piotroski.components_evaluated < 9 && (
                  <span className="text-[10px] text-[var(--color-text-muted)] ml-1">
                    ({fp.piotroski.components_evaluated} evaluated)
                  </span>
                )}
              </span>
            </div>
            <div className="mt-2 space-y-1">
              {fp.piotroski.components.map((c) => (
                <PiotroskiCheck key={c.key} component={c} />
              ))}
            </div>
          </div>
          <div className="space-y-4">
            <ScoreModel
              title="Altman Z-Score"
              value={fp.altman_z.z}
              zone={fp.altman_z.zone}
              naReason={fp.altman_z.not_applicable_reason}
            />
            <ScoreModel
              title="Beneish M-Score"
              value={fp.beneish_m.m}
              zone={fp.beneish_m.zone}
              naReason={fp.beneish_m.not_applicable_reason}
            />
          </div>
          {/* Margin slopes */}
          <div className="rounded-lg border border-[var(--color-border)] px-3 py-2">
            <p className="text-[10px] uppercase tracking-wide text-[var(--color-text-muted)] mb-2">
              Margin Trend (OLS slope)
            </p>
            <div className="space-y-1.5">
              <SlopeRow label="Gross" {...slopeProps(fp, "gross")} />
              <SlopeRow label="Operating" {...slopeProps(fp, "operating")} />
              <SlopeRow label="Net" {...slopeProps(fp, "net")} />
            </div>
          </div>
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <StatTile
            label="Accruals Ratio"
            value={fp.accruals_ratio === null ? "—" : fmtPct(fp.accruals_ratio * 100)}
            hint="(NI − CFO) / avg assets · negative is healthy"
          />
          <StatTile
            label="FCF Conversion"
            value={fp.fcf_conversion === null ? "—" : `${fp.fcf_conversion.toFixed(2)}×`}
            hint="FCF / net income, TTM"
          />
          <StatTile
            label="SBC / Revenue"
            value={fp.sbc.sbc_pct_revenue === null ? "—" : `${fp.sbc.sbc_pct_revenue.toFixed(1)}%`}
            hint="TTM stock comp intensity"
          />
          <StatTile
            label="Share Growth YoY"
            value={fmtPct(fp.sbc.share_growth_yoy_pct)}
            hint="Diluted shares, TTM avg"
          />
        </div>
      </div>
    </section>
  );
}

function slopeProps(fp: QuantFingerprintData, key: "gross" | "operating" | "net") {
  const entry = fp.margin_slopes?.[key];
  return { slope: entry?.slope_pp_per_quarter ?? null, quarters: entry?.quarters ?? 0 };
}
```

- [ ] **Step 3: Mount in `DeepDiveDashboard.tsx`**

Add to the import block:

```tsx
import { QuantFingerprint } from "./sections/QuantFingerprint";
```

After the `<CrossCategoryCorrelation ... />` line (~76):

```tsx
        {/* Quant Fingerprint — deterministic scores computed backend-side */}
        <QuantFingerprint financials={financials} />
```

- [ ] **Step 4: Register in `sections.ts`**

In the Financials group (after the `cross_category` entry):

```typescript
      { id: "quant_fingerprint", label: "Quant", title: "Quant Fingerprint" },
```

- [ ] **Step 5: Build + lint**

```bash
cd frontend && npm run build && npm run lint
```
Expected: build succeeds, lint clean. Fix any type errors before committing.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api.ts frontend/components/deep-dive/sections/QuantFingerprint.tsx frontend/components/deep-dive/DeepDiveDashboard.tsx frontend/components/deep-dive/sections.ts
git commit -m "feat(quant): Quant Fingerprint card + section registry entry"
```

---

### Task 11: Full verification + docs + PR

**Files:**
- Modify: `TODO.md` (Done log), `CLAUDE.md` (new subsection)

- [ ] **Step 1: Full backend suite**

```bash
backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```
Expected: OK, 0 failures.

- [ ] **Step 2: Frontend build + lint (again, from clean state)**

```bash
cd frontend && npm run build && npm run lint
```
Expected: clean.

- [ ] **Step 3: Optional smoke (if local DB + API keys available)**

```bash
backend/venv/bin/python -c "
import asyncio
from backend.app.clients.fmp import FMPClient
from backend.app.services.quant_fingerprint import build_quant_fingerprint
async def main():
    c = FMPClient()
    (inc, _), (bal, _), (cf, _), (prof, _) = await asyncio.gather(
        c.get_income_statement('NVDA', period='quarter', limit=8),
        c.get_balance_sheet('NVDA', period='quarter', limit=8),
        c.get_cash_flow('NVDA', period='quarter', limit=8),
        c.get_company_profile('NVDA'),
    )
    p = prof[0] if isinstance(prof, list) and prof else prof
    fp = build_quant_fingerprint(inc, bal, cf, p).to_dict()
    print('Piotroski', fp['piotroski']['score'], '/9,',
          fp['piotroski']['components_evaluated'], 'evaluated')
    print('Altman Z', fp['altman_z'])
    print('Beneish M', fp['beneish_m']['m'], fp['beneish_m']['zone'],
          'missing:', fp['beneish_m']['inputs_missing'])
    print('slopes', fp['margin_slopes'])
asyncio.run(main())
"
```
Expected: real values, no nulls except legitimately missing inputs. Sanity-check Z is positive for NVDA and M is in a plausible band (−4 to 0).

- [ ] **Step 4: Update `TODO.md`**

Add at the top of "Done (recent)":

```markdown
- **Deterministic quant layer (roadmap #5)** — `services/quant_fingerprint.py` (pure: Piotroski F, Altman Z, Beneish M, accruals, FCF conversion, SBC dilution, margin OLS slopes; TTM vs prior-TTM over the 8 quarters node_deep_dive already fetches). Attached to `CuratedFinancials.quant_fingerprint` (zero new API surface), routed into 5 category prompts via `QUANT_ROUTING` + `{quant_data}` slot ("established facts — don't recompute"), Quant Fingerprint card in the Financials cluster. Altman/Beneish n/a-gated for Financial Services. Spec: `docs/superpowers/specs/2026-06-10-quant-fingerprint-design.md`.
```

- [ ] **Step 5: Update `CLAUDE.md`**

Add a bullet to the "Deep-dive data routing" section's routing list, after the EDGAR XBRL routing bullet:

```markdown
- **Quant routing** (`QUANT_ROUTING`): deterministic quant fingerprint metric groups (Piotroski F, Altman Z, Beneish M, accruals, FCF conversion, SBC dilution, margin OLS slopes) computed in pure Python by `services/quant_fingerprint.py` from the same 8-quarter FMP statements, attached to `CuratedFinancials.quant_fingerprint` inside `_build_curated_financials`, rendered into the `{quant_data}` slot by `build_quant_context`. Financial Health / Risk Assessment / Growth & Earnings / Business Quality / Management & Governance. TTM (quarters 0–3) vs prior-TTM (quarters 4–7); every metric independently nullable; Altman/Beneish marked not-applicable for Financial Services. Frontend: `QuantFingerprint.tsx` card (Financials cluster), hidden for runs predating the feature.
```

- [ ] **Step 6: Commit docs**

```bash
git add TODO.md CLAUDE.md
git commit -m "docs: quant fingerprint — TODO done-log + CLAUDE.md routing section"
```

- [ ] **Step 7: Push and open PR**

Use the superpowers:finishing-a-development-branch skill. PR title: `feat: deterministic quant layer for deep dives (roadmap #5)`. Body should summarize: pure module, CuratedFinancials attachment, prompt routing, card; note zero-migration/zero-new-endpoints and old-run null-safety. End body with the standard generated-with footer.

---

## Self-review notes (already applied)

- **Spec coverage:** every spec section maps to a task — metric formulas (T2–T5), state attachment (T6), routing (T7), context builder (T8), prompt slot + threading (T9), frontend (T10), testing/docs/rollout (T1–T11). The spec's "compute in node_deep_dive" detail was refined to "inside `_build_curated_financials`" (Task 6 callout) — same behavior, testable without the async node.
- **Type consistency:** metric-group keys (`piotroski`, `altman_z`, `beneish_m`, `accruals`, `fcf_conversion`, `sbc`, `margin_slopes`) are identical across `QUANT_ROUTING` (T7), `_render_quant_metric` (T8), and the fingerprint dict fields (T1–T5; note `accruals` routes to the `accruals_ratio` field — handled inside `_render_quant_metric`). `quant_context` param name (nodes) vs `quant_data` format kwarg (prompt) mirrors the existing `counterparty_context_text` / `counterparty_context` split.
- **Fixture math:** Piotroski 8/9, Z = 9.3767, M = −3.0567 hand-verified against the formulas in the spec.
