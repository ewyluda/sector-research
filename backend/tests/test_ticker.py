"""Pins ticker normalization + validation behavior."""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi import HTTPException

from backend.app.models.ticker import TickerPath, normalize_ticker


class NormalizationTests(unittest.TestCase):
    def test_lowercase_to_upper(self):
        self.assertEqual(normalize_ticker("aapl"), "AAPL")

    def test_already_upper(self):
        self.assertEqual(normalize_ticker("MSFT"), "MSFT")

    def test_strip_whitespace(self):
        self.assertEqual(normalize_ticker("  nvda  "), "NVDA")

    def test_dotted_symbol(self):
        self.assertEqual(normalize_ticker("brk.a"), "BRK.A")

    def test_dashed_symbol(self):
        self.assertEqual(normalize_ticker("brk-b"), "BRK-B")


class ValidationTests(unittest.TestCase):
    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            normalize_ticker("")
        with self.assertRaises(ValueError):
            normalize_ticker("   ")

    def test_starts_with_digit_rejected(self):
        with self.assertRaises(ValueError):
            normalize_ticker("3M")  # actual ticker is MMM

    def test_contains_space_rejected(self):
        with self.assertRaises(ValueError):
            normalize_ticker("AB CD")

    def test_contains_slash_rejected(self):
        with self.assertRaises(ValueError):
            normalize_ticker("AB/CD")

    def test_too_long_rejected(self):
        with self.assertRaises(ValueError):
            normalize_ticker("A" * 11)


class TickerPathTests(unittest.TestCase):
    def test_valid_passes_through(self):
        self.assertEqual(TickerPath("aapl"), "AAPL")

    def test_invalid_raises_400(self):
        with self.assertRaises(HTTPException) as ctx:
            TickerPath("not a ticker!")
        self.assertEqual(ctx.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
