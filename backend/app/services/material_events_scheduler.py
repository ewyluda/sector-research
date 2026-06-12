"""Daily material-events scan: 8-K classification + Form 4 insider ingest
+ congressional-trade ingest (senate/house PTRs via FMP).

Universe = theme seed_tickers ∪ active-thesis tickers (the calendar's
definition — same private import of the status board's latest-runs SQL,
which owns the "active thesis" semantics).

Fanout-style isolation: each ticker runs in its own async_session() with an
explicit commit; per-ticker errors land in summary["errors"] and never abort
the loop. EDGAR rate limiting lives inside EdgarClient._throttle().
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient
from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.models.congress_transaction import CongressTransaction
from backend.app.models.filing import Filing
from backend.app.models.insider_transaction import InsiderTransaction
from backend.app.models.material_event import MaterialEvent
from backend.app.models.signal import Signal
from backend.app.models.signal_history import SignalHistory
from backend.app.models.theme import Theme
from backend.app.services.congress_ingest import upsert_congress_transactions
from backend.app.services.congress_signal import (
    WINDOW_DAYS as CONGRESS_WINDOW_DAYS,
)
from backend.app.services.congress_signal import (
    compute_congress_aggregate,
)
from backend.app.services.congress_signal import (
    signal_value as congress_signal_value,
)
from backend.app.services.edgar_sections_ingest import _upsert_filing
from backend.app.services.event_classifier import classify_8k, should_classify
from backend.app.services.insider_ingest import upsert_insider_transactions
from backend.app.services.insider_signal import (
    WINDOW_DAYS,
    compute_insider_aggregate,
    signal_value,
)

logger = logging.getLogger(__name__)

# Bounds the first run; accession dedupe makes every later run idempotent.
LOOKBACK_DAYS = 14
# FMP default limit (20) is too small for a 90-day window on active names.
FMP_INSIDER_LIMIT = 100


# ── Universe ──────────────────────────────────────────────────────────────────


async def _theme_universe(db: AsyncSession) -> dict[str, set[str]]:
    """theme_id -> tickers (seeds ∪ that theme's active-thesis tickers)."""
    # Private import is deliberate — same pattern + rationale as
    # calendar_events.get_universe: the status board owns "active thesis".
    from backend.app.services.status_board import _build_latest_runs_sql  # noqa: PLC0415

    out: dict[str, set[str]] = {}
    themes = (await db.execute(select(Theme))).scalars().all()
    for t in themes:
        seeds = t.seed_tickers if isinstance(t.seed_tickers, list) else []
        out[str(t.id)] = {str(s).upper() for s in seeds}

    sql, params = _build_latest_runs_sql(theme_id=None, include_archived=False)
    for r in (await db.execute(text(sql), params)).mappings().all():
        out.setdefault(str(r["theme_id"]), set()).add(str(r["ticker"]).upper())
    return out


# ── 8-K flow ──────────────────────────────────────────────────────────────────


def _recent_8ks(submissions: dict, since: date) -> list[dict]:
    """Plain-8-K entries from the submissions feed filed on/after `since`.
    (8-K/A amendments are out of scope for v1.)"""
    recent = submissions.get("filings", {}).get("recent", {}) or {}
    forms = recent.get("form", []) or []
    accessions = recent.get("accessionNumber", []) or []
    docs = recent.get("primaryDocument", []) or []
    filing_dates = recent.get("filingDate", []) or []
    items_list = recent.get("items", []) or []

    out: list[dict] = []
    for i, form in enumerate(forms):
        if form != "8-K":
            continue
        try:
            fd = date.fromisoformat(filing_dates[i])
        except (ValueError, IndexError):
            continue
        if fd < since:
            continue
        out.append({
            "accession_number": accessions[i] if i < len(accessions) else None,
            "primary_document": docs[i] if i < len(docs) else None,
            "filing_date": fd,
            "item_codes": items_list[i] if i < len(items_list) else "",
        })
    return out


async def _scan_ticker_8ks(
    *, ticker: str, cik: str, edgar: EdgarClient, db: AsyncSession, since: date
) -> dict:
    """Classify new 8-Ks for one ticker. Commit-free — caller owns the session."""
    counts = {
        "events_created": 0,
        "skipped_prefilter": 0,
        "skipped_existing": 0,
        "errors": [],
    }
    submissions, _ = await edgar.get_submissions(cik)
    for c in _recent_8ks(submissions, since=since):
        accession = c["accession_number"]
        if not accession or not c["primary_document"]:
            continue
        if not should_classify(c["item_codes"]):
            counts["skipped_prefilter"] += 1
            continue

        existing = await db.execute(
            select(MaterialEvent.id)
            .join(Filing, Filing.id == MaterialEvent.filing_id)
            .where(Filing.accession_number == accession)
            .limit(1)
        )
        if existing.first() is not None:
            counts["skipped_existing"] += 1
            continue

        doc_url = (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{accession.replace('-', '')}/{c['primary_document']}"
        )
        doc_text, _ = await edgar.fetch_document(doc_url)
        classification, err = await classify_8k(
            ticker=ticker,
            filing_date=c["filing_date"].isoformat(),
            item_codes=c["item_codes"],
            text=doc_text,
        )
        if classification is None:
            # No tombstone on failure — retried on the next run.
            counts["errors"].append(f"{accession}: {err}")
            continue

        filing = await _upsert_filing(
            db,
            ticker=ticker,
            cik=cik,
            form_type="8-K",
            accession_number=accession,
            primary_document_url=doc_url,
            filing_date=c["filing_date"],
            period_of_report=None,
        )
        db.add(MaterialEvent(
            filing_id=filing.id,
            ticker=ticker.upper(),
            item_codes=(c["item_codes"] or None),
            event_type=classification.event_type,
            materiality=classification.materiality,
            headline=classification.headline,
            summary=classification.summary,
            filing_date=c["filing_date"],
        ))
        counts["events_created"] += 1
    return counts


# ── Insider signal persist (mirrors signal_scheduler._persist_signal_set) ────


async def _persist_insider_signal(
    *, db: AsyncSession, ticker: str, theme_id: str, value: dict,
    computed_at: datetime, signal_type: str = "insider",
) -> None:
    await db.execute(
        delete(Signal).where(
            Signal.ticker == ticker,
            Signal.theme_id == theme_id,
            Signal.signal_type == signal_type,
        )
    )
    db.add(Signal(
        ticker=ticker, theme_id=theme_id, signal_type=signal_type,
        value=value, computed_at=computed_at, is_stale=False,
    ))
    db.add(SignalHistory(
        ticker=ticker, theme_id=theme_id, signal_type=signal_type,
        value=value, computed_at=computed_at,
    ))


# ── Orchestrator ─────────────────────────────────────────────────────────────


async def run_daily_material_scan(*, edgar: EdgarClient, fmp: FMPClient) -> dict:
    """Full daily scan. Returns a summary dict for logging."""
    started = datetime.now(timezone.utc)
    summary: dict = {
        "tickers_scanned": 0,
        "events_created": 0,
        "events_skipped_prefilter": 0,
        "events_skipped_existing": 0,
        "transactions_added": 0,
        "congress_transactions_added": 0,
        "signals_written": 0,
        "errors": [],
    }

    async with async_session() as db:
        theme_universe = await _theme_universe(db)
    all_tickers = sorted(set().union(*theme_universe.values())) if theme_universe else []
    today = date.today()
    since = today - timedelta(days=LOOKBACK_DAYS)
    window_cutoff = today - timedelta(days=WINDOW_DAYS)
    congress_cutoff = today - timedelta(days=CONGRESS_WINDOW_DAYS)
    insider_values: dict[str, dict] = {}
    congress_values: dict[str, dict] = {}

    for ticker in all_tickers:
        try:
            async with async_session() as db:
                # 8-K side — isolated so an EDGAR/Haiku failure can't
                # suppress the (more reliable) insider ingest below.
                try:
                    cik, _ = await edgar.get_ticker_to_cik(ticker)
                    if cik:
                        counts = await _scan_ticker_8ks(
                            ticker=ticker, cik=cik, edgar=edgar, db=db, since=since
                        )
                        summary["events_created"] += counts["events_created"]
                        summary["events_skipped_prefilter"] += counts["skipped_prefilter"]
                        summary["events_skipped_existing"] += counts["skipped_existing"]
                        summary["errors"].extend(f"{ticker} {e}" for e in counts["errors"])
                    else:
                        summary["errors"].append(f"{ticker}: no CIK in EDGAR ticker map")
                except Exception as e:
                    logger.exception("8-K scan failed for %s", ticker)
                    summary["errors"].append(f"{ticker} 8-K scan: {e}")
                    await db.rollback()  # discard any partial 8-K rows so the insider write commits clean

                rows, _ = await fmp.get_insider_trading(ticker, limit=FMP_INSIDER_LIMIT)
                ins = await upsert_insider_transactions(db, ticker, rows)
                summary["transactions_added"] += ins["added"]

                window_rows = (await db.execute(
                    select(InsiderTransaction).where(
                        InsiderTransaction.ticker == ticker,
                        InsiderTransaction.transaction_date >= window_cutoff,
                    )
                )).scalars().all()
                agg = compute_insider_aggregate(window_rows, today)
                insider_values[ticker] = signal_value(agg)

                await db.commit()

                # Congress side — after the insider commit and isolated, so
                # an FMP failure here rolls back only its own rows and can't
                # discard the insider work above.
                try:
                    senate_rows, _ = await fmp.get_senate_trades(ticker)
                    house_rows, _ = await fmp.get_house_trades(ticker)
                    cg = await upsert_congress_transactions(
                        db, ticker, senate_rows=senate_rows, house_rows=house_rows
                    )
                    summary["congress_transactions_added"] += cg["added"]

                    cg_rows = (await db.execute(
                        select(CongressTransaction).where(
                            CongressTransaction.ticker == ticker,
                            CongressTransaction.transaction_date >= congress_cutoff,
                        )
                    )).scalars().all()
                    congress_values[ticker] = congress_signal_value(
                        compute_congress_aggregate(cg_rows, today)
                    )
                    await db.commit()
                except Exception as e:
                    logger.exception("congress scan failed for %s", ticker)
                    summary["errors"].append(f"{ticker} congress: {e}")
                    await db.rollback()
            summary["tickers_scanned"] += 1
        except Exception as e:
            logger.exception("material scan failed for %s", ticker)
            summary["errors"].append(f"{ticker}: {e}")

    # Signal rows per (ticker, theme) — one shared timestamp, one session.
    now = datetime.now(timezone.utc)
    try:
        async with async_session() as db:
            for theme_id, tickers in theme_universe.items():
                for t in sorted(tickers):
                    if t in insider_values:
                        await _persist_insider_signal(
                            db=db, ticker=t, theme_id=theme_id,
                            value=insider_values[t], computed_at=now,
                        )
                        summary["signals_written"] += 1
                    if t in congress_values:
                        await _persist_insider_signal(
                            db=db, ticker=t, theme_id=theme_id,
                            value=congress_values[t], computed_at=now,
                            signal_type="congress",
                        )
                        summary["signals_written"] += 1
            await db.commit()
    except Exception as e:
        logger.exception("insider signal persist failed")
        summary["errors"].append(f"signal persist: {e}")

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    logger.info("material scan complete in %.1fs: %s", elapsed, summary)
    return summary
