"""Phase D supply-chain graph + bilateral reconciliation.

Graph model
-----------
Nodes:
  - The root ticker (its own filing emitted these relationships)
  - Each distinct counterparty, keyed by resolved CIK when available,
    or by normalized name when unresolved
Edges:
  - One per `relationships` row, carrying direction, type, magnitude,
    verbatim quote, and the bilateral-confirmation flag

Direction semantics (from the root ticker's perspective):
  - out: relationships where `ticker == root`
           (root's filing names the counterparty)
  - in:  relationships where `resolved_to_ticker == root`
           (some other ticker's filing names root as a counterparty;
            only meaningful when root itself has been resolved via
            the Phase C alias table)
  - both: union

Bilateral reconciliation
------------------------
When one filing discloses A→B and another filing discloses B→A under a
reciprocal relationship type, both rows are flipped to
`confirmed_bilateral=true`. Cheap SQL-only pass — no LLM.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filing import Filing, Relationship
from backend.app.models.theme import Theme
from backend.app.services.counterparty_resolver import normalize_name

logger = logging.getLogger(__name__)


# ── Node / edge dataclasses ──────────────────────────────────────────────────


@dataclass
class GraphNode:
    # Stable ID the frontend uses to link edges. Resolved → ticker or CIK,
    # unresolved → "unresolved:<normalized name>".
    id: str
    ticker: str | None
    cik: str | None
    name: str
    is_root: bool
    tracked: bool  # True if the CIK/ticker is in any theme's seed_tickers
    unnamed: bool  # True for the synthetic "disclosed but unnamed" bucket
    # Shortest-path hop distance from the root node (0 for root, 1 for direct
    # neighbours, 2 for two hops away).
    hop: int = 0
    # True iff a `theme_id` was provided to get_graph AND the node's ticker is
    # in that theme's seed_tickers. False otherwise (including when no theme
    # was specified). The root node is NOT auto-flagged.
    in_selected_theme: bool = False


@dataclass
class GraphEdge:
    # At hop=1, flows root → counterparty (out) or filer → root (in). At
    # hop=2, flows hop-1-node → counterparty (out) or filer → hop-1-node
    # (in). source_ticker always holds the filing-authoring ticker — i.e.
    # from_id's node when direction=out, the OTHER ticker when direction=in.
    from_id: str
    to_id: str
    relationship_type: str
    # Relative to the expanding node (root at hop=1, hop-1 node at hop=2),
    # not always the root.
    direction: Literal["out", "in"]
    magnitude_pct: float | None
    unnamed: bool
    confirmed_bilateral: bool
    verbatim_quote: str | None
    source_ticker: str  # the ticker whose filing emitted this row
    accession_number: str
    filing_date: str
    section_key: str
    # The BFS hop at which this edge was discovered (1 for root's neighbours,
    # 2 for hop-2 expansions). No edges carry hop=0.
    hop: int = 1


@dataclass
class SupplyChainGraph:
    root_ticker: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)


# ── Tracked-universe helper ───────────────────────────────────────────────────


async def _load_tracked_set(db: AsyncSession) -> set[str]:
    """Return uppercase tickers that appear in any theme's seed_tickers."""
    rows = await db.execute(select(Theme.seed_tickers))
    tracked: set[str] = set()
    for (seeds,) in rows.all():
        if not seeds:
            continue
        for t in seeds:
            if isinstance(t, str) and t.strip():
                tracked.add(t.upper())
    return tracked


async def _load_theme_seeds(db: AsyncSession, theme_id: str) -> set[str]:
    """Return uppercase tickers in a specific theme's seed_tickers, or empty."""
    result = await db.execute(
        select(Theme.seed_tickers).where(Theme.id == theme_id)
    )
    seeds = result.scalar_one_or_none() or []
    return {t.upper() for t in seeds if isinstance(t, str) and t.strip()}


# ── Graph traversal ───────────────────────────────────────────────────────────


def _node_id_for_counterparty(rel: Relationship) -> str:
    """Derive a stable node ID from a relationship row's counterparty side."""
    if rel.unnamed:
        # Every "unnamed" row collapses to a single synthetic per-type bucket
        # so the card can show "Disclosed but unnamed X" without hundreds of
        # isolated nodes.
        return f"unnamed:{rel.relationship_type}"
    if rel.resolved_to_cik:
        return f"cik:{rel.resolved_to_cik}"
    return f"unresolved:{normalize_name(rel.counterparty_name)}"


MAX_DEPTH = 2


async def get_graph(
    ticker: str,
    *,
    direction: Literal["out", "in", "both"] = "both",
    depth: int = 1,
    theme_id: str | None = None,
    db: AsyncSession,
) -> SupplyChainGraph:
    """Build a supply-chain graph centered on `ticker`.

    At depth=1, queries the root's direct neighbours (matches the original
    1-hop behaviour byte-for-byte aside from the new `hop` and
    `in_selected_theme` fields).

    At depth=2, runs a BFS frontier expansion: the root's full hop-1
    neighbourhood is always rendered, but hop-1 nodes are only expanded into
    hop-2 if they're in the expansion set:
      - theme_id provided → the theme's seed_tickers
      - theme_id omitted → the tracked-union (any theme's seed_tickers)

    Unresolved and unnamed counterparties are terminal (no `ticker` to query
    from). Direction is inherited at every hop. Edges are deduplicated by
    Relationship.id so the same DB row never appears twice in the output —
    matters at depth=2 with direction=both.
    """
    if depth < 1 or depth > MAX_DEPTH:
        raise ValueError(f"depth must be in [1, {MAX_DEPTH}], got {depth}")

    root = ticker.upper()
    graph = SupplyChainGraph(root_ticker=root)

    tracked = await _load_tracked_set(db)
    selected_seeds: set[str] = (
        await _load_theme_seeds(db, theme_id) if theme_id is not None else set()
    )
    expansion_set: set[str] = selected_seeds if theme_id is not None else tracked

    root_node = GraphNode(
        id=f"root:{root}",
        ticker=root,
        cik=None,
        name=root,
        is_root=True,
        tracked=root in tracked,
        unnamed=False,
        hop=0,
        in_selected_theme=False,
    )
    graph.nodes.append(root_node)
    node_index: dict[str, GraphNode] = {root_node.id: root_node}
    emitted_edge_ids: set[str] = set()

    def upsert_node(node: GraphNode) -> GraphNode:
        existing = node_index.get(node.id)
        if existing is not None:
            # Prefer the most-complete copy: if we later learn a name,
            # keep it.
            if not existing.ticker and node.ticker:
                existing.ticker = node.ticker
            if not existing.cik and node.cik:
                existing.cik = node.cik
            if not existing.name and node.name:
                existing.name = node.name
            existing.tracked = existing.tracked or node.tracked
            existing.in_selected_theme = (
                existing.in_selected_theme or node.in_selected_theme
            )
            # hop is the shortest-path distance — keep the smaller value.
            if node.hop < existing.hop:
                existing.hop = node.hop
            return existing
        node_index[node.id] = node
        graph.nodes.append(node)
        return node

    async def expand_node(node: GraphNode, current_hop: int) -> list[GraphNode]:
        """Query relationships from `node` and return newly-introduced nodes
        (caller decides whether they enter the next frontier)."""
        new_hop = current_hop + 1
        new_nodes: list[GraphNode] = []

        # Outbound — filings authored by node.ticker name these counterparties.
        if direction in ("out", "both") and node.ticker:
            rows = await db.execute(
                select(Relationship, Filing)
                .join(Filing, Filing.id == Relationship.filing_id)
                .where(Relationship.ticker == node.ticker)
            )
            for rel, filing in rows.all():
                if rel.id in emitted_edge_ids:
                    continue
                cp_ticker = rel.resolved_to_ticker
                # Back-edge to root: reuse root_node so the cycle is visible
                # as a single node rather than a duplicate.
                if cp_ticker and cp_ticker.upper() == root:
                    cp_node = root_node
                else:
                    cp_node = upsert_node(GraphNode(
                        id=_node_id_for_counterparty(rel),
                        ticker=cp_ticker,
                        cik=rel.resolved_to_cik,
                        name=(
                            f"[unnamed {rel.relationship_type}]" if rel.unnamed
                            else rel.counterparty_name
                        ),
                        is_root=False,
                        tracked=(cp_ticker.upper() in tracked) if cp_ticker else False,
                        unnamed=rel.unnamed,
                        hop=new_hop,
                        in_selected_theme=(
                            cp_ticker is not None
                            and theme_id is not None
                            and cp_ticker.upper() in selected_seeds
                        ),
                    ))
                graph.edges.append(GraphEdge(
                    from_id=node.id,
                    to_id=cp_node.id,
                    relationship_type=rel.relationship_type,
                    direction="out",
                    magnitude_pct=float(rel.magnitude_pct) if rel.magnitude_pct is not None else None,
                    unnamed=rel.unnamed,
                    confirmed_bilateral=rel.confirmed_bilateral,
                    verbatim_quote=rel.verbatim_quote,
                    source_ticker=rel.ticker,
                    accession_number=filing.accession_number,
                    filing_date=filing.filing_date.isoformat(),
                    section_key=rel.section_key,
                    hop=new_hop,
                ))
                emitted_edge_ids.add(rel.id)
                new_nodes.append(cp_node)

        # Inbound — other tickers' filings name `node` as a counterparty.
        if direction in ("in", "both") and node.ticker:
            rows = await db.execute(
                select(Relationship, Filing)
                .join(Filing, Filing.id == Relationship.filing_id)
                .where(Relationship.resolved_to_ticker == node.ticker)
                .where(Relationship.ticker != node.ticker)
            )
            for rel, filing in rows.all():
                if rel.id in emitted_edge_ids:
                    continue
                # If the filer IS root (e.g. expanding MSFT inbound and the
                # filer is NVDA), reuse root_node — same cycle dedup as
                # outbound.
                if rel.ticker.upper() == root:
                    src_node = root_node
                else:
                    src_node = upsert_node(GraphNode(
                        id=f"ticker:{rel.ticker}",
                        ticker=rel.ticker,
                        cik=None,
                        name=rel.ticker,
                        is_root=False,
                        tracked=rel.ticker.upper() in tracked,
                        unnamed=False,
                        hop=new_hop,
                        in_selected_theme=(
                            theme_id is not None
                            and rel.ticker.upper() in selected_seeds
                        ),
                    ))
                graph.edges.append(GraphEdge(
                    from_id=src_node.id,
                    to_id=node.id,
                    relationship_type=rel.relationship_type,
                    direction="in",
                    magnitude_pct=float(rel.magnitude_pct) if rel.magnitude_pct is not None else None,
                    unnamed=rel.unnamed,
                    confirmed_bilateral=rel.confirmed_bilateral,
                    verbatim_quote=rel.verbatim_quote,
                    source_ticker=rel.ticker,
                    accession_number=filing.accession_number,
                    filing_date=filing.filing_date.isoformat(),
                    section_key=rel.section_key,
                    hop=new_hop,
                ))
                emitted_edge_ids.add(rel.id)
                new_nodes.append(src_node)

        return new_nodes

    # BFS: hop 0 (always expand root), hop 1 (expand only in-expansion-set).
    frontier: list[GraphNode] = [root_node]
    expanded: set[str] = set()
    for current_hop in range(depth):
        next_frontier: list[GraphNode] = []
        for node in frontier:
            if node.id in expanded:
                continue
            expanded.add(node.id)
            # Root (current_hop=0) is always expanded. Beyond hop 0, gate on
            # the expansion set. Terminal nodes (unresolved/unnamed/no ticker)
            # are naturally skipped by expand_node's `if node.ticker` guards.
            if current_hop > 0:
                if not node.ticker or node.ticker.upper() not in expansion_set:
                    continue
            new_nodes = await expand_node(node, current_hop)
            next_frontier.extend(new_nodes)
        frontier = next_frontier

    return graph


# ── Theme-wide graph ──────────────────────────────────────────────────────────

MAX_THEME_NODES = 300


@dataclass
class ThemeGraph:
    theme_id: str
    theme_name: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    # Hard rail: when the node count exceeds MAX_THEME_NODES, nodes/edges are
    # emptied and too_dense flips true. Counts always reflect the full graph.
    too_dense: bool = False
    node_count: int = 0
    edge_count: int = 0


def _theme_node_id(rel: Relationship) -> str:
    """Node identity for the theme-wide graph.

    Unlike `_node_id_for_counterparty`, resolved counterparties are keyed by
    TICKER first: the same company appearing as a filer (`ticker:ORCL`) and
    as another filer's resolved counterparty must unify into one node.
    """
    if rel.resolved_to_ticker:
        return f"ticker:{rel.resolved_to_ticker.upper()}"
    if rel.resolved_to_cik:
        return f"cik:{rel.resolved_to_cik}"
    return f"unresolved:{normalize_name(rel.counterparty_name)}"


async def build_theme_graph(
    theme_id: str, *, db: AsyncSession,
) -> ThemeGraph | None:
    """Build the theme-wide supply-chain graph: every named `relationships`
    row where the filer OR the resolved counterparty is in the theme's
    seed_tickers.

    Returns None when the theme doesn't exist (caller 404s). Unnamed rows
    (`unnamed=true`) are excluded in SQL — per-type synthetic buckets are
    noise in a density view (the per-root `get_graph` still shows them).
    Self-edges (a filer resolved to itself) are skipped.
    """
    theme = (
        await db.execute(select(Theme).where(Theme.id == theme_id))
    ).scalar_one_or_none()
    if theme is None:
        return None

    seeds = {
        t.upper() for t in (theme.seed_tickers or [])
        if isinstance(t, str) and t.strip()
    }
    graph = ThemeGraph(theme_id=theme_id, theme_name=theme.name)
    if not seeds:
        return graph

    tracked = await _load_tracked_set(db)

    rows = await db.execute(
        select(Relationship, Filing)
        .join(Filing, Filing.id == Relationship.filing_id)
        .where(Relationship.unnamed.is_(False))
        .where(or_(
            Relationship.ticker.in_(seeds),
            Relationship.resolved_to_ticker.in_(seeds),
        ))
    )

    node_index: dict[str, GraphNode] = {}

    def upsert(
        node_id: str, *, ticker: str | None, cik: str | None, name: str,
    ) -> GraphNode:
        existing = node_index.get(node_id)
        if existing is not None:
            # Prefer the most-complete copy (same policy as get_graph).
            if not existing.cik and cik:
                existing.cik = cik
            if not existing.name and name:
                existing.name = name
            return existing
        up = ticker.upper() if ticker else None
        node = GraphNode(
            id=node_id,
            ticker=up,
            cik=cik,
            name=name,
            is_root=False,
            tracked=(up in tracked) if up else False,
            unnamed=False,
            # hop doubles as seed-flag for the theme view: 0 = theme seed.
            hop=0 if (up and up in seeds) else 1,
            in_selected_theme=bool(up and up in seeds),
        )
        node_index[node_id] = node
        graph.nodes.append(node)
        return node

    for rel, filing in rows.all():
        if (
            rel.resolved_to_ticker
            and rel.resolved_to_ticker.upper() == rel.ticker.upper()
        ):
            continue  # self-edge: a filer resolved to itself renders as a loop
        src = upsert(
            f"ticker:{rel.ticker.upper()}",
            ticker=rel.ticker, cik=None, name=rel.ticker,
        )
        cp = upsert(
            _theme_node_id(rel),
            ticker=rel.resolved_to_ticker,
            cik=rel.resolved_to_cik,
            name=rel.counterparty_name,
        )
        graph.edges.append(GraphEdge(
            from_id=src.id,
            to_id=cp.id,
            relationship_type=rel.relationship_type,
            direction="out",
            magnitude_pct=(
                float(rel.magnitude_pct)
                if rel.magnitude_pct is not None else None
            ),
            unnamed=False,
            confirmed_bilateral=rel.confirmed_bilateral,
            verbatim_quote=rel.verbatim_quote,
            source_ticker=rel.ticker,
            accession_number=filing.accession_number,
            filing_date=filing.filing_date.isoformat(),
            section_key=rel.section_key,
            hop=1,
        ))

    graph.node_count = len(graph.nodes)
    graph.edge_count = len(graph.edges)
    if graph.node_count > MAX_THEME_NODES:
        graph.nodes = []
        graph.edges = []
        graph.too_dense = True
    return graph


# ── Bilateral reconciliation ──────────────────────────────────────────────────

# Reciprocal relationship pairs. `(a, b)` means: an A-side row reconciles
# with a B-side row. Includes self-reciprocals (partner↔partner) and
# asymmetric pairs (customer↔supplier).
_RECIPROCAL_PAIRS: tuple[tuple[str, str], ...] = (
    ("customer", "supplier"),
    ("licensor", "licensee"),
    ("distributor", "reseller"),
    ("partner", "partner"),
    ("joint_venture", "joint_venture"),
)


def _reciprocal_types_for(rel_type: str) -> tuple[str, ...]:
    """Return the set of relationship types that reciprocate `rel_type`."""
    matches: list[str] = []
    for a, b in _RECIPROCAL_PAIRS:
        if a == rel_type:
            matches.append(b)
        if b == rel_type and b != a:
            matches.append(a)
    return tuple(matches)


async def reconcile_bilaterals(db: AsyncSession) -> dict:
    """SQL-only pass: find every (A ticker, A resolved→B) row that has a
    reciprocal (B ticker, B resolved→A) row under a compatible type pair,
    and set confirmed_bilateral=true on both sides.

    Runs globally — cheap because the `relationships` table is ticker-scoped
    and indexed on ticker + resolved_to_ticker. Returns a summary.
    """
    summary: dict = {
        "pairs_reconciled": 0,
        "rows_flipped": 0,
    }

    # Load every row with a resolved counterparty (only resolved rows can
    # participate in reconciliation — an unresolved counterparty has no
    # ticker to reciprocate from).
    rows = await db.execute(
        select(Relationship)
        .where(Relationship.resolved_to_ticker.isnot(None))
        .where(Relationship.unnamed.is_(False))
    )
    resolved = list(rows.scalars())
    if not resolved:
        return summary

    # Index by (filer_ticker, counterparty_ticker, relationship_type).
    by_triple: dict[tuple[str, str, str], list[Relationship]] = {}
    for rel in resolved:
        key = (rel.ticker, rel.resolved_to_ticker or "", rel.relationship_type)
        by_triple.setdefault(key, []).append(rel)

    already_flipped_ids: set[str] = set()

    for (filer_a, cp_b, type_a), a_rows in by_triple.items():
        if not cp_b:
            continue
        for type_b in _reciprocal_types_for(type_a):
            # Flip direction: does (filer_b=cp_b, counterparty_a=filer_a, type_b) exist?
            counterpart_rows = by_triple.get((cp_b, filer_a, type_b))
            if not counterpart_rows:
                continue
            # Reconcile: flip every A row and every B row that hasn't been
            # flipped yet. Counted-once-per-pair to avoid inflating the
            # summary on symmetric types (partner↔partner).
            if type_a == type_b and filer_a > cp_b:
                # Canonicalize self-reciprocal pairs so they count once.
                continue
            summary["pairs_reconciled"] += 1
            for rel in a_rows + counterpart_rows:
                if rel.id in already_flipped_ids:
                    continue
                if not rel.confirmed_bilateral:
                    rel.confirmed_bilateral = True
                    summary["rows_flipped"] += 1
                already_flipped_ids.add(rel.id)

    await db.flush()
    logger.info(
        "reconcile: %d reciprocal pairs found, %d rows flipped to confirmed_bilateral",
        summary["pairs_reconciled"], summary["rows_flipped"],
    )
    return summary


# ── Summaries for quick card rendering ────────────────────────────────────────


def summarize_for_card(graph: SupplyChainGraph) -> dict:
    """Bucket edges by type + direction for the Supply Chain card.

    Groups unnamed concentrations into their own bucket per type.
    """
    # { type: { "out_named": [...], "out_unnamed": [...], "in_named": [...] } }
    buckets: dict[str, dict[str, list[dict]]] = {}
    node_by_id = {n.id: n for n in graph.nodes}

    for edge in graph.edges:
        rel_type = edge.relationship_type
        bucket = buckets.setdefault(rel_type, {
            "out_named": [], "out_unnamed": [], "in_named": [],
        })

        entry = {
            "from_id": edge.from_id,
            "to_id": edge.to_id,
            "direction": edge.direction,
            "magnitude_pct": edge.magnitude_pct,
            "confirmed_bilateral": edge.confirmed_bilateral,
            "verbatim_quote": edge.verbatim_quote,
            "source_ticker": edge.source_ticker,
            "accession_number": edge.accession_number,
            "filing_date": edge.filing_date,
            "section_key": edge.section_key,
            "unnamed": edge.unnamed,
        }

        other_id = edge.to_id if edge.direction == "out" else edge.from_id
        other = node_by_id.get(other_id)
        if other:
            entry.update({
                "counterparty_name": other.name,
                "counterparty_ticker": other.ticker,
                "counterparty_cik": other.cik,
                "counterparty_tracked": other.tracked,
            })

        if edge.direction == "out":
            key = "out_unnamed" if edge.unnamed else "out_named"
        else:
            key = "in_named"
        bucket[key].append(entry)

    return buckets
