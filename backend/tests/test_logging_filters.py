"""Tests for the httpx apikey redaction logging filter."""
import logging
import unittest

from backend.app.logging_filters import ApiKeyRedactionFilter


def _record(msg: str, args: tuple | None) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


class TestApiKeyRedactionFilter(unittest.TestCase):
    def setUp(self):
        self.filter = ApiKeyRedactionFilter()

    def test_redacts_apikey_in_lazy_args(self):
        # Mirrors httpx's actual log call shape: URL arrives as an arg.
        rec = _record(
            'HTTP Request: %s %s "%s %d %s"',
            ("GET",
             "https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=SECRET123abc",
             "HTTP/1.1", 200, "OK"),
        )
        self.assertTrue(self.filter.filter(rec))
        rendered = rec.getMessage()
        self.assertNotIn("SECRET123abc", rendered)
        self.assertIn("apikey=REDACTED", rendered)
        self.assertIn("symbol=NVDA", rendered)  # only the key is redacted

    def test_redacts_apikey_embedded_in_msg(self):
        rec = _record("retrying https://x.test/q?apikey=SECRET123abc now", None)
        self.filter.filter(rec)
        self.assertNotIn("SECRET123abc", rec.getMessage())

    def test_leaves_clean_records_untouched(self):
        rec = _record('HTTP Request: %s %s', ("GET", "https://api.example.com/health"))
        self.filter.filter(rec)
        self.assertEqual(
            rec.getMessage(), "HTTP Request: GET https://api.example.com/health"
        )

    def test_non_string_args_survive(self):
        rec = _record("status %d for %s?apikey=k123", (200, "https://a.b/c"))
        self.filter.filter(rec)
        self.assertIn("apikey=REDACTED", rec.getMessage())
        self.assertIn("200", rec.getMessage())


if __name__ == "__main__":
    unittest.main()
