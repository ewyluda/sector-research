"""Pins services/supply_chain.py::build_theme_graph — the theme-wide graph
builder behind GET /api/relationships/theme-graph/{theme_id}.

Mocks at the SQLAlchemy execute() boundary. build_theme_graph issues exactly
3 execute() calls in fixed order:
  1. select(Theme).where(id)            -> .scalar_one_or_none()
  2. select(Theme.seed_tickers) (all)   -> .all()  (tracked-union helper)
  3. select(Relationship, Filing) join  -> .all()
"""
import os
import unittest
from datetime import date
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.filing import Filing, Relationship
from backend.app.models.theme import Theme
from backend.app.services.supply_chain import MAX_THEME_NODES, build_theme_graph

# Fixed UUID used as the test theme's id — must be a valid UUID string because
# themes.id is a Postgres UUID column and build_theme_graph guards on this.
_THEME_UUID = "a1b2c3d4-0000-0000-0000-000000000001"


def _result(rows=None, scalar_value=...):
    r = MagicMock()
    r.all.return_value = rows or []
    if scalar_value is not ...:
        r.scalar_one_or_none = MagicMock(return_value=scalar_value)
    return r


def _make_rel(*, ticker, counterparty_name, relationship_type,
              resolved_to_ticker=None, resolved_to_cik=None, unnamed=False,
              magnitude_pct=None, confirmed_bilateral=False):
    return Relationship(
        id=str(uuid4()), filing_id=str(uuid4()), ticker=ticker.upper(),
        section_key="item_1", source_type="filing",
        counterparty_name=counterparty_name,
        relationship_type=relationship_type, magnitude_pct=magnitude_pct,
        unnamed=unnamed, verbatim_quote="some quote",
        confirmed_bilateral=confirmed_bilateral,
        resolved_to_cik=resolved_to_cik,
        resolved_to_ticker=resolved_to_ticker.upper() if resolved_to_ticker else None,
    )


def _make_filing(ticker, accession="0000000000-00-000000"):
    return Filing(id=str(uuid4()), ticker=ticker.upper(),
                  accession_number=accession, form_type="10-K",
                  filing_date=date(2025, 1, 1), cik="0000000001")


def _make_theme(seeds):
    t = MagicMock(spec=Theme)
    t.id = _THEME_UUID
    t.name = "AI infra"
    t.seed_tickers = seeds
    return t


def _db(theme, all_seeds, rel_rows):
    """AsyncMock db with the 3 fixed-order execute results."""
    db = AsyncMock()
    db.execute.side_effect = [
        _result(scalar_value=theme),
        _result(rows=[(s,) for s in all_seeds]),
        _result(rows=rel_rows),
    ]
    return db


class ThemeGraphBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_theme_returns_none(self):
        db = AsyncMock()
        db.execute.side_effect = [_result(scalar_value=None)]
        self.assertIsNone(await build_theme_graph("nope", db=db))

    async def test_empty_seeds_returns_empty_graph(self):
        theme = _make_theme([])
        db = AsyncMock()
        db.execute.side_effect = [_result(scalar_value=theme)]
        g = await build_theme_graph(_THEME_UUID, db=db)
        self.assertEqual(g.nodes, [])
        self.assertEqual(g.edges, [])
        self.assertFalse(g.too_dense)

    async def test_basic_graph_seed_filer_and_resolved_counterparty(self):
        # NVDA (seed) discloses TSM as supplier (resolved).
        rel = _make_rel(ticker="NVDA", counterparty_name="Taiwan Semi",
                        relationship_type="supplier", resolved_to_ticker="TSM",
                        resolved_to_cik="0001046179")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            _THEME_UUID, db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        ids = {n.id for n in g.nodes}
        self.assertEqual(ids, {"ticker:NVDA", "ticker:TSM"})
        nvda = next(n for n in g.nodes if n.id == "ticker:NVDA")
        tsm = next(n for n in g.nodes if n.id == "ticker:TSM")
        self.assertTrue(nvda.in_selected_theme)
        self.assertEqual(nvda.hop, 0)
        self.assertFalse(tsm.in_selected_theme)
        self.assertEqual(tsm.hop, 1)
        self.assertEqual(len(g.edges), 1)
        e = g.edges[0]
        self.assertEqual((e.from_id, e.to_id), ("ticker:NVDA", "ticker:TSM"))
        self.assertEqual(e.direction, "out")
        self.assertEqual(g.node_count, 2)
        self.assertEqual(g.edge_count, 1)

    async def test_filer_and_counterparty_identity_unify_by_ticker(self):
        # ORCL appears as a filer AND as MSFT's resolved counterparty —
        # must be ONE node keyed ticker:ORCL, not ticker:ORCL + cik:....
        rel_a = _make_rel(ticker="MSFT", counterparty_name="Oracle Corp",
                          relationship_type="competitor",
                          resolved_to_ticker="ORCL", resolved_to_cik="0001341439")
        rel_b = _make_rel(ticker="ORCL", counterparty_name="Some Startup",
                          relationship_type="customer")
        theme = _make_theme(["MSFT", "ORCL"])
        g = await build_theme_graph(
            _THEME_UUID,
            db=_db(theme, [["MSFT", "ORCL"]],
                   [(rel_a, _make_filing("MSFT")), (rel_b, _make_filing("ORCL"))]))
        orcl_nodes = [n for n in g.nodes if n.ticker == "ORCL"]
        self.assertEqual(len(orcl_nodes), 1)
        self.assertEqual(orcl_nodes[0].id, "ticker:ORCL")
        # cik learned from the resolved row even if the filer row came first
        self.assertEqual(orcl_nodes[0].cik, "0001341439")

    async def test_unresolved_counterparty_is_terminal_named_node(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="CoreWeave, Inc.",
                        relationship_type="customer")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            _THEME_UUID, db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        unresolved = [n for n in g.nodes if n.id.startswith("unresolved:")]
        self.assertEqual(len(unresolved), 1)
        self.assertIsNone(unresolved[0].ticker)
        self.assertEqual(unresolved[0].name, "CoreWeave, Inc.")

    async def test_resolved_cik_without_ticker_keys_by_cik(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="Private Co",
                        relationship_type="supplier", resolved_to_cik="0009999999")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            _THEME_UUID, db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        self.assertIn("cik:0009999999", {n.id for n in g.nodes})

    async def test_self_edges_skipped(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="NVIDIA Corp",
                        relationship_type="other", resolved_to_ticker="NVDA")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            _THEME_UUID, db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        self.assertEqual(g.edges, [])

    async def test_magnitude_and_bilateral_pass_through(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="Taiwan Semi",
                        relationship_type="supplier", resolved_to_ticker="TSM",
                        magnitude_pct=22.5, confirmed_bilateral=True)
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            _THEME_UUID, db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        self.assertEqual(g.edges[0].magnitude_pct, 22.5)
        self.assertTrue(g.edges[0].confirmed_bilateral)

    async def test_tracked_flag_uses_union_of_all_themes(self):
        # TSM is not in this theme but seeded in another theme -> tracked=True.
        rel = _make_rel(ticker="NVDA", counterparty_name="Taiwan Semi",
                        relationship_type="supplier", resolved_to_ticker="TSM")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            _THEME_UUID,
            db=_db(theme, [["NVDA"], ["TSM"]], [(rel, _make_filing("NVDA"))]))
        tsm = next(n for n in g.nodes if n.id == "ticker:TSM")
        self.assertTrue(tsm.tracked)
        self.assertFalse(tsm.in_selected_theme)

    async def test_malformed_uuid_returns_none_without_query(self):
        # themes.id is a Postgres UUID column — a malformed id must short-
        # circuit to None (endpoint 404) instead of an asyncpg DataError 500.
        db = AsyncMock()
        self.assertIsNone(await build_theme_graph("bogus-id", db=db))
        db.execute.assert_not_called()

    async def test_too_dense_rail(self):
        # MAX_THEME_NODES+ distinct unresolved counterparties trip the rail.
        rels = [
            (_make_rel(ticker="NVDA", counterparty_name=f"Company {i}",
                       relationship_type="customer"), _make_filing("NVDA"))
            for i in range(MAX_THEME_NODES + 1)
        ]
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(_THEME_UUID, db=_db(theme, [["NVDA"]], rels))
        self.assertTrue(g.too_dense)
        self.assertEqual(g.nodes, [])
        self.assertEqual(g.edges, [])
        self.assertGreater(g.node_count, MAX_THEME_NODES)
        self.assertEqual(g.edge_count, MAX_THEME_NODES + 1)


if __name__ == "__main__":
    unittest.main()
