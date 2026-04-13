"""Phase node implementations for the LangGraph pipeline.

Each node receives ResearchState, does work, mutates state, and returns it.
Every node is a pure async function — no side effects except state mutation.

Phase assignments:
  quick_screen      → Haiku
  deep_dive (×9)    → Sonnet, parallel subgraph
  thesis            → Sonnet
  risk_stress_test  → Sonnet
  position_monitor  → Haiku
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import traceback
from typing import Any

from backend.app.clients.fmp import FMPClient
from backend.app.clients.fred import FREDClient
from backend.app.graph.llm import complete, SONNET, HAIKU
from backend.app.models.phase_schemas import QuickScreenOutput, ThesisOutput, RiskStressTestOutput, PositionMonitorOutput, DeepDiveCategoryOutput
from backend.app.graph.output_parser import parse_structured_output
from backend.app.graph.prompts import (
    QUICK_SCREEN_SYSTEM, QUICK_SCREEN_USER,
    DEEP_DIVE_SYSTEM, DEEP_DIVE_USER, DEEP_DIVE_CATEGORIES,
    THESIS_SYSTEM, THESIS_USER,
    RISK_SYSTEM, RISK_USER,
    POSITION_SYSTEM, POSITION_USER,
    TRANSCRIPT_PASS1_SYSTEM, TRANSCRIPT_PASS2_SYSTEM,
    TRANSCRIPT_PASS3_SYSTEM, TRANSCRIPT_PASS4_SYSTEM,
    TRANSCRIPT_PASS5_SYSTEM, TRANSCRIPT_PASS6_SYSTEM,
)
from backend.app.graph.state import (
    ResearchState, CategoryResult, CategoryError, StateCitation
)

logger = logging.getLogger(__name__)

CATEGORY_TIMEOUT = 90  # seconds per deep-dive category

TRANSCRIPT_ROUTING: dict[str, list[str]] = {
    "Management & Governance": ["pass1_claims", "pass2_tiers", "pass3_qa_tensions", "pass4_validation", "pass5_consistency"],
    "Business Quality": ["pass3_qa_tensions", "pass5_consistency"],
    "Growth & Earnings": ["pass1_claims", "pass4_validation", "pass6_bom"],
    "Sentiment & Narrative": ["pass3_qa_tensions", "pass5_consistency"],
    "Risk Assessment": ["pass1_claims", "pass4_validation"],
    "Future Durability": ["pass1_claims", "pass5_consistency"],
}

_ALL_MACRO = ["fed_funds_rate", "treasury_10y", "treasury_2y", "yield_curve_spread", "cpi", "unemployment", "gdp_growth", "m2_money_supply", "nonfarm_payrolls"]

MACRO_ROUTING: dict[str, list[str]] = {
    "Macro & Regime": _ALL_MACRO,
    "Risk Assessment": _ALL_MACRO,
    "Future Durability": ["gdp_growth", "cpi", "m2_money_supply", "fed_funds_rate", "treasury_10y"],
    "Financial Health": ["fed_funds_rate", "treasury_10y", "yield_curve_spread"],
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_score(text: str) -> int:
    """Parse 'SCORE: XX/100' or 'CONVICTION: XX/100' from LLM output."""
    for pattern in [r"(?:SCORE|CONVICTION):\s*(\d+)/100", r"(\d+)/100"]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return min(100, max(0, int(m.group(1))))
    return 50  # default if not found


def _extract_key_findings(text: str) -> list[str]:
    """Pull bullet points from the 'Key findings' section."""
    lines = text.split("\n")
    findings = []
    in_findings = False
    for line in lines:
        if "key finding" in line.lower():
            in_findings = True
            continue
        if in_findings:
            stripped = line.strip().lstrip("•-*123456789. ")
            if stripped and len(stripped) > 10:
                findings.append(stripped)
            if len(findings) >= 5:
                break
            if line.strip() == "" and findings:
                break
    return findings


def _fmt_fundamentals(
    ticker: str,
    income: list,
    balance: list,
    cashflow: list,
    profile: dict,
    *,
    dcf: dict | None = None,
    estimates: list | None = None,
    key_metrics: dict | None = None,
    fin_growth: list | None = None,
) -> str:
    """Format raw FMP data into a comprehensive block for LLM prompts.

    Includes multi-quarter trends, valuation ratios, return metrics,
    debt structure, forward estimates, and earnings surprises.
    """
    def _fv(val: Any, divisor: float = 1e9, suffix: str = "B") -> str:
        """Format a financial value."""
        if val is None or val == 0:
            return "N/A"
        return f"${val / divisor:.2f}{suffix}"

    def _pct(a: float | None, b: float | None) -> str:
        if a is None or b is None or b == 0:
            return "N/A"
        return f"{(a - b) / abs(b) * 100:+.1f}%"

    parts: list[str] = []

    # ── Company profile ──────────────────────────────────────────────────
    if profile and isinstance(profile, dict):
        parts.append(f"Company: {profile.get('companyName', ticker)}")
        parts.append(f"Sector: {profile.get('sector')} | Industry: {profile.get('industry')}")
        parts.append(f"Market Cap: ${profile.get('marketCap', 0)/1e9:.1f}B")
        parts.append(f"Beta: {profile.get('beta', 'N/A')}")
        parts.append(f"Description: {str(profile.get('description', ''))[:300]}")

    # ── Valuation ratios (from key_metrics_ttm) ──────────────────────────
    if key_metrics and isinstance(key_metrics, dict):
        parts.append("\nValuation Ratios (TTM):")
        for label, field in [
            ("P/E", "peRatioTTM"),
            ("EV/EBITDA", "enterpriseValueOverEBITDATTM"),
            ("P/B", "priceToBookRatioTTM"),
            ("P/FCF", "priceToFreeCashFlowsRatioTTM"),
            ("P/S", "priceToSalesRatioTTM"),
            ("PEG", "pegRatioTTM"),
            ("Dividend Yield", "dividendYieldTTM"),
        ]:
            v = key_metrics.get(field)
            if v is not None:
                if "Yield" in label:
                    parts.append(f"  {label}: {float(v)*100:.2f}%")
                else:
                    parts.append(f"  {label}: {float(v):.2f}")

        parts.append("\nReturn Metrics (TTM):")
        for label, field in [
            ("ROE", "roeTTM"),
            ("ROIC", "roicTTM"),
            ("ROA", "returnOnTangibleAssetsTTM"),
        ]:
            v = key_metrics.get(field)
            if v is not None:
                parts.append(f"  {label}: {float(v)*100:.1f}%")

        ic = key_metrics.get("interestCoverageTTM")
        if ic is not None:
            parts.append(f"  Interest Coverage: {float(ic):.1f}x")

    # ── Quarterly income trend (up to 8Q) ────────────────────────────────
    if income:
        parts.append(f"\nQuarterly Income Statement ({len(income)} quarters, newest first):")
        for i, stmt in enumerate(income[:8]):
            rev = stmt.get("revenue", 0) or 0
            gp = stmt.get("grossProfit", 0) or 0
            oi = stmt.get("operatingIncome", 0) or 0
            ni = stmt.get("netIncome", 0) or 0
            eps = stmt.get("eps", "N/A")
            gm = f"{gp/rev*100:.1f}%" if rev else "N/A"
            om = f"{oi/rev*100:.1f}%" if rev else "N/A"
            nm = f"{ni/rev*100:.1f}%" if rev else "N/A"
            # YoY growth (compare to same quarter one year ago = i+4)
            yoy = ""
            if i + 4 < len(income):
                prev_rev = income[i + 4].get("revenue", 0) or 0
                if prev_rev:
                    yoy = f" (YoY: {(rev - prev_rev)/abs(prev_rev)*100:+.1f}%)"
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            parts.append(f"  {period}: Rev {_fv(rev)} {yoy} | GM {gm} | OM {om} | NM {nm} | EPS {eps}")

    # ── Balance sheet with debt structure ────────────────────────────────
    if balance:
        parts.append(f"\nBalance Sheet ({len(balance)} quarters, newest first):")
        for stmt in balance[:4]:
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            cash = stmt.get("cashAndCashEquivalents", 0) or 0
            st_debt = stmt.get("shortTermDebt", 0) or 0
            lt_debt = stmt.get("longTermDebt", 0) or 0
            total_debt = stmt.get("totalDebt", 0) or 0
            equity = stmt.get("totalEquity", 0) or stmt.get("totalStockholdersEquity", 0) or 0
            ca = stmt.get("totalCurrentAssets", 0) or 0
            cl = stmt.get("totalCurrentLiabilities", 0) or 0
            cr = f"{ca/cl:.2f}" if cl else "N/A"
            de = f"{total_debt/equity:.2f}" if equity else "N/A"
            parts.append(f"  {period}: Cash {_fv(cash)} | ST Debt {_fv(st_debt)} | LT Debt {_fv(lt_debt)} | D/E {de} | Current Ratio {cr}")

        # Interest expense from latest income statement
        if income:
            ie = income[0].get("interestExpense", 0) or 0
            if ie:
                parts.append(f"  Latest Interest Expense: {_fv(abs(ie))}")

    # ── Cash flow trend ──────────────────────────────────────────────────
    if cashflow:
        parts.append(f"\nCash Flow ({len(cashflow)} quarters, newest first):")
        for stmt in cashflow[:4]:
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            ocf = stmt.get("operatingCashFlow", 0) or 0
            fcf = stmt.get("freeCashFlow", 0) or 0
            capex = stmt.get("capitalExpenditure", 0) or 0
            sbc = stmt.get("stockBasedCompensation", 0) or 0
            parts.append(f"  {period}: OCF {_fv(ocf)} | FCF {_fv(fcf)} | CapEx {_fv(capex)} | SBC {_fv(sbc)}")

    # ── DCF valuation ────────────────────────────────────────────────────
    if dcf and isinstance(dcf, dict):
        dcf_val = dcf.get("dcf")
        stock_price = dcf.get("Stock Price") or dcf.get("stockPrice")
        if dcf_val:
            gap = ""
            if stock_price and float(stock_price) > 0:
                gap_pct = (float(dcf_val) - float(stock_price)) / float(stock_price) * 100
                gap = f" ({gap_pct:+.1f}% vs current)"
            parts.append(f"\nDCF Intrinsic Value: ${dcf_val}{gap}")

    # ── Forward estimates + earnings surprise ────────────────────────────
    if estimates:
        parts.append(f"\nAnalyst Estimates ({len(estimates)} quarters):")
        for est in estimates[:4]:
            period = est.get("date", "")[:7]
            rev_est = est.get("estimatedRevenueAvg") or est.get("revenueAvg")
            eps_est = est.get("estimatedEpsAvg") or est.get("epsAvg")
            rev_act = est.get("actualRevenue")
            eps_act = est.get("actualEps")
            line = f"  {period}:"
            if rev_est is not None:
                line += f" Rev Est {_fv(rev_est)}"
                if rev_act is not None:
                    surprise = (float(rev_act) - float(rev_est)) / abs(float(rev_est)) * 100 if float(rev_est) else 0
                    line += f" → Actual {_fv(rev_act)} ({surprise:+.1f}% surprise)"
            if eps_est is not None:
                line += f" | EPS Est ${float(eps_est):.2f}"
                if eps_act is not None:
                    line += f" → Actual ${float(eps_act):.2f} ({float(eps_act) - float(eps_est):+.2f})"
            parts.append(line)

    # ── Historical growth rates ──────────────────────────────────────────
    if fin_growth:
        parts.append(f"\nGrowth Rates ({len(fin_growth)} quarters):")
        for g in fin_growth[:4]:
            period = g.get("date", "")[:7]
            rg = g.get("revenueGrowth")
            eg = g.get("epsgrowth") or g.get("epsGrowth")
            fcfg = g.get("freeCashFlowGrowth")
            line = f"  {period}:"
            if rg is not None:
                line += f" Rev Growth {float(rg)*100:+.1f}%"
            if eg is not None:
                line += f" | EPS Growth {float(eg)*100:+.1f}%"
            if fcfg is not None:
                line += f" | FCF Growth {float(fcfg)*100:+.1f}%"
            parts.append(line)

    return "\n".join(parts)


# ── Phase 1+2: quick_screen ───────────────────────────────────────────────────

async def node_quick_screen(state: ResearchState, fmp: FMPClient) -> ResearchState:
    """Phases 1+2: pull FMP data, score 5 dimensions, produce GO/WATCHLIST/PASS."""
    logger.info("[%s] quick_screen starting", state.ticker)
    state.phase = "quick_screen"

    try:
        # Fetch fundamentals
        (income, inc_cit), (balance, bal_cit), (cashflow, cf_cit), (profile, prof_cit) = (
            await asyncio.gather(
                fmp.get_income_statement(state.ticker, limit=4),
                fmp.get_balance_sheet(state.ticker, limit=2),
                fmp.get_cash_flow(state.ticker, limit=2),
                fmp.get_company_profile(state.ticker),
            )
        )

        for cit in [inc_cit, bal_cit, cf_cit, prof_cit]:
            state.add_citation(StateCitation.from_citation(cit))

        fundamentals_text = _fmt_fundamentals(
            state.ticker,
            income if isinstance(income, list) else [],
            balance if isinstance(balance, list) else [],
            cashflow if isinstance(cashflow, list) else [],
            profile[0] if isinstance(profile, list) and profile else profile or {},
        )

        response = await complete(
            system=QUICK_SCREEN_SYSTEM,
            user=QUICK_SCREEN_USER.format(
                ticker=state.ticker,
                theme=state.theme_id,
                fundamental_data=fundamentals_text,
            ),
            model=HAIKU,
            max_tokens=2500,
            assistant_prefill="{",
        )

        parsed, parse_err = parse_structured_output(response, QuickScreenOutput)

        if parsed is not None:
            score = parsed.overall_score
            recommendation = parsed.recommendation
            structured = parsed.model_dump()
        else:
            # Fallback — preserves original behavior so runs still complete.
            logger.warning(
                "[%s] quick_screen JSON parse failed: %s", state.ticker, parse_err
            )
            score = _extract_score(response)
            if score >= 60:
                recommendation = "GO"
            elif score >= 35:
                recommendation = "WATCHLIST"
            else:
                recommendation = "PASS"
            structured = None

        state.phase_outputs["quick_screen"] = {
            "__type__": "PhaseOutput",
            "content": response,
            "structured": structured,
            "score": score,
            "recommendation": recommendation,
            "parse_error": parse_err,
        }
        state.scores["quick_screen"] = score

        logger.info(
            "[%s] quick_screen complete: %d/100 → %s (structured=%s)",
            state.ticker, score, recommendation, structured is not None,
        )

    except Exception as e:
        logger.error("[%s] quick_screen failed: %s", state.ticker, e)
        state.phase_outputs["quick_screen"] = {
            "__type__": "PhaseError",
            "reason": str(e),
            "traceback": traceback.format_exc(),
        }

    state.status = "in_progress"
    return state


# ── Phase 3: deep_dive (parallel subgraph) ────────────────────────────────────

async def _run_one_category(
    category: str,
    ticker: str,
    theme_id: str,
    data: str,
    loop_context: str,
    transcript_context: str = "",
    macro_context: str = "",
) -> CategoryResult | CategoryError:
    """Run a single deep-dive category with a timeout."""
    try:
        response = await asyncio.wait_for(
            complete(
                system=DEEP_DIVE_SYSTEM.format(category=category),
                user=DEEP_DIVE_USER.format(
                    ticker=ticker,
                    theme=theme_id,
                    category=category,
                    data=data,
                    transcript_data=transcript_context,
                    macro_data=macro_context,
                    loop_context=loop_context,
                ),
                model=SONNET,
                max_tokens=3000,
            ),
            timeout=CATEGORY_TIMEOUT,
        )

        parsed, parse_err = parse_structured_output(response, DeepDiveCategoryOutput)

        if parsed is not None:
            score = parsed.score
            findings = [f.finding for f in parsed.key_findings]
            structured = parsed.model_dump()
        else:
            # Fallback — regex extraction preserves original behavior.
            logger.warning(
                "[%s] Category '%s' JSON parse failed: %s", ticker, category, parse_err
            )
            score = _extract_score(response)
            findings = _extract_key_findings(response)
            structured = None

        return CategoryResult(
            category=category, content=response, score=score,
            key_findings=findings, structured=structured,
        )

    except asyncio.TimeoutError:
        logger.warning("[%s] Category '%s' timed out after %ds", ticker, category, CATEGORY_TIMEOUT)
        return CategoryError(category=category, reason=f"Timeout after {CATEGORY_TIMEOUT}s")
    except Exception as e:
        logger.error("[%s] Category '%s' failed: %s", ticker, category, e)
        return CategoryError(category=category, reason=str(e), traceback=traceback.format_exc())


def _build_curated_financials(
    ticker: str,
    income: list[dict],
    balance: list[dict],
    cashflow: list[dict],
    profile: dict,
    dcf: dict | None,
    estimates: list[dict],
    key_metrics: dict | None = None,
) -> "CuratedFinancials":
    """Extract a curated subset of FMP data for frontend dashboard charts."""
    from backend.app.graph.state import CuratedFinancials, QuarterlyMetric, EstimateMetric

    def safe_div(a: float, b: float) -> float | None:
        return a / b if b else None

    def pct(a: float, b: float) -> float | None:
        return ((a - b) / abs(b)) * 100 if b else None

    def make_quarterly(statements: list[dict], field_name: str) -> list[QuarterlyMetric]:
        """Build QuarterlyMetric list from a series of FMP statements."""
        metrics = []
        for i, stmt in enumerate(statements):
            val = stmt.get(field_name, 0) or 0
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            prev_val = statements[i + 1].get(field_name, 0) if i + 1 < len(statements) else None
            yoy = pct(val, prev_val) if prev_val else None
            metrics.append(QuarterlyMetric(period=period, value=float(val), yoy_growth=yoy))
        return metrics

    def make_margin(statements: list[dict], numerator: str, denominator: str = "revenue") -> list[QuarterlyMetric]:
        """Build margin % metrics."""
        metrics = []
        for stmt in statements:
            rev = stmt.get(denominator, 0) or 0
            num = stmt.get(numerator, 0) or 0
            margin = (num / rev * 100) if rev else 0
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            metrics.append(QuarterlyMetric(period=period, value=round(margin, 2), yoy_growth=None))
        return metrics

    # Profile data
    prof = profile or {}
    company_name = prof.get("companyName", ticker)
    sector = prof.get("sector", "")
    industry = prof.get("industry", "")
    market_cap = float(prof.get("mktCap", 0) or prof.get("marketCap", 0) or 0)
    current_price = float(prof.get("price", 0) or 0)
    beta = prof.get("beta")
    beta = float(beta) if beta is not None else None
    vol_avg = prof.get("volAvg")
    vol_avg = float(vol_avg) if vol_avg is not None else None
    range_str = prof.get("range", "")
    fifty_two_low, fifty_two_high = None, None
    if range_str and "-" in range_str:
        parts = range_str.split("-")
        try:
            fifty_two_low = float(parts[0].strip())
            fifty_two_high = float(parts[1].strip())
        except (ValueError, IndexError):
            pass

    # DCF
    dcf_value = None
    dcf_gap = None
    if dcf and isinstance(dcf, dict):
        dcf_value = dcf.get("dcf")
        dcf_value = float(dcf_value) if dcf_value is not None else None
        stock_price = dcf.get("Stock Price") or dcf.get("stockPrice") or current_price
        if dcf_value and stock_price:
            dcf_gap = round((dcf_value - float(stock_price)) / float(stock_price) * 100, 2)

    # Balance sheet ratios
    d_e = 0.0
    if balance:
        b0 = balance[0]
        debt = float(b0.get("totalDebt", 0) or 0)
        equity = float(b0.get("totalEquity", 0) or b0.get("totalStockholdersEquity", 0) or 0)
        d_e = round(debt / equity, 2) if equity else 0.0

    def make_current_ratio(bs: list[dict]) -> list[QuarterlyMetric]:
        metrics = []
        for stmt in bs:
            ca = float(stmt.get("totalCurrentAssets", 0) or 0)
            cl = float(stmt.get("totalCurrentLiabilities", 0) or 0)
            cr = round(ca / cl, 2) if cl else 0
            period = stmt.get("period", "") or stmt.get("date", "")[:7]
            metrics.append(QuarterlyMetric(period=period, value=cr, yoy_growth=None))
        return metrics

    # Estimates
    fwd_rev = []
    fwd_eps = []
    for est in (estimates or []):
        period = est.get("date", "")[:7]
        rev_est = est.get("estimatedRevenueAvg") or est.get("revenueAvg")
        eps_est = est.get("estimatedEpsAvg") or est.get("epsAvg")
        rev_act = est.get("actualRevenue")
        eps_act = est.get("actualEps")
        if rev_est is not None:
            fwd_rev.append(EstimateMetric(period=period, estimate=float(rev_est), actual=float(rev_act) if rev_act is not None else None))
        if eps_est is not None:
            fwd_eps.append(EstimateMetric(period=period, estimate=float(eps_est), actual=float(eps_act) if eps_act is not None else None))

    # Key metrics (valuation + returns)
    def _safe_float(d: dict | None, key: str) -> float | None:
        if not d:
            return None
        v = d.get(key)
        return float(v) if v is not None else None

    km = key_metrics or {}

    return CuratedFinancials(
        ticker=ticker,
        company_name=company_name,
        sector=sector,
        industry=industry,
        market_cap=market_cap,
        current_price=current_price,
        quarterly_revenue=make_quarterly(income, "revenue"),
        quarterly_eps=make_quarterly(income, "eps"),
        quarterly_gross_margin=make_margin(income, "grossProfit"),
        quarterly_operating_margin=make_margin(income, "operatingIncome"),
        quarterly_net_margin=make_margin(income, "netIncome"),
        quarterly_cash=make_quarterly(balance, "cashAndCashEquivalents"),
        quarterly_total_debt=make_quarterly(balance, "totalDebt"),
        quarterly_shareholders_equity=make_quarterly(balance, "totalEquity"),
        quarterly_current_ratio=make_current_ratio(balance),
        debt_to_equity=d_e,
        quarterly_operating_cf=make_quarterly(cashflow, "operatingCashFlow"),
        quarterly_free_cf=make_quarterly(cashflow, "freeCashFlow"),
        quarterly_capex=make_quarterly(cashflow, "capitalExpenditure"),
        dcf_intrinsic_value=dcf_value,
        dcf_gap_percent=dcf_gap,
        forward_revenue_estimates=fwd_rev,
        forward_eps_estimates=fwd_eps,
        pe_ratio=_safe_float(km, "peRatioTTM"),
        ev_to_ebitda=_safe_float(km, "enterpriseValueOverEBITDATTM"),
        price_to_book=_safe_float(km, "priceToBookRatioTTM"),
        price_to_fcf=_safe_float(km, "priceToFreeCashFlowsRatioTTM"),
        price_to_sales=_safe_float(km, "priceToSalesRatioTTM"),
        peg_ratio=_safe_float(km, "pegRatioTTM"),
        roe=_safe_float(km, "roeTTM"),
        roic=_safe_float(km, "roicTTM"),
        roa=_safe_float(km, "returnOnTangibleAssetsTTM"),
        interest_coverage=_safe_float(km, "interestCoverageTTM"),
        dividend_yield=_safe_float(km, "dividendYieldTTM"),
        beta=beta,
        fifty_two_week_high=fifty_two_high,
        fifty_two_week_low=fifty_two_low,
        volume_avg=vol_avg,
    )


def _build_technical_data(prices: list[dict]) -> list[dict]:
    """Compute SMA 9/20/50/100/200 and RSI(14) from raw OHLCV data.

    Input: list of {date, open, high, low, close, volume} dicts, newest first (FMP order).
    Output: list of dicts oldest first (chronological), each with OHLCV + sma_* + rsi fields.
    """
    if not prices:
        return []

    # Reverse to oldest-first for computation
    rows = list(reversed(prices))
    closes = [float(r.get("close", 0) or 0) for r in rows]
    n = len(closes)

    # ── SMA computation ──────────────────────────────────────────────────
    sma_periods = [9, 20, 50, 100, 200]
    sma_values: dict[int, list[float | None]] = {}
    for period in sma_periods:
        vals: list[float | None] = []
        for i in range(n):
            if i < period - 1:
                vals.append(None)
            else:
                vals.append(round(sum(closes[i - period + 1 : i + 1]) / period, 4))
        sma_values[period] = vals

    # ── RSI(14) computation (Wilder's smoothing) ─────────────────────────
    rsi_period = 14
    rsi_values: list[float | None] = [None] * n
    if n > rsi_period:
        deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
        # Seed: simple average of first 14 deltas
        gains = [max(d, 0) for d in deltas[:rsi_period]]
        losses = [abs(min(d, 0)) for d in deltas[:rsi_period]]
        avg_gain = sum(gains) / rsi_period
        avg_loss = sum(losses) / rsi_period

        if avg_loss == 0:
            rsi_values[rsi_period] = 100.0
        else:
            rsi_values[rsi_period] = round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

        # Subsequent: exponential smoothing
        for i in range(rsi_period, len(deltas)):
            gain = max(deltas[i], 0)
            loss = abs(min(deltas[i], 0))
            avg_gain = (avg_gain * (rsi_period - 1) + gain) / rsi_period
            avg_loss = (avg_loss * (rsi_period - 1) + loss) / rsi_period
            if avg_loss == 0:
                rsi_values[i + 1] = 100.0
            else:
                rsi_values[i + 1] = round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

    # ── Assemble output ──────────────────────────────────────────────────
    result = []
    for i, row in enumerate(rows):
        result.append({
            "date": row.get("date", ""),
            "open": float(row.get("open", 0) or 0),
            "high": float(row.get("high", 0) or 0),
            "low": float(row.get("low", 0) or 0),
            "close": closes[i],
            "volume": int(row.get("volume", 0) or 0),
            "sma_9": sma_values[9][i],
            "sma_20": sma_values[20][i],
            "sma_50": sma_values[50][i],
            "sma_100": sma_values[100][i],
            "sma_200": sma_values[200][i],
            "rsi": rsi_values[i],
        })
    return result


async def node_deep_dive(state: ResearchState, fmp: FMPClient, fred: FREDClient | None = None) -> ResearchState:
    """Phase 3: run all 9 categories in parallel. Partial success is OK."""
    logger.info("[%s] deep_dive starting (loop %d)", state.ticker, state.loop_count)
    state.phase = "deep_dive"

    # Which categories to run (all on first pass, only flagged on loop-back)
    if state.loop_context and state.loop_context.get("categories"):
        categories_to_run = state.loop_context["categories"]
        logger.info("[%s] Loop-back: re-running %s", state.ticker, categories_to_run)
    else:
        categories_to_run = DEEP_DIVE_CATEGORIES

    # Fetch fresh fundamentals for the data payload
    try:
        from datetime import date, timedelta
        today = date.today()
        one_year_ago = (today - timedelta(days=365)).isoformat()
        today_str = today.isoformat()

        (income, _), (balance, _), (cashflow, _), (profile, _), (dcf, _), (estimates, _), (hist_prices, _), (transcripts, transcript_cit), (key_metrics, _), (fin_growth, _) = (
            await asyncio.gather(
                fmp.get_income_statement(state.ticker, period="quarter", limit=8),
                fmp.get_balance_sheet(state.ticker, period="quarter", limit=8),
                fmp.get_cash_flow(state.ticker, period="quarter", limit=8),
                fmp.get_company_profile(state.ticker),
                fmp.get_dcf(state.ticker),
                fmp.get_analyst_estimates(state.ticker, period="quarter", limit=8),
                fmp.get_historical_price(state.ticker, one_year_ago, today_str),
                fmp.get_earnings_transcript(state.ticker),
                fmp.get_key_metrics_ttm(state.ticker),
                fmp.get_financial_growth(state.ticker, period="quarter", limit=8),
            )
        )
        data_text = _fmt_fundamentals(
            state.ticker,
            income if isinstance(income, list) else [],
            balance if isinstance(balance, list) else [],
            cashflow if isinstance(cashflow, list) else [],
            profile[0] if isinstance(profile, list) and profile else profile or {},
            dcf=dcf if isinstance(dcf, dict) else None,
            estimates=estimates if isinstance(estimates, list) else [],
            key_metrics=key_metrics if isinstance(key_metrics, dict) else None,
            fin_growth=fin_growth if isinstance(fin_growth, list) else [],
        )

        # Build curated financials for frontend dashboard
        prof = profile[0] if isinstance(profile, list) and profile else profile or {}
        curated = _build_curated_financials(
            ticker=state.ticker,
            income=income if isinstance(income, list) else [],
            balance=balance if isinstance(balance, list) else [],
            cashflow=cashflow if isinstance(cashflow, list) else [],
            profile=prof,
            dcf=dcf if isinstance(dcf, dict) else None,
            estimates=estimates if isinstance(estimates, list) else [],
            key_metrics=key_metrics if isinstance(key_metrics, dict) else None,
        )
        curated.daily_prices = _build_technical_data(
            hist_prices if isinstance(hist_prices, list) else []
        )
        state.curated_financials = curated.to_dict()

        # Run transcript analysis (6 passes)
        if transcripts and isinstance(transcripts, list) and len(transcripts) > 0:
            logger.info("[%s] Running transcript analysis (%d transcripts)", state.ticker, len(transcripts))
            state.transcript_analysis = await run_transcript_analysis(state.ticker, transcripts, fmp)
            state.add_citation(StateCitation.from_citation(transcript_cit))
        else:
            logger.info("[%s] No transcripts available, skipping analysis", state.ticker)
            state.transcript_analysis = None

        # Fetch FRED macro indicators
        if fred and fred.available:
            try:
                macro_data, macro_citations = await fred.get_all_macro()
                curated_dict = state.curated_financials or {}
                curated_dict["macro_indicators"] = macro_data
                state.curated_financials = curated_dict
                for cit in macro_citations:
                    state.add_citation(StateCitation.from_citation(cit))
                logger.info("[%s] FRED macro data fetched (%d series)", state.ticker, len(macro_data))
            except Exception as e:
                logger.warning("[%s] FRED fetch failed, skipping macro data: %s", state.ticker, e)
        else:
            logger.info("[%s] FRED client not available, skipping macro data", state.ticker)

    except Exception as e:
        logger.warning("[%s] Data fetch failed, proceeding with partial data: %s", state.ticker, e)
        data_text = f"Note: data fetch partially failed ({e}). Analyze based on available information."
        state.curated_financials = None
        state.transcript_analysis = None

    loop_ctx_str = ""
    if state.loop_context:
        loop_ctx_str = f"\n\nNOTE: This is a loop-back run (attempt {state.loop_count}/2). Focus particularly on: {state.loop_context.get('reason', '')}"

    # Build per-category transcript context
    def _build_transcript_context(category: str) -> str:
        if not state.transcript_analysis or isinstance(state.transcript_analysis, str):
            return ""
        passes = TRANSCRIPT_ROUTING.get(category)
        if not passes:
            return ""
        sections = []
        for pass_key in passes:
            val = state.transcript_analysis.get(pass_key)
            if val is not None and not isinstance(val, str):
                sections.append(f"[Transcript: {pass_key}]\n{json.dumps(val, indent=2)}")
        if not sections:
            return ""
        return "Earnings transcript analysis:\n" + "\n\n".join(sections)

    def _build_macro_context(category: str) -> str:
        macro = (state.curated_financials or {}).get("macro_indicators")
        if not macro or not isinstance(macro, dict):
            return ""
        series_keys = MACRO_ROUTING.get(category)
        if not series_keys:
            return ""
        sections = []
        for key in series_keys:
            points = macro.get(key)
            if points and isinstance(points, list) and len(points) > 0:
                latest = points[-1]
                recent = points[-6:] if len(points) >= 6 else points
                trend_str = ", ".join(f"{p['date']}: {p['value']}" for p in recent)
                sections.append(f"{key}: latest={latest['value']} ({latest['date']}), trend=[{trend_str}]")
        if not sections:
            return ""
        return "Macro economic indicators (FRED):\n" + "\n".join(sections)

    # Run all categories in parallel
    tasks = [
        _run_one_category(cat, state.ticker, state.theme_id, data_text, loop_ctx_str, _build_transcript_context(cat), _build_macro_context(cat))
        for cat in categories_to_run
    ]
    results = await asyncio.gather(*tasks)

    for result in results:
        state.set_category_result(result)

    failed = state.failed_categories()
    succeeded = len(results) - len(failed)
    logger.info("[%s] deep_dive complete: %d/%d succeeded, failed: %s",
                state.ticker, succeeded, len(results), failed)

    state.status = "in_progress"
    return state


# ── Phase 4: thesis_construction ─────────────────────────────────────────────

async def node_thesis_construction(state: ResearchState) -> ResearchState:
    """Phase 4: synthesise all Phase 3 outputs into a structured thesis."""
    logger.info("[%s] thesis_construction starting", state.ticker)
    state.phase = "thesis_construction"

    # Format category results
    results = state.get_deep_dive_results()
    results_text = ""
    for cat, result in results.items():
        if isinstance(result, CategoryResult):
            results_text += f"\n\n## {cat} (Score: {result.score}/100)\n{result.content[:800]}"
        else:
            results_text += f"\n\n## {cat}\n[FAILED: {result.reason}]"

    failed = state.failed_categories()
    loop_ctx = str(state.loop_context) if state.loop_context else "None"

    try:
        response = await complete(
            system=THESIS_SYSTEM,
            user=THESIS_USER.format(
                ticker=state.ticker,
                theme=state.theme_id,
                category_results=results_text,
                failed_categories=", ".join(failed) if failed else "None",
                loop_context=loop_ctx,
            ),
            model=SONNET,
            max_tokens=4000,
        )

        parsed, parse_err = parse_structured_output(response, ThesisOutput)

        if parsed is not None:
            conviction = parsed.conviction_score
            structured = parsed.model_dump()
        else:
            logger.warning(
                "[%s] thesis JSON parse failed: %s", state.ticker, parse_err
            )
            conviction = _extract_score(response)
            structured = None

        state.phase_outputs["thesis"] = {
            "__type__": "PhaseOutput",
            "content": response,
            "structured": structured,
            "conviction_score": conviction,
            "parse_error": parse_err,
        }
        state.conviction_score = conviction
        state.thesis_status = "ON TRACK"
        state.scores["thesis"] = conviction
        logger.info(
            "[%s] thesis complete: conviction %d/100 (structured=%s)",
            state.ticker, conviction, structured is not None,
        )

    except Exception as e:
        logger.error("[%s] thesis_construction failed: %s", state.ticker, e)
        state.phase_outputs["thesis"] = {"__type__": "PhaseError", "reason": str(e)}

    state.status = "in_progress"
    return state


# ── Phase 5: risk_stress_test ─────────────────────────────────────────────────

async def node_risk_stress_test(state: ResearchState) -> ResearchState:
    """Phase 5: stress-test the thesis. Returns loop decision in state."""
    logger.info("[%s] risk_stress_test starting (loop %d)", state.ticker, state.loop_count)
    state.phase = "risk_stress_test"

    thesis_output = state.phase_outputs.get("thesis", {})
    thesis_text = thesis_output.get("content", "No thesis available") if isinstance(thesis_output, dict) else ""

    scores_text = "\n".join(f"  {k}: {v}/100" for k, v in state.scores.items())

    try:
        response = await complete(
            system=RISK_SYSTEM,
            user=RISK_USER.format(
                ticker=state.ticker,
                theme=state.theme_id,
                loop_count=state.loop_count,
                thesis=thesis_text[:2000],
                scores=scores_text,
            ),
            model=SONNET,
            max_tokens=3000,
        )

        parsed, parse_err = parse_structured_output(response, RiskStressTestOutput)

        if parsed is not None:
            rr_ratio = parsed.rr_ratio
            loop_required = parsed.loop_required
            loop_cats = parsed.loop_categories
            loop_reason = parsed.loop_reason
            structured = parsed.model_dump()
        else:
            # Fallback — regex extraction preserves original behavior.
            logger.warning(
                "[%s] risk JSON parse failed: %s", state.ticker, parse_err
            )
            rr_match = re.search(r"(?:RISK_REWARD|rr_ratio)[:\s]*([\d.]+)", response)
            loop_match = re.search(r"(?:LOOP_REQUIRED|loop_required)[:\s]*(YES|NO|true|false)", response, re.IGNORECASE)
            cats_match = re.search(r"(?:LOOP_CATEGORIES|loop_categories)[:\s]*\[([^\]]*)\]", response)
            reason_match = re.search(r"(?:LOOP_REASON|loop_reason)[:\s]*[\"']?(.+?)(?:[\"']?\s*[,}]|$)", response)

            rr_ratio = float(rr_match.group(1)) if rr_match else 0.0
            loop_required = loop_match.group(1).upper() in ("YES", "TRUE") if loop_match else False
            loop_cats = [c.strip().strip('"\'') for c in cats_match.group(1).split(",") if c.strip()] if cats_match else []
            loop_reason = reason_match.group(1).strip() if reason_match else ""
            structured = None

        state.phase_outputs["risk"] = {
            "__type__": "PhaseOutput",
            "content": response,
            "structured": structured,
            "rr_ratio": rr_ratio,
            "loop_required": loop_required,
            "loop_categories": loop_cats,
            "loop_reason": loop_reason,
            "parse_error": parse_err,
        }

        # Determine loop-back
        if loop_required and state.loop_count < 2:
            state.loop_count += 1
            state.loop_context = {
                "categories": loop_cats,
                "reason": loop_reason,
                "rr_ratio": rr_ratio,
            }
            # Auto-advance back to deep_dive; _next_phase() routes
            # back when loop_context is set.
            state.status = "in_progress"
            logger.info("[%s] Loop-back triggered (count %d): %s", state.ticker, state.loop_count, loop_cats)
        elif loop_required and state.loop_count >= 2:
            state.status = "watchlist"
            state.thesis_status = "BROKEN"
            logger.info("[%s] Loop cap reached — forcing WATCHLIST", state.ticker)
        else:
            state.status = "completed"
            logger.info(
                "[%s] risk_stress_test complete: RR %.1f:1 — approved (structured=%s)",
                state.ticker, rr_ratio, structured is not None,
            )

    except Exception as e:
        logger.error("[%s] risk_stress_test failed: %s", state.ticker, e)
        state.phase_outputs["risk"] = {"__type__": "PhaseError", "reason": str(e)}
        state.status = "completed"

    return state


# ── Phase 6: position_monitor ─────────────────────────────────────────────────

async def node_position_monitor(state: ResearchState) -> ResearchState:
    """Phase 6: generate entry zones, sizing, stops, and monitoring cadence."""
    logger.info("[%s] position_monitor starting", state.ticker)
    state.phase = "position_monitor"

    thesis_output = state.phase_outputs.get("thesis", {})
    thesis_text = thesis_output.get("content", "")[:1000] if isinstance(thesis_output, dict) else ""

    risk_output = state.phase_outputs.get("risk", {})
    risk_text = risk_output.get("content", "")[:800] if isinstance(risk_output, dict) else ""

    try:
        response = await complete(
            system=POSITION_SYSTEM,
            user=POSITION_USER.format(
                ticker=state.ticker,
                conviction_score=state.conviction_score,
                thesis_status=state.thesis_status,
                thesis_summary=thesis_text,
                risk_summary=risk_text,
            ),
            model=HAIKU,
            max_tokens=2000,
            assistant_prefill="{",
        )

        parsed, parse_err = parse_structured_output(response, PositionMonitorOutput)

        if parsed is not None:
            structured = parsed.model_dump()
        else:
            logger.warning(
                "[%s] position JSON parse failed: %s", state.ticker, parse_err
            )
            structured = None

        state.phase_outputs["position"] = {
            "__type__": "PhaseOutput",
            "content": response,
            "structured": structured,
            "parse_error": parse_err,
        }
        state.status = "completed"
        state.phase = "completed"
        logger.info(
            "[%s] position_monitor complete — run finished (structured=%s)",
            state.ticker, structured is not None,
        )

    except Exception as e:
        logger.error("[%s] position_monitor failed: %s", state.ticker, e)
        state.phase_outputs["position"] = {"__type__": "PhaseError", "reason": str(e)}
        state.status = "completed"
        state.phase = "completed"

    return state


# ── Earnings transcript analysis ──────────────────────────────────────────────

async def run_transcript_analysis(
    ticker: str,
    transcripts: list[dict],
    fmp: FMPClient,
) -> dict:
    """
    Run all 6 transcript passes. Returns structured dict of results.
    Called from within the deep_dive node for Management & Governance
    and Growth & Earnings categories.
    """
    if not transcripts:
        return {"error": "No transcripts available"}

    def _parse_pass(raw):
        """Parse LLM response as JSON, falling back to raw string on failure."""
        if isinstance(raw, Exception):
            return str(raw)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return raw
        return raw

    latest = transcripts[0] if transcripts else {}
    transcript_text = latest.get("content", latest.get("transcript", "No transcript content"))[:28000]

    prior_transcripts = transcripts[1:4] if len(transcripts) > 1 else []
    all_transcripts_text = "\n\n---QUARTER BREAK---\n\n".join(
        t.get("content", t.get("transcript", ""))[:11200] for t in transcripts[:4]
    )

    results = {}

    # Passes 1–2: Haiku
    from backend.app.graph.llm import HAIKU, SONNET
    pass1, pass2 = await asyncio.gather(
        complete(TRANSCRIPT_PASS1_SYSTEM, transcript_text, model=HAIKU, max_tokens=1000),
        complete(TRANSCRIPT_PASS2_SYSTEM, transcript_text, model=HAIKU, max_tokens=800),
        return_exceptions=True,
    )
    results["pass1_claims"] = _parse_pass(pass1)
    results["pass2_tiers"] = _parse_pass(pass2)

    # Passes 3–6: Sonnet
    qa_section = transcript_text[transcript_text.lower().find("question"):] if "question" in transcript_text.lower() else transcript_text
    qa_section = qa_section[:16800]
    pass3, pass4, pass5 = await asyncio.gather(
        complete(TRANSCRIPT_PASS3_SYSTEM, qa_section, model=SONNET, max_tokens=1000),
        complete(TRANSCRIPT_PASS4_SYSTEM, all_transcripts_text, model=SONNET, max_tokens=1200),
        complete(TRANSCRIPT_PASS5_SYSTEM, all_transcripts_text, model=SONNET, max_tokens=1000),
        return_exceptions=True,
    )
    results["pass3_qa_tensions"] = _parse_pass(pass3)
    results["pass4_validation"] = _parse_pass(pass4)
    results["pass5_consistency"] = _parse_pass(pass5)

    # Pass 6: BOM inference (only on management-flagged capex disclosures)
    capex_keywords = ["billion", "capex", "capital expenditure", "data center", "infrastructure", "invest"]
    has_capex = any(kw in transcript_text.lower() for kw in capex_keywords)
    if has_capex:
        try:
            pass6 = await complete(TRANSCRIPT_PASS6_SYSTEM, transcript_text[:4000], model=SONNET, max_tokens=1200)
        except Exception as exc:
            pass6 = exc
        results["pass6_bom"] = _parse_pass(pass6)
    else:
        results["pass6_bom"] = None

    return results
