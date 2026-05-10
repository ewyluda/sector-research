"""Time-series read access to the signal_history table."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.signal_history import SignalHistory


async def list_signal_history(
    db: AsyncSession,
    *,
    ticker: str,
    theme_id: str,
    signal_type: str,
    days: int,
) -> list[SignalHistory]:
    """Return SignalHistory rows for one (ticker, theme_id, signal_type)
    over the last `days` days, ordered oldest → newest so sparkline
    consumers can plot left-to-right without reversing.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = (
        select(SignalHistory)
        .where(
            SignalHistory.ticker == ticker.upper(),
            SignalHistory.theme_id == theme_id,
            SignalHistory.signal_type == signal_type,
            SignalHistory.computed_at >= cutoff,
        )
        .order_by(SignalHistory.computed_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
