"""Phase node implementations for the LangGraph pipeline.

Each node receives ResearchState, does work, mutates state, and returns it.
Every node is a pure async function — no side effects except state mutation.

Phase assignments:
  quick_screen      → Haiku
  deep_dive (×9)    → Sonnet, parallel subgraph
  thesis            → Sonnet
  risk_stress_test  → Sonnet
  position_monitor  → Haiku

Formatting helpers, curated-financials builders, transcript analysis, and
question-lifecycle helpers were split out in M2.2:
  - backend.app.graph.formatters  (data formatters)
  - backend.app.services.transcript_analysis
  - backend.app.services.question_lifecycle
All moved symbols are re-exported here so existing importers keep working.
New code should import from the destination modules directly; the re-exports
are a transitional shim deletable once the remaining consumers migrate
(backend/tests/test_output_parsing.py, test_quant_fingerprint.py,
test_deep_dive_valuation_ratios.py, scripts/smoke_question_log.py,
services/questions.py).
"""

from __future__ import annotations

import asyncio
import logging
import re
import traceback

from backend.app.clients.fmp import FMPClient
from backend.app.clients.fred import FREDClient
from backend.app.db import async_session, unit_of_work
from backend.app.graph.deep_dive_context import DeepDiveContext, build_all_contexts
from backend.app.graph.deep_dive_helpers import unwrap_gather_result as _unwrap
from backend.app.graph.formatters import (  # noqa: F401  re-exported for backwards compat
    _build_curated_financials,
    _build_technical_data,
    _extract_key_findings,
    _extract_score,
    _first_metric,
    _fmt_fundamentals,
)
from backend.app.graph.llm import complete, SONNET, HAIKU
from backend.app.graph.output_parser import parse_structured_output
from backend.app.graph.prompts import (
    QUICK_SCREEN_SYSTEM, QUICK_SCREEN_USER,
    DEEP_DIVE_SYSTEM, DEEP_DIVE_USER, DEEP_DIVE_CATEGORIES,
    THESIS_SYSTEM, THESIS_USER,
    RISK_SYSTEM, RISK_USER,
    POSITION_SYSTEM, POSITION_USER,
    TARGETED_FOLLOWUP_SYSTEM,
)
from backend.app.graph.state import (
    ResearchState, CategoryResult, CategoryError, StateCitation, StateQuestion, StateResolvedQuestion
)
from backend.app.models.phase_schemas import QuickScreenOutput, ThesisOutput, RiskStressTestOutput, PositionMonitorOutput, DeepDiveCategoryOutput, TargetedAnswer
from backend.app.services.catalyst_promotion import promote_catalysts
from backend.app.services.edgar_transcripts_relationships import (
    TRANSCRIPT_QUARTER_LIMIT,
    fetch_recent_transcripts,
)
from backend.app.services.question_lifecycle import (  # noqa: F401  re-exported for backwards compat
    _apply_resurfaced_resolutions,
    _fetch_prior_open_questions,
    _persist_extracted_questions,
    _render_prior_questions_slot,
    _render_questions_resolved,
)
from backend.app.services.transcript_analysis import run_transcript_analysis, TranscriptAnalysisResult  # noqa: F401  re-exported for backwards compat

logger = logging.getLogger(__name__)

CATEGORY_TIMEOUT = 90  # seconds per deep-dive category
TARGETED_FOLLOWUP_CONTEXT_BUDGET_CHARS = 14000


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
    quant_context: str = "",
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
                    quant_data=quant_context,
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
    route filings data (RPO, debt maturity, credit metrics) into the
    relevant category prompts. Customer concentration is NOT routed here
    — the SEC `companyfacts` endpoint only returns un-dimensioned parent
    facts and `ConcentrationRiskPercentage1` is always disclosed with
    axes (`CustomerAxis`, `ProductAxis`), so structured concentration
    intel arrives via Phase B narrative extraction (`Relationship`
    rows with `unnamed=true`).

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

        (income, _), (balance, _), (cashflow, _), (profile, _), (dcf, _), (estimates, _), (hist_prices, _), (transcripts, transcript_cit), (key_metrics, _), (ratios_ttm, _), (fin_growth, _) = (
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
                fmp.get_ratios_ttm(state.ticker),
                fmp.get_financial_growth(state.ticker, period="quarter", limit=8),
            )
        )

        # Tier 2 secondary fetch: analyst ratings + price targets + insider Form 4s.
        # Each call degrades independently via return_exceptions — a single 404
        # or rate-limit doesn't collapse the whole set. _unwrap is imported
        # from deep_dive_helpers (lifted out for unit-test reach).
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
            ratios=ratios_ttm if isinstance(ratios_ttm, dict) else None,
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
            ratios=ratios_ttm if isinstance(ratios_ttm, dict) else None,
        )
        curated.daily_prices = _build_technical_data(
            hist_prices if isinstance(hist_prices, list) else []
        )
        state.curated_financials = curated.to_dict()

        # Run transcript analysis (6 passes)
        if transcripts and isinstance(transcripts, list) and len(transcripts) > 0:
            logger.info("[%s] Running transcript analysis (%d transcripts)", state.ticker, len(transcripts))
            ta_result = await run_transcript_analysis(state.ticker, transcripts, fmp)
            if ta_result.status == "ok":
                state.transcript_analysis = ta_result.value
                if transcript_cit is not None:
                    state.add_citation(StateCitation.from_citation(transcript_cit))
            elif ta_result.status == "error":
                logger.warning("[%s] Transcript analysis failed: %s", state.ticker, ta_result.error)
                state.transcript_analysis = None
            else:
                state.transcript_analysis = None
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

    # Per-category context builders live in deep_dive_context; the seven
    # nested closures that used to be here were a hidden dependency surface
    # on state/signals/edgar_facts/filing_sections/counterparty_context.
    # Build the dataclass AFTER the FRED block above — that block mutates
    # state.curated_financials which two of the builders read.
    deep_dive_ctx = DeepDiveContext(
        ticker=state.ticker,
        categories=categories_to_run,
        transcript_analysis=state.transcript_analysis,
        curated_financials=state.curated_financials,
        signals=signals,
        edgar_facts=edgar_facts,
        filing_sections=filing_sections,
        counterparty_context=counterparty_context,
    )
    category_contexts = build_all_contexts(deep_dive_ctx)

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
            ("Quant context", ctx.get("quant", "")),
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
            category_contexts[cat]["quant"],
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
