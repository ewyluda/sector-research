"""Per-call LLM telemetry: cost, attribution scope, and persistence.

Every model call goes through `graph/llm.py`, which reports its usage here.
Runners (research pipeline, workspace loop, prospectus, model seeding) set a
scope with `set_scope` so each call is attributed to a run and phase without
threading ids through call sites — asyncio tasks copy the current context, so
the parallel deep-dive calls inherit their run's scope.

Rows are written only after `main.py` registers `record` as the usage sink;
tests and scripts log without touching the database.
"""
from __future__ import annotations

import hashlib
import logging
from contextvars import ContextVar
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# USD per million tokens: (input, 5-minute cache write, cache read, output).
# From platform.claude.com/docs/en/about-claude/pricing, read 2026-09-28.
PRICES_PER_MTOK: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.00, 5.00, 0.20, 20.00),
    "claude-haiku-4-5-20251001": (1.00, 1.25, 0.10, 5.00),
    "claude-sonnet-4-6": (3.00, 3.75, 0.30, 15.00),
}

_scope: ContextVar[dict | None] = ContextVar("llm_scope", default=None)


def set_scope(run_kind: str, run_id: str, phase: str | None = None) -> None:
    """Attribute subsequent calls in this task (and tasks it spawns) to a run."""
    _scope.set({"run_kind": run_kind, "run_id": str(run_id), "phase": phase})


def set_phase(phase: str) -> None:
    """Change the phase label within the current run scope."""
    current = _scope.get()
    if current is not None:
        _scope.set({**current, "phase": phase})


def current_scope() -> dict | None:
    return _scope.get()


def prompt_version(system: str) -> str:
    """Short content hash of the system prompt — changes whenever the prompt does."""
    return hashlib.sha256(system.encode()).hexdigest()[:12]


def cost_usd(model: str, *, input_tokens: int, output_tokens: int,
             cache_read_tokens: int, cache_write_tokens: int) -> float | None:
    """Dollar cost of one call, or None for a model with no price on file.
    `input_tokens` excludes cached tokens, as the API reports it."""
    prices = PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    p_in, p_write, p_read, p_out = prices
    return (input_tokens * p_in + cache_write_tokens * p_write
            + cache_read_tokens * p_read + output_tokens * p_out) / 1_000_000


@dataclass
class CallUsage:
    kind: str
    model: str
    prompt_version: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    latency_ms: int

    @property
    def cost_usd(self) -> float | None:
        return cost_usd(self.model, input_tokens=self.input_tokens, output_tokens=self.output_tokens,
                        cache_read_tokens=self.cache_read_tokens, cache_write_tokens=self.cache_write_tokens)


async def record(usage: CallUsage) -> None:
    """Usage sink: persist one row. Never raises — telemetry must not fail a run."""
    from backend.app.db import async_session
    from backend.app.models.llm_call import LLMCall

    scope = _scope.get() or {}
    try:
        async with async_session() as db:
            db.add(LLMCall(
                run_kind=scope.get("run_kind"), run_id=scope.get("run_id"), phase=scope.get("phase"),
                kind=usage.kind, model=usage.model, prompt_version=usage.prompt_version,
                stop_reason=usage.stop_reason, input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens, cache_read_tokens=usage.cache_read_tokens,
                cache_write_tokens=usage.cache_write_tokens, latency_ms=usage.latency_ms,
                cost_usd=usage.cost_usd,
            ))
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.warning("llm_calls: failed to record %s call", usage.kind, exc_info=True)


def summarize(rows: list) -> dict:
    """Roll llm_calls rows (ORM objects or anything with the same attributes)
    up into totals, a per-phase breakdown and wall-clock span."""
    def totals(rs: list) -> dict:
        read = sum(r.cache_read_tokens for r in rs)
        prompt = sum(r.input_tokens + r.cache_read_tokens + r.cache_write_tokens for r in rs)
        return {
            "calls": len(rs),
            "cost_usd": round(sum(float(r.cost_usd or 0) for r in rs), 4),
            "input_tokens": sum(r.input_tokens for r in rs),
            "output_tokens": sum(r.output_tokens for r in rs),
            "cache_read_tokens": read,
            "cache_write_tokens": sum(r.cache_write_tokens for r in rs),
            "cache_hit_rate": round(read / prompt, 3) if prompt else None,
        }

    by_phase: dict[str, list] = {}
    for r in rows:
        by_phase.setdefault(r.phase or "unscoped", []).append(r)
    span_s = None
    if rows:
        start = min(r.created_at.timestamp() - r.latency_ms / 1000 for r in rows)
        span_s = round(max(r.created_at.timestamp() for r in rows) - start, 1)
    return {
        **totals(rows),
        "wall_clock_s": span_s,
        "unpriced_calls": sum(1 for r in rows if r.cost_usd is None),
        "by_phase": [{"phase": p, **totals(rs)} for p, rs in by_phase.items()],
    }


async def run_usage(db, run_id: str) -> dict:
    from sqlalchemy import select

    from backend.app.models.llm_call import LLMCall

    rows = (await db.execute(
        select(LLMCall).where(LLMCall.run_id == str(run_id)).order_by(LLMCall.created_at)
    )).scalars().all()
    return {"run_id": str(run_id), **summarize(list(rows))}
