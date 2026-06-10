"""8-K event classifier — item-code prefilter + one Haiku call per filing.

Same structured-output pattern as edgar_relationships.py: `complete()` with
an assistant prefill, parsed via parse_structured_output. Never raises —
all error paths return (None, error_string).
"""
from __future__ import annotations

import logging

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from backend.app.graph.llm import HAIKU, complete
from backend.app.graph.output_parser import parse_structured_output

logger = logging.getLogger(__name__)

# Items that are pure noise on their own: Reg FD disclosure + exhibits.
# 2.02 (results) is deliberately NOT here — guidance changes arrive in
# earnings 8-Ks; materiality is the gate for those, not the prefilter.
SKIPPABLE_ITEMS = {"7.01", "9.01"}

# Same per-document budget as relationship extraction (~3.5K tokens).
DOC_CHAR_BUDGET = 15000

ALLOWED_EVENT_TYPES = ("guidance", "personnel", "ma", "financing", "other")
ALLOWED_MATERIALITY = ("high", "medium", "low")


class EventClassification(BaseModel):
    event_type: str = Field(
        ..., description="One of: guidance, personnel, ma, financing, other."
    )
    materiality: str = Field(..., description="One of: high, medium, low.")
    headline: str = Field(
        ..., description="One factual line, max ~120 chars, no ticker prefix."
    )
    summary: str = Field(..., description="1-2 sentences. What happened and why it matters.")


def should_classify(item_codes: str | None) -> bool:
    """False only when the filing discloses a NON-EMPTY subset of
    {7.01, 9.01}. Empty/missing items = missing metadata → classify."""
    items = {c.strip() for c in (item_codes or "").split(",") if c.strip()}
    if not items:
        return True
    return not items.issubset(SKIPPABLE_ITEMS)


_SYSTEM_PROMPT = """You classify SEC 8-K filings for a personal stock-research dashboard. Given the filing text, output the dominant event type, its materiality to an investor with a long thesis on the stock, a one-line headline, and a 1-2 sentence summary.

event_type — pick the dominant one:
- guidance: changes to financial guidance or outlook, preliminary results, earnings releases that raise/cut/introduce guidance
- personnel: executive or director departures, appointments, terminations (Item 5.02)
- ma: mergers, acquisitions, divestitures, material definitive agreements tied to M&A
- financing: debt issuance, credit agreements, equity offerings, buyback or dividend changes
- other: anything else (legal, restructuring, listing matters, routine items)

materiality:
- high: likely to move the stock or change an investment thesis — guidance cuts/raises, CEO/CFO departure, M&A announcement, bankruptcy, restatement, delisting notice
- medium: noteworthy but not thesis-changing on its own
- low: administrative or mechanical — routine earnings 8-K with no guidance change, housekeeping amendments, annual-meeting vote results

Rules:
- Judge ONLY from the provided text. Do not use background knowledge about the company.
- headline: one factual line (max ~120 characters). No editorializing.
- summary: 1-2 sentences, concrete (names, numbers, dates from the text).

Output strict JSON:
{
  "event_type": "guidance|personnel|ma|financing|other",
  "materiality": "high|medium|low",
  "headline": "string",
  "summary": "string"
}"""

_USER_TEMPLATE = """Ticker: {ticker}
Form: 8-K filed {filing_date}
Item codes: {item_codes}

Filing text (possibly truncated to {budget} chars):
\"\"\"
{text}
\"\"\"

Classify this 8-K. Output the JSON object described in the system prompt."""


def _strip_html(text: str) -> str:
    """8-K primary documents are HTML; send Haiku visible text only."""
    try:
        return BeautifulSoup(text, "lxml").get_text(" ", strip=True)
    except Exception:
        return text


async def classify_8k(
    *, ticker: str, filing_date: str, item_codes: str | None, text: str
) -> tuple[EventClassification | None, str | None]:
    plain = _strip_html(text)[:DOC_CHAR_BUDGET]
    prompt = _USER_TEMPLATE.format(
        ticker=ticker.upper(),
        filing_date=filing_date,
        item_codes=item_codes or "unknown",
        budget=DOC_CHAR_BUDGET,
        text=plain,
    )
    try:
        raw = await complete(
            system=_SYSTEM_PROMPT,
            user=prompt,
            model=HAIKU,
            max_tokens=600,
            assistant_prefill='{"event_type":',
        )
    except Exception as e:
        logger.warning("8-K classify call failed for %s: %s", ticker, e)
        return None, f"haiku_call_failed: {e}"

    parsed, err = parse_structured_output(raw, EventClassification)
    if parsed is None:
        logger.warning("8-K classify parse failed for %s: %s; raw head: %r",
                       ticker, err, raw[:300])
        return None, err or "unknown_parse_error"

    event_type = parsed.event_type.strip().lower()
    if event_type not in ALLOWED_EVENT_TYPES:
        event_type = "other"
    materiality = parsed.materiality.strip().lower()
    if materiality not in ALLOWED_MATERIALITY:
        # Don't guess a grade — error means "retry next run" (no tombstone).
        return None, f"invalid materiality: {parsed.materiality!r}"

    return EventClassification(
        event_type=event_type,
        materiality=materiality,
        headline=parsed.headline.strip()[:256],
        summary=parsed.summary.strip(),
    ), None
