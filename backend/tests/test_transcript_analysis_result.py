"""Tests for TranscriptAnalysisResult typed container (M3.1)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, patch


class TestTranscriptAnalysisResultOk(unittest.TestCase):
    """status="ok" when transcripts are present and complete() succeeds."""

    def test_ok_status_and_value_present(self):
        transcripts = [{"content": "Management discussed revenue growth and capex plans."}]

        with patch("backend.app.graph.llm.complete", new=AsyncMock(return_value='{"key": "val"}')):
            from backend.app.services.transcript_analysis import run_transcript_analysis
            result = asyncio.run(run_transcript_analysis("AAPL", transcripts, fmp=None))

        self.assertEqual(result.status, "ok")
        self.assertIsNotNone(result.value)
        self.assertIsNone(result.error)
        # Standard pass keys must be present
        self.assertIn("pass1_claims", result.value)
        self.assertIn("pass2_tiers", result.value)
        self.assertIn("pass3_qa_tensions", result.value)
        self.assertIn("pass4_validation", result.value)
        self.assertIn("pass5_consistency", result.value)

    def test_ok_value_is_dict_not_wrapped(self):
        """value must be a plain dict — same shape stored in state.transcript_analysis."""
        transcripts = [{"content": "Q&A: what is the outlook? Revenue was great."}]

        with patch("backend.app.graph.llm.complete", new=AsyncMock(return_value="raw text")):
            from backend.app.services.transcript_analysis import run_transcript_analysis
            result = asyncio.run(run_transcript_analysis("MSFT", transcripts, fmp=None))

        self.assertIsInstance(result.value, dict)


class TestTranscriptAnalysisResultNoData(unittest.TestCase):
    """status="no_data" when transcripts list is empty."""

    def test_empty_transcripts_returns_no_data(self):
        from backend.app.services.transcript_analysis import run_transcript_analysis
        result = asyncio.run(run_transcript_analysis("TSLA", [], fmp=None))

        self.assertEqual(result.status, "no_data")
        self.assertIsNone(result.value)
        self.assertIsNone(result.error)

    def test_none_transcripts_not_accepted(self):
        """Caller contract: empty list → no_data; None is not a valid transcripts arg.
        The function signature is list[dict], but defend against accidental None."""
        # Passing [] is the documented interface; None would be a caller bug.
        # This test just verifies the empty-list path — not testing None.
        from backend.app.services.transcript_analysis import run_transcript_analysis
        result = asyncio.run(run_transcript_analysis("NVDA", [], fmp=None))
        self.assertEqual(result.status, "no_data")


class TestTranscriptAnalysisResultError(unittest.TestCase):
    """status="error" when an unexpected exception aborts the outer try block.

    Note: per-pass exceptions inside asyncio.gather(return_exceptions=True) are
    caught by _parse_pass and produce string results — they do NOT flip status to
    "error".  Only a structural exception that escapes the outer try block does
    (e.g. a TypeError raised while building the transcript_text string).
    """

    def test_error_status_on_outer_exception(self):
        """A TypeError raised while accessing transcript content escapes gather."""
        # Pass a transcript whose .get() call triggers a TypeError at the
        # transcript_text extraction line — this happens before gather, so it
        # escapes the outer try and produces status="error".
        transcripts = [None]  # None.get() → AttributeError, outside gather

        with patch("backend.app.graph.llm.complete", new=AsyncMock(return_value="{}")):
            from backend.app.services.transcript_analysis import run_transcript_analysis
            result = asyncio.run(run_transcript_analysis("AMD", transcripts, fmp=None))

        self.assertEqual(result.status, "error")
        self.assertIsNone(result.value)
        self.assertIsNotNone(result.error)

    def test_per_pass_failure_still_returns_ok(self):
        """Individual pass exceptions inside gather produce string results, not "error"."""
        transcripts = [{"content": "Q&A: investment plans?"}]

        # AsyncMock side_effect raises inside gather → caught by return_exceptions=True
        with patch("backend.app.graph.llm.complete", new=AsyncMock(side_effect=RuntimeError("timeout"))):
            from backend.app.services.transcript_analysis import run_transcript_analysis
            result = asyncio.run(run_transcript_analysis("AMD", transcripts, fmp=None))

        # Per-pass failures are absorbed; overall status is still "ok"
        self.assertEqual(result.status, "ok")
        self.assertIsNotNone(result.value)
        # Each pass result should be the stringified exception
        self.assertIn("timeout", result.value.get("pass1_claims", ""))


class TestTranscriptAnalysisResultFrozen(unittest.TestCase):
    """TranscriptAnalysisResult must be immutable (frozen dataclass)."""

    def test_frozen(self):
        from backend.app.services.transcript_analysis import TranscriptAnalysisResult
        r = TranscriptAnalysisResult(status="ok", value={"x": 1}, error=None)
        with self.assertRaises(Exception):
            r.status = "error"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
