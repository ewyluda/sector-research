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
from backend.app.db import async_session, unit_of_work
from backend.app.graph.llm import complete, SONNET, HAIKU
from backend.app.services.catalyst_promotion import promote_catalysts
from backend.app.services.edgar_transcripts_relationships import (
    TRANSCRIPT_QUARTER_LIMIT,
    fetch_recent_transcripts,
)
from backend.app.models.phase_schemas import QuickScreenOutput, ThesisOutput, RiskStressTestOutput, PositionMonitorOutput, DeepDiveCategoryOutput, TargetedAnswer
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
    TARGETED_FOLLOWUP_SYSTEM,
)
from backend.app.graph.state import (
    ResearchState, CategoryResult, CategoryError, StateCitation, StateQuestion, StateResolvedQuestion
)

logger = logging.getLogger(__name__)

CATEGORY_TIMEOUT = 90  # seconds per deep-dive category
TARGETED_FOLLOWUP_CONTEXT_BUDGET_CHARS = 14000

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

# EDGAR XBRL concept routing — which concepts each deep-dive category should see.
# When a routed concept has no facts in xbrl_facts, the helper explicitly notes
# "not disclosed in XBRL" so the LLM distinguishes unrouted from unavailable.
_DEBT_MATURITY_CONCEPTS = [
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
    "us-gaap:LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
]
_RPO_CONCEPTS = [
    "us-gaap:RevenueRemainingPerformanceObligation",
    "us-gaap:RevenueRemainingPerformanceObligationExpectedTimingOfSatisfactionPercentage",
]
_CONCENTRATION_CONCEPTS = ["us-gaap:ConcentrationRiskPercentage1"]
_CREDIT_CONCEPTS = [
    "us-gaap:WeightedAverageInterestRate",
    "us-gaap:LongTermDebt",
    "us-gaap:LineOfCreditFacilityCurrentBorrowingCapacity",
]

EDGAR_ROUTING: dict[str, list[str]] = {
    "Growth & Earnings": _RPO_CONCEPTS,
    "Future Durability": _RPO_CONCEPTS,
    "Financial Health": _DEBT_MATURITY_CONCEPTS + _CREDIT_CONCEPTS,
    "Risk Assessment": _DEBT_MATURITY_CONCEPTS + _CONCENTRATION_CONCEPTS + _CREDIT_CONCEPTS,
    "Business Quality": _CONCENTRATION_CONCEPTS,
}

# Filing narrative section routing. Each category receives verbatim excerpts
# from the most recently ingested 10-K / 10-Q / DEF 14A for the ticker.
# Section text is stored in filing_sections by the Phase A ingest pipeline.
# Truncated to FILING_EXCERPT_BUDGET_CHARS at prompt build time.
FILING_EXCERPT_ROUTING: dict[str, list[str]] = {
    "Business Quality": ["item_1_business"],
    "Risk Assessment": ["item_1a_risk_factors"],
    "Growth & Earnings": ["item_7_mda", "item_2_mda_10q"],
    "Future Durability": ["item_7_mda", "item_1_business"],
    "Management & Governance": ["def14a_governance"],
}

# Per-section character budget when routing excerpts into a prompt.
# ~5K chars ≈ 1.2K tokens, so a category seeing two sections burns ~2.4K
# input tokens of filings context on top of its fundamentals payload.
FILING_EXCERPT_BUDGET_CHARS = 5000


# Categories that receive the counterparty (supply-chain) context in
# their deep-dive prompt. Uses DISPLAY NAMES to match FILING_EXCERPT_ROUTING.
# Structured as a set (no per-section sub-list needed — relationship
# data is already aggregated per-ticker, not per-filing-section).
RELATIONSHIP_ROUTING: set[str] = {
    "Business Quality",
    "Risk Assessment",
    "Future Durability",
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
    grade_consensus: dict | None = None,
    price_target: dict | None = None,
    ratings_snap: dict | None = None,
    grades_recent: list | None = None,
    grades_hist: list | None = None,
    insider_tx: list | None = None,
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

    # ── Analyst consensus + price target ───────────────────────────────────
    if grade_consensus or price_target or ratings_snap:
        parts.append("\nAnalyst Consensus & Ratings:")
        if isinstance(grade_consensus, dict) and grade_consensus:
            sb = grade_consensus.get("strongBuy") or 0
            b = grade_consensus.get("buy") or 0
            h = grade_consensus.get("hold") or 0
            s = grade_consensus.get("sell") or 0
            ss = grade_consensus.get("strongSell") or 0
            total = sb + b + h + s + ss
            label = grade_consensus.get("consensus") or "N/A"
            parts.append(
                f"  Consensus: {label} (StrongBuy {sb} / Buy {b} / Hold {h} / Sell {s} / StrongSell {ss}; {total} analysts)"
            )
        if isinstance(price_target, dict) and price_target:
            tc = price_target.get("targetConsensus")
            th = price_target.get("targetHigh")
            tl = price_target.get("targetLow")
            tm = price_target.get("targetMedian")
            current = profile.get("price") if isinstance(profile, dict) else None
            line = "  Price Target:"
            if tc is not None:
                line += f" avg ${float(tc):.2f}"
            if tm is not None:
                line += f" | median ${float(tm):.2f}"
            if th is not None and tl is not None:
                line += f" | range ${float(tl):.2f}–${float(th):.2f}"
            if current and tc:
                upside = (float(tc) - float(current)) / float(current) * 100
                line += f" | implied {upside:+.1f}% vs current ${float(current):.2f}"
            parts.append(line)
        if isinstance(ratings_snap, dict) and ratings_snap:
            rating = ratings_snap.get("rating")
            score = ratings_snap.get("overallScore")
            if rating or score is not None:
                parts.append(f"  FMP Rating: {rating or 'N/A'} (overall score {score}/5)")

    # ── Recent analyst rating changes (upgrade / downgrade events) ─────────
    if isinstance(grades_recent, list) and grades_recent:
        parts.append(f"\nRecent Analyst Actions ({len(grades_recent[:8])} most recent):")
        for g in grades_recent[:8]:
            date_ = g.get("date", "")[:10]
            firm = g.get("gradingCompany") or "Unknown"
            prev = g.get("previousGrade") or "—"
            new = g.get("newGrade") or "—"
            action = g.get("action") or ""
            parts.append(f"  {date_} {firm}: {prev} → {new} ({action})")

    # ── Analyst consensus count trend (last few months) ────────────────────
    if isinstance(grades_hist, list) and grades_hist:
        parts.append("\nAnalyst Consensus Trend (monthly):")
        for row in grades_hist[:4]:
            date_ = row.get("date", "")[:7]
            sb = row.get("analystRatingsStrongBuy") or 0
            b = row.get("analystRatingsBuy") or 0
            h = row.get("analystRatingsHold") or 0
            s = row.get("analystRatingsSell") or 0
            ss = row.get("analystRatingsStrongSell") or 0
            parts.append(f"  {date_}: SB {sb} / B {b} / H {h} / S {s} / SS {ss}")

    # ── Insider transactions (Form 4s with non-zero transactions only) ─────
    if isinstance(insider_tx, list) and insider_tx:
        # Filter to market-priced transactions — zero-price rows are usually
        # option grants or gifts and don't indicate conviction.
        meaningful = [
            t for t in insider_tx
            if float(t.get("securitiesTransacted") or 0) > 0
            and float(t.get("price") or 0) > 0
        ]
        if meaningful:
            # Aggregate buys vs sells (A = acquisition, D = disposition) for a quick summary
            buys = sum(
                float(t.get("securitiesTransacted") or 0) * float(t.get("price") or 0)
                for t in meaningful if (t.get("acquisitionOrDisposition") or "").upper() == "A"
            )
            sells = sum(
                float(t.get("securitiesTransacted") or 0) * float(t.get("price") or 0)
                for t in meaningful if (t.get("acquisitionOrDisposition") or "").upper() == "D"
            )
            parts.append(f"\nInsider Transactions (last {len(meaningful)} Form 4 filings):")
            parts.append(
                f"  Aggregate: ${buys/1e6:.2f}M buys vs ${sells/1e6:.2f}M sells (net ${(buys-sells)/1e6:+.2f}M)"
            )
            for t in meaningful[:6]:
                fdate = (t.get("filingDate") or "")[:10]
                name = t.get("reportingName") or "Unknown"
                role = t.get("typeOfOwner") or ""
                shares = float(t.get("securitiesTransacted") or 0)
                price = float(t.get("price") or 0)
                direction = "BUY" if (t.get("acquisitionOrDisposition") or "").upper() == "A" else "SELL"
                value = shares * price
                parts.append(
                    f"  {fdate} {name} ({role}): {direction} {shares:,.0f} sh @ ${price:.2f} = ${value/1e6:.2f}M"
                )

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
        state.status = "in_progress"

    except Exception as e:
        logger.error("[%s] quick_screen failed: %s", state.ticker, e)
        state.phase_outputs["quick_screen"] = {
            "__type__": "PhaseError",
            "reason": str(e),
            "traceback": traceback.format_exc(),
        }
        state.status = "error"

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
    technical_context: str = "",
    sentiment_context: str = "",
    edgar_context: str = "",
    filing_excerpts_context: str = "",
    counterparty_context_text: str = "",
    prior_questions_text: str = "",
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
                    technical_data=technical_context,
                    sentiment_data=sentiment_context,
                    edgar_data=edgar_context,
                    filing_excerpts=filing_excerpts_context,
                    counterparty_context=counterparty_context_text,
                    prior_questions=prior_questions_text,
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
            q = stmt.get("period", "")
            cy = stmt.get("calendarYear", "")
            period = f"{q} {cy}".strip() if q and cy else q or stmt.get("date", "")[:7]
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
            q = stmt.get("period", "")
            cy = stmt.get("calendarYear", "")
            period = f"{q} {cy}".strip() if q and cy else q or stmt.get("date", "")[:7]
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
            q = stmt.get("period", "")
            cy = stmt.get("calendarYear", "")
            period = f"{q} {cy}".strip() if q and cy else q or stmt.get("date", "")[:7]
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


async def node_deep_dive(
    state: ResearchState,
    fmp: FMPClient,
    fred: FREDClient | None = None,
    signals: dict | None = None,
    edgar_facts: dict | None = None,
    filing_sections: dict | None = None,
    counterparty_context=None,  # CounterpartyContext | None — typed loosely to avoid import cycle risk
) -> ResearchState:
    """Phase 3: run all 9 categories in parallel. Partial success is OK.

    `signals` is an optional dict of {signal_type: value} pre-fetched by the
    caller (typically PipelineService) from the signals table, used to route
    X sentiment/velocity data into the Sentiment & Narrative prompt.

    `edgar_facts` is an optional {concept: [fact_dict, ...]} dict of XBRL
    facts pre-fetched by the caller from the xbrl_facts table, used to
    route filings data (RPO, debt maturity, customer concentration) into
    the relevant category prompts.

    `filing_sections` is an optional {section_key: {text, heading, form_type,
    filing_date, accession_number}} dict pre-fetched from filing_sections
    (Phase A narrative sections). When present, excerpts are routed into
    Business Quality, Risk Assessment, Growth & Earnings, Management &
    Governance, and Future Durability per FILING_EXCERPT_ROUTING.

    `counterparty_context` is an optional CounterpartyContext pre-fetched
    from the relationships table. When present, the outbound + inbound
    counterparty graph is routed into Business Quality, Risk Assessment,
    and Future Durability prompts per RELATIONSHIP_ROUTING. Rendered as
    a structured anchor list — the prompt instructs the LLM to cite
    these entities by name rather than re-quoting filing text.
    """
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
                fetch_recent_transcripts(fmp, state.ticker, limit=TRANSCRIPT_QUARTER_LIMIT),
                fmp.get_key_metrics_ttm(state.ticker),
                fmp.get_financial_growth(state.ticker, period="quarter", limit=8),
            )
        )

        # Tier 2 secondary fetch: analyst ratings + price targets + insider Form 4s.
        # Each call degrades independently via return_exceptions — a single 404
        # or rate-limit doesn't collapse the whole set.
        def _unwrap(result, default):
            if isinstance(result, BaseException):
                return default
            return result[0]  # each FMP method returns (data, citation)

        secondary = await asyncio.gather(
            fmp.get_analyst_grades_consensus(state.ticker),
            fmp.get_price_target_consensus(state.ticker),
            fmp.get_ratings_snapshot(state.ticker),
            fmp.get_analyst_grades(state.ticker, limit=10),
            fmp.get_analyst_grades_historical(state.ticker, limit=6),
            fmp.get_insider_trading(state.ticker, limit=20),
            return_exceptions=True,
        )
        grade_consensus = _unwrap(secondary[0], {}) or {}
        price_target = _unwrap(secondary[1], {}) or {}
        ratings_snap = _unwrap(secondary[2], {}) or {}
        grades_recent = _unwrap(secondary[3], []) or []
        grades_hist = _unwrap(secondary[4], []) or []
        insider_tx = _unwrap(secondary[5], []) or []

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
            grade_consensus=grade_consensus if isinstance(grade_consensus, dict) else {},
            price_target=price_target if isinstance(price_target, dict) else {},
            ratings_snap=ratings_snap if isinstance(ratings_snap, dict) else {},
            grades_recent=grades_recent if isinstance(grades_recent, list) else [],
            grades_hist=grades_hist if isinstance(grades_hist, list) else [],
            insider_tx=insider_tx if isinstance(insider_tx, list) else [],
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
            if transcript_cit is not None:
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

    def _build_technical_context(category: str) -> str:
        if category != "Technical & Market Structure":
            return ""
        prices = (state.curated_financials or {}).get("daily_prices")
        if not prices or not isinstance(prices, list) or len(prices) == 0:
            return ""
        # Latest 20 sessions, newest last (chronological already)
        recent = prices[-20:]
        lines = ["date | close | volume | sma_9 | sma_20 | sma_50 | sma_200 | rsi"]
        for p in recent:
            lines.append(
                f"{p.get('date')} | {p.get('close')} | {p.get('volume')} | "
                f"{p.get('sma_9')} | {p.get('sma_20')} | {p.get('sma_50')} | "
                f"{p.get('sma_200')} | {p.get('rsi')}"
            )
        latest = prices[-1]
        summary = (
            f"Latest close: {latest.get('close')} | "
            f"RSI(14): {latest.get('rsi')} | "
            f"SMA50: {latest.get('sma_50')} | SMA200: {latest.get('sma_200')}"
        )
        return (
            "Technical indicators (computed from 1Y daily OHLCV):\n"
            f"{summary}\n\nLast 20 sessions:\n" + "\n".join(lines)
        )

    def _build_sentiment_context(category: str) -> str:
        if category != "Sentiment & Narrative":
            return ""
        if not signals:
            return ""
        parts = ["X social signal (Tier 2, directional only):"]
        vel = signals.get("velocity")
        if isinstance(vel, dict):
            parts.append(
                f"Velocity: ratio={vel.get('ratio')} direction={vel.get('direction')} "
                f"count_7d={vel.get('count_7d')} count_30d_approx={vel.get('count_30d_approx')}"
            )
        narr = signals.get("narrative")
        if isinstance(narr, dict):
            parts.append(f"Narrative: post_count={narr.get('post_count')} summary={narr.get('summary') or 'N/A'}")
        disc = signals.get("discovery")
        if isinstance(disc, dict):
            parts.append(
                f"Discovery: score={disc.get('score')} co_mentions_7d={disc.get('co_mentions_7d')} "
                f"total_theme_mentions_7d={disc.get('total_theme_mentions_7d')}"
            )
        if len(parts) == 1:
            return ""
        return "\n".join(parts)

    def _fmt_fact_value(value: float, unit: str) -> str:
        if unit.upper() == "USD":
            if abs(value) >= 1e9:
                return f"${value/1e9:.2f}B"
            if abs(value) >= 1e6:
                return f"${value/1e6:.2f}M"
            return f"${value:,.0f}"
        if unit.lower() == "pure":
            return f"{value*100:.2f}%" if abs(value) <= 1 else f"{value:.2f}"
        return f"{value:,.0f} {unit}"

    def _build_edgar_context(category: str) -> str:
        concepts = EDGAR_ROUTING.get(category)
        if not concepts:
            return ""
        present_lines: list[str] = []
        missing: list[str] = []
        facts = edgar_facts or {}
        for concept in concepts:
            entries = facts.get(concept)
            short = concept.split(":", 1)[-1]
            if not entries:
                missing.append(short)
                continue
            # Most recent first, show up to 4
            for e in entries[:4]:
                present_lines.append(
                    f"  {short} [{e.get('fiscal_year')} {e.get('fiscal_period') or ''}] "
                    f"{e.get('period_start')} → {e.get('period_end')}: "
                    f"{_fmt_fact_value(e['value'], e.get('unit') or '')}"
                )
        if not present_lines and not missing:
            return ""
        sections = ["SEC EDGAR XBRL facts (Tier 1, authoritative from 10-K/10-Q filings):"]
        if present_lines:
            sections.append("\n".join(present_lines))
        if missing:
            sections.append("Not disclosed in XBRL: " + ", ".join(missing))
        return "\n".join(sections)

    def _build_filing_excerpt_context(category: str) -> str:
        section_keys = FILING_EXCERPT_ROUTING.get(category)
        if not section_keys:
            return ""
        sections = filing_sections or {}
        blocks: list[str] = []
        for key in section_keys:
            payload = sections.get(key)
            if not payload:
                continue
            text = (payload.get("text") or "")[:FILING_EXCERPT_BUDGET_CHARS]
            if not text:
                continue
            truncated = len(payload.get("text") or "") > FILING_EXCERPT_BUDGET_CHARS
            header = (
                f"[{payload.get('form_type', '?')} · {payload.get('filing_date', '?')} · "
                f"{payload.get('heading') or key}]"
            )
            if truncated:
                header += f" (truncated to {FILING_EXCERPT_BUDGET_CHARS} chars)"
            blocks.append(f"{header}\n{text}")
        if not blocks:
            return ""
        return (
            "SEC filing excerpts (Tier 1, verbatim narrative from latest 10-K / 10-Q / DEF 14A):\n"
            + "\n\n".join(blocks)
        )

    def _build_counterparty_context(category: str) -> str:
        """Render the relationship graph payload for the deep-dive prompt.
        Returns '' when the category is not routed, or when we have no
        extracted relationships for this ticker."""
        if category not in RELATIONSHIP_ROUTING:
            return ""
        if not counterparty_context or not counterparty_context.has_data:
            return ""

        ctx = counterparty_context  # alias for brevity

        lines: list[str] = [
            "RESOLVED COUNTERPARTIES",
            "(pre-extracted from the filing excerpts above; use these as anchors when",
            "referring to named customers, suppliers, or partners.",
            "For resolved entities, use the $TICKER notation exactly as shown below",
            "on first mention — do not refer to them by product/vendor name alone.",
            "Do NOT re-quote verbatim text from the filings for these entities.)",
            "",
        ]

        def _fmt_entry(e) -> str:
            # e: CounterpartyEntry
            label = f"${e.resolved_ticker} — {e.name}" if e.resolved_ticker else e.name
            parts = [label, e.relationship_type]
            if e.magnitude_pct is not None:
                parts.append(f"{e.magnitude_pct:.1f}%")
            return "    - " + " — ".join(parts)

        if ctx.outbound:
            lines.append(f"Outbound — {state.ticker}'s disclosed relationships:")
            # Stable type order — show concentration-relevant buckets first.
            type_order = [
                "customer", "supplier", "partner", "joint_venture",
                "licensor", "licensee", "distributor", "reseller",
                "other",
            ]
            for t in type_order:
                entries = ctx.outbound.get(t)
                if not entries:
                    continue
                lines.append(f"  {t.replace('_', ' ').title()}s:")
                for e in entries:
                    lines.append(_fmt_entry(e))
            lines.append("")

        if ctx.inbound:
            lines.append(f"Mentioned by others — who named {state.ticker} in their own filings:")
            for t, entries in sorted(ctx.inbound.items()):
                if not entries:
                    continue
                lines.append(f"  As a {t.replace('_', ' ')} ({len(entries)} mention(s)):")
                for e in entries:
                    # e.resolved_ticker is the author ticker here
                    # Bucket header already states the relationship_type; don't repeat.
                    lines.append(f"    - ${e.resolved_ticker}")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    category_contexts: dict[str, dict[str, str]] = {}
    for cat in categories_to_run:
        category_contexts[cat] = {
            "transcript": _build_transcript_context(cat),
            "macro": _build_macro_context(cat),
            "technical": _build_technical_context(cat),
            "sentiment": _build_sentiment_context(cat),
            "edgar": _build_edgar_context(cat),
            "filing": _build_filing_excerpt_context(cat),
            "counterparty": _build_counterparty_context(cat),
        }

    def _build_targeted_context_for_category(category: str) -> str:
        parts = [f"Fundamental data:\n{data_text}"]
        ctx = category_contexts.get(category, {})
        for label, text in [
            ("Transcript context", ctx.get("transcript", "")),
            ("Macro context", ctx.get("macro", "")),
            ("Technical context", ctx.get("technical", "")),
            ("Sentiment context", ctx.get("sentiment", "")),
            ("EDGAR XBRL context", ctx.get("edgar", "")),
            ("Filing excerpt context", ctx.get("filing", "")),
            ("Counterparty context", ctx.get("counterparty", "")),
        ]:
            if text:
                parts.append(f"{label}:\n{text}")
        return "\n\n".join(parts)[:TARGETED_FOLLOWUP_CONTEXT_BUDGET_CHARS]

    # Fetch prior open questions for each category (cross-run resurfacing)
    prior_q_lists = await asyncio.gather(
        *[_fetch_prior_open_questions(state.ticker, cat) for cat in categories_to_run],
        return_exceptions=True,
    )
    prior_q_map: dict[str, list[dict]] = {}
    for cat, pq in zip(categories_to_run, prior_q_lists):
        prior_q_map[cat] = pq if isinstance(pq, list) else []

    # Run all categories in parallel
    tasks = [
        _run_one_category(
            cat, state.ticker, state.theme_id, data_text, loop_ctx_str,
            category_contexts[cat]["transcript"], category_contexts[cat]["macro"],
            category_contexts[cat]["technical"], category_contexts[cat]["sentiment"],
            category_contexts[cat]["edgar"],
            category_contexts[cat]["filing"],
            category_contexts[cat]["counterparty"],
            _render_prior_questions_slot(prior_q_map[cat]),
        )
        for cat in categories_to_run
    ]
    results = await asyncio.gather(*tasks)

    for result in results:
        state.set_category_result(result)

    failed = state.failed_categories()
    succeeded = len(results) - len(failed)
    logger.info("[%s] deep_dive complete: %d/%d succeeded, failed: %s",
                state.ticker, succeeded, len(results), failed)

    # Tier 1.2 — stage extracted questions for DB persistence
    question_categories: set[str] = set()
    for result in results:
        if not isinstance(result, CategoryResult):
            continue
        structured = result.structured or {}
        for raw_q in structured.get("questions", []) or []:
            question_categories.add(result.category)
            state.questions_extracted.append(StateQuestion(
                category=result.category,
                question_text=raw_q["question_text"],
                priority=int(raw_q["priority"]),
                auto_answerable=bool(raw_q["auto_answerable"]),
            ).to_dict())
        for raw_rq in structured.get("resolved_questions", []) or []:
            qid = raw_rq.get("question_id")
            # Look up original question text from this category's prior set
            original_text = qid  # fallback to the id if lookup fails
            for prior_entry in prior_q_map.get(result.category, []) or []:
                if prior_entry.get("id") == qid:
                    original_text = prior_entry.get("question_text") or qid
                    break
            state.questions_resolved_this_run.append(StateResolvedQuestion(
                question_text=original_text,
                answer_text=raw_rq["answer_text"],
                source="deep_dive_resurfaced",
            ).to_dict())

    state.targeted_followup_context = {
        cat: _build_targeted_context_for_category(cat)
        for cat in sorted(question_categories)
    }

    await _persist_extracted_questions(state)
    await _apply_resurfaced_resolutions(state)

    state.status = "in_progress"
    return state


# ── Tier 1.2 targeted followup ────────────────────────────────────────────────

def _build_targeted_followup_user_msg(
    *,
    question_text: str,
    category: str,
    key_findings: list[str],
    analysis: str,
    routed_context: str = "",
) -> str:
    findings_block = "\n".join(f"- {f}" for f in key_findings or []) or "(none)"
    parts = [
        f"Question: {question_text}",
        f"Originating category: {category}",
        f"Key findings from that category's deep-dive:\n{findings_block}",
        f"Full category analysis:\n{analysis}",
    ]
    if routed_context:
        parts.append(f"Original data payload and routed context:\n{routed_context}")
    return "\n\n".join(parts)


async def node_targeted_followup(state: ResearchState) -> ResearchState:
    """Tier 1.2 targeted second-pass.

    Picks ≤3 priority-1 + auto_answerable questions created this run,
    runs them in parallel through focused Sonnet calls, persists answers
    back to the questions table, and stages StateResolvedQuestion entries
    for node_thesis_construction to see."""
    from backend.app.models.question import Question
    from sqlalchemy import select, update
    from datetime import datetime, timezone

    state.phase = "targeted_followup"

    # 1. Pick eligible questions. All ID columns are UUID(as_uuid=False) — strings.
    async with async_session() as db:
        stmt = (
            select(Question)
            .where(Question.created_run_id == state.run_id)
            .where(Question.priority == 1)
            .where(Question.auto_answerable.is_(True))
            .where(Question.status == "open")
            .order_by(Question.category.asc(), Question.created_at.asc())
            .limit(3)
        )
        eligible = (await db.execute(stmt)).scalars().all()
        snapshots = [
            {"id": q.id, "category": q.category, "question_text": q.question_text}
            for q in eligible
        ]

    if not snapshots:
        state.status = "in_progress"
        return state

    deep = state.get_deep_dive_results()

    async def _answer_one(snap: dict) -> tuple[str, str | None]:
        cat = snap["category"]
        result = deep.get(cat)
        content = ""
        if result is not None and hasattr(result, "key_findings"):
            content = (getattr(result, "content", "") or "")[:6000]

        user_msg = _build_targeted_followup_user_msg(
            question_text=snap["question_text"],
            category=cat,
            key_findings=list(getattr(result, "key_findings", []) or []) if result is not None else [],
            analysis=content,
            routed_context=(state.targeted_followup_context or {}).get(cat, ""),
        )

        try:
            raw = await complete(
                model=SONNET,
                system=TARGETED_FOLLOWUP_SYSTEM,
                user=user_msg,
                max_tokens=600,
                assistant_prefill='{"answer_text":',
            )
            parsed = TargetedAnswer.model_validate_json(raw)
            return snap["id"], parsed.answer_text
        except Exception:  # noqa: BLE001
            logger.exception("targeted_followup failed for question %s — leaving open", snap["id"])
            return snap["id"], None

    answers = await asyncio.gather(*(_answer_one(s) for s in snapshots))

    async with async_session() as db:
        for qid, answer in answers:
            if answer is None:
                continue  # Sonnet failure — leave question open for retry
            stmt = (
                update(Question)
                .where(Question.id == qid)
                .where(Question.status == "open")
                .values(
                    status="resolved_auto",
                    answer_text=answer,
                    answer_source="targeted_followup",
                    resolved_run_id=state.run_id,
                    resolved_at=datetime.now(timezone.utc),
                )
            )
            await db.execute(stmt)
        await db.commit()

    for snap, (_, answer) in zip(snapshots, answers):
        if answer is None:
            continue
        state.questions_resolved_this_run.append(StateResolvedQuestion(
            question_text=snap["question_text"],
            answer_text=answer,
            source="targeted_followup",
        ).to_dict())

    state.status = "in_progress"
    return state


def _render_questions_resolved(staged: list[dict]) -> str:
    """Render state.questions_resolved_this_run for the thesis prompt slot."""
    if not staged:
        return "(none this run)"
    lines = []
    for entry in staged:
        src = entry.get("source", "?")
        text = entry.get("question_text", "?")
        ans = entry.get("answer_text", "?")
        lines.append(f"- [{src}] Q: {text}\n  A: {ans}")
    return "\n".join(lines)


# ── Phase 4: thesis_construction ─────────────────────────────────────────────

async def node_thesis_construction(state: ResearchState) -> ResearchState:
    """Phase 4: synthesise all Phase 3 outputs into a structured thesis."""
    logger.info("[%s] thesis_construction starting", state.ticker)
    state.phase = "thesis_construction"

    # Format category results
    results = state.get_deep_dive_results()

    # Build concise summary (scores + top 2 findings per category)
    summary_lines = []
    results_text = ""
    for cat, result in results.items():
        if isinstance(result, CategoryResult):
            top_findings = "; ".join(result.key_findings[:2]) if result.key_findings else "No key findings"
            summary_lines.append(f"- {cat}: {result.score}/100 — {top_findings}")
            results_text += f"\n\n## {cat} (Score: {result.score}/100)\n{result.content[:800]}"
        else:
            summary_lines.append(f"- {cat}: FAILED — {result.reason}")
            results_text += f"\n\n## {cat}\n[FAILED: {result.reason}]"

    category_summary = "\n".join(summary_lines)

    # Extract quick screen context
    qs_output = state.phase_outputs.get("quick_screen", {})
    qs_structured = qs_output.get("structured") if isinstance(qs_output, dict) else None
    qs_verdict = "N/A"
    qs_score = qs_output.get("score", "N/A") if isinstance(qs_output, dict) else "N/A"
    qs_thesis = "N/A"
    qs_risk = "N/A"
    if qs_structured and isinstance(qs_structured, dict):
        qs_verdict = qs_structured.get("recommendation", "N/A")
        qs_thesis = qs_structured.get("thesis", "N/A")
        qs_risk = qs_structured.get("key_risk", "N/A")

    failed = state.failed_categories()
    loop_ctx = str(state.loop_context) if state.loop_context else "None"

    try:
        response = await complete(
            system=THESIS_SYSTEM,
            user=THESIS_USER.format(
                ticker=state.ticker,
                theme=state.theme_id,
                quick_screen_verdict=qs_verdict,
                quick_screen_score=qs_score,
                quick_screen_thesis=qs_thesis,
                quick_screen_risk=qs_risk,
                category_summary=category_summary,
                category_results=results_text,
                failed_categories=", ".join(failed) if failed else "None",
                loop_context=loop_ctx,
                questions_resolved=_render_questions_resolved(state.questions_resolved_this_run),
            ),
            model=SONNET,
            max_tokens=6000,
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

        # Tier 1.3: promote parsed catalysts into first-class DB rows.
        # Failure here is non-fatal — JSONB still has the canonical copy.
        if parsed is not None:
            try:
                fmp = FMPClient()
                try:
                    async with unit_of_work() as cat_db:
                        await promote_catalysts(state, parsed, fmp, cat_db)
                finally:
                    await fmp.close()
            except Exception as cat_err:
                logger.warning(
                    "[%s] catalyst promotion failed: %s", state.ticker, cat_err
                )

        logger.info(
            "[%s] thesis complete: conviction %d/100 (structured=%s)",
            state.ticker, conviction, structured is not None,
        )
        state.status = "in_progress"

    except Exception as e:
        logger.error("[%s] thesis_construction failed: %s", state.ticker, e)
        state.phase_outputs["thesis"] = {"__type__": "PhaseError", "reason": str(e)}
        state.status = "error"

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
        state.status = "error"

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


# ── Tier 1.2 — question persistence ──────────────────────────────────────────

async def _persist_extracted_questions(state: ResearchState) -> None:
    """After deep_dive merges, write staged questions to the DB.

    All UUID(as_uuid=False) columns store strings at Python level."""
    from backend.app.db import async_session
    from backend.app.models.question import Question

    if not state.questions_extracted:
        return

    async with async_session() as db:
        for staged in state.questions_extracted:
            q = Question(
                ticker=state.ticker,
                theme_id=state.theme_id or None,
                category=staged["category"],
                question_text=staged["question_text"],
                priority=staged["priority"],
                auto_answerable=staged["auto_answerable"],
                status="open",
                created_run_id=state.run_id,
            )
            db.add(q)
        await db.commit()
    state.questions_extracted = []


async def _fetch_prior_open_questions(
    ticker: str,
    category: str,
    limit: int = 5,
) -> list[dict]:
    """Top open priority-1/2 questions for (ticker, category) ordered most-recent first.

    Returns list of {id, question_text, priority, created_at_iso} dicts.
    Caller renders these into the {prior_questions} slot."""
    from backend.app.db import async_session
    from backend.app.models.question import Question
    from sqlalchemy import select

    async with async_session() as db:
        stmt = (
            select(Question)
            .where(Question.ticker == ticker)
            .where(Question.category == category)
            .where(Question.status == "open")
            .where(Question.priority.in_([1, 2]))
            .order_by(Question.created_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": str(r.id),
            "question_text": r.question_text,
            "priority": r.priority,
            "created_at_iso": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]


def _render_prior_questions_slot(prior: list[dict]) -> str:
    """Render the {prior_questions} prompt block. Empty string when no priors."""
    if not prior:
        return ""
    lines = [
        "PREVIOUSLY UNRESOLVED QUESTIONS FOR THIS PILLAR.",
        "If the current data permits answering them, emit them in `resolved_questions` "
        "with `question_id` and `answer_text`. Otherwise, you may restate them — "
        "that's signal they're genuinely hard.",
        "",
    ]
    for q in prior:
        lines.append(f"- [{q['id']}] (P{q['priority']}) {q['question_text']}")
    lines.append("")
    return "\n".join(lines)


async def _apply_resurfaced_resolutions(state: ResearchState) -> None:
    """Mark resurfaced questions as resolved_inline in the DB.

    Reads the freshly-merged state.phase_outputs to find each category's
    resolved_questions list, then updates the corresponding question rows.
    Question IDs and run IDs are strings (UUID(as_uuid=False))."""
    from backend.app.db import async_session
    from backend.app.models.question import Question
    from sqlalchemy import update
    from uuid import UUID
    from datetime import datetime, timezone

    resolutions: list[tuple[str, str]] = []  # (question_id, answer_text)
    for category, payload in state.phase_outputs.items():
        if not isinstance(payload, dict):
            continue
        if payload.get("__type__") != "CategoryResult":
            continue
        structured = payload.get("structured") or {}
        for rq in structured.get("resolved_questions", []) or []:
            resolutions.append((rq["question_id"], rq["answer_text"]))

    if not resolutions:
        return

    async with async_session() as db:
        for qid_str, answer in resolutions:
            try:
                UUID(qid_str)  # validate; skip junk if LLM hallucinated a non-UUID
            except (ValueError, TypeError):
                continue
            stmt = (
                update(Question)
                .where(Question.id == qid_str)
                .where(Question.status == "open")
                .values(
                    status="resolved_inline",
                    answer_text=answer,
                    answer_source="deep_dive_resurfaced",
                    resolved_run_id=state.run_id,
                    resolved_at=datetime.now(timezone.utc),
                )
            )
            await db.execute(stmt)
        await db.commit()
