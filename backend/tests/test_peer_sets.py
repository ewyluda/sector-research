"""Pins peer-set seeding (competitor_landscape ∪ stock-peers, capped, deduped),
update normalization, and the curated-first/fallback derivation used by
workspace step 5."""

import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services import peer_sets
from backend.app.models.peer_set import PeerSet


def _db_returning(*rows):
    """Mock AsyncSession whose successive execute() calls return the given
    scalar_one_or_none / scalars().all() payloads in order."""
    db = MagicMock()
    results = []
    for row in rows:
        r = MagicMock()
        r.scalar_one_or_none.return_value = row
        scalars = MagicMock()
        scalars.all.return_value = row if isinstance(row, list) else []
        r.scalars.return_value = scalars
        results.append(r)
    db.execute = AsyncMock(side_effect=results)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def _landscape_row(competitors):
    row = MagicMock()
    row.competitors = competitors
    return row


class GetOrSeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_existing_row_returned_without_seeding(self):
        existing = PeerSet(ticker="NVDA", peers=["AMD", "INTC"])
        db = _db_returning(existing)
        fmp = AsyncMock()
        peers, seeded = await peer_sets.get_or_seed_peer_set("NVDA", db, fmp)
        self.assertEqual(peers, ["AMD", "INTC"])
        self.assertFalse(seeded)
        db.add.assert_not_called()
        fmp.get_stock_peers.assert_not_called()

    async def test_seed_unions_landscape_then_fmp_capped_deduped(self):
        # execute #1: PeerSet miss; execute #2: competitor_landscape rows
        landscape = [_landscape_row([
            {"resolved_to_ticker": "AMD"},
            {"resolved_to_ticker": "INTC"},
            {"resolved_to_ticker": "NVDA"},   # self — dropped
            {"resolved_to_ticker": None},      # unresolved — dropped
        ])]
        db = _db_returning(None, landscape)
        fmp = AsyncMock()
        fmp.get_stock_peers = AsyncMock(return_value=(
            ["INTC", "AVGO", "QCOM", "TSM", "MU", "ARM", "TXN", "ADI", "MRVL"],
            MagicMock(),
        ))
        peers, seeded = await peer_sets.get_or_seed_peer_set("NVDA", db, fmp)
        self.assertTrue(seeded)
        # landscape first, then fmp fill (INTC deduped), capped at 8
        self.assertEqual(peers, ["AMD", "INTC", "AVGO", "QCOM", "TSM", "MU", "ARM", "TXN"])
        db.add.assert_called_once()
        db.commit.assert_awaited()

    async def test_seed_tolerates_fmp_failure(self):
        landscape = [_landscape_row([{"resolved_to_ticker": "AMD"}])]
        db = _db_returning(None, landscape)
        fmp = AsyncMock()
        fmp.get_stock_peers = AsyncMock(side_effect=RuntimeError("FMP down"))
        peers, seeded = await peer_sets.get_or_seed_peer_set("NVDA", db, fmp)
        self.assertEqual(peers, ["AMD"])
        self.assertTrue(seeded)

    async def test_zero_sources_persists_empty_row(self):
        db = _db_returning(None, [])
        fmp = AsyncMock()
        fmp.get_stock_peers = AsyncMock(return_value=([], MagicMock()))
        peers, seeded = await peer_sets.get_or_seed_peer_set("ZZZQ", db, fmp)
        self.assertEqual(peers, [])
        self.assertTrue(seeded)
        db.add.assert_called_once()  # empty row persisted — no re-seed next visit


class UpdateTests(unittest.IsolatedAsyncioTestCase):
    async def test_normalizes_dedupes_drops_self(self):
        db = _db_returning(None)
        peers = await peer_sets.update_peer_set(
            "NVDA", ["amd ", "AMD", "nvda", "intc"], db
        )
        self.assertEqual(peers, ["AMD", "INTC"])
        db.add.assert_called_once()
        db.commit.assert_awaited()

    async def test_replaces_existing_row(self):
        existing = PeerSet(ticker="NVDA", peers=["OLD"])
        db = _db_returning(existing)
        peers = await peer_sets.update_peer_set("NVDA", ["AMD"], db)
        self.assertEqual(peers, ["AMD"])
        self.assertEqual(existing.peers, ["AMD"])
        db.add.assert_not_called()

    async def test_empty_list_clears(self):
        existing = PeerSet(ticker="NVDA", peers=["AMD"])
        db = _db_returning(existing)
        peers = await peer_sets.update_peer_set("NVDA", [], db)
        self.assertEqual(peers, [])
        self.assertEqual(existing.peers, [])

    async def test_invalid_ticker_raises_value_error(self):
        db = _db_returning(None)
        with self.assertRaises(ValueError):
            await peer_sets.update_peer_set("NVDA", ["NOT A TICKER!!"], db)

    async def test_over_cap_raises_value_error(self):
        db = _db_returning(None)
        thirteen = [f"T{i}" for i in range(13)]
        with self.assertRaises(ValueError):
            await peer_sets.update_peer_set("NVDA", thirteen, db)


class PeersForTickerTests(unittest.IsolatedAsyncioTestCase):
    async def test_curated_set_preferred(self):
        existing = PeerSet(ticker="NVDA", peers=["AMD", "INTC"])
        db = _db_returning(existing)
        peers = await peer_sets.peers_for_ticker("NVDA", db)
        self.assertEqual(peers, ["AMD", "INTC"])

    async def test_empty_curated_falls_back_to_landscape(self):
        existing = PeerSet(ticker="NVDA", peers=[])
        db = _db_returning(existing)
        with patch.object(
            peer_sets, "resolved_competitor_peers",
            new=AsyncMock(return_value=["AMD"]),
        ) as fallback:
            peers = await peer_sets.peers_for_ticker("NVDA", db)
        self.assertEqual(peers, ["AMD"])
        fallback.assert_awaited_once()

    async def test_missing_row_falls_back_to_landscape(self):
        db = _db_returning(None)
        with patch.object(
            peer_sets, "resolved_competitor_peers",
            new=AsyncMock(return_value=["AMD"]),
        ):
            peers = await peer_sets.peers_for_ticker("NVDA", db)
        self.assertEqual(peers, ["AMD"])


if __name__ == "__main__":
    unittest.main()
