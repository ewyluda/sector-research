"""GET /api/outcomes/*, POST /api/outcomes/backfill."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import fmean, median
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.app.db import async_session, unit_of_work
from backend.app.models.outcome import VerdictOutcome
from backend.app.models.outcome_schemas import (
    BackfillSummary,
    Benchmark,
    OutcomeDetail,
    OutcomeSummary,
    SignalBucket,
    SnapshotOffset,
    StatGroup,
    ThemeStat,
    VerdictStats,
    Window,
)
from backend.app.services import outcome_tracker

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])


# ── Serialization helper ──────────────────────────────────────────────────────

def _outcome_to_detail_dict(outcome: VerdictOutcome) -> dict:
    offset_order = ("1d", "1w", "1m", "3m", "6m")
    snaps = sorted(
        outcome.snapshots,
        key=lambda s: (
            offset_order.index(s.snapshot_offset)
            if s.snapshot_offset in offset_order
            else 999
        ),
    )
    return {
        "id": outcome.id,
        "source_type": outcome.source_type,
        "source_id": outcome.source_id,
        "ticker": outcome.ticker,
        "theme_id": outcome.theme_id,
        "verdict": outcome.verdict,
        "verdict_emitted_at": outcome.verdict_emitted_at,
        "entry_price_at": outcome.entry_price_at,
        "entry_price": outcome.entry_price,
        "sector_etf_ticker": outcome.sector_etf_ticker,
        "superseded_at": outcome.superseded_at,
        "closed_at": outcome.closed_at,
        "realized_ticker_return_pct": outcome.realized_ticker_return_pct,
        "realized_spy_excess_pct": outcome.realized_spy_excess_pct,
        "realized_sector_excess_pct": outcome.realized_sector_excess_pct,
        "realized_theme_basket_excess_pct": outcome.realized_theme_basket_excess_pct,
        "snapshots": [
            {
                "snapshot_offset": s.snapshot_offset,
                "snapshot_date": s.snapshot_date,
                "ticker_price": s.ticker_price,
                "spy_price": s.spy_price,
                "sector_etf_price": s.sector_etf_price,
                "theme_basket_value": s.theme_basket_value,
                "ticker_return_pct": s.ticker_return_pct,
                "spy_excess_pct": s.spy_excess_pct,
                "sector_excess_pct": s.sector_excess_pct,
                "theme_basket_excess_pct": s.theme_basket_excess_pct,
            }
            for s in snaps
        ],
        "theme_basket_constituents": outcome.theme_basket_constituents,
        "signal_snapshot": outcome.signal_snapshot,
    }


# ── Internal fetch helpers (module-level so tests can patch them) ─────────────

async def _query_outcomes(
    *,
    theme_id: str | None,
    verdict: str | None,
    source_type: str | None,
    superseded: str,
    closed: str,
    limit: int,
    offset: int,
    db,
) -> list[dict]:
    q = (
        select(VerdictOutcome)
        .options(selectinload(VerdictOutcome.snapshots))
    )
    if theme_id is not None:
        q = q.where(VerdictOutcome.theme_id == theme_id)
    if verdict is not None:
        q = q.where(VerdictOutcome.verdict == verdict)
    if source_type is not None:
        q = q.where(VerdictOutcome.source_type == source_type)
    if superseded == "true":
        q = q.where(VerdictOutcome.superseded_at.is_not(None))
    elif superseded == "false":
        q = q.where(VerdictOutcome.superseded_at.is_(None))
    if closed == "true":
        q = q.where(VerdictOutcome.closed_at.is_not(None))
    elif closed == "false":
        q = q.where(VerdictOutcome.closed_at.is_(None))
    q = q.order_by(VerdictOutcome.verdict_emitted_at.desc()).offset(offset).limit(limit)
    rows = (await db.execute(q)).scalars().all()
    return [_outcome_to_detail_dict(r) for r in rows]


async def _get_outcome_by_source(*, source_type: str, source_id: str, db) -> dict | None:
    outcome = (
        await db.execute(
            select(VerdictOutcome)
            .where(
                VerdictOutcome.source_type == source_type,
                VerdictOutcome.source_id == source_id,
            )
            .options(selectinload(VerdictOutcome.snapshots))
        )
    ).scalar_one_or_none()
    if outcome is None:
        return None
    return _outcome_to_detail_dict(outcome)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/backfill", status_code=status.HTTP_202_ACCEPTED, response_model=BackfillSummary)
async def trigger_backfill(request: Request) -> BackfillSummary:
    """One-shot backfill of verdict_outcomes from completed research + workspace runs.

    Idempotent. Safe to call multiple times. Returns 202 with summary stats.
    """
    fmp = request.app.state.fmp
    async with unit_of_work() as db:
        summary = await outcome_tracker.backfill_from_history(fmp=fmp, db=db)
    return summary


@router.get("", response_model=list[OutcomeDetail])
async def list_outcomes(
    theme_id: str | None = None,
    verdict: str | None = None,
    source_type: Literal["research_run", "workspace_run"] | None = None,
    superseded: Literal["true", "false", "all"] = "all",
    closed: Literal["true", "false", "all"] = "all",
    limit: int = 100,
    offset: int = 0,
) -> list[OutcomeDetail]:
    """List verdict outcomes with optional filters and pagination (max 500 per page)."""
    limit = max(1, min(limit, 500))
    async with async_session() as db:
        return await _query_outcomes(
            theme_id=theme_id,
            verdict=verdict,
            source_type=source_type,
            superseded=superseded,
            closed=closed,
            limit=limit,
            offset=offset,
            db=db,
        )


@router.get("/by-source/{source_type}/{source_id}", response_model=OutcomeDetail)
async def get_outcome_by_source(source_type: str, source_id: str) -> OutcomeDetail:
    """Fetch a single outcome by its originating run (source_type + source_id)."""
    if source_type not in ("research_run", "workspace_run"):
        raise HTTPException(status_code=400, detail="invalid source_type")
    async with async_session() as db:
        payload = await _get_outcome_by_source(
            source_type=source_type, source_id=source_id, db=db
        )
    if payload is None:
        raise HTTPException(status_code=404, detail="outcome not found")
    return payload


# ── Summary helpers ───────────────────────────────────────────────────────────

def _excess_attr(benchmark: Benchmark) -> str:
    return {
        "spy": "spy_excess_pct",
        "sector": "sector_excess_pct",
        "theme_basket": "theme_basket_excess_pct",
    }[benchmark]


def _window_cutoff(window: Window) -> datetime | None:
    if window == "all":
        return None
    days = {"30d": 30, "90d": 90, "1y": 365}[window]
    return datetime.now(timezone.utc) - timedelta(days=days)


def _stats_for(rows: list[tuple[float | None, float | None]]) -> StatGroup:
    """rows: list of (ticker_return_pct, excess_pct)."""
    n = len(rows)
    if n == 0:
        return StatGroup(n=0, mean_return_pct=None, mean_excess_pct=None,
                         win_rate=None, median_excess_pct=None)
    returns = [r for (r, _) in rows if r is not None]
    excess = [x for (_, x) in rows if x is not None]
    win_rate = (sum(1 for x in excess if x > 0) / len(excess)) if excess else None
    return StatGroup(
        n=n,
        mean_return_pct=fmean(returns) if returns else None,
        mean_excess_pct=fmean(excess) if excess else None,
        win_rate=win_rate,
        median_excess_pct=median(excess) if excess else None,
    )


def _quartile_buckets(values: list[tuple[float | None, float]]) -> list[SignalBucket]:
    """values: list of (signal_value, excess_pct). Buckets by quartile of signal_value over non-null."""
    non_null = [(s, e) for (s, e) in values if s is not None]
    null_n = len(values) - len(non_null)

    if not non_null:
        return [SignalBucket(bucket="null", n=null_n, mean_excess_pct=None, win_rate=None)]

    sorted_signals = sorted(s for s, _ in non_null)

    def q(p: float) -> float:
        i = int(p * (len(sorted_signals) - 1))
        return sorted_signals[i]

    q1, q2, q3 = q(0.25), q(0.5), q(0.75)

    bins: dict[str, list[float]] = defaultdict(list)
    for s, e in non_null:
        if s <= q1:
            bins["0-25th"].append(e)
        elif s <= q2:
            bins["25-50th"].append(e)
        elif s <= q3:
            bins["50-75th"].append(e)
        else:
            bins["75-100th"].append(e)

    buckets: list[SignalBucket] = []
    for key in ("0-25th", "25-50th", "50-75th", "75-100th"):
        es = bins.get(key, [])
        buckets.append(SignalBucket(
            bucket=key,
            n=len(es),
            mean_excess_pct=fmean(es) if es else None,
            win_rate=(sum(1 for x in es if x > 0) / len(es)) if es else None,
        ))
    buckets.append(SignalBucket(bucket="null", n=null_n, mean_excess_pct=None, win_rate=None))
    return buckets


async def _compute_summary(
    *,
    theme_id: str | None,
    window: Window,
    snapshot_offset: SnapshotOffset,
    benchmark: Benchmark,
    source_type: str,
    db,
) -> dict:
    from backend.app.models.outcome import VerdictReturnSnapshot
    from backend.app.models.theme import Theme

    cutoff = _window_cutoff(window)
    excess_attr = _excess_attr(benchmark)

    q = (
        select(VerdictOutcome, VerdictReturnSnapshot)
        .join(
            VerdictReturnSnapshot,
            (VerdictReturnSnapshot.outcome_id == VerdictOutcome.id)
            & (VerdictReturnSnapshot.snapshot_offset == snapshot_offset),
            isouter=True,
        )
    )
    if cutoff is not None:
        q = q.where(VerdictOutcome.verdict_emitted_at >= cutoff)
    if theme_id is not None:
        q = q.where(VerdictOutcome.theme_id == theme_id)
    if source_type != "all":
        q = q.where(VerdictOutcome.source_type == source_type)

    rows = (await db.execute(q)).all()

    overall_pairs: list[tuple[float | None, float | None]] = []
    by_verdict: dict[str, list[tuple[float | None, float | None]]] = defaultdict(list)
    by_theme: dict[str | None, list[tuple[float | None, float | None]]] = defaultdict(list)
    signals_data: dict[str, list[tuple[float | None, float]]] = defaultdict(list)

    for outcome, snap in rows:
        if snap is None:
            t_ret, x = None, None
        else:
            t_ret = float(snap.ticker_return_pct) if snap.ticker_return_pct is not None else None
            x_val = getattr(snap, excess_attr)
            x = float(x_val) if x_val is not None else None

        overall_pairs.append((t_ret, x))
        by_verdict[outcome.verdict].append((t_ret, x))
        by_theme[outcome.theme_id].append((t_ret, x))

        # Quartile buckets — only when we have an excess number to anchor to
        if x is not None and outcome.signal_snapshot:
            sigs = (outcome.signal_snapshot.get("signals_row") or {})
            for sig_name, sig_val in sigs.items():
                sval = sig_val if isinstance(sig_val, (int, float)) else None
                signals_data[sig_name].append((sval, x))

    # Theme name lookup
    distinct_ids = [tid for tid in by_theme.keys() if tid]
    theme_names: dict[str | None, str | None] = {None: None}
    if distinct_ids:
        themes = (await db.execute(
            select(Theme.id, Theme.name).where(Theme.id.in_(distinct_ids))
        )).all()
        for tid, name in themes:
            theme_names[tid] = name

    # Build VerdictStats via setattr (avoids 'pass' keyword collision)
    verdict_stats = VerdictStats()
    for v, pairs in by_verdict.items():
        field = "passed" if v == "pass" else v
        if hasattr(verdict_stats, field):
            setattr(verdict_stats, field, _stats_for(pairs))

    by_theme_list = [
        ThemeStat(theme_id=tid, theme_name=theme_names.get(tid), stats=_stats_for(pairs))
        for tid, pairs in by_theme.items()
    ]

    by_signal_bucket = {
        sig: _quartile_buckets(pairs) for sig, pairs in signals_data.items()
    }

    return {
        "window": window,
        "snapshot_offset": snapshot_offset,
        "benchmark": benchmark,
        "source_type": source_type,
        "overall": _stats_for(overall_pairs).model_dump(),
        "by_verdict": verdict_stats.model_dump(),
        "by_theme": [ts.model_dump() for ts in by_theme_list],
        "by_signal_bucket": {k: [b.model_dump() for b in v] for k, v in by_signal_bucket.items()},
    }


@router.get("/summary", response_model=OutcomeSummary)
async def get_summary(
    theme_id: str | None = None,
    window: Window = "90d",
    snapshot_offset: SnapshotOffset = "3m",
    benchmark: Benchmark = "spy",
    source_type: Literal["research_run", "workspace_run", "all"] = "all",
) -> dict:
    """Aggregate verdict/theme/signal-bucket rollups over the outcome set."""
    async with async_session() as db:
        return await _compute_summary(
            theme_id=theme_id,
            window=window,
            snapshot_offset=snapshot_offset,
            benchmark=benchmark,
            source_type=source_type,
            db=db,
        )
