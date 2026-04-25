"""Query layer that converts persisted `relationships` rows into the
structured counterparty payload the deep-dive prompt consumes.

Kept separate from `edgar_relationships.py` (the extractor) because
this is read-path-only: it assembles outbound + inbound views of the
graph for a single ticker, grouped by relationship_type.

The prompt renderer (`_build_counterparty_context` in graph/nodes.py)
consumes the dataclasses below.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.filing import Relationship

# Cap per (direction, relationship_type) bucket. Realistic counts are
# far lower than this; this is a safety valve for mega-caps with very
# long supplier/customer disclosures.
MAX_ENTRIES_PER_BUCKET = 20


@dataclass
class CounterpartyEntry:
    name: str
    resolved_ticker: str | None
    relationship_type: str
    magnitude_pct: float | None
    unnamed: bool


@dataclass
class CounterpartyContext:
    outbound: dict[str, list[CounterpartyEntry]] = field(default_factory=dict)
    inbound: dict[str, list[CounterpartyEntry]] = field(default_factory=dict)

    @property
    def has_data(self) -> bool:
        return bool(self.outbound) or bool(self.inbound)


async def get_counterparty_context(
    ticker: str, db: AsyncSession
) -> CounterpartyContext:
    """Pull outbound (this ticker says X about Y) and inbound (Z named
    this ticker) relationship rows, group by `relationship_type`, apply
    per-bucket cap.

    `Relationship.ticker` is denormalized at extraction time and always
    matches `Filing.ticker`, so no join is required here.
    """
    ticker_upper = ticker.upper()

    outbound_rows = (
        await db.execute(
            select(Relationship).where(Relationship.ticker == ticker_upper)
        )
    ).scalars().all()

    inbound_rows = (
        await db.execute(
            select(Relationship).where(
                Relationship.resolved_to_ticker == ticker_upper
            )
        )
    ).scalars().all()

    ctx = CounterpartyContext()

    # Outbound — grouped by relationship_type. Entry name + resolved
    # ticker come straight from the extraction row.
    for row in outbound_rows:
        entry = CounterpartyEntry(
            name=row.counterparty_name,
            resolved_ticker=row.resolved_to_ticker,
            relationship_type=row.relationship_type,
            magnitude_pct=float(row.magnitude_pct) if row.magnitude_pct is not None else None,
            unnamed=bool(row.unnamed),
        )
        ctx.outbound.setdefault(entry.relationship_type, []).append(entry)

    # Inbound — the "name" field is the AUTHOR's ticker (who named us)
    # not the counterparty field (which is us). Store the author ticker
    # both as name ($TICKER form) and as resolved_ticker for consistency.
    for row in inbound_rows:
        author = row.ticker  # the ticker whose filing generated this row
        entry = CounterpartyEntry(
            name=f"${author}" if author else "(unknown author)",
            resolved_ticker=author,
            relationship_type=row.relationship_type,
            magnitude_pct=float(row.magnitude_pct) if row.magnitude_pct is not None else None,
            unnamed=False,
        )
        ctx.inbound.setdefault(entry.relationship_type, []).append(entry)

    # Sort + cap each bucket. Prefer entries with magnitude_pct set
    # (proxy for disclosure salience), then alphabetical by name.
    for bucket in (ctx.outbound, ctx.inbound):
        for key, entries in bucket.items():
            entries.sort(
                key=lambda e: (
                    0 if e.magnitude_pct is not None else 1,
                    -(e.magnitude_pct or 0.0),
                    e.name.lower(),
                )
            )
            bucket[key] = entries[:MAX_ENTRIES_PER_BUCKET]

    return ctx
