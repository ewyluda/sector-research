"""Pure per-theme graph-centrality scoring (v3 graph pack item 2).

Input is the theme-wide graph build_theme_graph produces (PR #58). Undirected
projection: structure matters, not disclosure direction — a shared unresolved
supplier connecting two seeds is real betweenness. Unnamed nodes never reach
this module (excluded in SQL by the builder).

Output feeds the signals table (signal_type="centrality") as a bounded
discovery modifier — same routing decision as insider/congress: NOT a 4th
combined-score weight (centrality is sparse and slow-moving; a weight would
multiply zeros and force per-theme weight rework).

**Per-component design:** theme graphs are routinely disconnected (seeds only
connect through shared counterparties, so isolated stars are the norm). Global
eigenvector_centrality on a disconnected graph squashes every node outside the
largest component toward 0 — a genuine local hub in a smaller component loses
the top-20% cutoff silently. We therefore iterate connected components and
classify within each, so component-local hubs and brokers are recognised
regardless of component size.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import networkx as nx

from backend.app.services.supply_chain import GraphEdge, GraphNode

# Centrality is meaningful only with reasonable density — a theme with 3
# relationships gets noisy scores. Below this edge count, no signal at all.
MIN_EDGES = 10
# A component with fewer than this many edges is a trivial fragment — one
# filer's disclosure star — and shouldn't mint hub/broker badges; metric
# values are still recorded in CentralityScores.
MIN_COMPONENT_EDGES = 5
# Top 20% (ceil — at least one qualifies whenever the gate passes) of the
# component's ticker nodes per metric.
TOP_FRACTION = 0.2
# A "hub" must actually be connected, not just rank high in a tiny field.
HUB_MIN_DEGREE = 3
# Mirrors INSIDER/CONGRESS_STALE_HOURS: one missed daily run tolerated.
CENTRALITY_STALE_HOURS = 48


@dataclass
class CentralityScores:
    ticker: str
    # Component-local betweenness (0.0 when node is isolated in its component).
    betweenness: float
    # Component-local eigenvector. None when power iteration didn't converge
    # for this node's component — hub then impossible for that component.
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

    Classification is per connected component so that local hubs in smaller
    components are not penalised by global eigenvector normalisation.
    """
    if len(edges) < MIN_EDGES:
        return {}

    graph = nx.Graph()
    for n in nodes:
        graph.add_node(n.id)
    for e in edges:
        graph.add_edge(e.from_id, e.to_id)

    ticker_nodes = [n for n in nodes if n.ticker]
    if not ticker_nodes:
        return {}

    # Index ticker nodes by graph id for fast lookup inside the component loop.
    ticker_node_by_id: dict[str, GraphNode] = {n.id: n for n in ticker_nodes}

    scores: dict[str, CentralityScores] = {}

    for component_ids in nx.connected_components(graph):
        sub = graph.subgraph(component_ids)

        # Compute component-local metrics.
        bet_map = nx.betweenness_centrality(sub)
        try:
            eig_map: dict[str, float] | None = nx.eigenvector_centrality(
                sub, max_iter=500,
            )
        except nx.PowerIterationFailedConvergence:
            # Keep betweenness/broker; hub requires eigenvector.
            eig_map = None

        # Ticker nodes that live in this component.
        comp_ticker_nodes = [
            n for n in ticker_nodes if n.id in component_ids
        ]

        # A trivial fragment (one filer's disclosure star) shouldn't mint
        # hub/broker badges; scores are still recorded.
        classify = sub.number_of_edges() >= MIN_COMPONENT_EDGES

        if classify and comp_ticker_nodes:
            top_n = math.ceil(len(comp_ticker_nodes) * TOP_FRACTION)

            def _cutoff(values: dict[str, float]) -> float:
                ranked = sorted(
                    (values.get(n.id, 0.0) for n in comp_ticker_nodes),
                    reverse=True,
                )
                return ranked[top_n - 1]

            bet_cutoff = _cutoff(bet_map)
            eig_cutoff = _cutoff(eig_map) if eig_map is not None else None
        else:
            bet_cutoff = None
            eig_cutoff = None

        for n_id in component_ids:
            if n_id not in ticker_node_by_id:
                continue
            n = ticker_node_by_id[n_id]
            ticker = (n.ticker or "").upper()
            bet = bet_map.get(n_id, 0.0)
            eig = eig_map.get(n_id, 0.0) if eig_map is not None else None
            degree = sub.degree(n_id)

            if classify and bet_cutoff is not None:
                # Ties at the cutoff all qualify — a symmetric field promotes
                # everyone; deliberate.
                is_hub = (
                    eig is not None
                    and eig_cutoff is not None
                    and eig >= eig_cutoff
                    and degree >= HUB_MIN_DEGREE
                )
                is_broker = bet >= bet_cutoff and bet > 0
            else:
                is_hub = False
                is_broker = False

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
