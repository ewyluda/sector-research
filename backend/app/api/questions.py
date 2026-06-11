"""Questions API — Tier 1.2 question log + targeted second-pass.

CRITICAL: do NOT add `from __future__ import annotations` to this module.
FastAPI 0.115 + Python 3.12 evaluates `-> None` returns as the string
"None" and trips an internal assertion when the future import is
present. Same constraint applied to api/status.py and api/read_through.py.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.question import Question
from backend.app.services.questions import (
    by_ticker_rollup,
    list_questions,
    retry_auto_answer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


# ── Response models ──────────────────────────────────────────────────────────


class QuestionResponse(BaseModel):
    id: str
    ticker: str
    theme_id: Optional[str]
    category: str
    question_text: str
    priority: int
    auto_answerable: bool
    status: str
    answer_text: Optional[str]
    answer_source: Optional[str]
    created_run_id: str
    resolved_run_id: Optional[str]
    created_at: str
    resolved_at: Optional[str]
    dismissed_at: Optional[str]
    dismiss_note: Optional[str]
    snoozed_until: Optional[str]


def _serialize(q: Question) -> QuestionResponse:
    return QuestionResponse(
        id=str(q.id),
        ticker=q.ticker,
        theme_id=str(q.theme_id) if q.theme_id else None,
        category=q.category,
        question_text=q.question_text,
        priority=q.priority,
        auto_answerable=q.auto_answerable,
        status=q.status,
        answer_text=q.answer_text,
        answer_source=q.answer_source,
        created_run_id=str(q.created_run_id),
        resolved_run_id=str(q.resolved_run_id) if q.resolved_run_id else None,
        created_at=q.created_at.isoformat() if q.created_at else "",
        resolved_at=q.resolved_at.isoformat() if q.resolved_at else None,
        dismissed_at=q.dismissed_at.isoformat() if q.dismissed_at else None,
        dismiss_note=q.dismiss_note,
        snoozed_until=q.snoozed_until.isoformat() if q.snoozed_until else None,
    )


class QuestionListResponse(BaseModel):
    questions: list[QuestionResponse]


class TickerRollupRow(BaseModel):
    ticker: str
    p1_count: int
    p2_count: int
    p3_count: int
    open_count: int


class TickerRollupResponse(BaseModel):
    tickers: list[TickerRollupRow]


class DismissBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


class ResolveBody(BaseModel):
    answer_text: str = Field(min_length=1, max_length=10000)


class BulkFilter(BaseModel):
    ticker: Optional[str] = None
    theme_id: Optional[str] = None
    priority: Optional[int] = None
    category: Optional[str] = None
    status: Literal["open", "dismissed", "resolved_auto", "resolved_inline", "resolved_manual"] = "open"


class BulkBody(BaseModel):
    ids: Optional[list[str]] = None
    filter: Optional[BulkFilter] = None
    action: Literal["dismiss", "resolve", "snooze"]
    note: Optional[str] = Field(default=None, max_length=2000)
    answer_text: Optional[str] = Field(default=None, max_length=10000)
    snooze_days: int = Field(default=7, ge=1, le=90)


def _normalize_status_filter(status: Optional[str]) -> Optional[str]:
    if status == "all":
        return None
    return status or "open"


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=QuestionListResponse)
async def list_questions_endpoint(
    ticker: Optional[str] = None,
    theme_id: Optional[str] = None,
    status: Optional[str] = "open",
    priority: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> QuestionListResponse:
    rows = await list_questions(
        db,
        ticker=ticker,
        theme_id=theme_id,
        status=_normalize_status_filter(status),
        priority=priority,
        category=category,
        limit=min(limit, 500),
    )
    return QuestionListResponse(questions=[_serialize(r) for r in rows])


@router.get("/by-ticker", response_model=TickerRollupResponse)
async def by_ticker_endpoint(
    theme_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> TickerRollupResponse:
    rows = await by_ticker_rollup(db, theme_id=theme_id)
    return TickerRollupResponse(tickers=[TickerRollupRow(**r) for r in rows])


@router.post("/bulk")
async def bulk_endpoint(
    body: BulkBody,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Apply dismiss/resolve/snooze to a set of questions (spec §7).

    Exactly one of `ids` / `filter` must be provided. `resolve` requires
    answer_text. State transitions mirror the per-row endpoints; in ids
    mode only open questions are mutated (the bulk analogue of the
    per-row 409 on non-open rows).
    """
    if (body.ids is None) == (body.filter is None):
        raise HTTPException(status_code=422, detail="provide exactly one of ids|filter")
    if body.action == "resolve" and not body.answer_text:
        raise HTTPException(status_code=422, detail="resolve requires answer_text")

    q = select(Question)
    if body.ids is not None:
        q = q.where(Question.id.in_(body.ids)).where(Question.status == "open")
    else:
        f = body.filter
        q = q.where(Question.status == f.status)
        if f.ticker:
            q = q.where(Question.ticker == f.ticker.upper())
        if f.theme_id:
            q = q.where(Question.theme_id == f.theme_id)
        if f.priority is not None:
            q = q.where(Question.priority == f.priority)
        if f.category:
            q = q.where(Question.category == f.category)

    rows = list((await db.execute(q)).scalars())
    now = datetime.now(timezone.utc)
    for row in rows:
        if body.action == "dismiss":
            row.status = "dismissed"
            row.dismissed_at = now
            row.dismiss_note = body.note
        elif body.action == "resolve":
            row.status = "resolved_manual"
            row.answer_text = body.answer_text
            row.answer_source = "manual"
            row.resolved_at = now
        else:  # snooze
            row.snoozed_until = now + timedelta(days=body.snooze_days)
    await db.commit()
    return {"affected": len(rows)}


@router.post("/{question_id}/dismiss", response_model=QuestionResponse)
async def dismiss_endpoint(
    question_id: str,
    body: DismissBody,
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "question not found")
    if q.status != "open":
        raise HTTPException(409, f"question is {q.status}, cannot dismiss")

    stmt = (
        update(Question)
        .where(Question.id == question_id)
        .where(Question.status == "open")
        .values(
            status="dismissed",
            dismissed_at=datetime.now(timezone.utc),
            dismiss_note=body.note,
        )
        .returning(Question.id)
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(409, "question was concurrently modified")
    await db.commit()
    await db.refresh(q)
    return _serialize(q)


@router.post("/{question_id}/resolve", response_model=QuestionResponse)
async def resolve_endpoint(
    question_id: str,
    body: ResolveBody,
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "question not found")
    if q.status != "open":
        raise HTTPException(409, f"question is {q.status}, cannot resolve")

    stmt = (
        update(Question)
        .where(Question.id == question_id)
        .where(Question.status == "open")
        .values(
            status="resolved_manual",
            answer_text=body.answer_text,
            answer_source="manual",
            resolved_at=datetime.now(timezone.utc),
        )
        .returning(Question.id)
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(409, "question was concurrently modified")
    await db.commit()
    await db.refresh(q)
    return _serialize(q)


@router.post("/{question_id}/retry-auto", response_model=QuestionResponse)
async def retry_auto_endpoint(
    question_id: str,
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "question not found")
    try:
        updated = await retry_auto_answer(db, q)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        logger.exception("retry-auto Sonnet failure for %s", question_id)
        raise HTTPException(502, str(e))
    return _serialize(updated)
