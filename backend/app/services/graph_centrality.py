"""Pure per-theme graph-centrality scoring (v3 graph pack item 2).

Input is the theme-wide graph build_theme_graph produces (PR #58). Undirected
projection: structure matters, not disclosure direction — a shared unresolved
supplier connecting two seeds is real betweenness. Unnamed nodes never reach
this module (excluded in SQL by the builder).

Output feeds the signals table (signal_type="centrality") as a bounded
discovery modifier — same routing decision as insider/congress: NOT a 4th
combined-score weight (centrality is sparse and slow-moving; a weight would
multiply zeros and force per-theme weight rework).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import networkx as nx

from backend.app.services.supply_chain import GraphEdge, GraphNode

# Centrality is meaningful only with reasonable density — a theme with 3
# relationships gets noisy scores. Below this edge count, no signal at all.
MIN_EDGES = 10
# Top 20% (ceil — at least one qualifies whenever the gate passes) of the
# theme's ticker nodes per metric.
TOP_FRACTION = 0.2
# A "hub" must actually be connected, not just rank high in a tiny field.
HUB_MIN_DEGREE = 3
# Mirrors INSIDER/CONGRESS_STALE_HOURS: one missed daily run tolerated.
CENTRALITY_STALE_HOURS = 48


@dataclass
class CentralityScores:
    ticker: str
    betweenness: float
    # None when the power iteration didn't converge — hub then impossible.
    eigenvector: float | None
    degree: int  # distinct neighbors (nx collapses parallel edges)
    is_hub: bool
    is_broker: bool


def compute_theme_centrality(
    nodes: list[GraphNode], edges: list[GraphEdge],
) -> dict[str, CentralityScores]:
    """Score every ticker-bearing node in the theme graph.

    Returns {} when the graph is below MIN_EDGES (density gate) — absent
    signal rows are a no-op modifier downstream, same as insider/congress.
    """
    if len(edges) < MIN_EDGES:
        return {}

    graph = nx.Graph()
    for n in nodes:
        graph.add_node(n.id)
    for e in edges:
        graph.add_edge(e.from_id, e.to_id)

    betweenness = nx.betweenness_centrality(graph)
    try:
        eigenvector = nx.eigenvector_centrality(graph, max_iter=500)
    except nx.PowerIterationFailedConvergence:
        eigenvector = None  # keep betweenness/broker; hub needs eigenvector

    ticker_nodes = [n for n in nodes if n.ticker]
    if not ticker_nodes:
        return {}
    top_n = math.ceil(len(ticker_nodes) * TOP_FRACTION)

    def _top_cutoff(values: dict[str, float]) -> float:
        ranked = sorted(
            (values.get(n.id, 0.0) for n in ticker_nodes), reverse=True,
        )
        return ranked[top_n - 1]

    bet_cutoff = _top_cutoff(betweenness)
    eig_cutoff = _top_cutoff(eigenvector) if eigenvector is not None else None

    scores: dict[str, CentralityScores] = {}
    for n in ticker_nodes:
        ticker = (n.ticker or "").upper()
        bet = betweenness.get(n.id, 0.0)
        eig = eigenvector.get(n.id, 0.0) if eigenvector is not None else None
        degree = graph.degree(n.id) if n.id in graph else 0
        is_hub = (
            eig is not None
            and eig_cutoff is not None
            and eig >= eig_cutoff
            and degree >= HUB_MIN_DEGREE
        )
        is_broker = bet >= bet_cutoff and bet > 0
        scores[ticker] = CentralityScores(
            ticker=ticker, betweenness=bet, eigenvector=eig,
            degree=degree, is_hub=is_hub, is_broker=is_broker,
        )
    return scores


def modifier_from_scores(scores: CentralityScores) -> int:
    """+3 hub, +2 broker — larger wins, never summed (spec)."""
    if scores.is_hub:
        return 3
    if scores.is_broker:
        return 2
    return 0


def signal_value(scores: CentralityScores) -> dict:
    """JSONB payload for the signals row (signal_type='centrality') —
    same convention as congress_signal.signal_value."""
    return {**asdict(scores), "modifier": modifier_from_scores(scores)}
