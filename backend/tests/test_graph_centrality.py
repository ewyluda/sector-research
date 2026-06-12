"""Pins services/graph_centrality.py — pure per-theme centrality over the
theme-wide supply-chain graph (build_theme_graph output).

Hand-built graphs: a star (center = hub), a bridge/barbell (bridge = broker),
sparse graphs below the edge gate, and the eigenvector non-convergence path.
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.services.graph_centrality import (
    MIN_EDGES,
    CentralityScores,
    compute_theme_centrality,
    modifier_from_scores,
    signal_value,
)
from backend.app.services.supply_chain import GraphEdge, GraphNode


def _node(node_id, ticker=None, seed=False):
    return GraphNode(
        id=node_id, ticker=ticker, cik=None, name=ticker or node_id,
        is_root=False, tracked=bool(ticker), unnamed=False,
        hop=0 if seed else 1, in_selected_theme=seed,
    )


def _edge(from_id, to_id, rel_type="customer"):
    return GraphEdge(
        from_id=from_id, to_id=to_id, relationship_type=rel_type,
        direction="out", magnitude_pct=None, unnamed=False,
        confirmed_bilateral=False, verbatim_quote=None,
        source_ticker="X", accession_number="0000000000-00-000000",
        filing_date="2025-01-01", section_key="item_1", hop=1,
    )


def _star(center="HUB", leaves=12):
    """Star graph: center node connected to `leaves` distinct counterparties."""
    nodes = [_node("ticker:HUB", "HUB", seed=True)]
    edges = []
    for i in range(leaves):
        nodes.append(_node(f"unresolved:leaf{i}"))
        edges.append(_edge("ticker:HUB", f"unresolved:leaf{i}"))
    return nodes, edges


class ComputeTests(unittest.TestCase):
    def test_below_edge_gate_returns_empty(self):
        nodes, edges = _star(leaves=MIN_EDGES - 1)
        self.assertEqual(compute_theme_centrality(nodes, edges), {})

    def test_star_center_is_hub(self):
        nodes, edges = _star(leaves=12)
        scores = compute_theme_centrality(nodes, edges)
        self.assertIn("HUB", scores)
        s = scores["HUB"]
        self.assertTrue(s.is_hub)
        self.assertEqual(s.degree, 12)
        self.assertIsNotNone(s.eigenvector)

    def test_only_ticker_nodes_get_entries(self):
        nodes, edges = _star(leaves=12)
        scores = compute_theme_centrality(nodes, edges)
        self.assertEqual(set(scores), {"HUB"})  # leaves are unresolved

    def test_bridge_ticker_is_broker(self):
        # Two 4-cliques of unresolved nodes joined ONLY through ticker BRG.
        nodes, edges = [], []
        for side in ("a", "b"):
            ids = [f"unresolved:{side}{i}" for i in range(4)]
            nodes += [_node(i) for i in ids]
            for i in range(4):
                for j in range(i + 1, 4):
                    edges.append(_edge(ids[i], ids[j]))
        nodes.append(_node("ticker:BRG", "BRG", seed=True))
        edges.append(_edge("ticker:BRG", "unresolved:a0"))
        edges.append(_edge("ticker:BRG", "unresolved:b0"))
        scores = compute_theme_centrality(nodes, edges)
        s = scores["BRG"]
        self.assertTrue(s.is_broker)
        self.assertGreater(s.betweenness, 0)
        # degree 2 < HUB_MIN_DEGREE → not a hub even if eigenvector ranks high
        self.assertFalse(s.is_hub)

    def test_low_degree_ticker_is_neither(self):
        nodes, edges = _star(leaves=12)
        nodes.append(_node("ticker:LEAF", "LEAF", seed=True))
        edges.append(_edge("ticker:HUB", "ticker:LEAF"))
        scores = compute_theme_centrality(nodes, edges)
        leaf = scores["LEAF"]
        self.assertFalse(leaf.is_hub)
        self.assertFalse(leaf.is_broker)

    def test_parallel_edges_collapse_to_one_neighbor(self):
        # nx.Graph collapses parallel edges; degree = distinct neighbors.
        nodes, edges = _star(leaves=12)
        edges.append(_edge("ticker:HUB", "unresolved:leaf0", rel_type="supplier"))
        scores = compute_theme_centrality(nodes, edges)
        self.assertEqual(scores["HUB"].degree, 12)


class ModifierTests(unittest.TestCase):
    def _scores(self, hub=False, broker=False):
        return CentralityScores(
            ticker="T", betweenness=0.5, eigenvector=0.5, degree=5,
            is_hub=hub, is_broker=broker,
        )

    def test_hub_wins_over_broker(self):
        self.assertEqual(modifier_from_scores(self._scores(hub=True, broker=True)), 3)

    def test_broker_only(self):
        self.assertEqual(modifier_from_scores(self._scores(broker=True)), 2)

    def test_neither(self):
        self.assertEqual(modifier_from_scores(self._scores()), 0)

    def test_signal_value_payload(self):
        v = signal_value(self._scores(hub=True))
        self.assertEqual(v["modifier"], 3)
        self.assertEqual(v["ticker"], "T")
        self.assertTrue(v["is_hub"])


if __name__ == "__main__":
    unittest.main()
