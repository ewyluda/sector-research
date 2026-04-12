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
import logging
import re
import traceback
from typing import Any

from backend.app.clients.fmp import FMPClient
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


def _fmt_fundamentals(ticker: str, income: list, balance: list, cashflow: list, profile: dict) -> str:
    """Format raw FMP data into a readable block for LLM prompts."""
    parts = []
    if profile and isinstance(profile, dict):
        parts.append(f"Company: {profile.get('companyName', ticker)}")
        parts.append(f"Sector: {profile.get('sector')} | Industry: {profile.get('industry')}")
        parts.append(f"Market Cap: ${profile.get('marketCap', 0)/1e9:.1f}B")
        parts.append(f"Beta: {profile.get('beta', 'N/A')}")
        parts.append(f"Description: {str(profile.get('description', ''))[:300]}")

    if income:
        i = income[0]
        prev_rev = income[1].get("revenue", 0) if len(income) > 1 else 0
        curr_rev = i.get("revenue", 0)
        growth = (curr_rev - prev_rev) / prev_rev if prev_rev else 0
        parts.append(f"\nLatest Financials ({i.get('date', '')}):")
        parts.append(f"  Revenue: ${curr_rev/1e9:.2f}B (YoY: {growth*100:.1f}%)")
        parts.append(f"  Gross Profit: ${i.get('grossProfit', 0)/1e9:.2f}B")
        parts.append(f"  Operating Income: ${i.get('operatingIncome', 0)/1e9:.2f}B")
        parts.append(f"  Net Income: ${i.get('netIncome', 0)/1e9:.2f}B")
        parts.append(f"  EPS: {i.get('eps', 'N/A')}")

    if balance:
        b = balance[0]
        parts.append(f"\nBalance Sheet ({b.get('date', '')}):")
        parts.append(f"  Cash: ${b.get('cashAndCashEquivalents', 0)/1e9:.2f}B")
        parts.append(f"  Total Debt: ${b.get('totalDebt', 0)/1e9:.2f}B")
        parts.append(f"  Total Equity: ${b.get('totalEquity', 0)/1e9:.2f}B")

    if cashflow:
        cf = cashflow[0]
        parts.append(f"\nCash Flow ({cf.get('date', '')}):")
        parts.append(f"  Operating CF: ${cf.get('operatingCashFlow', 0)/1e9:.2f}B")
        parts.append(f"  Free Cash Flow: ${cf.get('freeCashFlow', 0)/1e9:.2f}B")
        parts.append(f"  CapEx: ${cf.get('capitalExpenditure', 0)/1e9:.2f}B")

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

    state.status = "awaiting_approval"
    return state


# ── Phase 3: deep_dive (parallel subgraph) ────────────────────────────────────

async def _run_one_category(
    category: str,
    ticker: str,
    theme_id: str,
    data: str,
    loop_context: str,
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


async def node_deep_dive(state: ResearchState, fmp: FMPClient) -> ResearchState:
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
        (income, _), (balance, _), (cashflow, _), (profile, _), (dcf, _), (estimates, _) = (
            await asyncio.gather(
                fmp.get_income_statement(state.ticker, limit=4),
                fmp.get_balance_sheet(state.ticker, limit=4),
                fmp.get_cash_flow(state.ticker, limit=4),
                fmp.get_company_profile(state.ticker),
                fmp.get_dcf(state.ticker),
                fmp.get_analyst_estimates(state.ticker, limit=4),
            )
        )
        data_text = _fmt_fundamentals(
            state.ticker,
            income if isinstance(income, list) else [],
            balance if isinstance(balance, list) else [],
            cashflow if isinstance(cashflow, list) else [],
            profile[0] if isinstance(profile, list) and profile else profile or {},
        )
        if dcf and isinstance(dcf, dict):
            data_text += f"\n\nDCF Value: ${dcf.get('dcf', 'N/A')} | Stock Price: ${dcf.get('Stock Price', 'N/A')}"

    except Exception as e:
        logger.warning("[%s] Data fetch failed, proceeding with partial data: %s", state.ticker, e)
        data_text = f"Note: data fetch partially failed ({e}). Analyze based on available information."

    loop_ctx_str = ""
    if state.loop_context:
        loop_ctx_str = f"\n\nNOTE: This is a loop-back run (attempt {state.loop_count}/2). Focus particularly on: {state.loop_context.get('reason', '')}"

    # Run all categories in parallel
    tasks = [
        _run_one_category(cat, state.ticker, state.theme_id, data_text, loop_ctx_str)
        for cat in categories_to_run
    ]
    results = await asyncio.gather(*tasks)

    for result in results:
        state.set_category_result(result)

    failed = state.failed_categories()
    succeeded = len(results) - len(failed)
    logger.info("[%s] deep_dive complete: %d/%d succeeded, failed: %s",
                state.ticker, succeeded, len(results), failed)

    state.status = "awaiting_approval"
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

    state.status = "awaiting_approval"
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
            # Pause for human review — user sees the risk card with the
            # loop-back recommendation and approves. _next_phase() routes
            # back to deep_dive when loop_context is set.
            state.status = "awaiting_approval"
            logger.info("[%s] Loop-back triggered (count %d): %s", state.ticker, state.loop_count, loop_cats)
        elif loop_required and state.loop_count >= 2:
            state.status = "watchlist"
            state.thesis_status = "BROKEN"
            logger.info("[%s] Loop cap reached — forcing WATCHLIST", state.ticker)
        else:
            state.status = "awaiting_approval"
            logger.info(
                "[%s] risk_stress_test complete: RR %.1f:1 — approved (structured=%s)",
                state.ticker, rr_ratio, structured is not None,
            )

    except Exception as e:
        logger.error("[%s] risk_stress_test failed: %s", state.ticker, e)
        state.phase_outputs["risk"] = {"__type__": "PhaseError", "reason": str(e)}
        state.status = "awaiting_approval"

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

    latest = transcripts[0] if transcripts else {}
    transcript_text = latest.get("content", latest.get("transcript", "No transcript content"))[:6000]

    prior_transcripts = transcripts[1:4] if len(transcripts) > 1 else []
    all_transcripts_text = "\n\n---QUARTER BREAK---\n\n".join(
        t.get("content", t.get("transcript", ""))[:2000] for t in transcripts[:4]
    )

    results = {}

    # Passes 1–2: Haiku
    from backend.app.graph.llm import HAIKU, SONNET
    pass1, pass2 = await asyncio.gather(
        complete(TRANSCRIPT_PASS1_SYSTEM, transcript_text, model=HAIKU, max_tokens=1000),
        complete(TRANSCRIPT_PASS2_SYSTEM, transcript_text, model=HAIKU, max_tokens=800),
        return_exceptions=True,
    )
    results["pass1_claims"] = pass1 if not isinstance(pass1, Exception) else str(pass1)
    results["pass2_tiers"] = pass2 if not isinstance(pass2, Exception) else str(pass2)

    # Passes 3–6: Sonnet
    qa_section = transcript_text[transcript_text.lower().find("question"):] if "question" in transcript_text.lower() else transcript_text
    pass3, pass4, pass5 = await asyncio.gather(
        complete(TRANSCRIPT_PASS3_SYSTEM, qa_section[:3000], model=SONNET, max_tokens=1000),
        complete(TRANSCRIPT_PASS4_SYSTEM, all_transcripts_text, model=SONNET, max_tokens=1200),
        complete(TRANSCRIPT_PASS5_SYSTEM, all_transcripts_text, model=SONNET, max_tokens=1000),
        return_exceptions=True,
    )
    results["pass3_qa_tensions"] = pass3 if not isinstance(pass3, Exception) else str(pass3)
    results["pass4_validation"] = pass4 if not isinstance(pass4, Exception) else str(pass4)
    results["pass5_consistency"] = pass5 if not isinstance(pass5, Exception) else str(pass5)

    # Pass 6: BOM inference (only on management-flagged capex disclosures)
    capex_keywords = ["billion", "capex", "capital expenditure", "data center", "infrastructure", "invest"]
    has_capex = any(kw in transcript_text.lower() for kw in capex_keywords)
    if has_capex:
        pass6 = await complete(TRANSCRIPT_PASS6_SYSTEM, transcript_text[:4000], model=SONNET, max_tokens=1200)
        results["pass6_bom"] = pass6
    else:
        results["pass6_bom"] = None

    return results
