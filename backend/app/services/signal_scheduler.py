"""Daily X signal scheduler.

Runs once per day (default: 2 AM local time via APScheduler).
Processes one theme at a time, 2-second sleep between ticker calls.
Writes results to the signals table and fires SurpriseAlerts when velocity spikes.

Estimated runtime per full refresh: 10–15 minutes for 4–6 themes × ~25 tickers.
"""

import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.fmp import FMPClient
from backend.app.clients.x_client import XClient, VELOCITY_SURPRISE_MULTIPLIER
from backend.app.db import async_session
from backend.app.models.signal import Signal
from backend.app.models.surprise_alert import SurpriseAlert
from backend.app.models.theme import Theme

logger = logging.getLogger(__name__)

INTER_CALL_SLEEP = 2.0  # seconds between X API calls


async def refresh_theme_signals(
    theme: Theme,
    fmp: FMPClient,
    x_client: XClient,
    db: AsyncSession,
) -> dict:
    """
    Refresh all three X signals for every ticker in a theme.
    Returns a summary dict for logging.
    """
    seed_tickers = theme.seed_tickers if isinstance(theme.seed_tickers, list) else []
    x_terms = theme.x_search_terms if isinstance(theme.x_search_terms, list) else []

    # Collect tickers: seed list + any previously signalled tickers for this theme
    result = await db.execute(
        select(Signal.ticker).where(Signal.theme_id == theme.id).distinct()
    )
    known_tickers = {row[0] for row in result.all()}
    all_tickers = list({t.upper() for t in seed_tickers} | known_tickers)

    processed = 0
    errors = 0
    surprises_fired = 0
    now = datetime.now(timezone.utc)

    for ticker in all_tickers:
        try:
            # ── Velocity ──────────────────────────────────────────────────────
            velocity_data, vel_cit = await x_client.compute_velocity_signal(ticker)
            await asyncio.sleep(INTER_CALL_SLEEP)

            # Check for surprise before overwriting the old signal
            old_velocity = await db.execute(
                select(Signal).where(
                    Signal.ticker == ticker,
                    Signal.theme_id == theme.id,
                    Signal.signal_type == "velocity",
                )
            )
            old_sig = old_velocity.scalar_one_or_none()
            prior_ratio = old_sig.value.get("ratio", 1.0) if old_sig else None

            # ── Narrative ─────────────────────────────────────────────────────
            narrative_data, narr_cit = await x_client.compute_narrative_signal(ticker)
            await asyncio.sleep(INTER_CALL_SLEEP)

            # ── Discovery ─────────────────────────────────────────────────────
            discovery_data, disc_cit = await x_client.compute_discovery_score(
                ticker=ticker,
                theme_x_search_terms=x_terms,
                seed_tickers=seed_tickers,
            )
            await asyncio.sleep(INTER_CALL_SLEEP)

            # ── Upsert signals ────────────────────────────────────────────────
            for signal_type, value in [
                ("velocity", velocity_data),
                ("narrative", narrative_data),
                ("discovery", discovery_data),
            ]:
                # Delete old signal of this type for this ticker/theme
                await db.execute(
                    delete(Signal).where(
                        Signal.ticker == ticker,
                        Signal.theme_id == theme.id,
                        Signal.signal_type == signal_type,
                    )
                )
                new_signal = Signal(
                    ticker=ticker,
                    theme_id=theme.id,
                    signal_type=signal_type,
                    value=value,
                    computed_at=now,
                    is_stale=False,
                )
                db.add(new_signal)

            await db.commit()

            # ── Surprise alert check ──────────────────────────────────────────
            current_ratio = velocity_data.get("ratio", 1.0)
            if (
                prior_ratio is not None
                and current_ratio > prior_ratio * VELOCITY_SURPRISE_MULTIPLIER
            ):
                # Check no unacknowledged alert already exists
                existing_alert = await db.execute(
                    select(SurpriseAlert).where(
                        SurpriseAlert.ticker == ticker,
                        SurpriseAlert.theme_id == theme.id,
                        SurpriseAlert.acknowledged_at.is_(None),
                    )
                )
                if not existing_alert.scalar_one_or_none():
                    alert = SurpriseAlert(
                        ticker=ticker,
                        theme_id=theme.id,
                        prior_velocity_ratio=prior_ratio,
                        current_velocity_ratio=current_ratio,
                    )
                    db.add(alert)
                    await db.commit()
                    surprises_fired += 1
                    logger.info(
                        "Surprise signal fired: %s in theme %s (%.2f → %.2f)",
                        ticker, theme.name, prior_ratio, current_ratio,
                    )

            processed += 1
            logger.debug("Signals refreshed for %s in %s", ticker, theme.name)

        except Exception as e:
            errors += 1
            logger.error("Signal refresh failed for %s in %s: %s", ticker, theme.name, e)
            continue

    return {
        "theme": theme.name,
        "processed": processed,
        "errors": errors,
        "surprises_fired": surprises_fired,
    }


async def run_daily_refresh(fmp: FMPClient, x_client: XClient) -> None:
    """
    Full daily refresh: process each theme sequentially.
    Called by APScheduler at 2 AM local time.
    """
    logger.info("Daily signal refresh starting...")
    start = datetime.now(timezone.utc)

    async with async_session() as db:
        result = await db.execute(select(Theme))
        themes = result.scalars().all()
        logger.info("Refreshing signals for %d themes", len(themes))

        total_processed = 0
        total_errors = 0
        total_surprises = 0

        for theme in themes:
            summary = await refresh_theme_signals(
                theme=theme, fmp=fmp, x_client=x_client, db=db
            )
            total_processed += summary["processed"]
            total_errors += summary["errors"]
            total_surprises += summary["surprises_fired"]
            logger.info("Theme '%s': %s", theme.name, summary)

    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
    logger.info(
        "Daily refresh complete in %.1fs — %d processed, %d errors, %d surprises",
        elapsed, total_processed, total_errors, total_surprises,
    )
