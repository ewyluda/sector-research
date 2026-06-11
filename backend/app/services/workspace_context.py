from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class WorkspaceContext:
    """Carrier passed through every workspace step.

    Pure relative to its inputs — step functions read from this and return
    a Pydantic output. The orchestrator owns persistence + SSE emission.
    """

    run_id: str
    ticker: str
    db: AsyncSession
    fmp: Any  # FMPClient
    edgar: Any  # EdgarClient
    anthropic: Any  # AsyncAnthropic
    prior_research_run: Any  # ResearchRun ORM row
    prior_ticker_model: Any  # TickerModel ORM row, or None when no saved model exists
    emit: Callable[[dict], None]
