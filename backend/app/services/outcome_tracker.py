"""Verdict outcome tracking — alpha feedback loop.

See docs/superpowers/specs/2026-05-10-verdict-outcome-tracking-design.md.
"""
from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.models.outcome import (
    SectorEtfMapping,
    VerdictOutcome,
    VerdictReturnSnapshot,
)
from backend.app.models.outcome_schemas import (
    BackfillSummary,
    EntryConstituent,
    EntryPriceBundle,
    RefreshSummary,
)

logger = logging.getLogger(__name__)


SNAPSHOT_OFFSETS: list[tuple[str, int]] = [
    ("1d", 1),
    ("1w", 7),
    ("1m", 30),
    ("3m", 90),
    ("6m", 180),
]

ENTRY_PRICE_LOOKAHEAD_DAYS = 7
SUPPORTED_SOURCE_TYPES = ("research_run", "workspace_run")


def calendar_target(entry_price_at: date, offset_key: str) -> date:
    """Return the calendar target date for a snapshot offset. Snapshot uses first trading day >= target."""
    for key, days in SNAPSHOT_OFFSETS:
        if key == offset_key:
            return entry_price_at + timedelta(days=days)
    raise ValueError(f"unknown offset {offset_key!r}")


def all_offset_keys() -> list[str]:
    return [k for (k, _) in SNAPSHOT_OFFSETS]


async def _resolve_entry_prices(
    *,
    ticker: str,
    verdict_emitted_at: datetime,
    theme_seed_tickers: list[str] | None,
    sector_etf_ticker: str | None,
    fmp: FMPClient,
) -> EntryPriceBundle:
    """Resolve entry-anchored prices for outcome creation.

    Entry day = first trading day STRICTLY AFTER verdict_emitted_at's calendar date.
    Fetches close price for ticker + SPY + (optional) sector ETF + theme constituents,
    all anchored to the same entry day for fair comparison.

    Uses FMPClient.get_historical_price_adjusted(ticker, from_date: str, to_date: str)
    which returns tuple[list[dict], Citation] with rows {date: str, close: float, ...}
    where close is split + dividend adjusted.
    """
    emitted_date = verdict_emitted_at.astimezone(timezone.utc).date()
    range_start = emitted_date + timedelta(days=1)
    range_end = emitted_date + timedelta(days=ENTRY_PRICE_LOOKAHEAD_DAYS)

    ticker_rows, _ = await fmp.get_historical_price_adjusted(
        ticker, range_start.isoformat(), range_end.isoformat()
    )
    if not ticker_rows:
        raise LookupError(
            f"no FMP price for {ticker} between {range_start} and {range_end}"
        )
    first = sorted(ticker_rows, key=lambda r: r["date"])[0]
    entry_day: date = date.fromisoformat(first["date"])
    ticker_price = Decimal(str(first["close"]))

    async def _close_on(symbol: str, target_day: date) -> Decimal | None:
        rows, _ = await fmp.get_historical_price_adjusted(
            symbol, target_day.isoformat(), target_day.isoformat()
        )
        if not rows:
            return None
        for r in rows:
            if r["date"] == target_day.isoformat():
                return Decimal(str(r["close"]))
        return None

    spy_price = await _close_on("SPY", entry_day)

    sector_price: Decimal | None = None
    if sector_etf_ticker:
        sector_price = await _close_on(sector_etf_ticker, entry_day)

    constituents: list[EntryConstituent] = []
    if theme_seed_tickers:
        for t in theme_seed_tickers:
            px = await _close_on(t, entry_day)
            if px is not None:
                constituents.append(EntryConstituent(ticker=t, entry_price=px))

    return EntryPriceBundle(
        entry_price_at=entry_day,
        ticker_price=ticker_price,
        spy_price=spy_price,
        sector_etf_ticker=sector_etf_ticker,
        sector_etf_price=sector_price,
        theme_basket_constituents=constituents,
    )


def compute_basket_value(
    constituents: list[dict],
    current_prices: dict[str, Decimal],
) -> Decimal | None:
    """Equal-weighted arithmetic basket value.

    constituents: list of {"ticker": str, "entry_price": Decimal}.
    Returns mean(current/entry) * 100, omitting constituents with no current price.
    Returns None when no constituent has a current price.
    """
    ratios: list[float] = []
    for c in constituents:
        symbol = c["ticker"]
        entry = c["entry_price"]
        if isinstance(entry, (str, int, float)):
            entry = Decimal(str(entry))
        current = current_prices.get(symbol)
        if current is None or entry == 0:
            continue
        ratios.append(float(current) / float(entry))
    if not ratios:
        return None
    return Decimal(str(statistics.fmean(ratios) * 100))


def build_research_run_signal_snapshot(
    *,
    state: Any,
    signals_row: dict | None,
    kill_states: list[dict] | None,
) -> dict:
    """Assemble signal_snapshot JSONB for a research-run verdict.

    Tolerant of missing fields on state — backfill against older state shapes must not raise.
    """
    deep_dive_scores: dict[str, float | None] = {}
    results = getattr(state, "deep_dive_results", None) or {}
    if isinstance(results, dict):
        for category, payload in results.items():
            score = getattr(payload, "score", None)
            if score is None and isinstance(payload, dict):
                score = payload.get("score")
            deep_dive_scores[category] = score

    return {
        "signals_row": signals_row or {},
        "deep_dive_scores": deep_dive_scores,
        "kill_criterion_state": kill_states or [],
    }


def build_workspace_run_signal_snapshot(
    *,
    run: Any,
    signals_row: dict | None,
    kill_states: list[dict] | None,
    model_assumptions: dict | None,
) -> dict:
    """Assemble signal_snapshot JSONB for a workspace-run verdict.

    Tolerant of missing keys on run.step_outputs.
    """
    step_outputs = getattr(run, "step_outputs", None) or {}
    verdicts: dict[str, str | None] = {}
    if isinstance(step_outputs, dict):
        for step_name, payload in step_outputs.items():
            if not isinstance(payload, dict):
                continue
            verdict = payload.get("proposed_verdict") or payload.get("verdict")
            verdicts[step_name] = verdict

    return {
        "signals_row": signals_row or {},
        "workspace_step_verdicts": verdicts,
        "kill_criterion_state": kill_states or [],
        "model_assumptions": model_assumptions or {},
    }


async def _resolve_sector_etf(*, sector: str | None, db: AsyncSession) -> str | None:
    """Look up the SPDR sector ETF for an FMP sector name. None if unmapped or sector is null."""
    if not sector:
        return None
    result = await db.execute(
        select(SectorEtfMapping.etf_ticker).where(SectorEtfMapping.fmp_sector == sector)
    )
    return result.scalar_one_or_none()


async def record_verdict(
    *,
    source_type: Literal["research_run", "workspace_run"],
    source_id: str,
    ticker: str,
    theme_id: str | None,
    theme_seed_tickers: list[str] | None,
    sector: str | None,
    verdict: str,
    verdict_emitted_at: datetime,
    signal_snapshot: dict | None,
    fmp: FMPClient,
    db: AsyncSession,
) -> VerdictOutcome:
    """Idempotent on (source_type, source_id).

    1) Return existing outcome if already recorded.
    2) Resolve entry-anchored prices for ticker + SPY + sector ETF + theme constituents.
    3) Stamp any prior open same-(ticker, theme_id, source_type) outcome as superseded.
    4) Insert the new outcome row.
    """
    existing = (await db.execute(
        select(VerdictOutcome).where(
            VerdictOutcome.source_type == source_type,
            VerdictOutcome.source_id == source_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        return existing

    sector_etf_ticker = await _resolve_sector_etf(sector=sector, db=db)

    bundle = await _resolve_entry_prices(
        ticker=ticker,
        verdict_emitted_at=verdict_emitted_at,
        theme_seed_tickers=theme_seed_tickers,
        sector_etf_ticker=sector_etf_ticker,
        fmp=fmp,
    )

    new_id = str(uuid4())
    constituents_payload = (
        [{"ticker": c.ticker, "entry_price": str(c.entry_price)}
         for c in bundle.theme_basket_constituents] or None
    )
    theme_basket_entry_value: Decimal | None = (
        Decimal("100") if constituents_payload else None
    )

    outcome = VerdictOutcome(
        id=new_id,
        source_type=source_type,
        source_id=source_id,
        ticker=ticker,
        theme_id=theme_id,
        verdict=verdict,
        verdict_emitted_at=verdict_emitted_at,
        entry_price_at=bundle.entry_price_at,
        entry_price=bundle.ticker_price,
        spy_entry_price=bundle.spy_price,
        sector_etf_ticker=bundle.sector_etf_ticker,
        sector_etf_entry_price=bundle.sector_etf_price,
        theme_basket_entry_value=theme_basket_entry_value,
        theme_basket_constituents=constituents_payload,
        signal_snapshot=signal_snapshot,
    )

    await _stamp_prior_open_as_superseded(
        ticker=ticker,
        theme_id=theme_id,
        source_type=source_type,
        new_outcome=outcome,
        bundle=bundle,
        db=db,
    )

    db.add(outcome)
    await db.flush()
    return outcome


async def _stamp_prior_open_as_superseded(
    *,
    ticker: str,
    theme_id: str | None,
    source_type: str,
    new_outcome: VerdictOutcome,
    bundle: EntryPriceBundle,
    db: AsyncSession,
) -> None:
    """If there's a prior open (ticker, theme_id, source_type) outcome, stamp realized returns on it."""
    q = select(VerdictOutcome).where(
        VerdictOutcome.ticker == ticker,
        VerdictOutcome.source_type == source_type,
        VerdictOutcome.superseded_at.is_(None),
    )
    if theme_id is None:
        q = q.where(VerdictOutcome.theme_id.is_(None))
    else:
        q = q.where(VerdictOutcome.theme_id == theme_id)
    q = q.order_by(VerdictOutcome.verdict_emitted_at.desc()).limit(1)

    prior = (await db.execute(q)).scalar_one_or_none()
    if prior is None:
        return

    def _excess(t_entry, t_now, b_entry, b_now) -> Decimal | None:
        if t_entry in (None, 0) or b_entry in (None, 0) or t_now is None or b_now is None:
            return None
        return ((Decimal(str(t_now)) / Decimal(str(t_entry))) - (Decimal(str(b_now)) / Decimal(str(b_entry))))

    t_return: Decimal | None = None
    if prior.entry_price and prior.entry_price != 0:
        t_return = (Decimal(str(bundle.ticker_price)) / Decimal(str(prior.entry_price))) - Decimal("1")

    # Theme basket realized: rebuild prior basket value using new entry-day constituent prices
    prior_basket_excess: Decimal | None = None
    if prior.theme_basket_constituents:
        current_prices = {c.ticker: c.entry_price for c in bundle.theme_basket_constituents}
        prior_value_at_new_entry = compute_basket_value(
            prior.theme_basket_constituents, current_prices
        )
        if prior_value_at_new_entry is not None and prior.theme_basket_entry_value:
            basket_return = (prior_value_at_new_entry / Decimal(str(prior.theme_basket_entry_value))) - Decimal("1")
            if t_return is not None:
                prior_basket_excess = t_return - basket_return

    prior.superseded_at = datetime.now(timezone.utc)
    prior.superseded_by_outcome_id = new_outcome.id
    prior.realized_ticker_return_pct = t_return
    prior.realized_spy_excess_pct = _excess(
        prior.entry_price, bundle.ticker_price, prior.spy_entry_price, bundle.spy_price
    )
    prior.realized_sector_excess_pct = _excess(
        prior.entry_price, bundle.ticker_price, prior.sector_etf_entry_price, bundle.sector_etf_price
    )
    prior.realized_theme_basket_excess_pct = prior_basket_excess
    await db.flush()


async def refresh_snapshots(*, fmp: FMPClient, db: AsyncSession) -> RefreshSummary:
    """Iterate open outcomes; insert any newly-due snapshots; close at 6m.

    Per-outcome errors captured in summary.errors[], never abort the loop.
    """
    open_outcomes = (await db.execute(
        select(VerdictOutcome).where(VerdictOutcome.closed_at.is_(None))
    )).scalars().all()

    today = date.today()
    snapshotted = 0
    closed = 0
    errors: list[dict[str, str]] = []

    for outcome in open_outcomes:
        try:
            inserted, did_close = await _refresh_one(
                outcome=outcome, today=today, fmp=fmp, db=db,
            )
            snapshotted += inserted
            if did_close:
                closed += 1
        except Exception as exc:  # noqa: BLE001 — captured per-outcome
            logger.exception("refresh_snapshots failed for outcome %s", outcome.id)
            errors.append({"outcome_id": outcome.id, "error": str(exc)})

    return RefreshSummary(
        processed=len(open_outcomes), snapshotted=snapshotted, closed=closed, errors=errors,
    )


async def backfill_from_history(*, fmp: FMPClient, db: AsyncSession) -> BackfillSummary:
    """Walk completed research_runs + terminal workspace_runs; record_verdict for each (idempotent).

    Then run refresh_snapshots once to populate due offsets across new outcomes.

    Tolerant of missing source tables (e.g., in test environments) — returns zero-created.
    """
    from sqlalchemy.exc import OperationalError, ProgrammingError
    from backend.app.models.research_run import ResearchRun
    from backend.app.models.workspace_run import WorkspaceRun
    from backend.app.models.theme import Theme
    from backend.app.models.signal import Signal

    created = 0
    existed = 0
    errors: list[dict[str, str]] = []

    # ── Research runs ────────────────────────────────────────────────────────
    try:
        research_runs = (await db.execute(
            select(ResearchRun).where(ResearchRun.status.in_(["completed", "watchlist", "pass"]))
        )).scalars().all()
    except (OperationalError, ProgrammingError):
        research_runs = []

    for run in research_runs:
        try:
            existing = (await db.execute(
                select(VerdictOutcome).where(
                    VerdictOutcome.source_type == "research_run",
                    VerdictOutcome.source_id == run.id,
                )
            )).scalar_one_or_none()
            if existing is not None:
                existed += 1
                continue

            theme_seed_tickers = None
            if run.theme_id:
                theme = (await db.execute(select(Theme).where(Theme.id == run.theme_id))).scalar_one_or_none()
                if theme and isinstance(theme.seed_tickers, list):
                    theme_seed_tickers = list(theme.seed_tickers)

            signals_row = None
            if run.theme_id:
                sigs = (await db.execute(
                    select(Signal).where(
                        Signal.ticker == run.ticker, Signal.theme_id == run.theme_id
                    )
                )).scalars().all()
                if sigs:
                    signals_row = {s.signal_type: s.value for s in sigs}

            profile, _ = await fmp.get_profile(run.ticker)
            sector = (profile or {}).get("sector")

            state_dict = run.state if isinstance(run.state, dict) else {}
            dd = state_dict.get("deep_dive_results") or {}
            scores = {k: (v.get("score") if isinstance(v, dict) else None) for k, v in dd.items()}
            snapshot = {
                "signals_row": signals_row or {},
                "deep_dive_scores": scores,
                "kill_criterion_state": [],
            }

            emitted_at = run.completed_at or run.created_at
            if emitted_at is None:
                errors.append({"source_id": run.id, "error": "no completed_at/created_at"})
                continue

            await record_verdict(
                source_type="research_run",
                source_id=run.id,
                ticker=run.ticker,
                theme_id=run.theme_id,
                theme_seed_tickers=theme_seed_tickers,
                sector=sector,
                verdict=run.status,
                verdict_emitted_at=emitted_at,
                signal_snapshot=snapshot,
                fmp=fmp,
                db=db,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("backfill failed for research_run %s", run.id)
            errors.append({"source_id": run.id, "error": str(exc)})

    # ── Workspace runs ────────────────────────────────────────────────────────
    try:
        workspace_runs = (await db.execute(
            select(WorkspaceRun).where(WorkspaceRun.status == "completed", WorkspaceRun.verdict.is_not(None))
        )).scalars().all()
    except (OperationalError, ProgrammingError):
        workspace_runs = []

    for wrun in workspace_runs:
        try:
            existing = (await db.execute(
                select(VerdictOutcome).where(
                    VerdictOutcome.source_type == "workspace_run",
                    VerdictOutcome.source_id == wrun.id,
                )
            )).scalar_one_or_none()
            if existing is not None:
                existed += 1
                continue

            theme_id: str | None = None
            theme_seed_tickers: list[str] | None = None
            if wrun.parent_research_run_id:
                parent = (await db.execute(
                    select(ResearchRun).where(ResearchRun.id == wrun.parent_research_run_id)
                )).scalar_one_or_none()
                if parent and parent.theme_id:
                    theme_id = parent.theme_id
                    theme = (await db.execute(
                        select(Theme).where(Theme.id == theme_id)
                    )).scalar_one_or_none()
                    if theme and isinstance(theme.seed_tickers, list):
                        theme_seed_tickers = list(theme.seed_tickers)

            signals_row = None
            if theme_id:
                sigs = (await db.execute(
                    select(Signal).where(
                        Signal.ticker == wrun.ticker, Signal.theme_id == theme_id
                    )
                )).scalars().all()
                if sigs:
                    signals_row = {s.signal_type: s.value for s in sigs}

            profile, _ = await fmp.get_profile(wrun.ticker)
            sector = (profile or {}).get("sector")

            step_outputs = wrun.step_outputs or {}
            verdicts = {}
            for step, payload in step_outputs.items():
                if isinstance(payload, dict):
                    verdicts[step] = payload.get("proposed_verdict") or payload.get("verdict")
            snapshot = {
                "signals_row": signals_row or {},
                "workspace_step_verdicts": verdicts,
                "kill_criterion_state": [],
                "model_assumptions": {},
            }

            emitted_at = wrun.updated_at or wrun.created_at
            if emitted_at is None:
                errors.append({"source_id": wrun.id, "error": "no timestamp"})
                continue

            await record_verdict(
                source_type="workspace_run",
                source_id=wrun.id,
                ticker=wrun.ticker,
                theme_id=theme_id,
                theme_seed_tickers=theme_seed_tickers,
                sector=sector,
                verdict=wrun.verdict,
                verdict_emitted_at=emitted_at,
                signal_snapshot=snapshot,
                fmp=fmp,
                db=db,
            )
            created += 1
        except Exception as exc:  # noqa: BLE001
            logger.exception("backfill failed for workspace_run %s", wrun.id)
            errors.append({"source_id": wrun.id, "error": str(exc)})

    # Refresh in the same transaction so existing outcomes also pick up any due snapshots
    refresh = await refresh_snapshots(fmp=fmp, db=db)
    return BackfillSummary(
        outcomes_created=created,
        outcomes_existed=existed,
        snapshots_inserted=refresh.snapshotted,
        errors=errors + refresh.errors,
    )


async def _refresh_one(
    *,
    outcome: VerdictOutcome,
    today: date,
    fmp: FMPClient,
    db: AsyncSession,
) -> tuple[int, bool]:
    """Insert any due snapshots for this outcome. Returns (insertions, did_close_at_6m)."""
    existing = {
        row.snapshot_offset
        for row in (await db.execute(
            select(VerdictReturnSnapshot).where(
                VerdictReturnSnapshot.outcome_id == outcome.id
            )
        )).scalars().all()
    }

    due_offsets: list[tuple[str, date]] = []
    for key, days in SNAPSHOT_OFFSETS:
        if key in existing:
            continue
        target = outcome.entry_price_at + timedelta(days=days)
        if target <= today:
            due_offsets.append((key, target))

    if not due_offsets:
        return 0, False

    overall_start = min(d for _, d in due_offsets)
    overall_end = max(d for _, d in due_offsets) + timedelta(days=3)

    ticker_rows, _ = await fmp.get_historical_price_adjusted(
        outcome.ticker, overall_start.isoformat(), overall_end.isoformat()
    )
    if not ticker_rows:
        raise LookupError(f"no FMP price for {outcome.ticker} in [{overall_start}, {overall_end}]")

    def _parse_row(rows: list[dict]) -> dict[date, Decimal]:
        out: dict[date, Decimal] = {}
        for r in rows or []:
            raw_date = r["date"]
            d = raw_date if isinstance(raw_date, date) else date.fromisoformat(raw_date)
            out[d] = Decimal(str(r["close"]))
        return out

    by_date = _parse_row(ticker_rows)

    spy_by_date: dict[date, Decimal] = {}
    if outcome.spy_entry_price is not None:
        spy_rows, _ = await fmp.get_historical_price_adjusted(
            "SPY", overall_start.isoformat(), overall_end.isoformat()
        )
        spy_by_date = _parse_row(spy_rows)

    sector_by_date: dict[date, Decimal] = {}
    if outcome.sector_etf_ticker:
        rows, _ = await fmp.get_historical_price_adjusted(
            outcome.sector_etf_ticker, overall_start.isoformat(), overall_end.isoformat()
        )
        sector_by_date = _parse_row(rows)

    constituent_by_date_by_ticker: dict[str, dict[date, Decimal]] = {}
    if outcome.theme_basket_constituents:
        for c in outcome.theme_basket_constituents:
            sym = c["ticker"]
            rows, _ = await fmp.get_historical_price_adjusted(
                sym, overall_start.isoformat(), overall_end.isoformat()
            )
            constituent_by_date_by_ticker[sym] = _parse_row(rows)

    def _first_on_or_after(
        by_date_map: dict[date, Decimal], target: date
    ) -> tuple[date, Decimal] | None:
        for d in sorted(by_date_map.keys()):
            if d >= target:
                return d, by_date_map[d]
        return None

    inserted = 0
    did_close = False

    for key, target in due_offsets:
        match = _first_on_or_after(by_date, target)
        if match is None:
            continue
        snap_date, ticker_px = match
        ticker_return = (ticker_px / outcome.entry_price) - Decimal("1")

        spy_px: Decimal | None = None
        spy_excess: Decimal | None = None
        if outcome.spy_entry_price is not None:
            spy_match = _first_on_or_after(spy_by_date, target)
            if spy_match is not None:
                _, spy_px = spy_match
                spy_return = (spy_px / outcome.spy_entry_price) - Decimal("1")
                spy_excess = ticker_return - spy_return

        sector_px: Decimal | None = None
        sector_excess: Decimal | None = None
        if outcome.sector_etf_ticker and outcome.sector_etf_entry_price:
            m = _first_on_or_after(sector_by_date, target)
            if m is not None:
                _, sector_px = m
                sector_return = (sector_px / outcome.sector_etf_entry_price) - Decimal("1")
                sector_excess = ticker_return - sector_return

        basket_value: Decimal | None = None
        basket_excess: Decimal | None = None
        if outcome.theme_basket_constituents and outcome.theme_basket_entry_value:
            current_prices: dict[str, Decimal] = {}
            for sym, by in constituent_by_date_by_ticker.items():
                m = _first_on_or_after(by, target)
                if m is not None:
                    current_prices[sym] = m[1]
            basket_value = compute_basket_value(outcome.theme_basket_constituents, current_prices)
            if basket_value is not None:
                basket_return = (basket_value / Decimal(str(outcome.theme_basket_entry_value))) - Decimal("1")
                basket_excess = ticker_return - basket_return

        db.add(VerdictReturnSnapshot(
            id=str(uuid4()),
            outcome_id=outcome.id,
            snapshot_offset=key,
            snapshot_date=snap_date,
            ticker_price=ticker_px,
            spy_price=spy_px,
            sector_etf_price=sector_px,
            theme_basket_value=basket_value,
            ticker_return_pct=ticker_return,
            spy_excess_pct=spy_excess,
            sector_excess_pct=sector_excess,
            theme_basket_excess_pct=basket_excess,
        ))
        inserted += 1
        if key == "6m":
            outcome.closed_at = datetime.now(timezone.utc)
            did_close = True

    if inserted:
        await db.flush()
    return inserted, did_close
