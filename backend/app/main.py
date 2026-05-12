"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.config import get_settings
from backend.app.clients.fmp import FMPClient
from backend.app.clients.x_client import XClient
from backend.app.api.health import router as health_router
from backend.app.api.themes import router as themes_router
from backend.app.api.discovery import router as discovery_router
from backend.app.api.pipeline import router as pipeline_router
from backend.app.api.filings import router as filings_router
from backend.app.api.fanouts import router as fanouts_router
from backend.app.api.catalysts import router as catalysts_router
from backend.app.api.status import router as status_router
from backend.app.api.read_through import router as read_through_router
from backend.app.api.earnings import router as earnings_router
from backend.app.api.questions import router as questions_router
from backend.app.api.models_api import router as models_router
from backend.app.services.pipeline import PipelineService
from backend.app.services.fanout import FanoutService
from backend.app.services.workspace import WorkspaceService
from backend.app.api import workspace as workspace_api
from backend.app.api import outcomes as outcomes_api
from backend.app.api import transcripts_delta as transcripts_delta_api
from backend.app.db import unit_of_work

settings = get_settings()

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("Starting Sector Research App...")

    # Shared API clients
    app.state.fmp = FMPClient()
    app.state.x_client = XClient()
    from backend.app.clients.fred import FREDClient
    from backend.app.clients.edgar import EdgarClient
    app.state.fred = FREDClient()
    app.state.edgar = EdgarClient()
    logger.info("FMP + X + FRED + EDGAR clients initialised")

    # Pipeline service
    app.state.pipeline = PipelineService(
        fmp=app.state.fmp, fred=app.state.fred, edgar=app.state.edgar,
    )
    logger.info("PipelineService initialised")

    # Fan-out service (relationship extraction orchestrator)
    app.state.fanout = FanoutService(edgar=app.state.edgar, fmp=app.state.fmp)
    logger.info("FanoutService initialised")

    # Workspace loop service
    import anthropic as _anthropic
    app.state.anthropic = _anthropic.AsyncAnthropic(
        api_key=settings.anthropic_api_key
    )
    app.state.workspace = WorkspaceService(
        fmp=app.state.fmp, edgar=app.state.edgar, anthropic=app.state.anthropic,
    )
    logger.info("WorkspaceService initialised")

    # Daily signal scheduler — 2 AM local time
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _daily_refresh_job,
        trigger=CronTrigger(hour=2, minute=0),
        args=[app],
        id="daily_signal_refresh",
        name="Daily X Signal Refresh",
        replace_existing=True,
    )
    scheduler.add_job(
        _daily_earnings_refresh_job,
        trigger=CronTrigger(hour=21, minute=0),
        args=[app],
        id="daily_earnings_refresh",
        name="Daily Earnings Prints Refresh",
        replace_existing=True,
    )
    # Daily verdict-outcome snapshot refresh — 03:00 UTC
    async def _run_daily_outcome_refresh() -> None:
        from backend.app.services.outcome_tracker import refresh_snapshots
        try:
            fmp = app.state.fmp
            async with unit_of_work() as db:
                summary = await refresh_snapshots(fmp=fmp, db=db)
            logger.info(
                "outcome refresh: processed=%d snapshotted=%d closed=%d errors=%d",
                summary.processed, summary.snapshotted, summary.closed, len(summary.errors),
            )
        except Exception:
            logger.exception("Daily outcome refresh crashed")

    scheduler.add_job(
        _run_daily_outcome_refresh,
        CronTrigger(hour=3, minute=0, timezone="UTC"),
        id="outcome_snapshot_refresh",
        replace_existing=True,
    )

    scheduler.start()
    app.state.scheduler = scheduler
    logger.info("Schedulers started: X signals @ 02:00 UTC, earnings @ 21:00 UTC, outcomes @ 03:00 UTC")

    yield

    # Cleanup
    scheduler.shutdown(wait=False)
    await app.state.fmp.close()
    await app.state.x_client.close()
    await app.state.edgar.close()
    logger.info("Shutdown complete")



async def _daily_refresh_job(app: FastAPI) -> None:
    """APScheduler job wrapper for the daily signal refresh."""
    from backend.app.services.signal_scheduler import run_daily_refresh
    await run_daily_refresh(fmp=app.state.fmp, x_client=app.state.x_client)


async def _daily_earnings_refresh_job(app: FastAPI) -> None:
    """APScheduler entry point — wraps run_daily_earnings_refresh with logging."""
    from backend.app.services.earnings_scheduler import run_daily_earnings_refresh
    try:
        summary = await run_daily_earnings_refresh()
        logger.info("Daily earnings refresh: %s", summary)
    except Exception:
        logger.exception("Daily earnings refresh crashed")


app = FastAPI(
    title="Sector Research App",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health_router)
app.include_router(themes_router, prefix="/api")
app.include_router(discovery_router, prefix="/api")
app.include_router(pipeline_router, prefix="/api")
app.include_router(filings_router, prefix="/api")
app.include_router(fanouts_router, prefix="/api")
app.include_router(catalysts_router, prefix="/api")
app.include_router(status_router, prefix="/api")
app.include_router(read_through_router, prefix="/api")
app.include_router(earnings_router, prefix="/api")
app.include_router(questions_router, prefix="/api")
app.include_router(models_router)
app.include_router(workspace_api.router)
app.include_router(outcomes_api.router)
app.include_router(transcripts_delta_api.router)
