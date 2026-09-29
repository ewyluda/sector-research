"""Earnings transcript multi-pass analysis extracted from nodes.py (M2.2).

This module holds ``run_transcript_analysis``, the 6-pass async function that
processes earnings call transcripts for the deep-dive node.  It was lifted from
``backend.app.graph.nodes`` as part of the M2.2 campaign unchanged except for
import paths (``complete`` is imported function-locally — patch ``llm.complete``
in tests, not this module).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from backend.app.clients.fmp import FMPClient
from backend.app.graph.llm import FAST_MODEL, DEEP_MODEL
from backend.app.graph.output_parser import extract_json_value
from backend.app.graph.prompts import (
    TRANSCRIPT_PASS1_SYSTEM,
    TRANSCRIPT_PASS2_SYSTEM,
    TRANSCRIPT_PASS3_SYSTEM,
    TRANSCRIPT_PASS4_SYSTEM,
    TRANSCRIPT_PASS5_SYSTEM,
    TRANSCRIPT_PASS6_SYSTEM,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptAnalysisResult:
    """Typed return value for ``run_transcript_analysis``.

    status:
      - "ok"       — analysis ran and produced a results dict
      - "no_data"  — no transcripts were provided; value is None
      - "error"    — an unexpected exception aborted the run; value is None
    """

    status: Literal["ok", "no_data", "error"]
    value: dict | None
    error: str | None


async def run_transcript_analysis(
    ticker: str,
    transcripts: list[dict],
    fmp: FMPClient,
) -> TranscriptAnalysisResult:
    """
    Run all 6 transcript passes. Returns a TranscriptAnalysisResult.
    Called from within the deep_dive node for Management & Governance
    and Growth & Earnings categories.
    """
    from backend.app.graph.llm import complete

    if not transcripts:
        return TranscriptAnalysisResult(status="no_data", value=None, error=None)

    def _parse_pass(raw):
        """Parse a pass's JSON. Models wrap it in ```json fences or add a
        preamble, and a bare json.loads left all 128 stored passes as strings
        that build_transcript_context then skipped — so transcript analysis
        never reached a deep-dive prompt. Keep the raw string only when no
        JSON can be recovered."""
        if isinstance(raw, Exception):
            return str(raw)
        if isinstance(raw, str):
            value = extract_json_value(raw)
            if value is None:
                logger.warning("transcript pass returned no JSON for %s; head: %r", ticker, raw[:200])
                return raw
            return value
        return raw

    try:
        latest = transcripts[0] if transcripts else {}
        transcript_text = latest.get("content", latest.get("transcript", "No transcript content"))[:28000]

        all_transcripts_text = "\n\n---QUARTER BREAK---\n\n".join(
            t.get("content", t.get("transcript", ""))[:11200] for t in transcripts[:4]
        )

        results = {}

        # Passes 1–2: Haiku. Their JSON runs past 1,000 tokens on a full
        # call; the old 800/1,000 caps truncated every one (live, 2026-09-27).
        pass1, pass2 = await asyncio.gather(
            complete(TRANSCRIPT_PASS1_SYSTEM, transcript_text, model=FAST_MODEL, max_tokens=4000),
            complete(TRANSCRIPT_PASS2_SYSTEM, transcript_text, model=FAST_MODEL, max_tokens=4000),
            return_exceptions=True,
        )
        results["pass1_claims"] = _parse_pass(pass1)
        results["pass2_tiers"] = _parse_pass(pass2)

        # Passes 3–6: Sonnet
        qa_section = transcript_text[transcript_text.lower().find("question"):] if "question" in transcript_text.lower() else transcript_text
        qa_section = qa_section[:16800]
        pass3, pass4, pass5 = await asyncio.gather(
            complete(TRANSCRIPT_PASS3_SYSTEM, qa_section, model=DEEP_MODEL, max_tokens=1000),
            complete(TRANSCRIPT_PASS4_SYSTEM, all_transcripts_text, model=DEEP_MODEL, max_tokens=1200),
            complete(TRANSCRIPT_PASS5_SYSTEM, all_transcripts_text, model=DEEP_MODEL, max_tokens=1000),
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
                pass6 = await complete(TRANSCRIPT_PASS6_SYSTEM, transcript_text[:4000], model=DEEP_MODEL, max_tokens=1200)
            except Exception as exc:
                pass6 = exc
            results["pass6_bom"] = _parse_pass(pass6)
        else:
            results["pass6_bom"] = None

        return TranscriptAnalysisResult(status="ok", value=results, error=None)

    except Exception as exc:  # noqa: BLE001
        logger.warning("run_transcript_analysis: structural failure for %s", ticker, exc_info=True)
        return TranscriptAnalysisResult(status="error", value=None, error=str(exc))
