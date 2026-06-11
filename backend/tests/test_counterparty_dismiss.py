"""Pins the curator_private tombstone behaviour in counterparty_resolver.py.

All tests mock at the SQLAlchemy AsyncSession boundary so no live DB is needed.
"""
import os
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.filing import CounterpartyAlias, Relationship
from backend.app.services.counterparty_resolver import (
    dismiss_counterparty,
    list_dismissed,
    list_unresolved_counterparties,
    normalize_name,
    resolve_ticker_relationships,
    undismiss_counterparty,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _alias(
    *,
    alias_name: str = "OpenAI",
    source: str = "curator_private",
    canonical_cik: str | None = None,
    canonical_ticker: str | None = None,
    canonical_name: str | None = None,
) -> CounterpartyAlias:
    norm = normalize_name(alias_name)
    a = CounterpartyAlias(
        id=str(uuid4()),
        alias_name=alias_name,
        alias_normalized=norm,
        canonical_cik=canonical_cik,
        canonical_ticker=canonical_ticker,
        canonical_name=canonical_name,
        source=source,
    )
    return a


def _make_rel(
    counterparty_name: str,
    *,
    resolved_to_cik: str | None = None,
    unnamed: bool = False,
) -> Relationship:
    return Relationship(
        id=str(uuid4()),
        filing_id=str(uuid4()),
        ticker="AAPL",
        section_key="item_1",
        source_type="filing",
        counterparty_name=counterparty_name,
        relationship_type="customer",
        unnamed=unnamed,
        verbatim_quote="quote",
        resolved_to_cik=resolved_to_cik,
        resolved_to_ticker=None,
    )


def _scalar_result(value):
    """Fake result whose scalar_one_or_none() returns value."""
    r = MagicMock()
    r.scalar_one_or_none = MagicMock(return_value=value)
    return r


def _scalars_result(rows):
    """Fake result whose .scalars().all() and list(.scalars()) both work."""
    rows_list = list(rows)
    scalars = MagicMock()
    scalars.all = MagicMock(return_value=rows_list)
    scalars.__iter__ = MagicMock(return_value=iter(rows_list))
    r = MagicMock()
    r.scalars = MagicMock(return_value=scalars)
    return r


def _make_db(*, alias_lookup=None, relationship_rows=None, scalars_rows=None):
    """Build a minimal fake AsyncSession.

    alias_lookup: value returned by _existing_alias_for (SELECT alias by norm)
    relationship_rows: Relationship list returned by the rows query
    scalars_rows: value returned by a generic scalars().all() call (e.g. list_dismissed)
    """
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    alias_result = _scalar_result(alias_lookup)
    rel_result = _scalars_result(relationship_rows or [])
    scalars_result = _scalars_result(scalars_rows or [])

    async def execute(stmt):
        compiled = str(stmt)
        # _existing_alias_for: SELECT * FROM counterparty_aliases WHERE alias_normalized = :x
        if "counterparty_aliases" in compiled and "alias_normalized" in compiled and "alias_normalized_1" in compiled:
            return alias_result
        # list_dismissed: SELECT * FROM counterparty_aliases WHERE source = :source_1
        if "counterparty_aliases" in compiled and "source_1" in compiled:
            return scalars_result
        return rel_result

    db.execute = execute
    return db


# ── 1. dismiss_counterparty writes a tombstone ────────────────────────────────


class TestDismissCounterparty(unittest.IsolatedAsyncioTestCase):
    async def test_writes_tombstone_row(self):
        """dismiss_counterparty should add a CounterpartyAlias with null
        canonical fields and source="curator_private"."""
        db = _make_db(alias_lookup=None)  # no pre-existing alias
        result = await dismiss_counterparty(db, alias_name="OpenAI")
        db.add.assert_called_once()
        added: CounterpartyAlias = db.add.call_args[0][0]
        self.assertIsInstance(added, CounterpartyAlias)
        norm = normalize_name("OpenAI")
        self.assertEqual(added.alias_normalized, norm)
        self.assertIsNone(added.canonical_cik)
        self.assertIsNone(added.canonical_name)
        self.assertEqual(added.source, "curator_private")
        self.assertEqual(result["alias_normalized"], norm)
        self.assertTrue(result["dismissed"])

    async def test_raises_if_alias_already_exists(self):
        """dismiss_counterparty must raise ValueError if ANY alias row exists
        for the normalized form — prevents tombstoning already-resolved names."""
        existing = _alias(source="curator_manual", canonical_cik="0001")
        db = _make_db(alias_lookup=existing)
        with self.assertRaises(ValueError) as ctx:
            await dismiss_counterparty(db, alias_name="OpenAI")
        self.assertIn("already exists", str(ctx.exception))
        db.add.assert_not_called()

    async def test_passes_created_by(self):
        db = _make_db(alias_lookup=None)
        await dismiss_counterparty(db, alias_name="OpenAI", created_by="alice")
        added: CounterpartyAlias = db.add.call_args[0][0]
        self.assertEqual(added.created_by, "alice")


# ── 2. resolver skips tombstones ──────────────────────────────────────────────


class TestResolverSkipsTombstone(unittest.IsolatedAsyncioTestCase):
    async def _run_resolve(self, *, rel_name: str, tombstone_norm: str):
        """Exercise resolve_ticker_relationships with a tombstoned alias.

        Returns the summary dict so callers can assert skipped_private counts.
        """
        tombstone = _alias(
            alias_name=rel_name,
            source="curator_private",
            canonical_cik=None,
        )
        rel = _make_rel(rel_name)
        rels_result = _scalars_result([rel])

        call_log = []

        async def fake_execute(stmt):
            compiled = str(stmt)
            if "counterparty_aliases" in compiled and "alias_normalized" in compiled:
                call_log.append("alias_lookup")
                r = MagicMock()
                r.scalar_one_or_none = MagicMock(return_value=tombstone)
                return r
            if "relationships" in compiled and "ticker" in compiled:
                call_log.append("rels_query")
                return rels_result
            # write-back cascade query
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=[])
            r = MagicMock()
            r.scalars = MagicMock(return_value=scalars)
            return r

        db = AsyncMock()
        db.add = MagicMock()
        db.execute = fake_execute
        db.flush = AsyncMock()

        # Patch EdgarClient so no real network call is made.
        mock_edgar = AsyncMock()
        mock_edgar.close = AsyncMock()
        mock_resolver = MagicMock()
        mock_resolver.load = AsyncMock()
        mock_resolver.match = MagicMock(return_value=[])  # no EDGAR candidates

        with patch(
            "backend.app.services.counterparty_resolver.EdgarClient",
            return_value=mock_edgar,
        ), patch(
            "backend.app.services.counterparty_resolver.CounterpartyResolver",
            return_value=mock_resolver,
        ):
            summary = await resolve_ticker_relationships("AAPL", db)

        return summary, rel

    async def test_tombstoned_rel_not_resolved(self):
        """A relationship whose normalized counterparty is tombstoned must NOT
        get resolved_to_cik written (Step 1 alias-reuse branch)."""
        summary, rel = await self._run_resolve(
            rel_name="OpenAI", tombstone_norm=normalize_name("OpenAI")
        )
        self.assertIsNone(rel.resolved_to_cik)

    async def test_tombstoned_increments_skipped_private(self):
        """skipped_private counter must be incremented for each tombstoned name
        encountered via the alias-reuse path."""
        summary, _ = await self._run_resolve(
            rel_name="OpenAI", tombstone_norm=normalize_name("OpenAI")
        )
        self.assertEqual(summary["skipped_private"], 1)

    async def test_tombstoned_via_cache_also_skipped(self):
        """When two Relationship rows share the same tombstoned name, the second
        hit goes through the local_alias_cache path. Both must be counted."""
        tombstone = _alias(
            alias_name="OpenAI",
            source="curator_private",
            canonical_cik=None,
        )
        rel1 = _make_rel("OpenAI")
        rel2 = _make_rel("OpenAI")

        alias_calls = {"n": 0}

        async def fake_execute(stmt):
            compiled = str(stmt)
            if "counterparty_aliases" in compiled and "alias_normalized" in compiled:
                alias_calls["n"] += 1
                r = MagicMock()
                # First real DB lookup returns tombstone; subsequent calls should
                # be served from cache (not re-querying DB).
                r.scalar_one_or_none = MagicMock(return_value=tombstone)
                return r
            if "relationships" in compiled and "ticker" in compiled:
                scalars = MagicMock()
                scalars.all = MagicMock(return_value=[rel1, rel2])
                r = MagicMock()
                r.scalars = MagicMock(return_value=scalars)
                return r
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=[])
            r = MagicMock()
            r.scalars = MagicMock(return_value=scalars)
            return r

        db = AsyncMock()
        db.add = MagicMock()
        db.execute = fake_execute
        db.flush = AsyncMock()

        mock_edgar = AsyncMock()
        mock_edgar.close = AsyncMock()
        mock_resolver = MagicMock()
        mock_resolver.load = AsyncMock()
        mock_resolver.match = MagicMock(return_value=[])

        with patch(
            "backend.app.services.counterparty_resolver.EdgarClient",
            return_value=mock_edgar,
        ), patch(
            "backend.app.services.counterparty_resolver.CounterpartyResolver",
            return_value=mock_resolver,
        ):
            summary = await resolve_ticker_relationships("AAPL", db)

        # Both rows should be counted in skipped_private
        self.assertEqual(summary["skipped_private"], 2)
        self.assertIsNone(rel1.resolved_to_cik)
        self.assertIsNone(rel2.resolved_to_cik)


# ── 3. queue exclusion regression ────────────────────────────────────────────


class TestQueueExcludesTombstone(unittest.IsolatedAsyncioTestCase):
    async def test_tombstoned_name_absent_from_unresolved_queue(self):
        """list_unresolved_counterparties already excludes names with ANY alias
        row. This test pins that a curator_private tombstone causes exclusion."""
        # Simulate: one unresolved relationship row named "OpenAI",
        # and its normalized form has a curator_private alias.
        openai_norm = normalize_name("OpenAI")
        aliased_norms = {openai_norm}

        # raw = [(counterparty_name, count, tickers), ...]
        raw_rows = [("OpenAI", 3, ["AAPL"])]

        call_n = {"n": 0}

        async def fake_execute(stmt):
            call_n["n"] += 1
            compiled = str(stmt)
            # aliased-norms query: SELECT alias_normalized FROM counterparty_aliases
            #   WHERE alias_normalized IN (__[POSTCOMPILE_alias_normalized_1])
            if "alias_normalized" in compiled and "POSTCOMPILE" in compiled:
                norm_list = list(aliased_norms)
                scalars = MagicMock()
                scalars.all = MagicMock(return_value=norm_list)
                scalars.__iter__ = MagicMock(return_value=iter(norm_list))
                r = MagicMock()
                r.scalars = MagicMock(return_value=scalars)
                return r
            # First query: aggregated unresolved rows (returns .all())
            r = MagicMock()
            r.all = MagicMock(return_value=raw_rows)
            return r

        db = AsyncMock()
        db.execute = fake_execute

        mock_edgar = AsyncMock()
        mock_edgar.close = AsyncMock()
        mock_resolver = MagicMock()
        mock_resolver.load = AsyncMock()
        mock_resolver.match = MagicMock(return_value=[])

        with patch(
            "backend.app.services.counterparty_resolver.EdgarClient",
            return_value=mock_edgar,
        ), patch(
            "backend.app.services.counterparty_resolver.CounterpartyResolver",
            return_value=mock_resolver,
        ):
            result = await list_unresolved_counterparties(db)

        # "OpenAI" should be excluded because its norm is in aliased_norms
        self.assertEqual(result, [])


# ── 4. undismiss_counterparty ─────────────────────────────────────────────────


class TestUndismiss(unittest.IsolatedAsyncioTestCase):
    async def test_deletes_tombstone(self):
        """undismiss_counterparty deletes the curator_private row."""
        tombstone = _alias(source="curator_private")
        db = _make_db(alias_lookup=tombstone)
        norm = tombstone.alias_normalized
        result = await undismiss_counterparty(db, alias_normalized=norm)
        db.delete.assert_awaited_once_with(tombstone)
        self.assertEqual(result["alias_normalized"], norm)
        self.assertTrue(result["restored"])

    async def test_raises_for_non_tombstone(self):
        """undismiss_counterparty must raise ValueError for curator_manual rows."""
        manual = _alias(source="curator_manual", canonical_cik="0001")
        db = _make_db(alias_lookup=manual)
        with self.assertRaises(ValueError) as ctx:
            await undismiss_counterparty(
                db, alias_normalized=manual.alias_normalized
            )
        self.assertIn("curator_private", str(ctx.exception))
        db.delete.assert_not_awaited()

    async def test_raises_for_missing_row(self):
        """undismiss_counterparty raises ValueError when no alias exists."""
        db = _make_db(alias_lookup=None)
        with self.assertRaises(ValueError):
            await undismiss_counterparty(db, alias_normalized="openai")


# ── 5. list_dismissed ─────────────────────────────────────────────────────────


class TestListDismissed(unittest.IsolatedAsyncioTestCase):
    async def test_returns_curator_private_rows(self):
        """list_dismissed must return only curator_private rows."""
        t1 = _alias(alias_name="OpenAI")
        t2 = _alias(alias_name="Anthropic")
        db = _make_db(scalars_rows=[t1, t2])
        rows = await list_dismissed(db)
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row.source, "curator_private")

    async def test_returns_empty_list_when_none(self):
        db = _make_db(scalars_rows=[])
        rows = await list_dismissed(db)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
