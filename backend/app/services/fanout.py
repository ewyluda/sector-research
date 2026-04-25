"""Fan-out orchestrator for relationship extraction.

On-demand service that walks a ticker list and runs ingest → extract →
resolve for each one. Results are tombstoned in the DB at the section
and row level, so re-runs are cheap unless `force=True` (which only
affects the extract stage — resolve already skips already-resolved
rows).

Status is tracked in memory per-process (no persistence across server
restarts). Mirrors the pattern of `PipelineService`'s in-memory SSE
queues. If the server restarts mid-run, the client polling the status
endpoint will see a 404 — acceptable for a personal tool.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient
from backend.app.db import async_session
from backend.app.models.theme import Theme
from backend.app.services import (
    counterparty_resolver,
    edgar_relationships,
    edgar_sections_ingest,
)

logger = logging.getLogger(__name__)

FanoutStatusLiteral = Literal["running", "completed", "failed"]
FanoutStageLiteral = Literal["ingest", "extract", "resolve"]


@dataclass
class FanoutError:
    ticker: str
    stage: FanoutStageLiteral
    message: str


@dataclass
class FanoutScope:
    kind: Literal["theme", "ticker"]
    theme_id: str | None = None
    ticker: str | None = None

    def to_dict(self) -> dict:
        if self.kind == "theme":
            return {"kind": "theme", "theme_id": self.theme_id}
        return {"kind": "ticker", "ticker": self.ticker}


@dataclass
class FanoutStatus:
    fanout_id: str
    status: FanoutStatusLiteral
    scope: FanoutScope
    total_tickers: int
    completed_tickers: int = 0
    current_ticker: str | None = None
    current_stage: FanoutStageLiteral | None = None
    errors: list[FanoutError] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "fanout_id": self.fanout_id,
            "status": self.status,
            "scope": self.scope.to_dict(),
            "total_tickers": self.total_tickers,
            "completed_tickers": self.completed_tickers,
            "current_ticker": self.current_ticker,
            "current_stage": self.current_stage,
            "errors": [
                {"ticker": e.ticker, "stage": e.stage, "message": e.message}
                for e in self.errors
            ],
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
        }


class FanoutService:
    """In-memory fan-out orchestrator. Instantiated once in main.py
    lifespan and stored on app.state.fanout — same pattern as
    PipelineService. `edgar` is the process-wide shared EdgarClient,
    so the service does NOT own its lifecycle (no close on exit)."""

    def __init__(self, *, edgar: EdgarClient) -> None:
        self._statuses: dict[str, FanoutStatus] = {}
        self._edgar = edgar

    @staticmethod
    def _new_id() -> str:
        return f"fo_{secrets.token_hex(6)}"

    def get(self, fanout_id: str) -> FanoutStatus | None:
        return self._statuses.get(fanout_id)

    def start_ticker(self, ticker: str, force: bool = False) -> FanoutStatus:
        """Begin a single-ticker fan-out. Returns the status immediately;
        work runs under asyncio.create_task."""
        status = FanoutStatus(
            fanout_id=self._new_id(),
            status="running",
            scope=FanoutScope(kind="ticker", ticker=ticker.upper()),
            total_tickers=1,
        )
        self._statuses[status.fanout_id] = status
        asyncio.create_task(self._run([ticker.upper()], status, force=force))
        return status

    async def start_theme(
        self, theme_id: str, db: AsyncSession, force: bool = False
    ) -> FanoutStatus:
        """Begin a theme-scoped fan-out. Reads seed_tickers from the theme
        row up-front so the returned total_tickers is accurate; raises if
        the theme doesn't exist."""
        # Theme.id is a PG UUID column, so a malformed string would hit
        # asyncpg as a DataError (500) before scalar_one_or_none() could
        # return None. Validate format first and treat invalid UUIDs as
        # "not found" so the router's ValueError → 404 mapping applies.
        try:
            UUID(theme_id)
        except (ValueError, TypeError):
            raise ValueError(f"theme {theme_id!r} not found")

        result = await db.execute(select(Theme).where(Theme.id == theme_id))
        theme = result.scalar_one_or_none()
        if theme is None:
            # Router maps ValueError → HTTP 404 (same pattern as
            # pipeline.py's run-not-found handling).
            raise ValueError(f"theme {theme_id!r} not found")

        raw_tickers = theme.seed_tickers or []
        # Theme.seed_tickers is JSONB. In practice rows are list-of-strings
        # (verified across current DB content), but we also tolerate
        # list-of-dicts with a "ticker" key so we don't blow up on any
        # historical shapes.
        tickers: list[str] = []
        for entry in raw_tickers:
            if isinstance(entry, str):
                tickers.append(entry.upper())
            elif isinstance(entry, dict) and entry.get("ticker"):
                tickers.append(str(entry["ticker"]).upper())
        tickers = sorted(set(tickers))

        status = FanoutStatus(
            fanout_id=self._new_id(),
            status="running",
            scope=FanoutScope(kind="theme", theme_id=theme_id),
            total_tickers=len(tickers),
        )
        self._statuses[status.fanout_id] = status

        if not tickers:
            status.status = "completed"
            status.finished_at = datetime.now(timezone.utc)
            return status

        asyncio.create_task(self._run(tickers, status, force=force))
        return status

    async def _run(
        self,
        tickers: list[str],
        status: FanoutStatus,
        *,
        force: bool,
    ) -> None:
        # `completed_tickers` increments whether or not each stage
        # succeeded — the name means "processed, moved past", not "all
        # stages green." Per-ticker failures surface in `errors[]`.
        # CancelledError (BaseException subclass) bypasses `except
        # Exception` below and propagates via the `finally` block, which
        # is the intended shutdown behaviour.
        try:
            for ticker in tickers:
                status.current_ticker = ticker
                await self._run_one_ticker(ticker, status, force=force)
                status.completed_tickers += 1
            status.status = "completed"
        except Exception as exc:  # orchestrator-level crash only
            logger.exception("Fanout orchestrator failed (id=%s)", status.fanout_id)
            status.status = "failed"
            status.errors.append(
                FanoutError(
                    ticker=status.current_ticker or "?",
                    stage=status.current_stage or "ingest",
                    message=f"orchestrator crash: {exc!r}",
                )
            )
        finally:
            status.current_ticker = None
            status.current_stage = None
            status.finished_at = datetime.now(timezone.utc)
            # If neither the success nor the `except Exception` path ran,
            # something like CancelledError escaped — don't leave the
            # status stuck on "running" with finished_at populated.
            if status.status == "running":
                status.status = "failed"

    async def _run_one_ticker(
        self,
        ticker: str,
        status: FanoutStatus,
        *,
        force: bool,
    ) -> None:
        """Run ingest → extract → resolve for one ticker. Per-stage errors
        are captured and do not abort the outer loop."""
        # Stage 1: ingest. Note: these service functions do NOT commit
        # — existing callers in api/filings.py commit after each one, so
        # we do the same here. async_session uses expire_on_commit=False.
        status.current_stage = "ingest"
        try:
            async with async_session() as db:
                summary = await edgar_sections_ingest.ingest_ticker_sections(
                    ticker, db=db, edgar=self._edgar
                )
                await db.commit()
            # `ingest_ticker_sections` returns a summary with `errors: []`
            # rather than raising on per-form problems (e.g., no CIK, no
            # recent filings). Surface those so the status endpoint shows
            # them instead of a silent success.
            for msg in summary.get("errors", []) or []:
                status.errors.append(
                    FanoutError(ticker=ticker, stage="ingest", message=str(msg))
                )
        except Exception as exc:
            logger.warning("Fanout ingest failed for %s: %r", ticker, exc)
            status.errors.append(
                FanoutError(ticker=ticker, stage="ingest", message=str(exc))
            )
            return  # no point extracting what we couldn't ingest

        # Stage 2: extract
        status.current_stage = "extract"
        try:
            async with async_session() as db:
                await edgar_relationships.extract_ticker_relationships(
                    ticker, db=db, force=force
                )
                await db.commit()
        except Exception as exc:
            logger.warning("Fanout extract failed for %s: %r", ticker, exc)
            status.errors.append(
                FanoutError(ticker=ticker, stage="extract", message=str(exc))
            )
            return  # no point resolving empty rows

        # Stage 3: resolve
        status.current_stage = "resolve"
        try:
            async with async_session() as db:
                await counterparty_resolver.resolve_ticker_relationships(
                    ticker, db=db
                )
                await db.commit()
        except Exception as exc:
            logger.warning("Fanout resolve failed for %s: %r", ticker, exc)
            status.errors.append(
                FanoutError(ticker=ticker, stage="resolve", message=str(exc))
            )


