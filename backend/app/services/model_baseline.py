# backend/app/services/model_baseline.py
"""Build the AI-seeded baseline ModelState for a ticker.

Flow: fetch 8 reported quarters + profile + TTM ratios + consensus from FMP →
lay out calendarized periods (model_periods) → seed the full historical
statements (model_history) → ask the deep model for annual drivers → fill any
driver it leaves out with TTM-implied defaults → set WACC / tax / exit multiple
from the company's own data → recompute.

Rework 2026-09-27. The previous version read keys that don't exist on the
research-run state (so the AI got "[]", "(no estimates)", "(no findings)"),
looked beta up at the wrong path (every model had β = 1.00), laid out periods
from today's date rather than the reported quarters, compounded annual drivers
quarterly, and seeded only two non-line-item balance-sheet keys.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from backend.app.graph.model_baseline_node import BaselineDriversResponse, generate_baseline_drivers
from backend.app.models.model_state import (
    DRIVER_KEYS, LINE_ITEMS_BS, LINE_ITEMS_CF, LINE_ITEMS_PNL,
    ModelAssumptions, ModelCell, ModelState,
)
from backend.app.services.model_balancing import recompute
from backend.app.services.model_history import (
    annual_to_quarterly, historical_driver_defaults, rows_by_quarter, seed_history, summarize_history,
)
from backend.app.services.model_periods import build_periods, calendar_quarter_label, period_year

EQUITY_RISK_PREMIUM = 0.055
DEFAULT_RISK_FREE = 0.045
EXIT_MULTIPLE_BOUNDS = (6.0, 30.0)
DEFAULT_EXIT_MULTIPLE = 12.0


async def _load_seeding_context(ticker: str) -> dict[str, Any]:
    """Latest completed research_run state for ticker (thesis + category rationales)."""
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
    """Latest 10Y treasury from FRED; DEFAULT_RISK_FREE on any error."""
    try:
        from backend.app.clients.fred import FREDClient
        series, _citation = await FREDClient().get_series("DGS10")
        if not series or not series[-1].get("value"):
            return DEFAULT_RISK_FREE
        return float(series[-1]["value"]) / 100.0
    except Exception:
        return DEFAULT_RISK_FREE


async def _fetch_fmp_inputs(ticker: str) -> dict[str, Any]:
    from backend.app.clients.fmp import FMPClient
    fmp = FMPClient()
    try:
        (inc, _), (bal, _), (cf, _), (prof, _), (ratios, _), (est, _) = await asyncio.gather(
            fmp.get_income_statement(ticker, period="quarter", limit=8),
            fmp.get_balance_sheet(ticker, period="quarter", limit=8),
            fmp.get_cash_flow(ticker, period="quarter", limit=8),
            fmp.get_company_profile(ticker),
            fmp.get_ratios_ttm(ticker),
            fmp.get_analyst_estimates(ticker, period="annual", limit=10),
        )
    finally:
        await fmp.close()
    return {
        "income": inc if isinstance(inc, list) else [],
        "balance": bal if isinstance(bal, list) else [],
        "cashflow": cf if isinstance(cf, list) else [],
        "profile": (prof[0] if isinstance(prof, list) and prof else prof) or {},
        "ratios": ratios if isinstance(ratios, dict) else {},
        "estimates": est if isinstance(est, list) else [],
    }


def _empty_state(periods) -> ModelState:
    return ModelState(
        periods=periods,
        drivers={p.label: {k: ModelCell(value=None, source="driver") for k in DRIVER_KEYS}
                 for p in periods if not p.is_historical},
        income_statement={li: {} for li in LINE_ITEMS_PNL},
        balance_sheet={li: {} for li in LINE_ITEMS_BS},
        cash_flow={li: {} for li in LINE_ITEMS_CF},
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=0.10, source="driver"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=DEFAULT_EXIT_MULTIPLE, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
        ),
    )


def assemble_historical_state(fmp_inputs: dict[str, Any], rf: float) -> tuple[ModelState, dict[str, tuple[float, str]]]:
    """Periods, seeded history and company-specific assumptions. Pure.

    Returns the state (drivers still empty) and the TTM driver defaults.
    """
    quarters = rows_by_quarter(fmp_inputs["income"], fmp_inputs["balance"], fmp_inputs["cashflow"])
    dated = [r for r in fmp_inputs["income"] if isinstance(r, dict) and r.get("date")]
    if not dated:
        raise ValueError("no quarterly income statements from FMP — cannot build a model")
    latest = max(r["date"] for r in dated)
    state = _empty_state(build_periods(calendar_quarter_label(latest)))
    seed_history(state, quarters)
    defaults = historical_driver_defaults(state)

    anchor = [p for p in state.periods if p.is_historical][-1].label
    bs = lambda line: (state.balance_sheet.get(line, {}).get(anchor) or ModelCell()).value or 0.0  # noqa: E731
    debt = bs("short_term_debt") + bs("long_term_debt")
    profile = fmp_inputs["profile"]
    mcap = float(profile.get("marketCap") or 0.0)
    beta = float(profile.get("beta") or 1.0)
    tax = defaults.get("effective_tax_rate", (0.21, ""))[0]
    ke = rf + beta * EQUITY_RISK_PREMIUM
    kd = max(defaults.get("interest_expense_rate", (0.0, ""))[0], rf)
    wacc = (mcap * ke + debt * kd * (1.0 - tax)) / (mcap + debt) if (mcap + debt) > 0 else ke
    state.assumptions.discount_rate = ModelCell(
        value=wacc, source="driver",
        formula=(f"WACC = E/V·Ke + D/V·Kd·(1−t); Ke = rf {rf:.4f} + β {beta:.2f} × ERP {EQUITY_RISK_PREMIUM}"
                 f" = {ke:.4f}; Kd = {kd:.4f}; E = ${mcap / 1e9:,.1f}B, D = ${debt / 1e9:,.1f}B, t = {tax:.2f}"),
    )
    state.assumptions.tax_rate = ModelCell(value=tax, source="driver", formula="TTM effective tax rate")
    current = fmp_inputs["ratios"].get("enterpriseValueMultipleTTM")
    if isinstance(current, (int, float)) and current > 0:
        lo, hi = EXIT_MULTIPLE_BOUNDS
        multiple = max(lo, min(hi, float(current)))
        note = f"current EV/EBITDA {current:.1f}x, bounded to [{lo:g}, {hi:g}]"
    else:
        multiple, note = DEFAULT_EXIT_MULTIPLE, "default (no TTM EV/EBITDA)"
    state.assumptions.terminal_multiple = ModelCell(value=multiple, source="driver", formula=note)
    return state, defaults


LONG_RUN_GROWTH = 0.04
TTM_GROWTH_BOUNDS = (-0.20, 0.50)


def _fiscal_to_calendar_year(fy_end: str) -> int:
    """Calendar year a fiscal year mostly covers (FY ending Jan 2027 → 2026)."""
    d = date.fromisoformat(fy_end[:10])
    return (d - timedelta(days=182)).year


def revenue_growth_path(
    years: list[str], estimates: list[dict], ttm_growth: float | None,
) -> dict[str, tuple[float, str]]:
    """Default annual revenue growth per forecast year, used where the AI
    gives none: consensus-implied growth where analysts cover the year, then a
    linear fade from the last known rate to LONG_RUN_GROWTH by the final year.
    (Holding trailing growth flat compounded NVDA's 83% into $15T of revenue.)
    """
    by_year: dict[int, float] = {}
    for e in estimates or []:
        if isinstance(e, dict) and e.get("date") and isinstance(e.get("revenueAvg"), (int, float)):
            by_year[_fiscal_to_calendar_year(str(e["date"]))] = float(e["revenueAvg"])
    out: dict[str, tuple[float, str]] = {}
    lo, hi = TTM_GROWTH_BOUNDS
    last = (max(lo, min(hi, ttm_growth)), f"TTM growth bounded to [{lo:.0%}, {hi:.0%}]") if ttm_growth is not None \
        else (LONG_RUN_GROWTH, "long-run default")
    unknown: list[str] = []
    for label in years:
        y = int(label.rstrip("Y"))
        if by_year.get(y) and by_year.get(y - 1):
            last = (by_year[y] / by_year[y - 1] - 1.0, "consensus-implied")
            out[label] = last
        else:
            unknown.append(label)
    # Fade the years without consensus from the last known rate to long-run.
    tail = [lbl for lbl in years if lbl in unknown]
    for i, label in enumerate(tail, start=1):
        start, note = last
        g = start + (LONG_RUN_GROWTH - start) * i / len(tail)
        out[label] = (g, f"fade from {start:.1%} ({note}) to {LONG_RUN_GROWTH:.0%}")
    return out


MAINTENANCE_CAPEX_TO_DA = 1.1


def capex_path(state: ModelState, defaults: dict[str, tuple[float, str]]) -> dict[str, tuple[float, str]]:
    """Default capex / revenue per year: the TTM level through the quarter
    years (a build-out in progress is real), then a linear fade across the
    annual years to maintenance (MAINTENANCE_CAPEX_TO_DA × D&A / revenue).
    Holding a build-out rate flat for five years valued CoreWeave (capex 271%
    of revenue) at −$902/share."""
    if "capex_pct_revenue" not in defaults:
        return {}
    start = defaults["capex_pct_revenue"][0]
    target = MAINTENANCE_CAPEX_TO_DA * defaults.get("da_pct_revenue", (start, ""))[0]
    quarter_years = {period_year(p) for p in state.periods if not p.is_historical and p.kind == "Q"}
    annual = [p.label for p in state.periods if p.kind == "Y" and not p.is_historical]
    out = {f"{y}Y": (start, "TTM capex / revenue (build-out years)") for y in sorted(quarter_years)}
    for i, label in enumerate(annual, start=1):
        g = start + (target - start) * i / len(annual)
        out[label] = (g, f"fade from TTM {start:.1%} to maintenance {target:.1%} (1.1 × D&A)")
    return out


def default_paths(state: ModelState, estimates: list[dict], defaults: dict[str, tuple[float, str]]):
    """Per-year default paths for drivers that shouldn't be held flat."""
    return {
        "revenue_growth_pct": revenue_growth_path(
            driver_years(state), estimates, defaults.get("revenue_growth_pct", (None, ""))[0]),
        "capex_pct_revenue": capex_path(state, defaults),
    }


def driver_years(state: ModelState) -> list[str]:
    """Annual driver sets to request: every calendar year a forecast period falls in."""
    return [f"{y}Y" for y in sorted({period_year(p) for p in state.periods if not p.is_historical})]


def apply_drivers(
    state: ModelState,
    ai: BaselineDriversResponse | None,
    defaults: dict[str, tuple[float, str]],
    paths: dict[str, dict[str, tuple[float, str]]] | None = None,
) -> None:
    """Annual AI drivers onto every forecast period; where the AI gives none,
    a per-year default path (revenue growth, capex) or the TTM default.

    Quarters take their calendar year's annual drivers, converted: rates of
    change are de-compounded and dollar amounts split across four quarters,
    so an annual figure is never applied four times a year.
    """
    now = datetime.now(timezone.utc).isoformat()
    ai_drivers = ai.drivers if ai else {}
    for p in (p for p in state.periods if not p.is_historical):
        year_set = ai_drivers.get(f"{period_year(p)}Y")
        for key in DRIVER_KEYS:
            proposal = getattr(year_set, key, None) if year_set is not None else None
            if proposal is not None and proposal.value is not None:
                value, source, note, by = proposal.value, "ai_baseline", proposal.reason or None, "ai_baseline"
            elif paths and f"{period_year(p)}Y" in paths.get(key, {}):
                value, why = paths[key][f"{period_year(p)}Y"]
                source, by, note = "driver", "system", f"default: {why}"
            elif key in defaults:
                value, source, by = defaults[key][0], "driver", "system"
                note = f"TTM default: {defaults[key][1]}"
            else:
                continue
            if p.kind == "Q":
                if key == "revenue_absolute":
                    continue  # quarters grow year-over-year from the same quarter
                value = annual_to_quarterly(key, value)
            state.drivers.setdefault(p.label, {})[key] = ModelCell(
                value=value, source=source, formula=note,
                citation_id=getattr(proposal, "source_citation_id", None) if source == "ai_baseline" else None,
                last_edited_at=now, last_edited_by=by,
            )


def research_summary(ctx: dict[str, Any]) -> str:
    """Thesis + per-category score and rationale from the research run state."""
    outputs = ctx.get("phase_outputs") or {}
    lines: list[str] = []
    thesis = (outputs.get("thesis") or {}).get("structured") or {}
    if thesis:
        lines.append(f"Stance: {thesis.get('stance') or 'n/a'}; conviction {thesis.get('conviction_score')}")
        if thesis.get("price_targets"):
            lines.append(f"Price targets ({thesis.get('time_horizon')}): {thesis['price_targets']}")
        lines.append(f"Core thesis: {str(thesis.get('core_thesis', ''))[:800]}")
    for name, out in outputs.items():
        if isinstance(out, dict) and out.get("__type__") == "CategoryResult":
            rationale = (out.get("structured") or {}).get("score_rationale") or ""
            lines.append(f"- {name}: {out.get('score')}/100 — {rationale[:300]}")
    return "\n".join(lines) or "(no research summary)"


def consensus_summary(estimates: list[dict], from_year: int) -> str:
    rows = sorted((e for e in estimates if isinstance(e, dict) and str(e.get("date", ""))[:4].isdigit()
                   and int(str(e["date"])[:4]) >= from_year), key=lambda e: e["date"])
    if not rows:
        return "(no consensus estimates)"
    return "\n".join(
        f"FY ending {e['date']}: revenue {e.get('revenueAvg')}, EBITDA {e.get('ebitdaAvg')}, EPS {e.get('epsAvg')} "
        f"({e.get('numAnalystsRevenue')} analysts)" for e in rows
    )


async def build_baseline_state(*, ticker: str) -> ModelState:
    ctx, fmp_inputs, rf = await asyncio.gather(
        _load_seeding_context(ticker), _fetch_fmp_inputs(ticker), _get_risk_free_rate(),
    )
    state, defaults = assemble_historical_state(fmp_inputs, rf)
    years = driver_years(state)
    ai = await generate_baseline_drivers(
        ticker=ticker,
        historicals_payload=json.dumps(summarize_history(state), indent=1),
        deep_dive_summary=research_summary(ctx),
        consensus_estimates=consensus_summary(fmp_inputs["estimates"], int(years[0].rstrip("Y"))),
        forecast_period_labels=years,
        ttm_defaults="\n".join(f"- {k}: {v:.4g} ({note})" for k, (v, note) in defaults.items()),
    )
    apply_drivers(state, ai, defaults, default_paths(state, fmp_inputs["estimates"], defaults))
    return recompute(state)


async def initialize_or_get_model(ticker: str, *, force: bool = False):
    """Returns the latest TickerModel row for ticker, building one if missing or force=True.
    The returned object is a TickerModel ORM row (state already a dict via Pydantic round-trip)."""
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
