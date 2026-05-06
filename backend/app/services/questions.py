"""Questions service — query helpers + on-demand retry-auto orchestration.

Mirrors the read_through.py / status_board.py pattern: thin DB queries
that the API layer calls; LLM orchestration kept here so api/questions.py
stays HTTP-shape only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pydantic import BaseModel, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.graph.llm import SONNET, complete
from backend.app.graph.state import ResearchState
from backend.app.models.question import Question
from backend.app.models.research_run import ResearchRun

logger = logging.getLogger(__name__)


# ── Query helpers ────────────────────────────────────────────────────────────


async def list_questions(
    db: AsyncSession,
    *,
    ticker: str | None = None,
    theme_id: str | None = None,
    status: str | None = "open",
    priority: int | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[Question]:
    stmt = select(Question)
    if ticker:
        stmt = stmt.where(Question.ticker == ticker.upper())
    if theme_id is not None:
        stmt = stmt.where(Question.theme_id == theme_id)
    if status:
        stmt = stmt.where(Question.status == status)
    if priority is not None:
        stmt = stmt.where(Question.priority == priority)
    if category:
        stmt = stmt.where(Question.category == category)
    stmt = stmt.order_by(Question.priority.asc(), Question.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def by_ticker_rollup(
    db: AsyncSession,
    *,
    theme_id: str | None = None,
) -> list[dict]:
    p1 = func.count(case((Question.priority == 1, 1), else_=None)).label("p1_count")
    p2 = func.count(case((Question.priority == 2, 1), else_=None)).label("p2_count")
    p3 = func.count(case((Question.priority == 3, 1), else_=None)).label("p3_count")
    total = func.count(Question.id).label("open_count")

    stmt = (
        select(Question.ticker, p1, p2, p3, total)
        .where(Question.status == "open")
        .group_by(Question.ticker)
        .order_by(p1.desc(), total.desc())
    )
    if theme_id is not None:
        stmt = stmt.where(Question.theme_id == theme_id)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "ticker": ticker,
            "p1_count": int(p1c),
            "p2_count": int(p2c),
            "p3_count": int(p3c),
            "open_count": int(total),
        }
        for ticker, p1c, p2c, p3c, total in rows
    ]


# ── Retry-auto: rerun targeted-followup logic for one question ───────────────


class _RetryAnswer(BaseModel):
    answer_text: str = Field(description="Concise answer using current data.")


_RETRY_SYSTEM = """You are a senior equity research analyst answering ONE specific question about a public company. The question previously surfaced during a deep-dive but was not auto-resolved. The user has explicitly asked you to retry.

Answer concisely (3-5 sentences). Cite specific numbers, quotes, or filing line items where possible. If the data available is insufficient, say so explicitly — that is a useful answer."""


async def retry_auto_answer(
    db: AsyncSession,
    question: Question,
) -> Question:
    """On-demand: rerun a focused Sonnet call for one question, regardless
    of its auto_answerable flag. Idempotent guard: only operates on
    open questions; raises ValueError otherwise."""
    if question.status != "open":
        raise ValueError(f"question {question.id} is not open (status={question.status!r})")

    run_stmt = select(ResearchRun).where(ResearchRun.id == question.created_run_id)
    run = (await db.execute(run_stmt)).scalar_one_or_none()
    if run is None:
        raise ValueError(f"originating run {question.created_run_id} not found")

    # Pull category findings from the run's persisted state
    rs = ResearchState.from_dict(run.state) if isinstance(run.state, dict) else None
    findings_block = "(no findings on file)"
    content = ""
    if rs is not None:
        deep = rs.get_deep_dive_results()
        result = deep.get(question.category)
        if result is not None and hasattr(result, "key_findings"):
            findings_block = "\n".join(f"- {f}" for f in (result.key_findings or [])) or "(none)"
            content = (getattr(result, "content", "") or "")[:6000]

    user_msg = (
        f"Question: {question.question_text}\n\n"
        f"Originating category: {question.category}\n\n"
        f"Key findings from that category's deep-dive:\n{findings_block}\n\n"
        f"Full category analysis:\n{content}\n"
    )

    try:
        raw = await complete(
            model=SONNET,
            system=_RETRY_SYSTEM,
            user=user_msg,
            max_tokens=600,
            assistant_prefill='{"answer_text":',
        )
        parsed = _RetryAnswer.model_validate_json(raw)
        answer = parsed.answer_text
    except Exception as e:  # noqa: BLE001
        logger.exception("retry_auto failed for question %s", question.id)
        raise RuntimeError(f"Sonnet error: {type(e).__name__}") from e

    stmt = (
        update(Question)
        .where(Question.id == question.id)
        .where(Question.status == "open")
        .values(
            status="resolved_auto",
            answer_text=answer,
            answer_source="targeted_followup",
            resolved_at=datetime.now(timezone.utc),
            # resolved_run_id stays None — retries aren't tied to a run
        )
        .returning(Question.id)
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none() is None:
        raise ValueError(f"question {question.id} was concurrently resolved")
    await db.commit()
    await db.refresh(question)
    return question
