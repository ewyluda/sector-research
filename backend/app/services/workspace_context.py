from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from backend.app.clients.fmp import FMPClient
    from backend.app.clients.edgar import EdgarClient
    from backend.app.models.research_run import ResearchRun
    from backend.app.models.ticker_model import TickerModel


@dataclass
class WorkspaceContext:
    """Carrier passed through every workspace step.

    Pure relative to its inputs — step functions read from this and return
    a Pydantic output. The orchestrator owns persistence + SSE emission.
    """

    run_id: str
    ticker: str
    db: AsyncSession
    fmp: FMPClient
    edgar: EdgarClient
    anthropic: AsyncAnthropic
    prior_research_run: ResearchRun
    # None when no saved model exists (model-less runs skip update_refresh's model work)
    prior_ticker_model: TickerModel | None
    emit: Callable[[dict], None]
