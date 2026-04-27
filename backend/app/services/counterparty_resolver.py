"""Phase C counterparty resolution.

Maps free-text counterparty names extracted by Haiku (Phase B) to canonical
SEC entities (CIK + optional ticker). Resolutions are persisted in
`counterparty_aliases` so each decision is made exactly once per normalized
alias — subsequent relationships for the same alias reuse it for free.

Strategy (in order):
  1. Alias reuse — if the normalized alias is already in
     counterparty_aliases, apply that resolution.
  2. Exact match — normalized alias equals a normalized EDGAR company name.
  3. Fuzzy match — RapidFuzz token_set_ratio ≥ FUZZY_AUTO_THRESHOLD.
  4. Otherwise, leave unresolved; it'll surface in the curation queue.

Thresholds:
  ≥ 95 → auto-apply, source="fuzzy_auto"
  80–94 → surface in curation queue, no auto-apply
  < 80 → surface in curation queue only if the user asks to see all
         unresolved counterparties
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable

from rapidfuzz import fuzz, process
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient
from backend.app.models.filing import CompetitorLandscape, CounterpartyAlias, Relationship
from sqlalchemy.orm.attributes import flag_modified

logger = logging.getLogger(__name__)


FUZZY_AUTO_THRESHOLD = 95
FUZZY_CURATION_THRESHOLD = 80
TOP_N_CANDIDATES = 5


# ── Normalization ────────────────────────────────────────────────────────────

# Corporate suffixes + structural tokens stripped before matching. Order
# matters — longer phrases first so "Holdings Inc." becomes "" not "Inc".
_SUFFIX_PATTERNS: tuple[str, ...] = (
    r"incorporated",
    r"corporation",
    r"company",
    r"holdings",
    r"group",
    r"limited",
    r"inc\.?",
    r"corp\.?",
    r"co\.?",
    r"ltd\.?",
    r"llc\.?",
    r"plc\.?",
    r"l\.?p\.?",
    r"l\.?l\.?c\.?",
    r"n\.?v\.?",
    r"s\.?a\.?",
    r"a\.?g\.?",
    r"ag",
    r"se",
)

_SUFFIX_RE = re.compile(
    r"\b(?:" + "|".join(_SUFFIX_PATTERNS) + r")\b",
    flags=re.IGNORECASE,
)
_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_SPACES_RE = re.compile(r"\s+")


def normalize_name(s: str) -> str:
    """Canonicalize a company name so fuzzy matching is stable.

    Strips incorporation suffixes, punctuation, and collapses whitespace.
    Returns empty string for all-whitespace or all-suffix inputs.
    """
    if not s:
        return ""
    out = s.lower()
    out = _SUFFIX_RE.sub(" ", out)
    out = _PUNCT_RE.sub(" ", out)
    out = _SPACES_RE.sub(" ", out)
    return out.strip()


# ── Candidate match ──────────────────────────────────────────────────────────


@dataclass
class ResolutionCandidate:
    cik: str
    ticker: str | None
    canonical_name: str
    score: float  # 0-100
    source: str  # "exact_match" | "fuzzy_auto" | "fuzzy_candidate"


# ── Resolver state ────────────────────────────────────────────────────────────


class CounterpartyResolver:
    """Holds the loaded EDGAR universe in memory for batch resolution.

    Call `load()` once per request (cached by the caller's scope — the
    EdgarClient's ticker map itself is cached on the client for 24h, so
    this is cheap to reload).
    """

    def __init__(self, edgar: EdgarClient) -> None:
        self._edgar = edgar
        # List of (normalized_name, canonical_name, cik, ticker) rows —
        # built once per resolver instance for fast fuzzy scanning.
        self._universe: list[tuple[str, str, str, str | None]] = []
        self._normalized_to_idx: dict[str, int] = {}

    async def load(self) -> None:
        """Populate the resolver's universe from EDGAR's company_tickers.json.

        The returned data has keys: ticker, cik_str, title (company name).
        We build a normalized name → canonical entry index so exact lookups
        and fuzzy scans are both fast.
        """
        # Piggy-back on EdgarClient's cached ticker map pull. We don't have
        # a public accessor for the raw payload, so re-fetch; the httpx
        # client inside EdgarClient caches the HTTP response for 24h so the
        # second call inside the same request is instant.
        import httpx

        from backend.app.clients.edgar import BASE_SEC_URL
        from backend.app.config import get_settings

        settings = get_settings()
        async with httpx.AsyncClient(
            timeout=15.0,
            headers={"User-Agent": settings.sec_user_agent},
        ) as client:
            resp = await client.get(f"{BASE_SEC_URL}/files/company_tickers.json")
            resp.raise_for_status()
            data = resp.json()

        universe: list[tuple[str, str, str, str | None]] = []
        seen_norm: dict[str, int] = {}
        for v in data.values():
            if not isinstance(v, dict):
                continue
            title = v.get("title")
            cik_int = v.get("cik_str")
            ticker = v.get("ticker")
            if not title or cik_int is None:
                continue
            norm = normalize_name(title)
            if not norm:
                continue
            cik = str(cik_int).zfill(10)
            if norm in seen_norm:
                # Duplicate normalized name (different tickers for same name).
                # Prefer the entry already seen — first wins.
                continue
            seen_norm[norm] = len(universe)
            universe.append((norm, title, cik, ticker.upper() if ticker else None))

        self._universe = universe
        self._normalized_to_idx = seen_norm
        logger.info("Counterparty resolver loaded %d EDGAR entities", len(universe))

    def match(self, alias_name: str) -> list[ResolutionCandidate]:
        """Return up to TOP_N_CANDIDATES best matches, ordered by score desc.

        An exact normalized-name hit returns a single candidate at score 100.
        Otherwise, fuzzy top-N via RapidFuzz token_set_ratio.
        """
        norm = normalize_name(alias_name)
        if not norm or not self._universe:
            return []

        exact_idx = self._normalized_to_idx.get(norm)
        if exact_idx is not None:
            _, canonical, cik, ticker = self._universe[exact_idx]
            return [ResolutionCandidate(
                cik=cik, ticker=ticker, canonical_name=canonical,
                score=100.0, source="exact_match",
            )]

        norm_names = [row[0] for row in self._universe]
        matches = process.extract(
            norm, norm_names, scorer=fuzz.token_set_ratio,
            limit=TOP_N_CANDIDATES,
        )

        candidates: list[ResolutionCandidate] = []
        for _, score, idx in matches:
            _, canonical, cik, ticker = self._universe[idx]
            candidates.append(ResolutionCandidate(
                cik=cik, ticker=ticker, canonical_name=canonical, score=float(score),
                source="fuzzy_auto" if score >= FUZZY_AUTO_THRESHOLD else "fuzzy_candidate",
            ))
        return candidates


# ── Persistence helpers ──────────────────────────────────────────────────────


async def _write_back_relationships(
    db: AsyncSession, alias_normalized: str, cik: str, ticker: str | None,
) -> int:
    """Populate resolved_to_cik / resolved_to_ticker on every Relationship
    row whose counterparty_name normalizes to `alias_normalized`. Returns
    the number of rows updated.

    Done via a Python-side iterate rather than a single SQL UPDATE because
    we don't have a normalized index on counterparty_name — the normalization
    rule can evolve, so we'd rather recompute per row.
    """
    rows = await db.execute(
        select(Relationship).where(
            Relationship.resolved_to_cik.is_(None),
        )
    )
    updated = 0
    for rel in rows.scalars():
        if normalize_name(rel.counterparty_name) != alias_normalized:
            continue
        rel.resolved_to_cik = cik
        rel.resolved_to_ticker = ticker
        updated += 1
    return updated


async def _existing_alias_for(
    db: AsyncSession, alias_normalized: str
) -> CounterpartyAlias | None:
    result = await db.execute(
        select(CounterpartyAlias).where(
            CounterpartyAlias.alias_normalized == alias_normalized
        )
    )
    return result.scalar_one_or_none()


# ── Resolution passes ─────────────────────────────────────────────────────────


async def resolve_ticker_relationships(
    ticker: str, db: AsyncSession,
) -> dict:
    """Attempt to resolve all unresolved counterparties for a ticker.

    For each unresolved (no resolved_to_cik) Relationship row:
      1. Reuse alias if one exists for the normalized form.
      2. Exact match against EDGAR universe → create alias, apply.
      3. Fuzzy match ≥ FUZZY_AUTO_THRESHOLD → create alias, apply.
      4. Otherwise leave unresolved for the curation queue.

    Returns a summary dict with counts per resolution path.
    """
    ticker = ticker.upper()
    summary: dict = {
        "ticker": ticker,
        "rows_considered": 0,
        "already_resolved": 0,
        "resolved_via_alias": 0,
        "resolved_via_exact": 0,
        "resolved_via_fuzzy": 0,
        "unresolved_surfaced_to_queue": 0,
        "unnamed_skipped": 0,
        "relationships_updated": 0,
        "aliases_created": 0,
    }

    # Fetch the ticker's relationship rows
    result = await db.execute(
        select(Relationship).where(Relationship.ticker == ticker)
    )
    rows = result.scalars().all()
    if not rows:
        return summary

    edgar = EdgarClient()
    resolver = CounterpartyResolver(edgar)
    try:
        await resolver.load()

        # Cache results within this run so we don't hit the resolver
        # multiple times for the same normalized alias.
        local_alias_cache: dict[str, str | None] = {}  # norm → cik or None if unresolvable

        for rel in rows:
            summary["rows_considered"] += 1
            if rel.resolved_to_cik:
                summary["already_resolved"] += 1
                continue
            if rel.unnamed:
                # Unnamed concentrations have no counterparty to resolve.
                summary["unnamed_skipped"] += 1
                continue

            norm = normalize_name(rel.counterparty_name)
            if not norm:
                summary["unresolved_surfaced_to_queue"] += 1
                continue

            # Check per-run cache (same ticker often has the same name twice)
            if norm in local_alias_cache:
                cik = local_alias_cache[norm]
                if cik is None:
                    summary["unresolved_surfaced_to_queue"] += 1
                    continue
                alias = await _existing_alias_for(db, norm)
                if alias is not None:
                    rel.resolved_to_cik = alias.canonical_cik
                    rel.resolved_to_ticker = alias.canonical_ticker
                    summary["resolved_via_alias"] += 1
                    summary["relationships_updated"] += 1
                continue

            # Step 1: alias reuse
            existing = await _existing_alias_for(db, norm)
            if existing is not None:
                rel.resolved_to_cik = existing.canonical_cik
                rel.resolved_to_ticker = existing.canonical_ticker
                summary["resolved_via_alias"] += 1
                summary["relationships_updated"] += 1
                local_alias_cache[norm] = existing.canonical_cik
                continue

            # Steps 2+3: exact or fuzzy match
            candidates = resolver.match(rel.counterparty_name)
            if not candidates:
                local_alias_cache[norm] = None
                summary["unresolved_surfaced_to_queue"] += 1
                continue

            best = candidates[0]
            if best.source == "exact_match" or best.score >= FUZZY_AUTO_THRESHOLD:
                new_alias = CounterpartyAlias(
                    alias_name=rel.counterparty_name,
                    alias_normalized=norm,
                    canonical_cik=best.cik,
                    canonical_ticker=best.ticker,
                    canonical_name=best.canonical_name,
                    source=best.source,
                    confidence_score=best.score,
                )
                db.add(new_alias)
                rel.resolved_to_cik = best.cik
                rel.resolved_to_ticker = best.ticker
                summary["aliases_created"] += 1
                summary["relationships_updated"] += 1
                local_alias_cache[norm] = best.cik
                if best.source == "exact_match":
                    summary["resolved_via_exact"] += 1
                else:
                    summary["resolved_via_fuzzy"] += 1
                continue

            # Below auto-threshold: surface for curation.
            summary["unresolved_surfaced_to_queue"] += 1
            local_alias_cache[norm] = None

    finally:
        await edgar.close()

    # Write-back cascade: if this run created aliases, also update OTHER
    # tickers' relationships that share the same normalized counterparty.
    # E.g. AAPL's "Microsoft Corp" alias now applies to ORCL's "Microsoft"
    # row in the same resolution pass.
    new_aliases = await db.execute(
        select(CounterpartyAlias).order_by(CounterpartyAlias.created_at.desc()).limit(summary["aliases_created"])
    )
    for alias in new_aliases.scalars():
        extra_updates = await _write_back_relationships(
            db, alias.alias_normalized, alias.canonical_cik, alias.canonical_ticker,
        )
        # Subtract the ones we've already counted for this ticker.
        summary["relationships_updated"] += max(0, extra_updates)

    await db.flush()
    logger.info(
        "counterparty resolve: %s — updated=%d aliases=%d queue=%d",
        ticker,
        summary["relationships_updated"],
        summary["aliases_created"],
        summary["unresolved_surfaced_to_queue"],
    )
    return summary


async def resolve_batch(
    tickers: Iterable[str], db: AsyncSession,
) -> list[dict]:
    out: list[dict] = []
    for t in tickers:
        try:
            out.append(await resolve_ticker_relationships(t, db))
        except Exception as e:
            logger.exception("resolve failed for %s", t)
            out.append({"ticker": t.upper(), "error": str(e)})
    return out


async def resolve_competition_for_ticker(
    ticker: str, db: AsyncSession,
) -> dict:
    """Walk competitor_landscape rows for `ticker`, attempt to resolve each
    unresolved competitor name in the JSONB array, write resolved_to_cik /
    resolved_to_ticker back into the array, persist.

    Mirrors `resolve_ticker_relationships` semantics (alias reuse → exact
    match → fuzzy ≥ FUZZY_AUTO_THRESHOLD). Score 80–94 is left unresolved
    (no curation queue for the new surface in v1).

    Per-ticker only: does NOT cascade newly-created aliases to other
    tickers' competitor_landscape rows (the relationship resolver does
    that via `_write_back_relationships`, but JSONB-element write-back
    across rows is deferred until cross-ticker resolution is needed).

    Caller is responsible for `await db.commit()`.
    """
    ticker_upper = ticker.upper()
    summary: dict = {
        "ticker": ticker_upper,
        "rows_considered": 0,
        "competitors_considered": 0,
        "already_resolved": 0,
        "resolved_via_alias": 0,
        "resolved_via_exact": 0,
        "resolved_via_fuzzy": 0,
        "unresolved": 0,
        "rows_updated": 0,
        "aliases_created": 0,
    }

    rows = (
        await db.execute(
            select(CompetitorLandscape).where(
                CompetitorLandscape.ticker == ticker_upper
            )
        )
    ).scalars().all()
    if not rows:
        return summary

    edgar = EdgarClient()
    resolver = CounterpartyResolver(edgar)
    try:
        await resolver.load()

        # Cache normalized→(cik, ticker) decisions inside this run
        local_cache: dict[str, tuple[str | None, str | None]] = {}

        for row in rows:
            summary["rows_considered"] += 1
            competitors = list(row.competitors or [])
            row_changed = False

            for comp in competitors:
                summary["competitors_considered"] += 1
                if comp.get("resolved_to_cik"):
                    summary["already_resolved"] += 1
                    continue

                raw_name = comp.get("name", "")
                normalized = comp.get("name_normalized") or normalize_name(raw_name)
                if not normalized:
                    summary["unresolved"] += 1
                    continue

                # Local cache hit
                if normalized in local_cache:
                    cik, t = local_cache[normalized]
                    if cik is None:
                        summary["unresolved"] += 1
                        continue
                    comp["resolved_to_cik"] = cik
                    comp["resolved_to_ticker"] = t
                    row_changed = True
                    continue

                # 1. Alias reuse
                alias = await _existing_alias_for(db, normalized)
                if alias is not None:
                    comp["resolved_to_cik"] = alias.canonical_cik
                    comp["resolved_to_ticker"] = alias.canonical_ticker
                    summary["resolved_via_alias"] += 1
                    local_cache[normalized] = (
                        alias.canonical_cik, alias.canonical_ticker,
                    )
                    row_changed = True
                    continue

                # 2 + 3. Exact / fuzzy match via the resolver universe
                candidates = resolver.match(raw_name)
                top = candidates[0] if candidates else None
                if top is None or top.score < FUZZY_AUTO_THRESHOLD:
                    local_cache[normalized] = (None, None)
                    summary["unresolved"] += 1
                    continue

                # The resolver labels exact matches with source="exact_match"
                # and fuzzy auto-resolves with source="fuzzy_auto". We persist
                # alias rows mirroring those values so the existing curation
                # tooling stays consistent.
                if top.source == "exact_match":
                    summary["resolved_via_exact"] += 1
                    alias_source = "exact_match"
                else:
                    summary["resolved_via_fuzzy"] += 1
                    alias_source = "fuzzy_auto"

                new_alias = CounterpartyAlias(
                    alias_name=raw_name[:256],
                    alias_normalized=normalized,
                    canonical_cik=top.cik,
                    canonical_ticker=top.ticker,
                    canonical_name=top.canonical_name,
                    source=alias_source,
                    confidence_score=top.score,
                )
                db.add(new_alias)
                summary["aliases_created"] += 1

                comp["resolved_to_cik"] = top.cik
                comp["resolved_to_ticker"] = top.ticker
                local_cache[normalized] = (top.cik, top.ticker)
                row_changed = True

            if row_changed:
                row.competitors = competitors
                # JSONB mutation tracking — without flag_modified, SA may not
                # detect the in-place dict change on the JSONB column.
                flag_modified(row, "competitors")
                summary["rows_updated"] += 1

    finally:
        await edgar.close()

    return summary


# ── Curation queue ────────────────────────────────────────────────────────────


@dataclass
class UnresolvedCounterparty:
    counterparty_name: str
    alias_normalized: str
    occurrence_count: int
    tickers: list[str]
    candidates: list[ResolutionCandidate]


async def list_unresolved_counterparties(
    db: AsyncSession, limit: int = 50,
) -> list[UnresolvedCounterparty]:
    """Return unresolved counterparties sorted by occurrence count,
    each with top-N candidate matches.

    A counterparty is "unresolved" if at least one Relationship row has
    null resolved_to_cik AND no CounterpartyAlias exists for its normalized
    form.
    """
    # Aggregate unresolved rows by counterparty_name.
    result = await db.execute(
        select(
            Relationship.counterparty_name,
            func.count(Relationship.id).label("count"),
            func.array_agg(Relationship.ticker.distinct()).label("tickers"),
        )
        .where(
            Relationship.resolved_to_cik.is_(None),
            Relationship.unnamed.is_(False),
        )
        .group_by(Relationship.counterparty_name)
        .order_by(func.count(Relationship.id).desc())
        .limit(limit * 2)  # over-fetch so we can drop any that have aliases
    )
    raw = result.all()
    if not raw:
        return []

    # Exclude any whose normalized form already has an alias (those should
    # be re-resolvable by the main pass, just haven't been yet).
    norms = {normalize_name(name): name for name, _, _ in raw if name}
    alias_rows = await db.execute(
        select(CounterpartyAlias.alias_normalized).where(
            CounterpartyAlias.alias_normalized.in_(norms.keys())
        )
    )
    aliased = {row for row in alias_rows.scalars()}

    edgar = EdgarClient()
    resolver = CounterpartyResolver(edgar)
    try:
        await resolver.load()
        out: list[UnresolvedCounterparty] = []
        for name, count, tickers in raw:
            norm = normalize_name(name)
            if not norm or norm in aliased:
                continue
            candidates = resolver.match(name)
            out.append(UnresolvedCounterparty(
                counterparty_name=name,
                alias_normalized=norm,
                occurrence_count=int(count),
                tickers=list(tickers) if tickers else [],
                candidates=candidates,
            ))
            if len(out) >= limit:
                break
        return out
    finally:
        await edgar.close()


async def upsert_manual_alias(
    db: AsyncSession, *, alias_name: str, canonical_cik: str,
    canonical_ticker: str | None, canonical_name: str, created_by: str | None,
) -> dict:
    """User-driven resolution. Overrides any existing auto-resolved alias
    and writes back to every matching Relationship row."""
    norm = normalize_name(alias_name)
    if not norm:
        raise ValueError("alias name normalizes to empty string")

    existing = await _existing_alias_for(db, norm)
    if existing is not None:
        existing.canonical_cik = canonical_cik
        existing.canonical_ticker = canonical_ticker.upper() if canonical_ticker else None
        existing.canonical_name = canonical_name
        existing.source = "curator_manual"
        existing.confidence_score = None
        existing.created_by = created_by
        alias = existing
    else:
        alias = CounterpartyAlias(
            alias_name=alias_name,
            alias_normalized=norm,
            canonical_cik=canonical_cik,
            canonical_ticker=canonical_ticker.upper() if canonical_ticker else None,
            canonical_name=canonical_name,
            source="curator_manual",
            confidence_score=None,
            created_by=created_by,
        )
        db.add(alias)

    await db.flush()

    # Write-back to every Relationship row that matches this normalization.
    # Pass True for unresolved AND True for resolved (manual override
    # rewrites previous auto-resolutions).
    updated = 0
    rows = await db.execute(select(Relationship))
    for rel in rows.scalars():
        if normalize_name(rel.counterparty_name) != norm:
            continue
        rel.resolved_to_cik = canonical_cik
        rel.resolved_to_ticker = canonical_ticker.upper() if canonical_ticker else None
        updated += 1

    await db.flush()
    return {
        "alias_id": alias.id,
        "alias_normalized": norm,
        "canonical_cik": canonical_cik,
        "canonical_ticker": canonical_ticker,
        "canonical_name": canonical_name,
        "relationships_updated": updated,
    }
