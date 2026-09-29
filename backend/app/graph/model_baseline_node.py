"""AI pass that proposes annual forecast drivers from history, consensus and the deep dive."""
from __future__ import annotations
from typing import Literal

from pydantic import BaseModel, ConfigDict, create_model

from backend.app.graph import llm
from backend.app.models.model_state import DRIVER_KEYS


class DriverProposal(BaseModel):
    value: float | None = None
    reason: str = ""
    source_citation_id: str | None = None


class _StrictDriversBase(BaseModel):
    """Base class for the per-period drivers model. `extra="forbid"` means the
    LLM cannot invent driver keys outside DRIVER_KEYS — Pydantic raises at parse
    time. This pins the vocabulary to the canonical set that `model_balancing.
    recompute()` reads."""
    model_config = ConfigDict(extra="forbid")


# Dynamically build a strict per-period model with one optional DriverProposal
# field per canonical driver key. Derived from DRIVER_KEYS so the two never drift.
PeriodDrivers = create_model(
    "PeriodDrivers",
    __base__=_StrictDriversBase,
    **{k: (DriverProposal | None, None) for k in DRIVER_KEYS},
)


class BaselineDriversResponse(BaseModel):
    drivers: dict[str, PeriodDrivers]   # {period_label: PeriodDrivers}


DriverKey = Literal[tuple(DRIVER_KEYS)]  # type: ignore[valid-type]


class _DriverRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    period_label: str
    driver: DriverKey
    value: float
    reason: str


class _BaselineDriversLLMOutput(BaseModel):
    """Structured-output shape: flat rows with an enum driver key.

    A nested per-period object with 19 optional driver sub-objects was
    rejected by the API as "Schema is too complex" (live, 2026-09-27); a dict
    keyed by period can't be a closed schema at all. Rows are simple, and the
    enum makes an invented driver name impossible."""
    model_config = ConfigDict(extra="forbid")
    rows: list[_DriverRow]


def _rows_to_response(rows: list[_DriverRow]) -> "BaselineDriversResponse":
    grouped: dict[str, dict[str, DriverProposal]] = {}
    for r in rows:
        grouped.setdefault(r.period_label, {})[r.driver] = DriverProposal(value=r.value, reason=r.reason)
    return BaselineDriversResponse(drivers={lbl: PeriodDrivers(**d) for lbl, d in grouped.items()})


# Per-driver glosses for the system prompt. Required keys: every name in
# DRIVER_KEYS. Keeping this in the same module so a missed addition is caught
# at import time, not silently shipped.
_DRIVER_GLOSSES: dict[str, str] = {
    "revenue_growth_pct":      "revenue growth for the year vs the prior year (0.10 = 10%); populate ONE of growth/absolute per period",
    "revenue_absolute":        "absolute annual revenue in same units as historicals; populate ONE of growth/absolute per period",
    "gross_margin_pct":        "gross profit / revenue (decimal)",
    "sga_pct_revenue":         "SG&A expense / revenue (decimal)",
    "rd_pct_revenue":          "R&D expense / revenue (decimal)",
    "other_opex_pct_revenue":  "other operating expense / revenue (decimal)",
    "da_pct_revenue":          "depreciation & amortization / revenue (decimal)",
    "effective_tax_rate":      "income tax / pretax income (decimal)",
    "interest_income_yield":   "annual interest income / cash & equivalents (decimal)",
    "interest_expense_rate":   "annual interest expense / total debt (decimal)",
    "capex_pct_revenue":       "capital expenditures / revenue (decimal)",
    "dso_days":                "days sales outstanding",
    "dio_days":                "days inventory outstanding",
    "dpo_days":                "days payable outstanding",
    "dividend_payout_ratio":   "dividends / net income (decimal)",
    "buyback_dollars":         "annual share buybacks in dollars (same units as revenue)",
    "share_count_change_pct":  "annual change in diluted share count (decimal)",
    "debt_repayment_dollars":  "annual scheduled debt repayment in dollars",
    "revolver_rate":           "revolver interest rate (decimal)",
}
assert set(_DRIVER_GLOSSES.keys()) == set(DRIVER_KEYS), (
    "DRIVER_KEYS and _DRIVER_GLOSSES drifted — every canonical driver needs a gloss"
)


def _format_driver_glosses() -> str:
    return "\n".join(f"- {k}: {g}" for k, g in _DRIVER_GLOSSES.items())


SYSTEM_PROMPT = f"""You are building a baseline financial forecast for a 3-statement model. \
Use the deep-dive findings, analyst consensus, and historical trends to produce structured driver \
assumptions for each forecast YEAR. Every value is annual — the model converts them for its \
quarterly periods (quarterly revenue grows year-over-year at the year's rate). The TTM-implied \
defaults show where history points; depart from them only for a reason you state. For each driver, give a numeric value, a one-line reason, and \
optionally a source_citation_id pointing back to a deep-dive finding ID, an analyst estimate label, \
or a historical-trend note. Anchor near consensus estimates unless the deep-dive findings explicitly \
contradict them — in which case explain why in `reason`. Use percentages as decimals (10% = 0.10). \
Days drivers (DSO/DIO/DPO) in days. Dollar drivers in same units as revenue.

Use EXACTLY these driver keys — no others, no aliases:
{_format_driver_glosses()}

Return one row per (year, driver) you have a view on: period_label exactly as given, the driver \
key, its value and a one-line reason. Omit a row when you have no view — the TTM default is used. \
Populate revenue_growth_pct for every year."""


async def generate_baseline_drivers(
    *,
    ticker: str,
    historicals_payload: str,
    deep_dive_summary: str,
    consensus_estimates: str,
    forecast_period_labels: list[str],
    ttm_defaults: str = "",
) -> BaselineDriversResponse:
    user = (
        f"Ticker: {ticker}\n\n"
        f"Forecast years (in order): {', '.join(forecast_period_labels)}\n\n"
        f"=== Historical quarters (calendarized) ===\n{historicals_payload}\n\n"
        f"=== TTM-implied annual driver defaults ===\n{ttm_defaults or '(none)'}\n\n"
        f"=== Analyst consensus estimates (annual) ===\n{consensus_estimates}\n\n"
        f"=== Research summary (thesis, category scores, rationales) ===\n{deep_dive_summary}\n\n"
        f"Produce the drivers for each forecast year now."
    )
    out = await llm.complete_structured(
        system=SYSTEM_PROMPT,
        user=user,
        output_model=_BaselineDriversLLMOutput,
        model=llm.DEEP_MODEL,
        max_tokens=16000,
    )
    return _rows_to_response(out.rows)
