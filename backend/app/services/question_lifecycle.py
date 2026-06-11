"""Question-persistence helpers extracted from nodes.py (M2.2).

This module holds the async DB helpers that manage the open-question log
across pipeline runs: persisting newly-extracted questions, fetching prior
open questions for cross-run resurfacing, rendering them into prompt slots,
and applying resurfaced resolutions back to the DB.

Extracted from ``backend.app.graph.nodes`` as part of the M2.2 campaign;
all function bodies are byte-identical to their origin.

Symbols exported:
  _persist_extracted_questions
  _fetch_prior_open_questions
  _render_prior_questions_slot
  _apply_resurfaced_resolutions
  _render_questions_resolved
"""

from __future__ import annotations

import logging

from backend.app.graph.state import ResearchState

logger = logging.getLogger(__name__)


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
