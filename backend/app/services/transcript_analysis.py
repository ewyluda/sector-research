"""Earnings transcript multi-pass analysis extracted from nodes.py (M2.2).

This module holds ``run_transcript_analysis``, the 6-pass async function that
processes earnings call transcripts for the deep-dive node.  It was lifted from
``backend.app.graph.nodes`` as part of the M2.2 campaign; the function body is
byte-identical to its origin.
"""

from __future__ import annotations

import asyncio
import json
import logging

from backend.app.clients.fmp import FMPClient
from backend.app.graph.llm import HAIKU, SONNET
from backend.app.graph.prompts import (
    TRANSCRIPT_PASS1_SYSTEM,
    TRANSCRIPT_PASS2_SYSTEM,
    TRANSCRIPT_PASS3_SYSTEM,
    TRANSCRIPT_PASS4_SYSTEM,
    TRANSCRIPT_PASS5_SYSTEM,
    TRANSCRIPT_PASS6_SYSTEM,
)

logger = logging.getLogger(__name__)


async def run_transcript_analysis(
    ticker: str,
    transcripts: list[dict],
    fmp: FMPClient,
) -> dict:
    """
    Run all 6 transcript passes. Returns structured dict of results.
    Called from within the deep_dive node for Management & Governance
    and Growth & Earnings categories.
    """
    from backend.app.graph.llm import complete

    if not transcripts:
        return {"error": "No transcripts available"}

    def _parse_pass(raw):
        """Parse LLM response as JSON, falling back to raw string on failure."""
        if isinstance(raw, Exception):
            return str(raw)
        if isinstance(raw, str):
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                return raw
        return raw

    latest = transcripts[0] if transcripts else {}
    transcript_text = latest.get("content", latest.get("transcript", "No transcript content"))[:28000]

    all_transcripts_text = "\n\n---QUARTER BREAK---\n\n".join(
        t.get("content", t.get("transcript", ""))[:11200] for t in transcripts[:4]
    )

    results = {}

    # Passes 1–2: Haiku
    pass1, pass2 = await asyncio.gather(
        complete(TRANSCRIPT_PASS1_SYSTEM, transcript_text, model=HAIKU, max_tokens=1000),
        complete(TRANSCRIPT_PASS2_SYSTEM, transcript_text, model=HAIKU, max_tokens=800),
        return_exceptions=True,
    )
    results["pass1_claims"] = _parse_pass(pass1)
    results["pass2_tiers"] = _parse_pass(pass2)

    # Passes 3–6: Sonnet
    qa_section = transcript_text[transcript_text.lower().find("question"):] if "question" in transcript_text.lower() else transcript_text
    qa_section = qa_section[:16800]
    pass3, pass4, pass5 = await asyncio.gather(
        complete(TRANSCRIPT_PASS3_SYSTEM, qa_section, model=SONNET, max_tokens=1000),
        complete(TRANSCRIPT_PASS4_SYSTEM, all_transcripts_text, model=SONNET, max_tokens=1200),
        complete(TRANSCRIPT_PASS5_SYSTEM, all_transcripts_text, model=SONNET, max_tokens=1000),
        return_exceptions=True,
    )
    results["pass3_qa_tensions"] = _parse_pass(pass3)
    results["pass4_validation"] = _parse_pass(pass4)
    results["pass5_consistency"] = _parse_pass(pass5)

    # Pass 6: BOM inference (only on management-flagged capex disclosures)
    capex_keywords = ["billion", "capex", "capital expenditure", "data center", "infrastructure", "invest"]
    has_capex = any(kw in transcript_text.lower() for kw in capex_keywords)
    if has_capex:
        try:
            pass6 = await complete(TRANSCRIPT_PASS6_SYSTEM, transcript_text[:4000], model=SONNET, max_tokens=1200)
        except Exception as exc:
            pass6 = exc
        results["pass6_bom"] = _parse_pass(pass6)
    else:
        results["pass6_bom"] = None

    return results
