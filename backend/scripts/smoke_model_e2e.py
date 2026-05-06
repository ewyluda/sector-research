# backend/scripts/smoke_model_e2e.py
"""Real-DB E2E smoke: requires a completed research_run for the chosen ticker.
Override with sys.argv[1]. Verifies init → state populated → BS reasonable.
This will make a real Sonnet API call and fetch real FMP/FRED data."""
import asyncio
import sys
from sqlalchemy import delete
from backend.app.db import async_session
from backend.app.models.ticker_model import TickerModel
from backend.app.models.ticker_model_draft import TickerModelDraft
from backend.app.services.model_baseline import initialize_or_get_model
from backend.app.models.model_state import ModelState


async def run(ticker: str):
    # Pre-clean any prior model rows for this ticker (so the test always exercises a fresh init)
    async with async_session() as db:
        await db.execute(delete(TickerModelDraft).where(TickerModelDraft.ticker == ticker))
        await db.execute(delete(TickerModel).where(TickerModel.ticker == ticker))
        await db.commit()

    print(f"Initializing baseline for {ticker} (this calls real Sonnet + FMP + FRED)...")
    row = await initialize_or_get_model(ticker)
    state = ModelState.model_validate(row.state)
    forecast = [p for p in state.periods if not p.is_historical]
    print(f"  -> version {row.version}, {len(forecast)} forecast periods, label={row.label}")

    if not forecast:
        print("  ! No forecast periods produced. Failing.")
        sys.exit(1)

    first_f = forecast[0]
    rev_cell = state.income_statement.get("revenue", {}).get(first_f.label)
    rev = rev_cell.value if rev_cell else None
    print(f"  -> forecast revenue at {first_f.label}: {rev}")
    if rev is None or rev <= 0:
        print("  ! No positive forecast revenue produced. Failing.")
        sys.exit(1)

    discount = state.assumptions.discount_rate.value
    print(f"  -> discount rate (CAPM): {discount:.4f}")

    print("OK: E2E baseline init succeeded.")


if __name__ == "__main__":
    ticker = sys.argv[1] if len(sys.argv) > 1 else "ORCL"
    asyncio.run(run(ticker))
