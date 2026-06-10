"""Pins FMP Form 4 row normalization, the natural-key dedupe, and the
idempotent upsert (re-ingest of identical rows adds nothing)."""

import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.insider_transaction import InsiderTransaction
from backend.app.services.insider_ingest import (
    _accession_from_link,
    _direction,
    _map_fmp_row,
    _natural_key,
    upsert_insider_transactions,
)

ROW = {
    "symbol": "NVDA",
    "reportingName": "HUANG JEN HSUN",
    "typeOfOwner": "officer: CEO",
    "transactionType": "S-Sale",
    "transactionDate": "2026-06-01",
    "securitiesTransacted": 1000,
    "price": 120.5,
    "securitiesOwned": 75000000,
    "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000123/0001045810-26-000123-index.htm",
}


class DirectionTests(unittest.TestCase):
    def test_purchase_is_buy(self):
        self.assertEqual(_direction("P-Purchase"), "buy")

    def test_sale_is_sell(self):
        self.assertEqual(_direction("S-Sale"), "sell")

    def test_award_exercise_gift_are_other(self):
        for code in ("A-Award", "M-Exempt", "G-Gift", "F-InKind", None, ""):
            self.assertEqual(_direction(code), "other")


class AccessionTests(unittest.TestCase):
    def test_extracts_dashed_accession(self):
        self.assertEqual(
            _accession_from_link(ROW["url"]), "0001045810-26-000123"
        )

    def test_none_when_absent(self):
        self.assertIsNone(_accession_from_link("https://example.com/x.htm"))
        self.assertIsNone(_accession_from_link(None))


class MappingTests(unittest.TestCase):
    def test_maps_all_fields(self):
        kwargs = _map_fmp_row("NVDA", ROW)
        self.assertEqual(kwargs["ticker"], "NVDA")
        self.assertEqual(kwargs["insider_name"], "HUANG JEN HSUN")
        self.assertEqual(kwargs["insider_title"], "officer: CEO")
        self.assertEqual(kwargs["transaction_type"], "S-Sale")
        self.assertEqual(kwargs["direction"], "sell")
        self.assertEqual(kwargs["transaction_date"], date(2026, 6, 1))
        self.assertEqual(kwargs["shares"], 1000)
        self.assertEqual(kwargs["price"], 120.5)
        self.assertEqual(kwargs["shares_owned_after"], 75000000)
        self.assertEqual(kwargs["accession_number"], "0001045810-26-000123")
        self.assertTrue(kwargs["sec_link"].startswith("https://www.sec.gov/"))
        self.assertEqual(len(kwargs["natural_key"]), 64)

    def test_bad_date_maps_to_none(self):
        kwargs = _map_fmp_row("NVDA", {**ROW, "transactionDate": "garbage"})
        self.assertIsNone(kwargs["transaction_date"])

    def test_natural_key_deterministic_and_distinct(self):
        a = _natural_key("NVDA", ROW)
        b = _natural_key("NVDA", dict(ROW))
        c = _natural_key("NVDA", {**ROW, "securitiesTransacted": 999})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)


class UpsertTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_existing_keys_adds_new(self):
        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)

        existing_key = _natural_key("NVDA", ROW)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [existing_key]
        db.execute = AsyncMock(return_value=result)

        new_row = {**ROW, "transactionDate": "2026-06-05", "transactionType": "P-Purchase"}
        summary = await upsert_insider_transactions(
            db, "NVDA", [ROW, new_row]
        )

        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["skipped_existing"], 1)
        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], InsiderTransaction)
        self.assertEqual(added[0].direction, "buy")

    async def test_empty_rows_no_db_calls(self):
        db = MagicMock()
        db.execute = AsyncMock()
        summary = await upsert_insider_transactions(db, "NVDA", [])
        self.assertEqual(summary["added"], 0)
        db.execute.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
