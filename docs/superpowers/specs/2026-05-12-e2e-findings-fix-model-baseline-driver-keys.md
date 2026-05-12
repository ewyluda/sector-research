# Fix: AI-baseline driver-key vocabulary drift breaks the forecast model

**Source:** e2e findings 2026-05-12 (financial-model, BUG [high]; reverse-dcf, BUG [med] ×3).
**Status:** Validated against live backend. Reproduces 100% on every freshly-built model.

## Problem

End-to-end, every NVDA-style forecast model in the app is broken:

- `/model/NVDA#forecast` shows every driver row (`revenue_growth_pct`, `gross_margin_pct`, `sga_pct_revenue`, …) as em-dashes across all 13 forecast periods.
- `/model/NVDA#reverse-dcf` renders the panels but `implied_drivers` and every `priced_in` value comes back `null`.

The user-visible symptoms map to two separate e2e findings but trace to one upstream cause.

## Root cause

`backend/app/models/model_state.py:8` declares the canonical driver vocabulary:

```python
DRIVER_KEYS: list[str] = [
    "revenue_growth_pct", "revenue_absolute",
    "gross_margin_pct", "sga_pct_revenue", "rd_pct_revenue",
    "other_opex_pct_revenue", "da_pct_revenue",
    "effective_tax_rate", "interest_income_yield", "interest_expense_rate",
    "capex_pct_revenue", "dso_days", "dio_days", "dpo_days",
    "dividend_payout_ratio", "buyback_dollars", "share_count_change_pct",
    "debt_repayment_dollars", "revolver_rate",
]
```

`backend/app/services/model_balancing.py:54+` reads exactly these names (`_drv(s, p.label, "revenue_growth_pct")`, `"gross_margin_pct"`, `"sga_pct_revenue"`, etc.). The frontend `DriverPanel.tsx` also reads exactly these names.

But the Sonnet baseline prompt at `backend/app/graph/model_baseline_node.py:19-26` is open-ended:

```python
SYSTEM_PROMPT = """You are building a baseline financial forecast for a 3-statement model. \
... For each driver, give a numeric value, a one-line reason, ...
Output JSON ONLY ... Schema: {"drivers": {<period_label>: {<driver_key>: {"value": ..., "reason": ...}}}}"""
```

It says "driver_key" but never *enumerates* them. The LLM picks its own names. A live `2029Y` snapshot from a freshly-built NVDA model shows what it emitted:

```
gross_margin       = 0.73   (LLM-chosen; recompute() doesn't read this)
ebit_margin        = 0.55   (LLM-chosen; recompute() doesn't read this)
tax_rate           = 0.13   (LLM-chosen; recompute() reads effective_tax_rate)
dpo_days           = 45
dio_days           = 55
dso_days           = 50
```

And the canonical keys (`revenue_growth_pct`, `gross_margin_pct`, `sga_pct_revenue`, …) sit there with `value=None, source="driver"` — the empty shells from `_build_drivers` at `model_baseline.py:202` that the AI was supposed to fill.

Downstream consequences:

1. `recompute()` cannot compute revenue (no `revenue_growth_pct`), so `income_statement.revenue` stays empty for every forecast period.
2. With empty revenue, no margin/opex/EBIT/net-income cell gets computed.
3. `cash_flow.free_cash_flow` stays empty.
4. `dcf()` reads `cash_flow.free_cash_flow` and either raises `ValueError` or silently uses zeros depending on path.
5. `solve_implied_driver` bisects on a function whose output is meaningless → returns `None` (no root found in bracket).
6. UI: forecast grid renders only the empty `DRIVER_KEYS` cells (em-dashes); reverse-DCF table shows `priced_in: —` everywhere.

Two of the days drivers (`dpo_days`, `dso_days`, `dio_days`) *happen* to overlap with canonical names — the LLM got those right by coincidence — which is why those rows in the grid show values where it does. None of the percent-style drivers overlap.

## Fix

Pin the LLM to the canonical vocabulary. Two parts:

### 1. Use Pydantic structured output to constrain the schema

`backend/app/graph/model_baseline_node.py`: replace the open `dict[str, dict[str, DriverProposal]]` with an explicit per-key field set. The canonical list lives in `model_state.DRIVER_KEYS` — derive the schema from it so the two never drift:

```python
from backend.app.models.model_state import DRIVER_KEYS

# Build the per-period model dynamically from DRIVER_KEYS
PeriodDrivers = create_model(
    "PeriodDrivers",
    **{k: (DriverProposal | None, None) for k in DRIVER_KEYS},
)

class BaselineDriversResponse(BaseModel):
    drivers: dict[str, PeriodDrivers]
```

This is a structural pin; the LLM can still return `null` for keys that don't apply to a period, but it cannot invent `gross_margin` instead of `gross_margin_pct`.

### 2. Enumerate the canonical keys in the system prompt

Even with Pydantic validation, the prompt should *show* the LLM the names so it isn't fighting the validator. Replace the schema line in `SYSTEM_PROMPT` with the canonical list:

```
Driver keys (use exactly these names, percentages as decimals):
- revenue_growth_pct          — period-over-period revenue growth (0.10 = 10%)
- revenue_absolute            — absolute revenue $; populate ONE of growth/absolute per period
- gross_margin_pct            — gross profit / revenue
- sga_pct_revenue, rd_pct_revenue, other_opex_pct_revenue, da_pct_revenue
- effective_tax_rate
- interest_income_yield, interest_expense_rate
- capex_pct_revenue
- dso_days, dio_days, dpo_days
- dividend_payout_ratio, buyback_dollars, share_count_change_pct
- debt_repayment_dollars, revolver_rate
```

The one-line gloss matters: the LLM previously emitted `gross_margin` (the *ratio*) and `ebit_margin` because the prompt asked for "margin assumptions" — disambiguating the field tells it which slot to populate.

### 3. Validation guard

In `_apply_baseline_drivers` (`backend/app/services/model_baseline.py:135`), warn (or fail in dev) if the response contains driver keys that are NOT in `DRIVER_KEYS`. This catches future prompt regressions before they ship a broken model into production. A `set(response.drivers[label].keys()) - set(DRIVER_KEYS)` diff per period is enough.

## Verification

1. `python -m unittest backend.tests.test_model_baseline` (add if absent) with a fixture that captures the current bad-shape LLM output. New test: assert the response shape rejects unknown keys via Pydantic and that all canonical keys are present-or-null. Test must pass on the fix branch.
2. Re-run `POST /api/models/NVDA/initialize?force=true` against a real Anthropic API key (or use a recorded fixture). Confirm:
   - `state.drivers["2029Y"]["revenue_growth_pct"].value is not None`
   - `state.income_statement["revenue"]["2029Y"].value` is non-zero after recompute
   - `state.cash_flow["free_cash_flow"]["2029Y"].value` is non-zero
3. `GET /api/models/NVDA/reverse-dcf?price=220` returns non-null `implied_drivers.revenue_growth_pct` and non-null `priced_in` values.
4. Browser: `/model/NVDA#forecast` shows numeric values in the driver grid; `/model/NVDA#reverse-dcf` shows numbers in the "Priced in" column.

## Backfill

This is data corruption, not just a code bug — every saved `TickerModel` row currently in `ticker_models` has the broken drivers. After the fix lands, re-run `initialize_or_get_model(ticker, force=True)` for each affected ticker (one-off script). The saved `version=1` rows can stay; the new versions become `version=2 AI reseed`.

## Out of scope

- The earlier-mentioned `gross_margin` / `ebit_margin` keys the LLM invented are arguably *useful* (they're computed line-items rather than drivers). Not in scope here — recompute() owns those calculations. The fix is to stop the AI from putting them in the *drivers* dict.
- The `_apply_baseline_drivers` "fallback: clone from nearest annual" loop at `model_baseline.py:158-187` only helps when the LLM specifies *some* periods. With the canonical-key fix, all forecast periods get the same key vocabulary, so the fallback loop continues to work as intended.
