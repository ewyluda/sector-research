"""Trade-journal persistence + FMP price auto-fill.

Write functions are COMMIT-FREE — the caller owns the session and must
commit (same contract as peer_sets.py; API routes commit). FMP benchmark
fetches are best-effort: SPY gaps degrade to NULL columns, never raise.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.app.models.journal_trade import JournalTrade
from backend.app.models.outcome import VerdictOutcome

log = logging.getLogger(__name__)

PRICE_LOOKBACK_DAYS = 7  # covers weekends + holiday clusters


class PriceUnavailableError(Exception):
    """No FMP price for the requested date and no manual price supplied."""


async def adjusted_close_on_or_before(
    fmp, ticker: str, target: date
) -> tuple[Decimal, date] | None:
    """Newest dividend-adjusted close at or before `target` within the
    lookback window. None on FMP failure or no usable rows — callers fall
    back to manual entry / NULL benchmark. The returned date may be earlier
    than requested (weekend/holiday) — surface it so the user sees which
    session priced the fill."""
    from_date = (target - timedelta(days=PRICE_LOOKBACK_DAYS)).isoformat()
    try:
        rows, _ = await fmp.get_historical_price_adjusted(
            ticker, from_date, target.isoformat()
        )
    except Exception:  # noqa: BLE001 — best-effort by contract
        log.warning("adjusted-close lookup failed for %s @ %s", ticker, target)
        return None
    best: tuple[Decimal, date] | None = None
    for row in rows or []:
        raw_date, raw_px = row.get("date"), row.get("adjClose")
        if not raw_date or raw_px is None:
            continue
        try:
            d = date.fromisoformat(str(raw_date)[:10])
            px = Decimal(str(raw_px))
        except (ValueError, InvalidOperation):
            continue
        if d <= target and (best is None or d > best[1]):
            best = (px, d)
    return best


async def create_trade(
    db: AsyncSession,
    fmp,
    *,
    ticker: str,
    entry_date: date,
    entry_price: Decimal | None,
    quantity: Decimal | None,
    direction: str,
    outcome_id: str | None,
    entry_rationale: str | None,
) -> JournalTrade:
    """Add (not commit) a new open trade. Auto-fills entry price when not
    supplied; raises PriceUnavailableError when neither manual nor FMP
    price is available. SPY entry is best-effort NULL-on-failure."""
    if entry_price is not None:
        price, source = entry_price, "manual"
    else:
        found = await adjusted_close_on_or_before(fmp, ticker, entry_date)
        if found is None:
            raise PriceUnavailableError(
                f"no adjusted close for {ticker} on or before {entry_date}"
            )
        price, source = found[0], "fmp_eod_adjusted"
    spy = await adjusted_close_on_or_before(fmp, "SPY", entry_date)
    trade = JournalTrade(
        ticker=ticker,
        direction=direction,
        entry_date=entry_date,
        entry_price=price,
        entry_price_source=source,
        quantity=quantity,
        outcome_id=outcome_id,
        entry_rationale=entry_rationale,
        spy_entry_price=spy[0] if spy else None,
    )
    db.add(trade)
    return trade


_EXIT_FIELDS = ("exit_date", "exit_price", "exit_price_source",
                "exit_reason", "exit_note", "spy_exit_price")


async def update_trade(
    db: AsyncSession, fmp, trade: JournalTrade, changes: dict
) -> JournalTrade:
    """Apply a PATCH (mutates, does not commit). `changes` must come from
    model_dump(exclude_unset=True) so absent-key ≠ explicit-null.

    Closing = exit_date arrives non-null (auto-fills exit_price when not
    supplied). Reopening = explicit exit_date=None (clears every exit
    field). Raises ValueError on invariant violations (exit before entry,
    exit fields on an open trade), PriceUnavailableError when a close has
    no resolvable price."""
    if "entry_price" in changes and changes["entry_price"] is not None:
        trade.entry_price = changes["entry_price"]
        trade.entry_price_source = "manual"
    for field in ("entry_date", "quantity", "direction", "outcome_id", "entry_rationale"):
        if field in changes:
            setattr(trade, field, changes[field])

    if "exit_date" in changes and changes["exit_date"] is None:
        for field in _EXIT_FIELDS:
            setattr(trade, field, None)
        return trade

    if changes.get("exit_date") is not None:
        trade.exit_date = changes["exit_date"]

    if trade.exit_date is None:
        bad = [k for k in ("exit_price", "exit_reason", "exit_note")
               if changes.get(k) is not None]
        if bad:
            raise ValueError(f"{bad[0]} requires exit_date")
        return trade

    if trade.exit_date < trade.entry_date:
        raise ValueError("exit_date is before entry_date")

    if changes.get("exit_price") is not None:
        trade.exit_price = changes["exit_price"]
        trade.exit_price_source = "manual"
    elif trade.exit_price is None:
        found = await adjusted_close_on_or_before(fmp, trade.ticker, trade.exit_date)
        if found is None:
            raise PriceUnavailableError(
                f"no adjusted close for {trade.ticker} on or before {trade.exit_date}"
            )
        trade.exit_price = found[0]
        trade.exit_price_source = "fmp_eod_adjusted"

    if "exit_reason" in changes:
        trade.exit_reason = changes["exit_reason"]
    if "exit_note" in changes:
        trade.exit_note = changes["exit_note"]

    if trade.spy_exit_price is None:
        spy = await adjusted_close_on_or_before(fmp, "SPY", trade.exit_date)
        trade.spy_exit_price = spy[0] if spy else None
    return trade


async def delete_trade(db: AsyncSession, trade: JournalTrade) -> None:
    """Mark for deletion (does not commit — caller owns the session)."""
    await db.delete(trade)


def _eager_options():
    return selectinload(JournalTrade.outcome).selectinload(VerdictOutcome.snapshots)


async def get_trade(db: AsyncSession, trade_id: str) -> JournalTrade | None:
    stmt = (
        select(JournalTrade)
        .options(_eager_options())
        .where(JournalTrade.id == trade_id)
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def list_trades(
    db: AsyncSession,
    *,
    status: str = "all",
    ticker: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[JournalTrade]:
    stmt = (
        select(JournalTrade)
        .options(_eager_options())
        .order_by(JournalTrade.entry_date.desc(), JournalTrade.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    if status == "open":
        stmt = stmt.where(JournalTrade.exit_date.is_(None))
    elif status == "closed":
        stmt = stmt.where(JournalTrade.exit_date.is_not(None))
    if ticker:
        stmt = stmt.where(JournalTrade.ticker == ticker.upper())
    return list((await db.execute(stmt)).scalars().all())


async def trade_counts(db: AsyncSession) -> tuple[int, int]:
    """(open_count, closed_count)."""
    open_count = (
        await db.execute(
            select(func.count()).select_from(JournalTrade)
            .where(JournalTrade.exit_date.is_(None))
        )
    ).scalar_one()
    closed_count = (
        await db.execute(
            select(func.count()).select_from(JournalTrade)
            .where(JournalTrade.exit_date.is_not(None))
        )
    ).scalar_one()
    return open_count, closed_count


async def link_candidates(
    db: AsyncSession, ticker: str, limit: int = 10
) -> list[VerdictOutcome]:
    """Recent non-superseded outcomes for the ticker — the form's picker.
    Lives here because GET /api/outcomes has no ticker filter."""
    stmt = (
        select(VerdictOutcome)
        .where(
            VerdictOutcome.ticker == ticker.upper(),
            VerdictOutcome.superseded_at.is_(None),
        )
        .order_by(VerdictOutcome.verdict_emitted_at.desc())
        .limit(limit)
    )
    return list((await db.execute(stmt)).scalars().all())


async def coverage_counts(db: AsyncSession) -> tuple[int, int]:
    """(outcomes_traded, outcomes_total) over non-superseded outcomes."""
    total = (
        await db.execute(
            select(func.count()).select_from(VerdictOutcome)
            .where(VerdictOutcome.superseded_at.is_(None))
        )
    ).scalar_one()
    traded = (
        await db.execute(
            select(func.count(func.distinct(JournalTrade.outcome_id)))
            .select_from(JournalTrade)
            .join(VerdictOutcome, VerdictOutcome.id == JournalTrade.outcome_id)
            .where(VerdictOutcome.superseded_at.is_(None))
        )
    ).scalar_one()
    return traded, total
