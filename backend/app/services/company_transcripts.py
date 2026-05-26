"""Company-workspace transcripts service.

Lists available earnings-call transcripts, fetches + segments a specific
quarter's transcript into speaker turns, and produces an on-demand AI summary
(Haiku). Kept separate from company_snapshot.py (which is fmp-only) because the
summary path calls the LLM.
"""
import re
from typing import Optional

from pydantic import BaseModel

from backend.app.graph.llm import HAIKU, complete


class TranscriptEvent(BaseModel):
    quarter: int
    fiscal_year: int
    date: str


class TranscriptList(BaseModel):
    ticker: str
    events: list[TranscriptEvent]


class TranscriptSegment(BaseModel):
    speaker: str
    text: str


class Transcript(BaseModel):
    ticker: str
    year: int
    quarter: int
    date: Optional[str] = None
    segments: list[TranscriptSegment]


class TranscriptSummary(BaseModel):
    summary_md: str


_SPEAKER_RE = re.compile(r"(?:^|\n)\s*([A-Z][^:\n]{1,40}?):\s")

# The frontend renders this with a lightweight markdown component that supports
# **bold** and "- " bullet lists separated by blank lines, but NOT ATX "#" headings —
# so the prompt formats sections as bold labels + blank-line-separated bullet lists.
# Kept > 500 chars so graph.llm.complete() enables ephemeral prompt caching (this
# fixed system prompt is reused on every summary request).
_SUMMARY_SYSTEM = (
    "You are a buy-side equity research analyst. Summarize the earnings-call "
    "transcript as concise markdown. Use these four sections in order, each labeled "
    "with a bold header on its own line and separated from the next section by a "
    "blank line: **Key Themes** (3-5 bullets on the quarter's most important "
    "narratives), **Guidance & Outlook** (forward guidance, targets, and any changes "
    "vs. prior commentary), **Q&A Highlights** (the most revealing analyst questions "
    "and management's answers — attribute each question to the analyst's name/firm "
    "when stated), and **Notable Quotes** (verbatim lines worth remembering, each "
    "attributed to the speaker by name). Format every bullet on its own line starting "
    "with '- ', and put a blank line between each section and before each bullet list. "
    "Be specific with the actual figures, percentages, and dates stated in the call, "
    "and note management's tone or confidence where it is evident. Keep the entire "
    "summary under ~400 words. Do not invent, infer, or extrapolate any data that is "
    "not explicitly present in the transcript."
)


def _segment_transcript(content: str) -> list[TranscriptSegment]:
    if not content:
        return []
    matches = list(_SPEAKER_RE.finditer(content))
    if not matches:
        return [TranscriptSegment(speaker="", text=content.strip())]
    segments: list[TranscriptSegment] = []
    for i, m in enumerate(matches):
        speaker = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        text = content[start:end].strip()
        if text:
            segments.append(TranscriptSegment(speaker=speaker, text=text))
    return segments


def _first(data) -> dict:
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return data if isinstance(data, dict) else {}


async def build_transcript_list(fmp, ticker: str) -> TranscriptList:
    ticker = ticker.upper()
    try:
        dates, _ = await fmp.get_transcript_dates(ticker)
    except Exception:
        dates = []
    events: list[TranscriptEvent] = []
    if isinstance(dates, list):
        for d in dates:
            if not isinstance(d, dict):
                continue
            q, fy, dt = d.get("quarter"), d.get("fiscalYear"), d.get("date")
            if isinstance(q, int) and isinstance(fy, int) and dt:
                events.append(TranscriptEvent(quarter=q, fiscal_year=fy, date=str(dt)))
    return TranscriptList(ticker=ticker, events=events)


async def build_transcript(fmp, ticker: str, year: int, quarter: int) -> Transcript:
    ticker = ticker.upper()
    try:
        data, _ = await fmp.get_earnings_transcript(ticker, year=year, quarter=quarter)
    except Exception:
        data = []
    row = _first(data)
    raw = row.get("content")
    content = raw if isinstance(raw, str) else ""
    return Transcript(
        ticker=ticker,
        year=year,
        quarter=quarter,
        date=row.get("date"),
        segments=_segment_transcript(content),
    )


async def summarize_transcript(fmp, ticker: str, year: int, quarter: int) -> str:
    """Fetch a transcript and return an AI markdown summary (Haiku).

    Re-fetches the transcript independently of the reader endpoint so the summary
    route stays stateless; FMP responses are TTL-cached, so this is an in-process
    cache hit, not a second network round-trip.
    """
    ticker = ticker.upper()
    try:
        data, _ = await fmp.get_earnings_transcript(ticker, year=year, quarter=quarter)
    except Exception:
        data = []
    row = _first(data)
    raw = row.get("content")
    content = raw if isinstance(raw, str) else ""
    if not content.strip():
        return "_No transcript available to summarize._"
    return await complete(
        system=_SUMMARY_SYSTEM,
        user=content,
        model=HAIKU,
        max_tokens=1500,
    )
