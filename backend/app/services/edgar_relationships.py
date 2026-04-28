"""Extract business relationships from filing sections using Haiku.

Runs on-demand (not inline) via POST /api/filings/extract-relationships/{ticker}.
For each ingested filing section that doesn't yet have extracted relationships,
calls Haiku once with a structured-output schema and persists the results into
the `relationships` table.

Idempotent on (filing_id, section_key) — existing extractions are never
re-run. To force re-extraction, delete the existing rows first.

Token cost control: each section is truncated to SECTION_CHAR_BUDGET before
the call. At ~15K chars per section, one full ticker (3 sections extracted —
Item 1, 1A, 7 / Item 2) burns ~12K input tokens at Haiku pricing.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.graph.llm import HAIKU, complete
from backend.app.graph.output_parser import parse_structured_output
from backend.app.models.filing import Filing, FilingSection, Relationship

logger = logging.getLogger(__name__)

# Only these sections contain counterparty narrative. DEF 14A is governance —
# no meaningful business relationships to extract.
EXTRACTABLE_SECTION_KEYS: tuple[str, ...] = (
    "item_1_business",
    "item_1a_risk_factors",
    "item_7_mda",
    "item_2_mda_10q",
)

# Upper bound on characters sent to Haiku per section. 15K chars ≈ 3.5K
# tokens — well within Haiku's context and keeps the per-ticker bill small.
SECTION_CHAR_BUDGET = 15000

ALLOWED_TYPES: tuple[str, ...] = (
    "customer", "supplier", "partner", "licensor",
    "licensee", "distributor", "reseller", "joint_venture", "other",
)


# ── Structured output schemas ─────────────────────────────────────────────────


class ExtractedRelationship(BaseModel):
    counterparty_name: str = Field(
        ...,
        description=(
            "Name of the other entity as it appears in the filing. Use the "
            "exact casing from the text. Empty string when the filing "
            "describes an unnamed concentration — in that case also set "
            "`unnamed` to true."
        ),
    )
    relationship_type: str = Field(
        ...,
        description=(
            "One of: customer, supplier, partner, licensor, licensee, "
            "distributor, reseller, joint_venture, other."
        ),
    )
    magnitude_pct: float | None = Field(
        default=None,
        description=(
            "Percentage when the filing discloses one (e.g. '15% of "
            "revenue'). Null when not disclosed."
        ),
    )
    unnamed: bool = Field(
        default=False,
        description=(
            "True when the filing describes a concentration without naming "
            "the counterparty (e.g. 'one customer represented 12% of "
            "revenue'). When true, counterparty_name should be empty."
        ),
    )
    verbatim_quote: str = Field(
        ...,
        description=(
            "The sentence(s) in the filing that establish this relationship. "
            "Copy verbatim (max ~500 chars) — this is an audit trail."
        ),
    )


class ExtractionResult(BaseModel):
    relationships: list[ExtractedRelationship] = Field(
        default_factory=list,
        description="All distinct counterparty relationships found in this section.",
    )


# ── Prompts ──────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """You extract business-relationship disclosures from SEC filing sections or earnings call transcripts.

A relationship is any named business counterparty (customer, supplier, partner, licensor, licensee, distributor, reseller, joint-venture partner) OR an UNNAMED counterparty concentration (e.g. "one customer represented 12% of revenue") that the filer discloses.

Rules:
- Only extract relationships that the filer explicitly describes in the text. Do NOT infer from company background knowledge.
- Copy the counterparty name EXACTLY as written (including "Inc.", "Corporation", etc.). Don't normalize.
- Pull a verbatim quote (the sentence or two that establishes the relationship). Don't paraphrase.
- When the filing describes a concentration without naming the counterparty, set unnamed=true and counterparty_name="".
- Skip generic mentions of "customers" or "suppliers" — only extract specific entities or specific concentrations.
- Skip analysts and brokerage firm participants in earnings call Q&A — they ask questions but are not counterparties.
- Skip internal entities (subsidiaries, the filer's own products).
- Deduplicate by (counterparty_name, relationship_type). Pick the quote with the most context.
- Extract 0 relationships if none are disclosed — don't force matches.

Output strict JSON matching this schema:
{
  "relationships": [
    {
      "counterparty_name": "string (exact name or empty for unnamed)",
      "relationship_type": "customer|supplier|partner|licensor|licensee|distributor|reseller|joint_venture|other",
      "magnitude_pct": number | null,
      "unnamed": boolean,
      "verbatim_quote": "verbatim sentence(s) up to ~500 chars"
    }
  ]
}"""

_USER_TEMPLATE = """Ticker: {ticker}
Section: {section_key} ({heading})
Filing: {form_type} filed {filing_date}

Section text (possibly truncated to {budget} chars):
\"\"\"
{text}
\"\"\"

Extract all counterparty relationships disclosed in the section above. Output the JSON object described in the system prompt."""


# ── Extraction ────────────────────────────────────────────────────────────────


async def _call_haiku_on_section(
    ticker: str, form_type: str, filing_date: str,
    section_key: str, heading: str | None, text: str,
) -> tuple[list[ExtractedRelationship], str | None]:
    """Run one Haiku extraction pass. Returns (relationships, error).

    On parse failure returns an empty list and an error string so the caller
    can persist nothing and log. Never raises.
    """
    truncated = text[:SECTION_CHAR_BUDGET]
    prompt = _USER_TEMPLATE.format(
        ticker=ticker.upper(),
        section_key=section_key,
        heading=heading or section_key,
        form_type=form_type,
        filing_date=filing_date,
        budget=SECTION_CHAR_BUDGET,
        text=truncated,
    )
    try:
        raw = await complete(
            system=_SYSTEM_PROMPT,
            user=prompt,
            model=HAIKU,
            max_tokens=3000,
            # Prefill locks Haiku into JSON-first output.
            assistant_prefill='{"relationships":',
        )
    except Exception as e:
        logger.warning("Haiku relationship call failed for %s %s: %s",
                       ticker, section_key, e)
        return [], f"haiku_call_failed: {e}"

    parsed, err = parse_structured_output(raw, ExtractionResult)
    if parsed is None:
        logger.warning(
            "relationship parse failed for %s %s: %s; raw head: %r",
            ticker, section_key, err, raw[:400],
        )
        return [], err or "unknown_parse_error"
    return parsed.relationships, None


def _normalize_relationship(e: ExtractedRelationship) -> ExtractedRelationship | None:
    """Drop obviously bad rows; normalize fields to pass the DB constraint."""
    rel_type = e.relationship_type.strip().lower()
    if rel_type not in ALLOWED_TYPES:
        return None
    name = (e.counterparty_name or "").strip()[:256]
    quote = (e.verbatim_quote or "").strip()[:2000]
    if e.unnamed:
        # Synthesize a name so the UNIQUE constraint doesn't collapse all
        # unnamed entries of the same type in the same section into one row.
        # Use the magnitude as the discriminator when present.
        discriminator = (
            f" ({e.magnitude_pct}%)" if e.magnitude_pct is not None else ""
        )
        name = f"[unnamed {rel_type}]{discriminator}"
    if not name:
        return None
    return ExtractedRelationship(
        counterparty_name=name,
        relationship_type=rel_type,
        magnitude_pct=e.magnitude_pct,
        unnamed=e.unnamed,
        verbatim_quote=quote,
    )


async def extract_ticker_relationships(
    ticker: str, db: AsyncSession,
    *, force: bool = False,
) -> dict:
    """Extract relationships for every ingested section the ticker has.

    Skips (filing_id, section_key) pairs that already have extraction rows
    (any row counts — we only run the pass once per section). Set force=True
    to delete existing rows before re-extracting.
    """
    ticker = ticker.upper()
    summary: dict = {
        "ticker": ticker,
        "sections_considered": 0,
        "sections_extracted": 0,
        "sections_skipped_existing": 0,
        "sections_skipped_unextractable": 0,
        "relationships_added": 0,
        "relationships_dropped": 0,
        "per_section": [],
        "errors": [],
    }

    rows = await db.execute(
        select(FilingSection, Filing)
        .join(Filing, Filing.id == FilingSection.filing_id)
        .where(
            Filing.ticker == ticker,
            FilingSection.section_key.in_(EXTRACTABLE_SECTION_KEYS),
        )
        .order_by(Filing.filing_date.desc())
    )
    entries = rows.all()
    if not entries:
        summary["errors"].append("no ingested sections for ticker")
        return summary

    for section, filing in entries:
        summary["sections_considered"] += 1
        per: dict = {
            "filing_id": filing.id,
            "accession_number": filing.accession_number,
            "form_type": filing.form_type,
            "filing_date": filing.filing_date.isoformat(),
            "section_key": section.section_key,
            "relationships_added": 0,
            "relationships_dropped": 0,
            "skipped": None,
            "error": None,
        }
        summary["per_section"].append(per)

        # Idempotency check:
        #   1. relationships_extracted_at timestamp signals prior attempt
        #      (including zero-relationship results). Skip.
        #   2. For rows written before the column existed, an existing
        #      Relationship row also means "already attempted" — backfill
        #      the timestamp so subsequent runs use check #1.
        already_attempted = section.relationships_extracted_at is not None
        if not already_attempted:
            existing_row = await db.execute(
                select(Relationship.id).where(
                    Relationship.filing_id == filing.id,
                    Relationship.section_key == section.section_key,
                ).limit(1)
            )
            if existing_row.first() is not None:
                section.relationships_extracted_at = datetime.utcnow()
                already_attempted = True

        if already_attempted and not force:
            per["skipped"] = "existing_extraction"
            summary["sections_skipped_existing"] += 1
            continue
        if already_attempted and force:
            await db.execute(
                Relationship.__table__.delete().where(
                    Relationship.filing_id == filing.id,
                    Relationship.section_key == section.section_key,
                )
            )

        relationships, err = await _call_haiku_on_section(
            ticker=ticker,
            form_type=filing.form_type,
            filing_date=filing.filing_date.isoformat(),
            section_key=section.section_key,
            heading=section.heading,
            text=section.text,
        )
        if err is not None:
            per["error"] = err
            summary["errors"].append(f"{section.section_key}: {err}")
            # Don't mark as attempted — we want to retry on next run.
            continue

        # Mark the section as attempted regardless of whether relationships
        # were found. Zero-relationship sections are still "done".
        section.relationships_extracted_at = datetime.utcnow()

        # Insert extractions, deduplicating per (counterparty, rel_type)
        # because the LLM sometimes reports the same relationship twice.
        seen: set[tuple[str, str]] = set()
        for raw_rel in relationships:
            normalized = _normalize_relationship(raw_rel)
            if normalized is None:
                per["relationships_dropped"] += 1
                summary["relationships_dropped"] += 1
                continue
            key = (normalized.counterparty_name, normalized.relationship_type)
            if key in seen:
                per["relationships_dropped"] += 1
                summary["relationships_dropped"] += 1
                continue
            seen.add(key)
            db.add(Relationship(
                filing_id=filing.id,
                ticker=ticker,
                section_key=section.section_key,
                counterparty_name=normalized.counterparty_name,
                relationship_type=normalized.relationship_type,
                magnitude_pct=normalized.magnitude_pct,
                unnamed=normalized.unnamed,
                verbatim_quote=normalized.verbatim_quote,
            ))
            per["relationships_added"] += 1
            summary["relationships_added"] += 1

        summary["sections_extracted"] += 1

    await db.flush()
    logger.info(
        "relationships: %s — %d sections extracted, %d relationships added",
        ticker, summary["sections_extracted"], summary["relationships_added"],
    )
    return summary


async def extract_batch_relationships(
    tickers: Iterable[str], db: AsyncSession, *, force: bool = False,
) -> list[dict]:
    """Sequential batch — Haiku is rate-limited at the API level, and we
    want each ticker to commit before starting the next."""
    out: list[dict] = []
    for t in tickers:
        try:
            out.append(await extract_ticker_relationships(t, db, force=force))
        except Exception as e:
            logger.exception("relationship extraction failed for %s", t)
            out.append({"ticker": t.upper(), "errors": [f"unhandled: {e}"]})
    return out
