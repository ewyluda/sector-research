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

from sqlalchemy import select
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
    tracked: bool  # True if the CIK/ticker is in a theme's seed_tickers
    unnamed: bool  # True for the synthetic "disclosed but unnamed" bucket


@dataclass
class GraphEdge:
    # Always flows root → counterparty, regardless of out/in direction.
    # When direction=in, source_ticker holds the OTHER ticker (the filer).
    from_id: str
    to_id: str
    relationship_type: str
    direction: Literal["out", "in"]  # relative to the root
    magnitude_pct: float | None
    unnamed: bool
    confirmed_bilateral: bool
    verbatim_quote: str | None
    source_ticker: str  # the ticker whose filing emitted this row
    accession_number: str
    filing_date: str
    section_key: str


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


async def get_graph(
    ticker: str,
    *,
    direction: Literal["out", "in", "both"] = "both",
    db: AsyncSession,
) -> SupplyChainGraph:
    """Build a 1-hop supply-chain graph centered on `ticker`."""
    root = ticker.upper()
    graph = SupplyChainGraph(root_ticker=root)

    tracked = await _load_tracked_set(db)

    root_node = GraphNode(
        id=f"root:{root}",
        ticker=root,
        cik=None,
        name=root,
        is_root=True,
        tracked=root in tracked,
        unnamed=False,
    )
    graph.nodes.append(root_node)
    node_index: dict[str, GraphNode] = {root_node.id: root_node}

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
            return existing
        node_index[node.id] = node
        graph.nodes.append(node)
        return node

    # Outbound edges — root's filings name these counterparties.
    if direction in ("out", "both"):
        out_rows = await db.execute(
            select(Relationship, Filing)
            .join(Filing, Filing.id == Relationship.filing_id)
            .where(Relationship.ticker == root)
        )
        for rel, filing in out_rows.all():
            cp_id = _node_id_for_counterparty(rel)
            cp_ticker = rel.resolved_to_ticker
            cp_node = GraphNode(
                id=cp_id,
                ticker=cp_ticker,
                cik=rel.resolved_to_cik,
                name=(
                    f"[unnamed {rel.relationship_type}]" if rel.unnamed
                    else rel.counterparty_name
                ),
                is_root=False,
                tracked=(cp_ticker.upper() in tracked) if cp_ticker else False,
                unnamed=rel.unnamed,
            )
            upsert_node(cp_node)
            graph.edges.append(GraphEdge(
                from_id=root_node.id,
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
            ))

    # Inbound edges — other tickers' filings resolve back to root.
    if direction in ("in", "both"):
        in_rows = await db.execute(
            select(Relationship, Filing)
            .join(Filing, Filing.id == Relationship.filing_id)
            .where(Relationship.resolved_to_ticker == root)
            .where(Relationship.ticker != root)
        )
        for rel, filing in in_rows.all():
            # Source is the OTHER ticker's node (the filer). Use ticker-based
            # id so it co-indexes cleanly with out-nodes for the same company.
            src_node = GraphNode(
                id=f"ticker:{rel.ticker}",
                ticker=rel.ticker,
                cik=None,  # we don't store the filer's CIK on the row
                name=rel.ticker,
                is_root=False,
                tracked=rel.ticker.upper() in tracked,
                unnamed=False,
            )
            upsert_node(src_node)
            graph.edges.append(GraphEdge(
                from_id=src_node.id,
                to_id=root_node.id,
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
            ))

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
    ("competitor", "competitor"),
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
