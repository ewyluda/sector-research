# Company Workspace — Slice 4 Implementation Plan (Transcripts reader + AI Summary)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Transcripts tab — a list of available earnings-call quarters, a speaker-segmented transcript reader with search, and an on-demand AI Summary (Haiku) — replacing the slice-1 placeholder.

**Architecture:** A new `company_transcripts.py` service (keeps the fmp-only `company_snapshot.py` focused). It exposes the available transcript dates, fetches a specific quarter's transcript and segments the single-blob `content` into `[{speaker, text}]` turns via a line-start regex (90 clean turns confirmed against live FMP), and summarizes a transcript with `graph/llm.complete(HAIKU)`. Three endpoints on the existing company router. The frontend `TranscriptReader` is a 3-region layout: event rail, segmented transcript + client-side search, and an AI Summary panel.

**Tech Stack:** FastAPI + Pydantic + the shared `FMPClient` (`get_earnings_transcript` exists; add `get_transcript_dates`) + `graph/llm.complete`; Next.js 16 client components + the existing `MarkdownProse` renderer; stdlib `unittest`.

**Spec:** `docs/superpowers/specs/2026-05-25-company-workspace-design.md` (Transcripts = slice 4; AI Summary was flagged "requires LLM").

**Scope (decided with the user):** event list + speaker-segmented reader + client-side search + on-demand AI Summary (Haiku). Deferred: Quartr audio dock / "Skip to Q&A", Custom Summary, Report sub-tab, conference-appearance events (earnings calls only).

**Conventions:** backend absolute imports from project root; run from project root with `backend/venv` active; `ticker.upper()` at entry; FMP methods return `tuple[data, Citation]`; frontend `"use client"` + `useParams`. Known pre-existing tsc errors in three `.mts` files — ignore.

**Verified live FMP facts:**
- `earning-call-transcript-dates?symbol=` → `[{"quarter": 2, "fiscalYear": 2026, "date": "2026-04-30"}, ...]` (newest-first).
- `earning-call-transcript?symbol=&year=&quarter=` → `[{symbol, year, period, date, content}]`; `content` is a single string, newline-separated, each turn `"Speaker Name: text"`. The regex `(?:^|\n)\s*([A-Z][^:\n]{1,40}?):\s` finds all turns cleanly.
- `complete(system, user, model=HAIKU, max_tokens=...) -> str` lives in `backend/app/graph/llm.py` (uses its own client; `HAIKU = "claude-haiku-4-5-20251001"`).

---

## File Structure

**Backend:**
- Modify `backend/app/clients/fmp.py` — add `get_transcript_dates`.
- Create `backend/app/services/company_transcripts.py` — models + `_segment_transcript` + `build_transcript_list` + `build_transcript` + `summarize_transcript`.
- Modify `backend/app/api/company.py` — add 3 transcript routes.
- Create `backend/tests/test_company_transcripts.py`.

**Frontend:**
- Modify `frontend/lib/api.ts` — transcript types + `getTranscripts` / `getTranscript` / `summarizeTranscript`.
- Create `frontend/components/company/TranscriptReader.tsx` — the 3-region reader.
- Modify `frontend/app/company/[ticker]/transcripts/page.tsx` — render `TranscriptReader`.

---

## Task 1: Backend — transcript list + segmented reader

**Files:**
- Modify: `backend/app/clients/fmp.py`
- Create: `backend/app/services/company_transcripts.py`
- Modify: `backend/app/api/company.py`
- Create: `backend/tests/test_company_transcripts.py`

- [ ] **Step 1: Add `get_transcript_dates` to `backend/app/clients/fmp.py`.** Directly after `get_earnings_transcript`, add:

```python
    async def get_transcript_dates(self, ticker: str) -> tuple[list[dict], Citation]:
        """Available earnings-call transcripts for a ticker.

        GET /stable/earning-call-transcript-dates?symbol=X
        Returns newest-first list of {quarter, fiscalYear, date}.
        """
        params = {"symbol": ticker}
        data = await self._request("earning-call-transcript-dates", params, ttl=TTL_TRANSCRIPT)
        citation = self._make_citation(
            "earning-call-transcript-dates", "Transcript Dates", ticker, params
        )
        return data if isinstance(data, list) else [], citation
```

- [ ] **Step 2: Write the failing test.** Create `backend/tests/test_company_transcripts.py`:

```python
"""Unit tests for the company_transcripts service.

Stubs the FMP client; the transcript-segmentation parser is the core logic.
"""
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_transcripts import (
    _segment_transcript,
    build_transcript,
    build_transcript_list,
    summarize_transcript,
)


_SAMPLE = (
    "Operator: Good afternoon and welcome.\n"
    "Tim Cook: Thanks. Revenue was a record: 95 billion dollars this quarter.\n"
    "Erik Woodring: Can you talk about gross margin trends?\n"
    "Tim Cook: Gross margin expanded to 47%."
)


class _StubFMP:
    def __init__(self, dates=None, transcript=None):
        self._dates = dates or []
        self._transcript = transcript or []

    async def get_transcript_dates(self, ticker):
        return self._dates, None

    async def get_earnings_transcript(self, ticker, year=None, quarter=None):
        return self._transcript, None


class SegmentTranscriptTest(unittest.TestCase):
    def test_splits_on_speaker_labels(self):
        segs = _segment_transcript(_SAMPLE)
        self.assertEqual([s.speaker for s in segs],
                         ["Operator", "Tim Cook", "Erik Woodring", "Tim Cook"])
        # body keeps internal colons (the "record: 95 billion" colon is not a split)
        self.assertIn("record: 95 billion dollars", segs[1].text)

    def test_empty_content(self):
        self.assertEqual(_segment_transcript(""), [])

    def test_no_labels_returns_single_segment(self):
        segs = _segment_transcript("Just a blob with no speaker labels here.")
        self.assertEqual(len(segs), 1)
        self.assertEqual(segs[0].speaker, "")


class BuildTranscriptTest(unittest.IsolatedAsyncioTestCase):
    async def test_list_maps_events(self):
        fmp = _StubFMP(dates=[
            {"quarter": 2, "fiscalYear": 2026, "date": "2026-04-30"},
            {"quarter": 1, "fiscalYear": 2026, "date": "2026-01-29"},
        ])
        tl = await build_transcript_list(fmp, "aapl")
        self.assertEqual(tl.ticker, "AAPL")
        self.assertEqual(len(tl.events), 2)
        self.assertEqual(tl.events[0].quarter, 2)
        self.assertEqual(tl.events[0].fiscal_year, 2026)
        self.assertEqual(tl.events[0].date, "2026-04-30")

    async def test_build_transcript_segments(self):
        fmp = _StubFMP(transcript=[{"symbol": "AAPL", "year": 2025, "period": "Q1",
                                    "date": "2025-01-30", "content": _SAMPLE}])
        t = await build_transcript(fmp, "AAPL", 2025, 1)
        self.assertEqual(t.ticker, "AAPL")
        self.assertEqual(t.year, 2025)
        self.assertEqual(t.quarter, 1)
        self.assertEqual(t.date, "2025-01-30")
        self.assertEqual(len(t.segments), 4)

    async def test_build_transcript_empty(self):
        t = await build_transcript(_StubFMP(transcript=[]), "X", 2025, 1)
        self.assertEqual(t.segments, [])


class SummarizeTranscriptTest(unittest.IsolatedAsyncioTestCase):
    async def test_summarize_calls_llm_with_content(self):
        fmp = _StubFMP(transcript=[{"content": _SAMPLE, "date": "2025-01-30"}])
        with patch(
            "backend.app.services.company_transcripts.complete",
            new=AsyncMock(return_value="## Key Themes\n- Record revenue"),
        ) as mock_complete:
            md = await summarize_transcript(fmp, "AAPL", 2025, 1)
        self.assertIn("Key Themes", md)
        # the transcript content was passed to the LLM as the user message
        _, kwargs = mock_complete.call_args
        user_arg = kwargs.get("user") or mock_complete.call_args.args[1]
        self.assertIn("Tim Cook", user_arg)

    async def test_summarize_empty_transcript(self):
        md = await summarize_transcript(_StubFMP(transcript=[]), "X", 2025, 1)
        self.assertIn("No transcript", md)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run it, confirm it FAILS** (ImportError for `company_transcripts`).

```bash
source backend/venv/bin/activate
python -m unittest backend.tests.test_company_transcripts -v
```

- [ ] **Step 4: Implement `backend/app/services/company_transcripts.py`:**

```python
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


# Speaker turns start at a line with a Proper-Name-ish label then ": ".
# Body colons (e.g. "a record: 95 billion") are NOT line-start, so they don't split.
_SPEAKER_RE = re.compile(r"(?:^|\n)\s*([A-Z][^:\n]{1,40}?):\s")

_SUMMARY_SYSTEM = (
    "You are an equity research analyst. Summarize the earnings-call transcript "
    "into concise markdown with these sections: '## Key Themes' (3-5 bullets), "
    "'## Guidance & Outlook', '## Q&A Highlights' (notable analyst question + "
    "management answer), and '## Notable Quotes'. Be specific with numbers stated "
    "in the call. Do not invent any data that is not in the transcript."
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
    content = row.get("content", "") if isinstance(row.get("content"), str) else ""
    return Transcript(
        ticker=ticker,
        year=year,
        quarter=quarter,
        date=row.get("date"),
        segments=_segment_transcript(content),
    )


async def summarize_transcript(fmp, ticker: str, year: int, quarter: int) -> str:
    """Fetch a transcript and return an AI markdown summary (Haiku)."""
    ticker = ticker.upper()
    try:
        data, _ = await fmp.get_earnings_transcript(ticker, year=year, quarter=quarter)
    except Exception:
        data = []
    row = _first(data)
    content = row.get("content", "") if isinstance(row.get("content"), str) else ""
    if not content.strip():
        return "_No transcript available to summarize._"
    return await complete(
        system=_SUMMARY_SYSTEM,
        user=content,
        model=HAIKU,
        max_tokens=1500,
    )
```

- [ ] **Step 5: Run the test, confirm all PASS** (3 segmentation + 3 build + 2 summarize = 8).

- [ ] **Step 6: Add endpoints in `backend/app/api/company.py`.** Extend the import and add 3 routes:

```python
from backend.app.services.company_transcripts import (
    Transcript,
    TranscriptList,
    TranscriptSummary,
    build_transcript,
    build_transcript_list,
    summarize_transcript,
)
```
Add after the financials route:
```python
@router.get("/{ticker}/transcripts", response_model=TranscriptList)
async def get_company_transcripts(ticker: str, request: Request) -> TranscriptList:
    return await build_transcript_list(request.app.state.fmp, ticker)


@router.get("/{ticker}/transcripts/{year}/{quarter}", response_model=Transcript)
async def get_company_transcript(
    ticker: str, year: int, quarter: int, request: Request
) -> Transcript:
    return await build_transcript(request.app.state.fmp, ticker, year, quarter)


@router.post("/{ticker}/transcripts/{year}/{quarter}/summary", response_model=TranscriptSummary)
async def post_company_transcript_summary(
    ticker: str, year: int, quarter: int, request: Request
) -> TranscriptSummary:
    md = await summarize_transcript(request.app.state.fmp, ticker, year, quarter)
    return TranscriptSummary(summary_md=md)
```

- [ ] **Step 7: Verify route wiring.**

```bash
python -c "from backend.app.main import app; print(sorted(r.path for r in app.routes if 'company' in r.path))"
```
Expected includes `/api/company/{ticker}/transcripts`, `/api/company/{ticker}/transcripts/{year}/{quarter}`, `/api/company/{ticker}/transcripts/{year}/{quarter}/summary`.

- [ ] **Step 8: Commit.**

```bash
git add backend/app/clients/fmp.py backend/app/services/company_transcripts.py backend/app/api/company.py backend/tests/test_company_transcripts.py
git commit -m "feat(company): transcripts service — list, segmented reader, AI summary"
```

---

## Task 2: Frontend — transcripts API client

**Files:** Modify `frontend/lib/api.ts` (Company workspace section, after `getCompanyFinancials`).

- [ ] **Step 1: Add types + fetch fns:**

```ts
export interface TranscriptEvent {
  quarter: number;
  fiscal_year: number;
  date: string;
}

export interface TranscriptList {
  ticker: string;
  events: TranscriptEvent[];
}

export interface TranscriptSegment {
  speaker: string;
  text: string;
}

export interface Transcript {
  ticker: string;
  year: number;
  quarter: number;
  date: string | null;
  segments: TranscriptSegment[];
}

export async function getTranscripts(ticker: string): Promise<TranscriptList> {
  return apiFetch<TranscriptList>(`/api/company/${encodeURIComponent(ticker)}/transcripts`);
}

export async function getTranscript(ticker: string, year: number, quarter: number): Promise<Transcript> {
  return apiFetch<Transcript>(
    `/api/company/${encodeURIComponent(ticker)}/transcripts/${year}/${quarter}`,
  );
}

export async function summarizeTranscript(ticker: string, year: number, quarter: number): Promise<{ summary_md: string }> {
  return apiFetch<{ summary_md: string }>(
    `/api/company/${encodeURIComponent(ticker)}/transcripts/${year}/${quarter}/summary`,
    { method: "POST" },
  );
}
```

- [ ] **Step 2: Type-check.** `cd frontend && npx tsc --noEmit` → no new errors.

- [ ] **Step 3: Commit.**

```bash
git add frontend/lib/api.ts
git commit -m "feat(company): typed transcript clients (list, reader, summary)"
```

---

## Task 3: Frontend — TranscriptReader + wire page

**Files:**
- Create: `frontend/components/company/TranscriptReader.tsx`
- Modify: `frontend/app/company/[ticker]/transcripts/page.tsx`

Context: 3-region layout — left event rail, center segmented transcript + search, right AI Summary panel. Reuses `MarkdownProse` from `@/components/deep-dive/renderMarkdown` to render the summary markdown (confirm that export exists by reading the file; it is imported the same way in `app/pipeline/[runId]/page.tsx`).

- [ ] **Step 1: `frontend/components/company/TranscriptReader.tsx`:**

```tsx
"use client";

import { useEffect, useMemo, useState } from "react";
import {
  getTranscripts,
  getTranscript,
  summarizeTranscript,
  type TranscriptEvent,
  type Transcript,
} from "@/lib/api";
import { MarkdownProse } from "@/components/deep-dive/renderMarkdown";
import { EmptyState } from "./EmptyState";

export function TranscriptReader({ ticker }: { ticker: string }) {
  const [events, setEvents] = useState<TranscriptEvent[] | null>(null);
  const [active, setActive] = useState<{ year: number; quarter: number } | null>(null);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [query, setQuery] = useState("");
  const [summary, setSummary] = useState<string | null>(null);
  const [summarizing, setSummarizing] = useState(false);

  // Load the event list; default to the most recent.
  useEffect(() => {
    let alive = true;
    getTranscripts(ticker)
      .then((tl) => {
        if (!alive) return;
        setEvents(tl.events);
        if (tl.events[0]) setActive({ year: tl.events[0].fiscal_year, quarter: tl.events[0].quarter });
      })
      .catch(() => alive && setEvents([]));
    return () => { alive = false; };
  }, [ticker]);

  // Load the selected transcript; reset summary.
  useEffect(() => {
    if (!active) return;
    let alive = true;
    setTranscript(null);
    setSummary(null);
    getTranscript(ticker, active.year, active.quarter)
      .then((t) => { if (alive) setTranscript(t); })
      .catch(() => { if (alive) setTranscript(null); });
    return () => { alive = false; };
  }, [ticker, active]);

  const filtered = useMemo(() => {
    if (!transcript) return [];
    const q = query.trim().toLowerCase();
    if (!q) return transcript.segments;
    return transcript.segments.filter(
      (s) => s.speaker.toLowerCase().includes(q) || s.text.toLowerCase().includes(q),
    );
  }, [transcript, query]);

  async function onSummarize() {
    if (!active) return;
    setSummarizing(true);
    try {
      const r = await summarizeTranscript(ticker, active.year, active.quarter);
      setSummary(r.summary_md);
    } catch {
      setSummary("_Could not generate summary._");
    } finally {
      setSummarizing(false);
    }
  }

  if (events === null) {
    return <div className="p-6 text-sm text-[var(--text-muted)]">Loading transcripts…</div>;
  }
  if (events.length === 0) {
    return <EmptyState title="No transcripts" message="No earnings-call transcripts are available for this company." />;
  }

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[180px_1fr_320px]">
      {/* Event rail */}
      <nav className="space-y-1">
        {events.map((e) => {
          const isActive = active?.year === e.fiscal_year && active?.quarter === e.quarter;
          return (
            <button
              key={`${e.fiscal_year}-${e.quarter}`}
              onClick={() => setActive({ year: e.fiscal_year, quarter: e.quarter })}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm transition-colors ${
                isActive
                  ? "bg-[var(--accent-bg)] font-medium text-[var(--text)]"
                  : "text-[var(--text-muted)] hover:bg-[var(--surface-alt)] hover:text-[var(--text)]"
              }`}
            >
              Q{e.quarter} FY{e.fiscal_year}
              <span className="block text-[10px] text-[var(--text-muted)]">{e.date}</span>
            </button>
          );
        })}
      </nav>

      {/* Transcript */}
      <div className="min-w-0">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search transcript…"
          className="mb-3 w-full rounded-md border border-[var(--border)] bg-[var(--surface-alt)] px-3 py-1.5 text-sm text-[var(--text)] placeholder:text-[var(--text-muted)]"
        />
        {transcript === null ? (
          <div className="p-6 text-sm text-[var(--text-muted)]">Loading transcript…</div>
        ) : transcript.segments.length === 0 ? (
          <div className="p-6 text-sm text-[var(--text-muted)]">Transcript not available for this quarter.</div>
        ) : (
          <div className="space-y-3">
            {filtered.map((s, i) => (
              <div key={i}>
                {s.speaker && <div className="text-sm font-semibold text-[var(--text)]">{s.speaker}</div>}
                <p className="text-sm leading-relaxed text-[var(--text-muted)]">{s.text}</p>
              </div>
            ))}
            {filtered.length === 0 && (
              <p className="text-sm text-[var(--text-muted)]">No segments match “{query}”.</p>
            )}
          </div>
        )}
      </div>

      {/* AI Summary */}
      <aside className="space-y-2">
        <button
          onClick={onSummarize}
          disabled={summarizing || !transcript || transcript.segments.length === 0}
          className="w-full rounded-md bg-[var(--primary)] px-3 py-1.5 text-sm text-white hover:bg-[var(--primary-dk)] disabled:opacity-40"
        >
          {summarizing ? "Summarizing…" : "AI Summary"}
        </button>
        {summary && (
          <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-3">
            <MarkdownProse markdown={summary} />
          </div>
        )}
      </aside>
    </div>
  );
}
```

- [ ] **Step 2: Confirm `MarkdownProse` prop name.** Read `frontend/components/deep-dive/renderMarkdown.tsx` and confirm `MarkdownProse` takes a `markdown` string prop. If the prop is named differently (e.g. `content` or `children`), adjust the call to match the real signature — do NOT change the component.

- [ ] **Step 3: Wire the page.** Overwrite `frontend/app/company/[ticker]/transcripts/page.tsx`:

```tsx
"use client";

import { useParams } from "next/navigation";
import { TranscriptReader } from "@/components/company/TranscriptReader";

export default function TranscriptsPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = (Array.isArray(params.ticker) ? params.ticker[0] : params.ticker ?? "").toUpperCase();
  return <TranscriptReader ticker={ticker} />;
}
```

- [ ] **Step 4: Type-check + lint + build.**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build 2>&1 | tail -6
```
Expected: zero new tsc errors; clean lint; "Compiled successfully"; `/company/[ticker]/transcripts` listed.

- [ ] **Step 5: Manual smoke.** Backend + frontend running, `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000`. Open `/company/AAPL/transcripts`:
  - Event rail lists quarters (newest first); most recent auto-selected.
  - Center shows speaker-segmented turns (bold speaker name); search filters segments.
  - Selecting an older quarter loads its transcript and resets the summary.
  - "AI Summary" → spinner → markdown summary renders in the right panel.

- [ ] **Step 6: Commit.**

```bash
git add frontend/components/company/TranscriptReader.tsx frontend/app/company/[ticker]/transcripts/page.tsx
git commit -m "feat(company): wire Transcripts tab — segmented reader, search, AI summary"
```

---

## Full-slice verification
- [ ] Backend: `python -m unittest backend.tests.test_company_transcripts -v` → 8 OK.
- [ ] Route wiring lists the 3 transcript routes.
- [ ] Frontend: `tsc` clean (only pre-existing `.mts`), `lint` clean, `next build` succeeds.
- [ ] Manual: reader + search + AI summary all behave per Task 3 Step 5.

## Out of scope (fast-follows)
- Quartr audio dock / "Skip to Q&A" / persistent player.
- Custom Summary, the Report sub-tab, conference-appearance (non-earnings) events.
- Streaming the AI summary (currently a single POST returning the full markdown).
- Caching/persisting generated summaries (regenerated on each click).
