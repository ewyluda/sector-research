"""Record the FMP responses a research run needs, for the end-to-end test.

Runs the real pipeline once with live FMP behind a recording proxy and the
fake LLM from the test harness (no Anthropic spend), then writes
backend/tests/fixtures/fmp_<TICKER>.json. Point DATABASE_URL at a disposable,
migrated database — the run is written there.

    DATABASE_URL=postgresql+asyncpg://…/sector_research_ci \
      python -m backend.scripts.record_pipeline_fixture VRT
"""
import asyncio
import logging
import sys
from unittest.mock import patch

from backend.app.clients.fmp import FMPClient
from backend.app.db import async_session
from backend.app.graph import llm
from backend.app.graph.state import ResearchState
from backend.app.models.theme import Theme
from backend.app.services.pipeline import PipelineService
from backend.tests.pipeline_harness import FIXTURES, FakeAnthropic, ReplayFMP

logging.disable(logging.INFO)  # httpx logs request URLs, API keys included


async def main(ticker: str) -> None:
    path = FIXTURES / f"fmp_{ticker}.json"
    fmp = ReplayFMP(path, record_from=FMPClient())
    profile, _ = await fmp.get_company_profile(ticker)
    price = float((profile[0] if isinstance(profile, list) else profile)["price"])
    fake = FakeAnthropic(price=price, risk_loops=1)
    with patch.object(llm, "get_client", return_value=fake):
        svc = PipelineService(fmp=fmp)
        async with async_session() as db:
            theme = Theme(name="Fixture theme", description="Recorded for the end-to-end test.")
            db.add(theme)
            await db.commit()
            run = await svc.create_run(ticker, theme.id, db)
        await svc._run_phase(run.id, ResearchState.from_dict(run.state))
        pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        await asyncio.gather(*pending, return_exceptions=True)  # terminal outcome recording
    fmp.save()
    await fmp.close()
    print(f"wrote {path} ({path.stat().st_size / 1024:.0f} KB, {len(fake.requests)} fake LLM calls)")


if __name__ == "__main__":
    asyncio.run(main((sys.argv[1] if len(sys.argv) > 1 else "VRT").upper()))
