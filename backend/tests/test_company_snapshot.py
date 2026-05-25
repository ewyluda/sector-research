"""Unit tests for build_company_header.

The service assembles the company-workspace header from FMP quote + profile.
We stub the FMP client (its methods return tuple[data, Citation]) — no network.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_snapshot import build_company_header


class _StubFMP:
    """Returns canned (data, citation) tuples; citation is irrelevant here."""

    def __init__(self, quote, profile):
        self._quote = quote
        self._profile = profile

    async def get_quote(self, ticker):
        return self._quote, None

    async def get_company_profile(self, ticker):
        return self._profile, None


class BuildCompanyHeaderTest(unittest.IsolatedAsyncioTestCase):
    async def test_maps_quote_and_profile(self):
        fmp = _StubFMP(
            quote={"price": 214.36, "change": -5.57, "changePercentage": -2.53},
            profile={
                "companyName": "Nebius Group N.V.",
                "exchangeShortName": "NasdaqGS",
                "image": "https://logo.example/nbis.png",
                "currency": "USD",
            },
        )
        header = await build_company_header(fmp, "nbis")
        self.assertEqual(header.ticker, "NBIS")
        self.assertEqual(header.name, "Nebius Group N.V.")
        self.assertEqual(header.exchange, "NasdaqGS")
        self.assertEqual(header.logo_url, "https://logo.example/nbis.png")
        self.assertEqual(header.currency, "USD")
        self.assertEqual(header.price, 214.36)
        self.assertEqual(header.change, -5.57)
        self.assertEqual(header.change_pct, -2.53)
        self.assertEqual(header.delay_label, "15 min delay")

    async def test_degrades_when_quote_missing(self):
        fmp = _StubFMP(quote={}, profile={"companyName": "Acme Inc"})
        header = await build_company_header(fmp, "ACME")
        self.assertEqual(header.ticker, "ACME")
        self.assertEqual(header.name, "Acme Inc")
        self.assertIsNone(header.price)
        self.assertIsNone(header.change)
        self.assertIsNone(header.change_pct)

    async def test_handles_non_dict_payloads(self):
        fmp = _StubFMP(quote=[], profile=None)
        header = await build_company_header(fmp, "ZZZ")
        self.assertEqual(header.ticker, "ZZZ")
        self.assertIsNone(header.name)
        self.assertIsNone(header.price)


if __name__ == "__main__":
    unittest.main()
