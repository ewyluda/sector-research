"""Pins multi-hop BFS behaviour in services/supply_chain.py::get_graph.

Mocks at the SQLAlchemy execute() boundary. Each hop emits one or two
execute() calls (one for "out", one for "in" — direction-dependent).
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
from backend.app.services.supply_chain import get_graph


# ── Result-mock helpers ──────────────────────────────────────────────────────


def _result(rows=None, scalar_value=...):
    """Fake SQLAlchemy Result. `rows` feeds .all(); `scalar_value` feeds
    .scalar_one_or_none() (use `...` sentinel to skip)."""
    r = MagicMock()
    r.all.return_value = rows or []
    if scalar_value is not ...:
        r.scalar_one_or_none = MagicMock(return_value=scalar_value)
    return r


def _make_rel(
    *,
    ticker: str,
    counterparty_name: str,
    relationship_type: str,
    resolved_to_ticker: str | None = None,
    resolved_to_cik: str | None = None,
    unnamed: bool = False,
    magnitude_pct: float | None = None,
    confirmed_bilateral: bool = False,
) -> Relationship:
    rel = Relationship(
        id=str(uuid4()),
        filing_id=str(uuid4()),
        ticker=ticker.upper(),
        section_key="item_1",
        source_type="filing",
        counterparty_name=counterparty_name,
        relationship_type=relationship_type,
        magnitude_pct=magnitude_pct,
        unnamed=unnamed,
        verbatim_quote="some quote",
        confirmed_bilateral=confirmed_bilateral,
        resolved_to_cik=resolved_to_cik,
        resolved_to_ticker=resolved_to_ticker.upper() if resolved_to_ticker else None,
    )
    return rel


def _make_filing(ticker: str, accession: str = "0000000000-00-000000") -> Filing:
    return Filing(
        id=str(uuid4()),
        ticker=ticker.upper(),
        accession_number=accession,
        form_type="10-K",
        filing_date=date(2025, 1, 1),
        cik="0000000001",
    )


# ── Scenario builder ─────────────────────────────────────────────────────────


class _Scenario:
    """Curates outbound + inbound (Relationship, Filing) lists keyed by ticker.

    The fake `db.execute` interprets each select() by inspecting its compiled
    WHERE clause to decide which scenario list to return. This avoids
    hand-ordering side_effects when BFS hops re-query the same shape multiple
    times.
    """

    def __init__(
        self,
        *,
        all_theme_seeds: list[list[str]],
        out_by_ticker: dict[str, list[tuple]] | None = None,
        in_by_ticker: dict[str, list[tuple]] | None = None,
        single_theme_seeds: list[str] | None = None,
    ):
        self.all_theme_seeds = all_theme_seeds
        self.out_by_ticker = out_by_ticker or {}
        self.in_by_ticker = in_by_ticker or {}
        self.single_theme_seeds = single_theme_seeds
        self.calls: list[str] = []  # log of dispatched query types

    async def execute(self, stmt):
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        # _load_tracked_set: SELECT themes.seed_tickers (no WHERE on themes.id)
        if "themes.seed_tickers" in compiled and "themes.id" not in compiled:
            self.calls.append("tracked_set")
            return _result(rows=[(seeds,) for seeds in self.all_theme_seeds])
        # _load_theme_seeds: SELECT themes.seed_tickers WHERE themes.id = X
        if "themes.seed_tickers" in compiled and "themes.id" in compiled:
            self.calls.append("theme_seeds")
            return _result(scalar_value=self.single_theme_seeds or [])
        # Look for the WHERE comparison — both column names appear in the
        # SELECT list, so we must inspect the equality (= ') specifically.
        # Inbound is determined first because its WHERE has both clauses
        # (resolved_to_ticker = X AND ticker != X).
        if "relationships.resolved_to_ticker = '" in compiled:
            ticker = self._extract_after(compiled, "relationships.resolved_to_ticker = '")
            self.calls.append(f"in:{ticker}")
            rows = self.in_by_ticker.get(ticker, [])
            return _result(rows=rows)
        if "relationships.ticker = '" in compiled:
            ticker = self._extract_after(compiled, "relationships.ticker = '")
            self.calls.append(f"out:{ticker}")
            rows = self.out_by_ticker.get(ticker, [])
            return _result(rows=rows)
        raise AssertionError(f"unexpected query: {compiled[:200]}")

    @staticmethod
    def _extract_after(compiled: str, marker: str) -> str:
        idx = compiled.find(marker)
        if idx == -1:
            return ""
        start = idx + len(marker)
        end = compiled.find("'", start)
        return compiled[start:end] if end != -1 else compiled[start:]


def _fake_db(scenario: _Scenario):
    db = MagicMock()
    db.execute = AsyncMock(side_effect=scenario.execute)
    return db


# ── Tests ────────────────────────────────────────────────────────────────────


class Depth1ByteIdenticalTests(unittest.IsolatedAsyncioTestCase):
    """At depth=1 the new code path must produce the same nodes+edges as today
    (plus the two new fields: hop on every node/edge, in_selected_theme False
    on every node when theme_id is omitted)."""

    async def test_one_outbound_named_counterparty(self):
        rel = _make_rel(
            ticker="NVDA",
            counterparty_name="Microsoft Corporation",
            relationship_type="customer",
            resolved_to_ticker="MSFT",
            resolved_to_cik="0000789019",
        )
        filing = _make_filing("NVDA", "0001045810-25-000001")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA", "MSFT"]],
            out_by_ticker={"NVDA": [(rel, filing)]},
            in_by_ticker={},
        )
        db = _fake_db(scenario)

        graph = await get_graph("NVDA", direction="out", db=db)

        self.assertEqual(graph.root_ticker, "NVDA")
        self.assertEqual(len(graph.nodes), 2)
        root = next(n for n in graph.nodes if n.is_root)
        cp = next(n for n in graph.nodes if not n.is_root)
        self.assertEqual(root.hop, 0)
        self.assertEqual(cp.hop, 1)
        self.assertTrue(root.tracked)
        self.assertTrue(cp.tracked)
        self.assertFalse(root.in_selected_theme)
        self.assertFalse(cp.in_selected_theme)
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(graph.edges[0].hop, 1)
        self.assertEqual(graph.edges[0].direction, "out")

    async def test_one_inbound_edge(self):
        rel = _make_rel(
            ticker="MSFT",
            counterparty_name="NVIDIA",
            relationship_type="supplier",
            resolved_to_ticker="NVDA",
        )
        filing = _make_filing("MSFT")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA", "MSFT"]],
            in_by_ticker={"NVDA": [(rel, filing)]},
        )
        db = _fake_db(scenario)

        graph = await get_graph("NVDA", direction="in", db=db)
        self.assertEqual(len(graph.edges), 1)
        self.assertEqual(graph.edges[0].hop, 1)
        self.assertEqual(graph.edges[0].direction, "in")


class Depth2ExpansionGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_theme_id_narrows_expansion(self):
        # NVDA → MSFT (in-theme) and NVDA → AAPL (out-of-theme).
        # At depth=2 with theme_id pointing at a theme that contains only MSFT,
        # only MSFT gets expanded. AAPL is hop-1 terminal.
        rel_msft = _make_rel(
            ticker="NVDA",
            counterparty_name="Microsoft",
            relationship_type="customer",
            resolved_to_ticker="MSFT",
        )
        rel_aapl = _make_rel(
            ticker="NVDA",
            counterparty_name="Apple",
            relationship_type="customer",
            resolved_to_ticker="AAPL",
        )
        rel_goog = _make_rel(
            ticker="MSFT",
            counterparty_name="Google",
            relationship_type="partner",
            resolved_to_ticker="GOOG",
        )
        filing_n = _make_filing("NVDA")
        filing_m = _make_filing("MSFT")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA", "MSFT", "AAPL", "GOOG"]],
            single_theme_seeds=["NVDA", "MSFT"],
            out_by_ticker={
                "NVDA": [(rel_msft, filing_n), (rel_aapl, filing_n)],
                "MSFT": [(rel_goog, filing_m)],
                "AAPL": [],  # would be empty even if expanded
            },
        )
        db = _fake_db(scenario)

        graph = await get_graph(
            "NVDA", direction="out", depth=2, theme_id="t1", db=db,
        )

        ticker_nodes = {n.ticker: n for n in graph.nodes if n.ticker}
        self.assertIn("NVDA", ticker_nodes)
        self.assertIn("MSFT", ticker_nodes)
        self.assertIn("AAPL", ticker_nodes)
        self.assertIn("GOOG", ticker_nodes)  # reached via MSFT expansion
        # MSFT is in_selected_theme; AAPL is not.
        self.assertTrue(ticker_nodes["MSFT"].in_selected_theme)
        self.assertFalse(ticker_nodes["AAPL"].in_selected_theme)
        # AAPL was NOT expanded — no "out:AAPL" call.
        self.assertNotIn("out:AAPL", scenario.calls)
        self.assertIn("out:MSFT", scenario.calls)
        # GOOG appears as hop-2.
        self.assertEqual(ticker_nodes["GOOG"].hop, 2)

    async def test_tracked_union_fallback_when_theme_id_omitted(self):
        # Without theme_id, expansion uses the tracked-union (every ticker in
        # any theme's seed_tickers). Confirm both hop-1 nodes get expanded.
        rel_msft = _make_rel(
            ticker="NVDA",
            counterparty_name="Microsoft",
            relationship_type="customer",
            resolved_to_ticker="MSFT",
        )
        rel_aapl = _make_rel(
            ticker="NVDA",
            counterparty_name="Apple",
            relationship_type="customer",
            resolved_to_ticker="AAPL",
        )
        filing = _make_filing("NVDA")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA", "MSFT"], ["AAPL"]],
            out_by_ticker={
                "NVDA": [(rel_msft, filing), (rel_aapl, filing)],
                "MSFT": [],
                "AAPL": [],
            },
        )
        db = _fake_db(scenario)

        await get_graph("NVDA", direction="out", depth=2, db=db)
        # Both MSFT and AAPL get expanded.
        self.assertIn("out:MSFT", scenario.calls)
        self.assertIn("out:AAPL", scenario.calls)

    async def test_unresolved_counterparty_is_terminal(self):
        # An unresolved counterparty (no resolved_to_ticker) at hop 1 has no
        # ticker to expand from, so no hop-2 query is issued for it.
        rel = _make_rel(
            ticker="NVDA",
            counterparty_name="Some Private Vendor LLC",
            relationship_type="supplier",
            resolved_to_ticker=None,
        )
        filing = _make_filing("NVDA")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA"]],
            out_by_ticker={"NVDA": [(rel, filing)]},
        )
        db = _fake_db(scenario)

        await get_graph("NVDA", direction="out", depth=2, db=db)
        # Only the root expansion happened. No "out:<anything>" beyond NVDA.
        out_calls = [c for c in scenario.calls if c.startswith("out:")]
        self.assertEqual(out_calls, ["out:NVDA"])

    async def test_unnamed_concentration_is_terminal(self):
        # An "unnamed customer at 15%" row produces a synthetic terminal node.
        # It cannot be expanded.
        rel = _make_rel(
            ticker="NVDA",
            counterparty_name="[unnamed customer]",
            relationship_type="customer",
            unnamed=True,
            magnitude_pct=15.0,
        )
        filing = _make_filing("NVDA")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA"]],
            out_by_ticker={"NVDA": [(rel, filing)]},
        )
        db = _fake_db(scenario)

        graph = await get_graph("NVDA", direction="out", depth=2, db=db)
        unnamed_node = next((n for n in graph.nodes if n.unnamed), None)
        self.assertIsNotNone(unnamed_node)
        self.assertEqual(unnamed_node.hop, 1)
        # No hop-2 expansion for the unnamed bucket.
        out_calls = [c for c in scenario.calls if c.startswith("out:")]
        self.assertEqual(out_calls, ["out:NVDA"])


class Depth2CycleAndDedupTests(unittest.IsolatedAsyncioTestCase):
    async def test_cycle_edge_emitted_root_node_not_duplicated(self):
        # NVDA → MSFT (hop 1) → NVDA (hop 2 back-edge). Root node appears once.
        rel_nvda_msft = _make_rel(
            ticker="NVDA",
            counterparty_name="Microsoft",
            relationship_type="customer",
            resolved_to_ticker="MSFT",
        )
        rel_msft_nvda = _make_rel(
            ticker="MSFT",
            counterparty_name="NVIDIA",
            relationship_type="supplier",
            resolved_to_ticker="NVDA",
        )
        filing_n = _make_filing("NVDA")
        filing_m = _make_filing("MSFT")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA", "MSFT"]],
            out_by_ticker={
                "NVDA": [(rel_nvda_msft, filing_n)],
                "MSFT": [(rel_msft_nvda, filing_m)],
            },
        )
        db = _fake_db(scenario)

        graph = await get_graph("NVDA", direction="out", depth=2, db=db)

        # Root NVDA appears exactly once.
        root_nodes = [n for n in graph.nodes if n.ticker == "NVDA"]
        self.assertEqual(len(root_nodes), 1)
        self.assertTrue(root_nodes[0].is_root)
        # Two edges: NVDA→MSFT (hop 1) and MSFT→NVDA (hop 2 back-edge).
        self.assertEqual(len(graph.edges), 2)
        hops = sorted(e.hop for e in graph.edges)
        self.assertEqual(hops, [1, 2])
        # The hop-2 edge points to root.
        hop2_edge = next(e for e in graph.edges if e.hop == 2)
        self.assertEqual(hop2_edge.to_id, "root:NVDA")

    async def test_edge_dedup_by_relationship_id_under_both(self):
        # direction=both. MSFT→NVDA reachable at hop-1 inbound AND at hop-2
        # outbound expansion of MSFT. Same Relationship row → one edge.
        rel_msft_nvda = _make_rel(
            ticker="MSFT",
            counterparty_name="NVIDIA",
            relationship_type="supplier",
            resolved_to_ticker="NVDA",
        )
        filing_m = _make_filing("MSFT")
        # Also a NVDA→MSFT outbound to give us a hop-1 path to expand.
        rel_nvda_msft = _make_rel(
            ticker="NVDA",
            counterparty_name="Microsoft",
            relationship_type="customer",
            resolved_to_ticker="MSFT",
        )
        filing_n = _make_filing("NVDA")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA", "MSFT"]],
            out_by_ticker={
                "NVDA": [(rel_nvda_msft, filing_n)],
                "MSFT": [(rel_msft_nvda, filing_m)],
            },
            in_by_ticker={
                "NVDA": [(rel_msft_nvda, filing_m)],  # MSFT filing names NVDA
                "MSFT": [],
            },
        )
        db = _fake_db(scenario)

        graph = await get_graph("NVDA", direction="both", depth=2, db=db)
        # Two unique Relationship.ids → two edges total, no duplicate.
        # Each Relationship.id appears at most once.
        rel_ids = [
            (e.from_id, e.to_id, e.relationship_type, e.source_ticker)
            for e in graph.edges
        ]
        self.assertEqual(len(rel_ids), len(set(rel_ids)))


class DepthCapTests(unittest.IsolatedAsyncioTestCase):
    async def test_depth_3_raises(self):
        scenario = _Scenario(all_theme_seeds=[[]])
        db = _fake_db(scenario)
        with self.assertRaises(ValueError):
            await get_graph("NVDA", direction="out", depth=3, db=db)


class InSelectedThemeFlagTests(unittest.IsolatedAsyncioTestCase):
    async def test_flag_set_only_for_theme_seed_tickers(self):
        rel = _make_rel(
            ticker="NVDA",
            counterparty_name="Microsoft",
            relationship_type="customer",
            resolved_to_ticker="MSFT",
        )
        filing = _make_filing("NVDA")
        scenario = _Scenario(
            all_theme_seeds=[["NVDA", "MSFT"]],
            single_theme_seeds=["MSFT"],  # NVDA is root (special), MSFT is in theme
            out_by_ticker={"NVDA": [(rel, filing)], "MSFT": []},
        )
        db = _fake_db(scenario)

        graph = await get_graph(
            "NVDA", direction="out", depth=2, theme_id="t1", db=db,
        )
        msft = next(n for n in graph.nodes if n.ticker == "MSFT")
        nvda = next(n for n in graph.nodes if n.ticker == "NVDA")
        self.assertTrue(msft.in_selected_theme)
        # Root is NOT automatically in the selected theme.
        self.assertFalse(nvda.in_selected_theme)


if __name__ == "__main__":
    unittest.main()
