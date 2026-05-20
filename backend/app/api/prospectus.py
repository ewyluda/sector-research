"""HTTP surface for prospectus reports."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.prospectus_report import ProspectusReport
from backend.app.services.prospectus_service import ProspectusService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prospectus", tags=["prospectus"])


class CreateReportRequest(BaseModel):
    url_or_accession: str
    theme_id: str | None = None


def get_prospectus_service(request: Request) -> ProspectusService:
    svc = getattr(request.app.state, "prospectus", None)
    if svc is None:
        raise HTTPException(status_code=500, detail="prospectus service not initialized")
    return svc


@router.post("", status_code=202)
async def create_report(
    body: CreateReportRequest,
    svc: ProspectusService = Depends(get_prospectus_service),
):
    try:
        rid = await svc.kick_off(
            url_or_accession=body.url_or_accession, theme_id=body.theme_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"report_id": rid}


@router.get("/{report_id}")
async def get_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(ProspectusReport).where(ProspectusReport.id == str(report_id))
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="prospectus report not found")
    return _serialize(row)


@router.get("/{report_id}/stream")
async def stream_report(
    report_id: UUID, svc: ProspectusService = Depends(get_prospectus_service)
):
    async def gen():
        try:
            async for evt in svc.event_stream(str(report_id)):
                yield f"data: {json.dumps(evt)}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("")
async def list_reports(db: AsyncSession = Depends(get_db), limit: int = 50):
    rows = (await db.execute(
        select(ProspectusReport)
        .order_by(ProspectusReport.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [_serialize(r) for r in rows]


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        delete(ProspectusReport).where(ProspectusReport.id == str(report_id))
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="prospectus report not found")
    await db.commit()
    return None


def _serialize(r: ProspectusReport) -> dict:
    return {
        "id": str(r.id),
        "accession_number": r.accession_number,
        "issuer_cik": r.issuer_cik,
        "issuer_name": r.issuer_name,
        "proposed_ticker": r.proposed_ticker,
        "synthetic_ticker": r.synthetic_ticker,
        "theme_id": str(r.theme_id) if r.theme_id else None,
        "status": r.status,
        "step_outputs": r.step_outputs,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
