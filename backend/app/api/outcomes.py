"""GET /api/outcomes/*, POST /api/outcomes/backfill.

Stub registered in main.py — full endpoints filled in by subsequent tasks.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/outcomes", tags=["outcomes"])
