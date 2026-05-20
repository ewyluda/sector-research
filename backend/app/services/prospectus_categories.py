"""Parallel per-category analysis for a prospectus report.

Mirrors graph/nodes.py::node_deep_dive but skips the FMP/transcripts/
analyst-data scaffolding entirely. Each category gets a self-contained
prompt assembled from the S-1 sections it cares about.
"""
from __future__ import annotations

import asyncio
import json
import logging

from backend.app.graph.llm import SONNET, complete
from backend.app.graph.prospectus_prompts import (
    CATEGORY_FOCUS,
    CATEGORY_SECTION_ROUTING,
    CATEGORY_USES_MACRO,
    CATEGORY_USES_RELATIONSHIPS,
    PROSPECTUS_CATEGORIES,
    PROSPECTUS_SYSTEM,
    PROSPECTUS_USER,
    SECTION_BUDGET_CHARS,
)
from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    ProspectusCategoryResult,
)

logger = logging.getLogger(__name__)


def _render_filing_excerpts(sections_text: dict[str, str], keys: tuple[str, ...]) -> str:
    if not keys:
        return "_No S-1 sections routed to this category._"
    blocks: list[str] = []
    for key in keys:
        text = (sections_text.get(key) or "").strip()
        if not text:
            continue
        blocks.append(f"### {key}\n\n{text[:SECTION_BUDGET_CHARS]}")
    if not blocks:
        return "_The referenced S-1 sections were not extracted from this filing._"
    return "## S-1 Excerpts\n\n" + "\n\n".join(blocks)


async def _run_one_category(
    *,
    category: str,
    issuer_name: str,
    filing_date: str,
    form_type: str,
    sections_text: dict[str, str],
    counterparty_context: str,
    macro_indicators: str,
) -> ProspectusCategoryResult:
    keys = CATEGORY_SECTION_ROUTING.get(category, ())
    focus = CATEGORY_FOCUS.get(category, "")

    user = PROSPECTUS_USER.format(
        category=category,
        filing_excerpts=_render_filing_excerpts(sections_text, keys),
        counterparty_context=(
            "## Counterparty Context\n\n" + counterparty_context
            if category in CATEGORY_USES_RELATIONSHIPS and counterparty_context
            else ""
        ),
        macro_indicators=(
            "## Macro Indicators (FRED)\n\n" + macro_indicators
            if category in CATEGORY_USES_MACRO and macro_indicators
            else ""
        ),
        issuer_name=issuer_name,
        filing_date=filing_date,
        form_type=form_type,
    )
    if focus:
        user = user + "\n\n## Per-category focus\n\n" + focus

    raw = await complete(
        system=PROSPECTUS_SYSTEM.format(category=category),
        user=user,
        model=SONNET,
        max_tokens=3072,
        assistant_prefill='{"category":',
    )
    candidate = raw if raw.lstrip().startswith("{") else '{"category":' + raw
    payload = json.loads(candidate)
    return ProspectusCategoryResult.model_validate(payload)


async def run_categories(
    *,
    issuer_name: str,
    filing_date: str,
    form_type: str,
    sections_text: dict[str, str],
    counterparty_context: str,
    macro_indicators: str,
) -> CategoriesStepOutput:
    """Run all 7 categories in parallel. One failure does not abort the rest."""
    coros = {
        cat: _run_one_category(
            category=cat,
            issuer_name=issuer_name,
            filing_date=filing_date,
            form_type=form_type,
            sections_text=sections_text,
            counterparty_context=counterparty_context,
            macro_indicators=macro_indicators,
        )
        for cat in PROSPECTUS_CATEGORIES
    }
    results: dict[str, ProspectusCategoryResult] = {}
    failures: dict[str, str] = {}
    done = await asyncio.gather(*coros.values(), return_exceptions=True)
    for cat, outcome in zip(coros.keys(), done):
        if isinstance(outcome, Exception):
            logger.warning("[prospectus] category %r failed: %s", cat, outcome)
            failures[cat] = str(outcome)
        else:
            results[cat] = outcome
    return CategoriesStepOutput(results=results, failures=failures)
