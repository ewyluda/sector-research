# Graph Centrality → Discovery Ranking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Betweenness + eigenvector centrality computed per theme over the theme-wide relationship graph, persisted as `signals` rows (`signal_type="centrality"`), feeding discovery ranking as a bounded modifier (+3 hub / +2 broker) with a Hub/Broker chip on discovery cards.

**Architecture:** Pure NetworkX module (`services/graph_centrality.py`) over the `build_theme_graph` output (PR #58); persisted via the existing `_persist_signal_set` dual-write in `signal_scheduler.run_daily_refresh` (per-theme, fault-isolated); applied in discovery via the `_apply_cached_modifier` family exactly like insider/congress. **The congress signal (2026-06-11) is the precedent for every layer — mirror it.**

**Tech Stack:** networkx (new backend dep), existing signals/signal_history tables (no migration), React chip on theme detail.

**Spec:** `docs/superpowers/specs/2026-06-12-v3-graph-pack-design.md` item 2.

**Key pre-verified seams** (re-verify against the file before editing):
- `signal_scheduler._persist_signal_set(db, ticker, theme_id, results, computed_at)` — Signal replace + SignalHistory append per signal_type; centrality rides it with `{"centrality": payload}`.
- `signal_scheduler.run_daily_refresh` — `async with async_session() as db:` loop over themes calling `refresh_theme_signals`; find the existing commit point in/after `refresh_theme_signals` and mirror it for the centrality pass (async_session does NOT autocommit).
- `discovery._apply_cached_modifier(base, signal_data, now, stale_hours)` — reads `signal_data["modifier"]` + `signal_data["computed_at"]` (ISO string), clamps [0,100]; `_load_cached_signals` merges `computed_at` into every cached payload automatically.
- `discovery._merge_results` — insider block then congress block (~line 565-590); centrality block goes after congress, identical shape.
- `congress_signal.signal_value(agg) = {**asdict(agg), "modifier": modifier_from_aggregate(agg)}` — copy this payload convention.
- `CompanySignalCard` (discovery.py ~line 86) carries `insider`/`congress` snapshot fields; frontend mirrors in `frontend/lib/api/themes.ts` (`InsiderSnapshot`/`CongressSnapshot` interfaces ~lines 43-78). Find the congress chip on the theme-detail card component and mirror it.
- `supply_chain.build_theme_graph(theme_id, *, db)` → `ThemeGraph` with `nodes: list[GraphNode]`, `edges: list[GraphEdge]`, `too_dense` — the centrality input.

---

### Task 0: Branch

- [ ] **Step 0.1:**
```bash
cd /Users/ericwyluda/Development/projects/sector-research
git checkout main && git pull --ff-only && git checkout -b feat/graph-centrality
```

---

### Task 1: Pure centrality module

**Files:**
- Modify: `backend/requirements.txt` (add `networkx` — match the file's pin style) + `pip install networkx` into `backend/venv`
- Create: `backend/app/services/graph_centrality.py`
- Test: `backend/tests/test_graph_centrality.py` (create)

- [ ] **Step 1.1: Write failing tests** — hand-built small graphs with exact assertions:

```python
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
```

- [ ] **Step 1.2: Run — expect ImportError** (`python -m unittest backend.tests.test_graph_centrality -v`, venv active, from project root).

- [ ] **Step 1.3: Implement** `backend/app/services/graph_centrality.py`:

```python
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
```

- [ ] **Step 1.4: Run tests** — all pass. Then `ruff check backend`.
- [ ] **Step 1.5: Commit** — `feat(signals): pure per-theme graph-centrality scoring` (include `backend/requirements.txt`).

---

### Task 2: Scheduler wiring

**Files:**
- Modify: `backend/app/services/signal_scheduler.py`
- Test: `backend/tests/test_centrality_scheduler.py` (create — mirror `backend/tests/test_congress_scheduler.py` conventions; read it first)

- [ ] **Step 2.1: Failing tests** — `refresh_theme_centrality(theme, db)`:
  - graph below gate / too_dense / build returns None → no persist calls, summary reflects skip
  - normal path → `_persist_signal_set` called once per scored ticker with `{"centrality": {...}}` and a shared `computed_at`; payload carries `modifier`
  - fault isolation: `build_theme_graph` raising → summary `errors` count, no raise
  Patch `backend.app.services.signal_scheduler.build_theme_graph` and `_persist_signal_set` (AsyncMock) — assert call shapes, not SQL.
- [ ] **Step 2.2: Implement:**
  - Import `build_theme_graph` from supply_chain and `compute_theme_centrality`/`signal_value` from graph_centrality.
  - `async def refresh_theme_centrality(theme: Theme, db: AsyncSession) -> dict` — build graph (skip on None/too_dense/empty with a log line + summary), compute, persist per ticker via `_persist_signal_set(db, ticker, theme.id, {"centrality": signal_value(s)}, computed_at)` with one shared `computed_at = datetime.now(timezone.utc)`.
  - Call it from `run_daily_refresh` inside the existing per-theme loop, AFTER `refresh_theme_signals`, wrapped in try/except (log + count, never abort the theme loop). Mirror where the existing flow commits — `_persist_signal_set` does not commit; confirm `refresh_theme_signals`' commit placement and commit the centrality writes the same way.
- [ ] **Step 2.3: Tests green + ruff + full suite.** Commit: `feat(signals): daily per-theme centrality refresh in signal_scheduler`.

---

### Task 3: Discovery modifier + snapshot

**Files:**
- Modify: `backend/app/services/discovery.py`
- Test: extend `backend/tests/test_discovery_scoring.py` conventions in a new `backend/tests/test_centrality_modifier.py`

- [ ] **Step 3.1: Failing tests** (mirror the congress modifier tests in `test_discovery_scoring.py` — read them first): fresh hub +3 / broker +2 / zero-modifier no-op / stale (>48h) no-op / absent no-op / clamp at 100 / `CentralitySnapshot` population in `_merge_results` is covered implicitly by the modifier unit tests plus one snapshot-shape test if the existing suite has a precedent (follow it; if congress has no merge-level test, don't invent one).
- [ ] **Step 3.2: Implement** in `discovery.py`:
  - `from backend.app.services.graph_centrality import CENTRALITY_STALE_HOURS`
  - `apply_centrality_modifier(base_score, centrality_data, now)` → `_apply_cached_modifier(base_score, centrality_data, now, CENTRALITY_STALE_HOURS)` with a docstring noting it's the third bounded-modifier signal and deliberately NOT a 4th weight.
  - `@dataclass CentralitySnapshot` next to `CongressSnapshot` — fields: `modifier: int = 0`, `betweenness: float | None = None`, `eigenvector: float | None = None`, `degree: int = 0`, `is_hub: bool = False`, `is_broker: bool = False`, `is_stale: bool = True` — copy the is_stale-overloading NOTE by reference ("Same shape and is_stale overloading as InsiderSnapshot").
  - `CompanySignalCard` gains `centrality: CentralitySnapshot = field(default_factory=CentralitySnapshot)`.
  - In `_merge_results`, after the congress block: `centrality_data = ticker_signals.get("centrality", {})`, apply modifier, build snapshot (`is_stale=centrality_modifier == 0 and bool(centrality_data)`), pass `centrality=centrality_snap` into the `CompanySignalCard(...)` constructor.
  - Check how cards reach the API response (likely `asdict`) — the new field should flow without endpoint changes; verify by reading the themes API serialization path.
- [ ] **Step 3.3: Tests green + ruff + full suite.** Commit: `feat(discovery): centrality bounded modifier + card snapshot`.

---

### Task 4: Frontend chip

**Files:**
- Modify: `frontend/lib/api/themes.ts` (add `CentralitySnapshot` interface + `centrality` field on the card type — mirror `CongressSnapshot` exactly)
- Modify: the theme-detail card component that renders the insider/congress chips (locate via `grep -rn "CongressSnapshot\|congress" frontend/components/` — read the chip block and mirror)

- [ ] **Step 4.1:** Add the type + a "Hub" / "Broker" chip: render when `card.centrality.modifier !== 0`; label `Hub +3` / `Broker +2` (pick is_hub ? "Hub" : "Broker"); tooltip/title with `degree` and the raw centrality values formatted to 2dp; visual style copied from the congress chip (same classes, different accent if the existing chips differentiate).
- [ ] **Step 4.2:** Gates: `npm run typecheck && npm run lint && npm test && npm run build`. Commit: `feat(frontend): hub/broker centrality chip on discovery cards`.

---

### Task 5: Live verification (test DB)

- [ ] **Step 5.1:** Start backend on `sector_research_test` (env-var override; 127.0.0.1 note applies). Run the centrality refresh once for the Neo-clouds theme via a throwaway `python -c` asyncio script that opens `async_session()`, loads the theme, and calls `refresh_theme_centrality` (commit included). Verify: `SELECT ticker, value->>'modifier', value->>'is_hub', value->>'is_broker' FROM signals WHERE signal_type='centrality';` returns rows; `signal_history` got the dual-write; re-run is idempotent (replace, not duplicate).
- [ ] **Step 5.2:** Trigger a discovery run for the theme (`GET /api/themes/{id}` discovery path or the theme detail page) and verify the chip renders for whichever ticker scored hub/broker (expect ORCL or CRWV in Neo-clouds). Playwright screenshot.
- [ ] **Step 5.3:** Full gates both sides one final time.

---

### Task 6: Docs + PR

- [ ] CLAUDE.md: Discovery-engine section (modifier list gains centrality: "+3 hub / +2 broker, larger wins, ≥10-edge density gate, 48h staleness, computed daily in signal_scheduler from the theme-wide graph"); scheduler bullet in "Background task scheduling" (the 2 AM job now also writes centrality); Material-events section's "deliberately NOT a 4th weight" note now covers three signals.
- [ ] TODO.md: move centrality item to Done with a summary.
- [ ] Push, PR, CI green, merge (try `gh pr merge --merge` first; git/SSH fallback).

---

## Self-review notes

- Spec coverage: NetworkX dep ✓, undirected projection incl. unresolved nodes ✓, density gate ✓, top-20% ceil classification ✓, signals+history persistence via existing helper ✓, modifier larger-wins ✓, chip ✓, daily cadence ✓.
- Type consistency: `CentralityScores`/`compute_theme_centrality`/`modifier_from_scores`/`signal_value`/`CENTRALITY_STALE_HOURS`/`MIN_EDGES` defined Task 1, consumed Tasks 2-3 by those names.
- Deliberate deviations from handoff: persistence is `signals` table (not a new `theme_centrality_scores` table) — the spec resolved this open question in favor of the established signal plumbing; recompute cadence daily (spec decision).
