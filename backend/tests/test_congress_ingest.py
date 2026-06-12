"""Pins FMP senate/house-trades row normalization, the amount-range parser,
the natural-key dedupe, and the idempotent upsert (re-ingest adds nothing).

Mirrors test_insider_ingest.py. Wire keys live-verified 2026-06-11 against
/stable/senate-trades and /stable/house-trades (shared row shape; house rows
may carry senateID=null).
"""

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

from backend.app.models.congress_transaction import CongressTransaction
from backend.app.services.congress_ingest import (
    _amount_mid,
    _direction,
    _map_fmp_row,
    _natural_key,
    upsert_congress_transactions,
)

ROW = {
    "symbol": "NVDA",
    "senateID": "W000802",
    "disclosureDate": "2026-06-02",
    "transactionDate": "2026-05-08",
    "firstName": "Sheldon",
    "lastName": "Whitehouse",
    "office": "Sheldon Whitehouse",
    "district": "RI",
    "owner": "Self",
    "assetDescription": "NVIDIA Corporation",
    "assetType": "Stock",
    "type": "Sale",
    "amount": "$100,001 - $250,000",
    "capitalGainsOver200USD": "False",
    "comment": "",
    "link": "https://efdsearch.senate.gov/search/view/ptr/4aa0094d/",
}


class DirectionTests(unittest.TestCase):
    def test_purchase_is_buy(self):
        self.assertEqual(_direction("Purchase"), "buy")

    def test_sale_variants_are_sell(self):
        for t in ("Sale", "Sale (Partial)", "Sale (Full)", "sale"):
            self.assertEqual(_direction(t), "sell")

    def test_exchange_and_unknown_are_other(self):
        for t in ("Exchange", "Received", None, ""):
            self.assertEqual(_direction(t), "other")


class AmountMidTests(unittest.TestCase):
    def test_standard_range_midpoint(self):
        self.assertEqual(_amount_mid("$1,001 - $15,000"), 8000.5)

    def test_large_range_midpoint(self):
        self.assertEqual(_amount_mid("$100,001 - $250,000"), 175000.5)

    def test_open_ended_uses_lower_bound(self):
        self.assertEqual(_amount_mid("$50,000,000 +"), 50_000_000.0)

    def test_unparseable_is_none(self):
        self.assertIsNone(_amount_mid("Unknown"))
        self.assertIsNone(_amount_mid(None))
        self.assertIsNone(_amount_mid(""))


class MappingTests(unittest.TestCase):
    def test_maps_all_fields(self):
        kwargs = _map_fmp_row("nvda", "senate", ROW)
        self.assertEqual(kwargs["ticker"], "NVDA")
        self.assertEqual(kwargs["politician_name"], "Sheldon Whitehouse")
        self.assertEqual(kwargs["chamber"], "senate")
        self.assertEqual(kwargs["district"], "RI")
        self.assertEqual(kwargs["owner"], "Self")
        self.assertEqual(kwargs["transaction_type"], "Sale")
        self.assertEqual(kwargs["direction"], "sell")
        self.assertEqual(kwargs["transaction_date"], date(2026, 5, 8))
        self.assertEqual(kwargs["disclosure_date"], date(2026, 6, 2))
        self.assertEqual(kwargs["amount_range"], "$100,001 - $250,000")
        self.assertEqual(kwargs["amount_mid"], 175000.5)
        self.assertTrue(kwargs["disclosure_link"].startswith("https://"))
        self.assertEqual(len(kwargs["natural_key"]), 64)

    def test_missing_names_fall_back_to_office(self):
        row = {**ROW, "firstName": None, "lastName": None}
        kwargs = _map_fmp_row("NVDA", "senate", row)
        self.assertEqual(kwargs["politician_name"], "Sheldon Whitehouse")

    def test_bad_date_maps_to_none(self):
        kwargs = _map_fmp_row("NVDA", "senate", {**ROW, "transactionDate": "garbage"})
        self.assertIsNone(kwargs["transaction_date"])


class NaturalKeyTests(unittest.TestCase):
    def test_deterministic_and_distinct(self):
        a = _natural_key("NVDA", "senate", ROW)
        b = _natural_key("NVDA", "senate", dict(ROW))
        c = _natural_key("NVDA", "senate", {**ROW, "owner": "Spouse"})
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_chamber_distinguishes(self):
        self.assertNotEqual(
            _natural_key("NVDA", "senate", ROW),
            _natural_key("NVDA", "house", ROW),
        )


class UpsertTests(unittest.IsolatedAsyncioTestCase):
    async def test_skips_existing_keys_adds_new(self):
        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)

        existing_key = _natural_key("NVDA", "senate", ROW)
        result = MagicMock()
        result.scalars.return_value.all.return_value = [existing_key]
        db.execute = AsyncMock(return_value=result)

        new_row = {**ROW, "transactionDate": "2026-05-12", "type": "Purchase"}
        summary = await upsert_congress_transactions(
            db, "NVDA", senate_rows=[ROW, new_row], house_rows=[]
        )

        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["skipped_existing"], 1)
        self.assertEqual(len(added), 1)
        self.assertIsInstance(added[0], CongressTransaction)
        self.assertEqual(added[0].direction, "buy")

    async def test_empty_rows_no_db_calls(self):
        db = MagicMock()
        db.execute = AsyncMock()
        summary = await upsert_congress_transactions(
            db, "NVDA", senate_rows=[], house_rows=[]
        )
        self.assertEqual(summary["added"], 0)
        db.execute.assert_not_awaited()

    async def test_house_rows_get_house_chamber(self):
        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        summary = await upsert_congress_transactions(
            db, "NVDA", senate_rows=[], house_rows=[dict(ROW)]
        )
        self.assertEqual(summary["added"], 1)
        self.assertEqual(added[0].chamber, "house")

    async def test_in_batch_duplicate_added_once(self):
        added: list[object] = []
        db = MagicMock()
        db.add = MagicMock(side_effect=added.append)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(return_value=result)

        summary = await upsert_congress_transactions(
            db, "NVDA", senate_rows=[ROW, dict(ROW)], house_rows=[]
        )
        self.assertEqual(summary["added"], 1)
        self.assertEqual(summary["skipped_existing"], 1)


if __name__ == "__main__":
    unittest.main()
