"""Sonnet pass that generates a baseline ForecastDrivers payload from deep-dive context."""
from __future__ import annotations
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


# Per-driver glosses for the system prompt. Required keys: every name in
# DRIVER_KEYS. Keeping this in the same module so a missed addition is caught
# at import time, not silently shipped.
_DRIVER_GLOSSES: dict[str, str] = {
    "revenue_growth_pct":      "period-over-period revenue growth (0.10 = 10%); populate ONE of growth/absolute per period",
    "revenue_absolute":        "absolute revenue in same units as historicals; populate ONE of growth/absolute per period",
    "gross_margin_pct":        "gross profit / revenue (decimal)",
    "sga_pct_revenue":         "SG&A expense / revenue (decimal)",
    "rd_pct_revenue":          "R&D expense / revenue (decimal)",
    "other_opex_pct_revenue":  "other operating expense / revenue (decimal)",
    "da_pct_revenue":          "depreciation & amortization / revenue (decimal)",
    "effective_tax_rate":      "income tax / pretax income (decimal)",
    "interest_income_yield":   "interest income / cash & equivalents (decimal)",
    "interest_expense_rate":   "interest expense / total debt (decimal)",
    "capex_pct_revenue":       "capital expenditures / revenue (decimal)",
    "dso_days":                "days sales outstanding",
    "dio_days":                "days inventory outstanding",
    "dpo_days":                "days payable outstanding",
    "dividend_payout_ratio":   "dividends / net income (decimal)",
    "buyback_dollars":         "share buyback in dollars (same units as revenue)",
    "share_count_change_pct":  "period-over-period change in diluted share count (decimal)",
    "debt_repayment_dollars":  "scheduled debt repayment in dollars",
    "revolver_rate":           "revolver interest rate (decimal)",
}
assert set(_DRIVER_GLOSSES.keys()) == set(DRIVER_KEYS), (
    "DRIVER_KEYS and _DRIVER_GLOSSES drifted — every canonical driver needs a gloss"
)


def _format_driver_glosses() -> str:
    return "\n".join(f"- {k}: {g}" for k, g in _DRIVER_GLOSSES.items())


SYSTEM_PROMPT = f"""You are building a baseline financial forecast for a 3-statement model. \
Use the deep-dive findings, analyst consensus, and historical trends to produce structured driver \
assumptions for each forecast period. For each driver, give a numeric value, a one-line reason, and \
optionally a source_citation_id pointing back to a deep-dive finding ID, an analyst estimate label, \
or a historical-trend note. Anchor near consensus estimates unless the deep-dive findings explicitly \
contradict them — in which case explain why in `reason`. Use percentages as decimals (10% = 0.10). \
Days drivers (DSO/DIO/DPO) in days. Dollar drivers in same units as revenue.

Use EXACTLY these driver keys — no others, no aliases:
{_format_driver_glosses()}

Any key not listed above will be rejected. Leave a driver out (omit the key) if you have no view \
on it for a given period; do not invent a substitute name.

Output JSON ONLY — no preamble. Schema: {{"drivers": {{<period_label>: {{<driver_key>: \
{{"value": <num|null>, "reason": <str>, "source_citation_id": <str|null>}}}}}}}}"""


async def generate_baseline_drivers(
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
    raw = await llm.complete(
        system=SYSTEM_PROMPT,
        user=user,
        max_tokens=8192,
    )
    # Strip markdown code fences if the model wraps the JSON
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Drop opening fence (```json or ```) and closing fence (```)
        inner = lines[1:] if lines[0].startswith("```") else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        stripped = "\n".join(inner)
    return BaselineDriversResponse.model_validate_json(stripped)
