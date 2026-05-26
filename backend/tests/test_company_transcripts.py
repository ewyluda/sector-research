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
        _, kwargs = mock_complete.call_args
        user_arg = kwargs.get("user") or mock_complete.call_args.args[1]
        self.assertIn("Tim Cook", user_arg)

    async def test_summarize_empty_transcript(self):
        md = await summarize_transcript(_StubFMP(transcript=[]), "X", 2025, 1)
        self.assertIn("No transcript", md)


if __name__ == "__main__":
    unittest.main()
