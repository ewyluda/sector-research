# 13F Institutional Ownership (Thin Path) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 13F institutional-ownership context (aggregate summary + top holders, framed "as of [quarter-end]") in every deep-dive category's fundamentals payload, via FMP's now-working ticker-side endpoints. No new tables, no scheduler changes, no frontend.

**Architecture:** Two `FMPClient` methods (`tuple[data, Citation]` convention) + a pure quarter-walk-back helper + a new optional section in `_fmt_fundamentals` (new kwargs default to None → absent data renders nothing → the frozen-copy identity test `test_fmt_fundamentals_identity.py` keeps passing untouched). Fetched in `node_deep_dive`'s degradable tier-2 gather; citations ride the existing `unwrap_gather_citation` persistence.

**Spec:** `docs/superpowers/specs/2026-06-12-v3-graph-pack-design.md` item 4 (probe-resolved thin path).

**Live-verified endpoints (2026-06-12, current plan):**
- `GET /stable/institutional-ownership/symbol-positions-summary?symbol=&year=&quarter=` → `[{symbol, cik, date, investorsHolding, investorsHoldingChange, numberOf13Fshares, numberOf13FsharesChange, totalInvested, totalInvestedChange, ownershipPercent, ownershipPercentChange, newPositions, increasedPositions, reducedPositions, closedPositions (+changes), putCallRatio, putCallRatioChange, …}]` (single-element list).
- `GET /stable/institutional-ownership/extract-analytics/holder?symbol=&year=&quarter=` → per-holder rows (investorName, cik/securityCusip, shares/value-type fields — dump one row live before writing the parser and pin the actual key names in a recorded-payload test, per house convention).

**Out of scope (pinned):** company-overview stat row (YAGNI for v1); crowding score; any frontend change; `institutional-ownership/latest` filer-side ingestion.

---

### Task 0: Branch
```bash
git checkout main && git pull --ff-only && git checkout -b feat/institutional-ownership
```

### Task 1: FMP client methods + quarter helper (TDD)

**Files:** Modify `backend/app/clients/fmp.py`; test `backend/tests/test_fmp_institutional.py` (create; mirror `test_fmp_congress_trades.py` conventions — mock `_request`, recorded-payload fixtures).

- `recent_13f_quarters(today: date, n: int = 4) -> list[tuple[int, int]]` — pure, module-level in `fmp.py` (or `graph/formatters.py` if client-side feels wrong — implementer's call, state it): starting from the PREVIOUS calendar quarter (13Fs for the current quarter can't exist yet), walk back n quarters. Pin: 2026-06-12 → [(2026,1),(2025,4),(2025,3),(2025,2)].
- `async get_institutional_summary(symbol, year, quarter) -> tuple[dict | None, Citation]` — `self._request("institutional-ownership/symbol-positions-summary", {...}, ttl=TTL_FUNDAMENTAL)`; single-element list unwrapped to dict, `None` on empty/error-shape (error dicts pass through `_request` verbatim per house docs — guard `isinstance(data, list)`).
- `async get_institutional_holders(symbol, year, quarter, limit=25) -> tuple[list, Citation]` — same endpoint family; empty list fallback; cap rows client-side at `limit` after fetch (wire `limit` param only if the live API honors it — check once with the real key, the implementer may run one live curl).
- Citations: mirror the existing citation construction in neighboring methods (source_url with full param string, metric label like `"13F institutional ownership summary"`).

Commit: `feat(clients): FMP 13F institutional-ownership methods + quarter walk-back`.

### Task 2: Formatter section (TDD)

**Files:** Modify `backend/app/graph/formatters.py` (new section helper + two new keyword-only params on `_fmt_fundamentals`, threaded through the composer); test `backend/tests/test_fmt_institutional.py` (create).

- `_fmt_fundamentals(..., inst_summary: dict | None = None, inst_holders: list | None = None)` — when `inst_summary` is None AND `inst_holders` falsy → render NOTHING (identity with pre-change output; the frozen-copy test must stay green and untouched — run it explicitly).
- New `_section_institutional(inst_summary, inst_holders) -> str` helper following the file's per-section style. Content:
  - Header: `INSTITUTIONAL OWNERSHIP (13F, as of {date} quarter-end — filings lag ≥45 days; positioning context, NOT current data):`
  - Summary line(s): investorsHolding (+change), numberOf13Fshares (+change, humanized), ownershipPercent, position churn (new/increased/reduced/closed), putCallRatio (+change) — every field independently nullable (`.get` with em-dash fallbacks, house style).
  - Top holders: top 10 by value (or shares if value absent): `INVESTOR — {shares} sh (${value})`, one line each. Truncate names ~40 chars.
- Tests: full payload renders all lines; summary-only; holders-only; both absent → empty string; null-field tolerance. Plus run `python -m unittest backend.tests.test_fmt_fundamentals_identity -v` — MUST pass unmodified.

Commit: `feat(graph): 13F institutional-ownership section in fundamentals payload`.

### Task 3: node_deep_dive wiring

**Files:** Modify `backend/app/graph/nodes.py` (tier-2 gather + `_fmt_fundamentals` call site + citation persistence); test coverage per existing tier-2 conventions (read how the tier-2 gather is currently tested — if it isn't unit-tested directly, don't invent a heavy harness; a focused test on the new quarter-walk-back-then-fetch helper is enough).

- In `node_deep_dive`, locate the tier-2 degradable gather (`return_exceptions=True` — grade consensus / price target / ratings / grades / insider). Add a small `async _fetch_institutional(fmp, ticker)` helper (module-level or local per file convention): walk `recent_13f_quarters(date.today())`, call `get_institutional_summary` until one returns data, then `get_institutional_holders` for that quarter; returns `((summary, holders), [citations])` or `((None, []), [])` — degradable, never raises.
- Thread `inst_summary=` / `inst_holders=` into the `_fmt_fundamentals` call; persist the citations via the same `unwrap_gather_citation`/`state.add_citation` path the other tier-2 fetches use (read the polish-pack wiring first).
- Full backend suite + ruff green.

Commit: `feat(graph): 13F context fetched in deep-dive tier-2 gather`.

### Task 4: Live verify + docs + PR

- Live: venv + real `.env` key, small script calling `_fetch_institutional`-equivalent for NVDA → summary quarter 2026Q1, holders non-empty, citation URL well-formed. Then a quick `_fmt_fundamentals` render with the live payload printed for eyeball sanity (one screenful).
- CLAUDE.md: deep-dive data routing section (tier-2 gather list gains 13F; note the "as of"-framing rule); TODO.md: 13F item → Done (note putCallRatio partial coverage of backlog item #6).
- PR, CI, merge.
