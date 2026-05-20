"""ProspectusService — orchestrates the 4-step prospectus pipeline.

Mirrors WorkspaceService:
  - in-memory dict[report_id, asyncio.Queue] for SSE
  - kick_off creates the row + spawns a background task
  - each step runs in its own session with explicit commit
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, AsyncIterator
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient
from backend.app.db import unit_of_work
from backend.app.models.filing import Relationship
from backend.app.models.prospectus_report import ProspectusReport
from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    RelationshipsStepOutput,
    RelationshipSummary,
)
from backend.app.services.counterparty_resolver import resolve_ticker_relationships
from backend.app.services.edgar_relationships import extract_ticker_relationships
from backend.app.services.edgar_sections_ingest import get_latest_sections_by_keys
from backend.app.services.prospectus_categories import run_categories
from backend.app.services.prospectus_financials import extract_financials
from backend.app.services.prospectus_ingest import (
    SourceInput,
    ingest_prospectus,
    parse_source_input,
)
from backend.app.services.prospectus_thesis import synthesize_thesis
from backend.app.services.relationship_context import (
    CounterpartyContext,
    get_counterparty_context,
)

logger = logging.getLogger(__name__)

TERMINAL_EVENTS = {"prospectus_complete", "prospectus_failed"}


class ProspectusService:
    def __init__(self, *, edgar: EdgarClient, fred: Any = None) -> None:
        self._edgar = edgar
        self._fred = fred
        self._queues: dict[str, asyncio.Queue] = {}

    # ── SSE plumbing ──────────────────────────────────────────────────────────

    def _q(self, rid: str) -> asyncio.Queue:
        q = self._queues.get(rid)
        if q is None:
            q = asyncio.Queue()
            self._queues[rid] = q
        return q

    def _emit(self, rid: str, evt: dict) -> None:
        try:
            self._q(rid).put_nowait(evt)
        except asyncio.QueueFull:
            logger.warning("prospectus SSE queue full for %s; dropping", rid)

    async def event_stream(self, rid: str) -> AsyncIterator[dict]:
        q = self._q(rid)
        while True:
            evt = await q.get()
            yield evt
            if evt.get("type") in TERMINAL_EVENTS:
                while not q.empty():
                    yield q.get_nowait()
                return

    # ── Kick-off ──────────────────────────────────────────────────────────────

    async def kick_off(self, *, url_or_accession: str, theme_id: str | None) -> str:
        source = parse_source_input(url_or_accession)

        cik_trimmed = source.cik_trimmed
        if not cik_trimmed:
            raise ValueError(
                "Bare accession number input not yet supported — please paste the full URL"
            )
        cik_padded = cik_trimmed.zfill(10)
        subs, _ = await self._edgar.get_submissions(cik_padded)
        issuer_name = subs.get("name") or subs.get("entityName") or "(unknown issuer)"

        rid = str(uuid4())
        async with unit_of_work() as db:
            db.add(ProspectusReport(
                id=rid,
                accession_number=source.accession_number,
                issuer_cik=cik_padded,
                issuer_name=issuer_name,
                proposed_ticker=None,
                theme_id=theme_id,
                status="ingesting",
                step_outputs={},
            ))

        asyncio.create_task(self._run_pipeline(rid, source))
        return rid

    # ── Pipeline ─────────────────────────────────────────────────────────────

    async def _run_pipeline(self, rid: str, source: SourceInput) -> None:
        try:
            await self._step_ingest(rid, source)
            await self._step_relationships(rid)
            await self._step_categories(rid)
            await self._step_thesis(rid)
            await self._set_status(rid, "completed")
            self._emit(rid, {"type": "prospectus_complete", "report_id": rid})
        except Exception as e:
            logger.exception("prospectus pipeline failed for %s", rid)
            await self._set_status(rid, "failed", error=f"{e}\n{traceback.format_exc()}")
            self._emit(rid, {"type": "prospectus_failed", "report_id": rid, "error": str(e)})

    async def _load_report(self, db: AsyncSession, rid: str) -> ProspectusReport:
        row = (await db.execute(
            select(ProspectusReport).where(ProspectusReport.id == rid)
        )).scalar_one()
        return row

    async def _set_status(self, rid: str, status: str, *, error: str | None = None) -> None:
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            row.status = status
            if error:
                row.error_message = error
            await db.commit()

    async def _save_step(self, rid: str, step: str, payload: dict) -> None:
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            outputs = dict(row.step_outputs or {})
            outputs[step] = payload
            row.step_outputs = outputs
            await db.commit()

    # ── Steps ────────────────────────────────────────────────────────────────

    async def _step_ingest(self, rid: str, source: SourceInput) -> None:
        self._emit(rid, {"type": "step_start", "step": "ingest"})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            synthetic_ticker = row.synthetic_ticker
            _filing, ingest_out = await ingest_prospectus(
                source=source,
                synthetic_ticker=synthetic_ticker,
                issuer_cik=row.issuer_cik,
                db=db,
                edgar=self._edgar,
            )
            # Pull MD&A text for the financials extractor (Selected Financials
            # text lives in s1_mda in the regex defs — there's no separate
            # section_key today; the prompt itself focuses Sonnet on the right
            # parts of the MD&A blob.)
            sections = await get_latest_sections_by_keys(
                synthetic_ticker, ["s1_mda"], db,
            )
            mda_text = (sections.get("s1_mda") or {}).get("text") or ""
            await db.commit()

        financials = await extract_financials(
            mda_text=mda_text, selected_financials_text="",
        )
        ingest_out.financials = financials
        await self._save_step(rid, "ingest", ingest_out.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "ingest"})

    async def _step_relationships(self, rid: str) -> None:
        self._emit(rid, {"type": "step_start", "step": "relationships"})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            synthetic_ticker = row.synthetic_ticker
            # Extract + resolve side-effects persist into the DB; we read the
            # final rows back to build the step payload.
            await extract_ticker_relationships(
                ticker=synthetic_ticker, db=db, force=False,
            )
            await resolve_ticker_relationships(
                ticker=synthetic_ticker, db=db,
            )
            # Pull full Relationship rows directly so we have verbatim_quote;
            # CounterpartyEntry (from get_counterparty_context) doesn't expose it.
            rel_rows = (await db.execute(
                select(Relationship).where(Relationship.ticker == synthetic_ticker)
            )).scalars().all()
            edges = [RelationshipSummary(
                counterparty_name=r.counterparty_name or "",
                relationship_type=r.relationship_type or "other",
                magnitude_pct=r.magnitude_pct,
                resolved_to_ticker=r.resolved_to_ticker,
                verbatim_quote=r.verbatim_quote or "",
            ) for r in rel_rows]
            resolved_count = sum(1 for r in rel_rows if r.resolved_to_ticker)
            await db.commit()

        payload = RelationshipsStepOutput(
            edges_extracted=len(edges),
            edges_resolved=resolved_count,
            edges=edges,
        )
        await self._save_step(rid, "relationships", payload.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "relationships"})

    async def _step_categories(self, rid: str) -> None:
        self._emit(rid, {"type": "step_start", "step": "categories"})
        from backend.app.graph.prospectus_prompts import CATEGORY_SECTION_ROUTING

        all_keys = sorted({k for keys in CATEGORY_SECTION_ROUTING.values() for k in keys})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            synthetic_ticker = row.synthetic_ticker
            sections = await get_latest_sections_by_keys(synthetic_ticker, all_keys, db)
            sections_text = {k: (v.get("text") or "") for k, v in sections.items()}
            ctx = await get_counterparty_context(synthetic_ticker, db)
            issuer_name = row.issuer_name
            filing_date = ""
            outputs = row.step_outputs or {}
            form_type = (outputs.get("ingest") or {}).get("form_type") or "S-1"

        counterparty_blob = self._render_counterparty_blob(ctx)
        macro_blob = await self._fetch_macro_blob()

        out = await run_categories(
            issuer_name=issuer_name,
            filing_date=filing_date,
            form_type=form_type,
            sections_text=sections_text,
            counterparty_context=counterparty_blob,
            macro_indicators=macro_blob,
        )
        await self._save_step(rid, "categories", out.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "categories"})

    async def _step_thesis(self, rid: str) -> None:
        self._emit(rid, {"type": "step_start", "step": "thesis"})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            outputs = row.step_outputs or {}
            issuer_name = row.issuer_name
        categories_payload = outputs.get("categories") or {}
        financials_payload = (outputs.get("ingest") or {}).get("financials") or {}

        thesis = await synthesize_thesis(
            issuer_name=issuer_name,
            categories=CategoriesStepOutput.model_validate(categories_payload),
            financials_json=financials_payload,
        )
        await self._save_step(rid, "thesis", thesis.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "thesis"})

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _render_counterparty_blob(self, ctx: CounterpartyContext) -> str:
        # ctx.outbound is dict[relationship_type, list[CounterpartyEntry]].
        # We render a flat at-a-glance list grouped by type for prospectus
        # categories — full per-type template in relationship_context.py is
        # used by the equity pipeline only.
        if not ctx.has_data:
            return ""
        lines: list[str] = []
        for rel_type, entries in ctx.outbound.items():
            for e in entries:
                name = e.name or "(unnamed)"
                mag = f" ({e.magnitude_pct}%)" if e.magnitude_pct else ""
                ticker = f" [${e.resolved_ticker}]" if e.resolved_ticker else ""
                lines.append(f"- {name}{ticker} — {rel_type}{mag}")
        return "\n".join(lines)

    async def _fetch_macro_blob(self) -> str:
        if self._fred is None or not getattr(self._fred, "available", lambda: False)():
            return ""
        try:
            data, _ = await self._fred.get_all_macro()
        except Exception as e:
            logger.warning("FRED fetch failed for prospectus: %s", e)
            return ""
        # Compact one-line-per-series summary: latest observation only.
        lines: list[str] = []
        for series, points in (data or {}).items():
            if not points:
                continue
            latest = points[-1]
            val = latest.get("value")
            dt = latest.get("date")
            if val is not None and dt:
                lines.append(f"- {series}: {val} ({dt})")
        return "\n".join(lines)
