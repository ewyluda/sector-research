"""Trade-journal CRUD + decision-vs-outcome summary.

Routes own sessions (unit_of_work for writes) and commit; the journal
service is commit-free. FMP failures degrade per the spec's error-handling
section — no 500s from benchmark gaps.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select

from backend.app.db import async_session, unit_of_work
from backend.app.models.journal_schemas import (
    JournalSummary,
    LinkCandidate,
    PricePreview,
    TradeCreate,
    TradeDetail,
    TradeStatusFilter,
    TradeUpdate,
)
from backend.app.models.journal_trade import JournalTrade
from backend.app.models.outcome import VerdictOutcome
from backend.app.models.ticker import Ticker, TickerPath
from backend.app.services import journal
from backend.app.services import journal_comparison as comparison

router = APIRouter(prefix="/api/journal", tags=["journal"])


# ── Serialization helpers ─────────────────────────────────────────────────────

def _snap_dicts(outcome: VerdictOutcome) -> list[dict]:
    return [
        {
            "snapshot_offset": s.snapshot_offset,
            "ticker_return_pct": s.ticker_return_pct,
            "spy_excess_pct": s.spy_excess_pct,
        }
        for s in (outcome.snapshots or [])
    ]


def _realized(trade: JournalTrade) -> comparison.TradeReturns:
    return comparison.trade_returns(
        direction=trade.direction,
        entry_date=trade.entry_date,
        entry_price=trade.entry_price,
        exit_date=trade.exit_date,
        exit_price=trade.exit_price,
        spy_entry_price=trade.spy_entry_price,
        spy_exit_price=trade.spy_exit_price,
    )


def _serialize(
    trade: JournalTrade,
    outcome: VerdictOutcome | None,
    unrealized: comparison.TradeReturns | None = None,
) -> dict:
    """Build the TradeDetail payload. `outcome` is passed explicitly — never
    touch trade.outcome here unless the caller eager-loaded it (lazy loads
    explode in async context)."""
    closed = trade.exit_date is not None
    returns = None
    comp = None
    if closed:
        r = _realized(trade)
        returns = {
            "return_pct": r.return_pct,
            "spy_excess_pct": r.spy_excess_pct,
            "holding_days": r.holding_days,
            "unrealized": False,
        }
        if outcome is not None:
            c = comparison.decision_vs_outcome(r, _snap_dicts(outcome))
            if c is not None:
                comp = {
                    "offset": c.offset,
                    "trade_return_pct": c.trade_return_pct,
                    "trade_spy_excess_pct": c.trade_spy_excess_pct,
                    "paper_return_pct": c.paper_return_pct,
                    "paper_spy_excess_pct": c.paper_spy_excess_pct,
                    "execution_delta_pct": c.execution_delta_pct,
                }
    elif unrealized is not None:
        returns = {
            "return_pct": unrealized.return_pct,
            "spy_excess_pct": unrealized.spy_excess_pct,
            "holding_days": unrealized.holding_days,
            "unrealized": True,
        }

    linked = None
    if outcome is not None:
        linked = {
            "id": outcome.id,
            "verdict": outcome.verdict,
            "source_type": outcome.source_type,
            "source_id": outcome.source_id,
            "theme_id": outcome.theme_id,
            "verdict_emitted_at": outcome.verdict_emitted_at,
            "entry_price_at": outcome.entry_price_at,
            "realized_spy_excess_pct": outcome.realized_spy_excess_pct,
        }

    return {
        "id": trade.id,
        "ticker": trade.ticker,
        "direction": trade.direction,
        "status": "closed" if closed else "open",
        "entry_date": trade.entry_date,
        "entry_price": trade.entry_price,
        "entry_price_source": trade.entry_price_source,
        "exit_date": trade.exit_date,
        "exit_price": trade.exit_price,
        "exit_price_source": trade.exit_price_source,
        "quantity": trade.quantity,
        "spy_entry_price": trade.spy_entry_price,
        "spy_exit_price": trade.spy_exit_price,
        "outcome_id": trade.outcome_id,
        "entry_rationale": trade.entry_rationale,
        "exit_reason": trade.exit_reason,
        "exit_note": trade.exit_note,
        "returns": returns,
        "linked_outcome": linked,
        "comparison": comp,
        "created_at": trade.created_at,
    }


async def _unrealized(fmp, trade: JournalTrade) -> comparison.TradeReturns:
    """Open-trade mark from a live quote — best-effort. NOTE: the quote is
    unadjusted while entry may be adjClose; accepted approximation for open
    trades (spec: error handling)."""
    price = None
    try:
        q, _ = await fmp.get_quote(trade.ticker)
        if isinstance(q, dict) and q.get("price") is not None:
            price = Decimal(str(q["price"]))
    except Exception:  # noqa: BLE001 — degrade to no-mark
        price = None
    if price is None:
        return comparison.TradeReturns(
            None, None, (date.today() - trade.entry_date).days
        )
    return comparison.trade_returns(
        direction=trade.direction,
        entry_date=trade.entry_date,
        entry_price=trade.entry_price,
        exit_date=date.today(),
        exit_price=price,
        spy_entry_price=None,
        spy_exit_price=None,
    )


# ── Static routes (declared before /trades/{trade_id} by convention) ─────────

@router.get("/summary", response_model=JournalSummary)
async def get_summary() -> JournalSummary:
    async with async_session() as db:
        closed = await journal.list_trades(db, status="closed", limit=5000)
        open_count, closed_count = await journal.trade_counts(db)
        traded, total = await journal.coverage_counts(db)

    stats: list[comparison.ClosedTradeStat] = []
    for t in closed:
        r = _realized(t)
        if r.return_pct is None or r.holding_days is None:
            continue
        delta = None
        if t.outcome is not None:
            c = comparison.decision_vs_outcome(r, _snap_dicts(t.outcome))
            if c is not None:
                delta = c.execution_delta_pct
        stats.append(
            comparison.ClosedTradeStat(
                return_pct=r.return_pct,
                spy_excess_pct=r.spy_excess_pct,
                holding_days=r.holding_days,
                exit_reason=t.exit_reason,
                execution_delta_pct=delta,
            )
        )
    rollup = comparison.summarize(stats)
    return JournalSummary(
        trade_count=open_count + closed_count,
        open_count=open_count,
        coverage={"outcomes_traded": traded, "outcomes_total": total},
        **{**rollup, "closed_count": closed_count},
    )


@router.get("/price-preview", response_model=PricePreview)
async def price_preview(
    request: Request,
    ticker: Ticker = Depends(TickerPath),
    on: date = Query(alias="date"),
) -> PricePreview:
    fmp = request.app.state.fmp
    found = await journal.adjusted_close_on_or_before(fmp, ticker, on)
    if found is None:
        raise HTTPException(status_code=404, detail="no price available for that date")
    price, price_date = found
    return PricePreview(price=price, price_date=price_date, source="fmp_eod_adjusted")


@router.get("/link-candidates", response_model=list[LinkCandidate])
async def get_link_candidates(ticker: Ticker = Depends(TickerPath)) -> list[LinkCandidate]:
    async with async_session() as db:
        rows = await journal.link_candidates(db, ticker)
    return [
        LinkCandidate(
            id=o.id,
            verdict=o.verdict,
            source_type=o.source_type,
            theme_id=o.theme_id,
            verdict_emitted_at=o.verdict_emitted_at,
            entry_price_at=o.entry_price_at,
        )
        for o in rows
    ]


# ── Trade CRUD ────────────────────────────────────────────────────────────────

@router.post("/trades", status_code=201, response_model=TradeDetail)
async def create_trade(body: TradeCreate, request: Request) -> TradeDetail:
    fmp = request.app.state.fmp
    focus = TickerPath(body.ticker)
    async with unit_of_work() as db:
        if body.outcome_id is not None:
            exists = (
                await db.execute(
                    select(VerdictOutcome.id).where(VerdictOutcome.id == body.outcome_id)
                )
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=404, detail="outcome not found")
        try:
            trade = await journal.create_trade(
                db,
                fmp,
                ticker=focus,
                entry_date=body.entry_date,
                entry_price=body.entry_price,
                quantity=body.quantity,
                direction=body.direction,
                outcome_id=body.outcome_id,
                entry_rationale=body.entry_rationale,
            )
        except journal.PriceUnavailableError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await db.commit()
        full = await journal.get_trade(db, trade.id)
    final = full or trade
    return _serialize(final, final.outcome if full else None)


@router.patch("/trades/{trade_id}", response_model=TradeDetail)
async def patch_trade(trade_id: str, body: TradeUpdate, request: Request) -> TradeDetail:
    fmp = request.app.state.fmp
    changes = body.model_dump(exclude_unset=True)
    async with unit_of_work() as db:
        trade = await journal.get_trade(db, trade_id)
        if trade is None:
            raise HTTPException(status_code=404, detail="trade not found")
        if changes.get("outcome_id") is not None:
            exists = (
                await db.execute(
                    select(VerdictOutcome.id).where(
                        VerdictOutcome.id == changes["outcome_id"]
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                raise HTTPException(status_code=404, detail="outcome not found")
        try:
            trade = await journal.update_trade(db, fmp, trade, changes)
        except journal.PriceUnavailableError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await db.commit()
        full = await journal.get_trade(db, trade.id)
    final = full or trade
    return _serialize(final, final.outcome if full else None)


@router.delete("/trades/{trade_id}", status_code=204)
async def delete_trade(trade_id: str):
    async with unit_of_work() as db:
        trade = await journal.get_trade(db, trade_id)
        if trade is None:
            raise HTTPException(status_code=404, detail="trade not found")
        await journal.delete_trade(db, trade)


@router.get("/trades", response_model=list[TradeDetail])
async def list_trades(
    request: Request,
    status: TradeStatusFilter = "all",
    ticker: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[TradeDetail]:
    fmp = request.app.state.fmp
    limit = max(1, min(limit, 500))
    focus = TickerPath(ticker) if ticker else None
    async with async_session() as db:
        trades = await journal.list_trades(
            db, status=status, ticker=focus, limit=limit, offset=offset
        )
    out = []
    for t in trades:
        unrealized = None
        if t.exit_date is None:
            unrealized = await _unrealized(fmp, t)
        out.append(_serialize(t, t.outcome, unrealized=unrealized))
    return out
