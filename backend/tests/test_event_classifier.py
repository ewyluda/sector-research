"""Pins the 8-K item-code prefilter and the Haiku classification parse path.
Prefilter spec: skip filings whose item set is a non-empty subset of
{7.01, 9.01}; an EMPTY items string means missing metadata → classify."""

import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.event_classifier import (
    EventClassification,
    _strip_html,
    classify_8k,
    should_classify,
)


class PrefilterTests(unittest.TestCase):
    def test_regfd_only_skipped(self):
        self.assertFalse(should_classify("7.01"))

    def test_exhibits_only_skipped(self):
        self.assertFalse(should_classify("9.01"))

    def test_regfd_plus_exhibits_skipped(self):
        self.assertFalse(should_classify("7.01,9.01"))

    def test_earnings_8k_kept(self):
        # 2.02 must NOT be skipped — guidance changes live there (spec)
        self.assertTrue(should_classify("2.02,9.01"))

    def test_personnel_kept(self):
        self.assertTrue(should_classify("5.02"))

    def test_empty_or_none_kept(self):
        self.assertTrue(should_classify(""))
        self.assertTrue(should_classify(None))


class ClassifyTests(unittest.IsolatedAsyncioTestCase):
    async def test_parses_valid_response(self):
        raw = (
            '{"event_type": "personnel", "materiality": "high",'
            ' "headline": "CFO resigns effective immediately",'
            ' "summary": "The company announced its CFO resigned."}'
        )
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(return_value=raw),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09",
                item_codes="5.02", text="<html>CFO resigns</html>",
            )
        self.assertIsNone(err)
        self.assertIsInstance(result, EventClassification)
        self.assertEqual(result.event_type, "personnel")
        self.assertEqual(result.materiality, "high")

    async def test_unknown_event_type_normalizes_to_other(self):
        raw = (
            '{"event_type": "weird", "materiality": "low",'
            ' "headline": "h", "summary": "s"}'
        )
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(return_value=raw),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09", item_codes="", text="x",
            )
        self.assertIsNone(err)
        self.assertEqual(result.event_type, "other")

    async def test_invalid_materiality_is_error(self):
        raw = (
            '{"event_type": "guidance", "materiality": "extreme",'
            ' "headline": "h", "summary": "s"}'
        )
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(return_value=raw),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09", item_codes="", text="x",
            )
        self.assertIsNone(result)
        self.assertIn("materiality", err)

    async def test_call_failure_returns_error_not_raise(self):
        with patch(
            "backend.app.services.event_classifier.complete",
            new=AsyncMock(side_effect=RuntimeError("api down")),
        ):
            result, err = await classify_8k(
                ticker="NVDA", filing_date="2026-06-09", item_codes="", text="x",
            )
        self.assertIsNone(result)
        self.assertIn("haiku_call_failed", err)


class StripHtmlTests(unittest.TestCase):
    def test_unwraps_inline_xbrl_and_tags(self):
        html = "<html><body><ix:nonFraction>5.5</ix:nonFraction> grew <b>10%</b></body></html>"
        self.assertEqual(_strip_html(html), "5.5 grew 10%")

    def test_plain_text_passthrough(self):
        self.assertEqual(_strip_html("no markup here"), "no markup here")


if __name__ == "__main__":
    unittest.main()
