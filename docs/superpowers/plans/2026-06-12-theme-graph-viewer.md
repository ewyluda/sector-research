# Theme-Wide Graph + D3 Force Viewer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A theme-wide supply-chain graph endpoint plus an interactive D3 force-directed viewer at `/filings/graph/theme?theme=<id>`, making hubs and density patterns visible across a theme's whole relationship universe.

**Architecture:** New `build_theme_graph()` in `services/supply_chain.py` (separate from the root-centered `get_graph`) selects every named `relationships` row where filer OR resolved counterparty is in the theme's seeds, unifying node identity by ticker. New endpoint `GET /api/relationships/theme-graph/{theme_id}`. Frontend: pure adapter logic in `lib/themeGraph.ts` (node-tested), synchronous d3-force layout in a `useMemo`, React-rendered SVG, d3-zoom for pan/zoom, click → side panel with relationship buckets.

**Tech Stack:** FastAPI + SQLAlchemy async (mock-at-execute tests), d3-force/d3-zoom/d3-selection (modular, no full d3), Next.js 16 App Router.

**Spec:** `docs/superpowers/specs/2026-06-12-v3-graph-pack-design.md` item 1.

**Conventions that bind this work:**
- Backend launched/tested from project root, venv active: `source backend/venv/bin/activate`.
- Run a single test module: `python -m unittest backend.tests.test_theme_graph_builder -v`.
- Frontend gates from `frontend/`: `npm run typecheck && npm run lint && npm test && npm run build`.
- ⚠️ Next.js 16: before writing any frontend file, read the relevant guide in `frontend/node_modules/next/dist/docs/` (per `frontend/AGENTS.md`). The existing `/filings/graph` page pattern (server component + `export const dynamic = "force-dynamic"` + client view component) is known-good — mirror it.
- All tickers uppercase at boundaries.

---

### Task 0: Branch

- [ ] **Step 0.1: Create the feature branch from main**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
git checkout main && git pull && git checkout -b feat/theme-graph-viewer
```

---

### Task 1: Backend builder — `build_theme_graph`

**Files:**
- Modify: `backend/app/services/supply_chain.py` (add after `get_graph`, before "Bilateral reconciliation" section)
- Test: `backend/tests/test_theme_graph_builder.py` (create)

- [ ] **Step 1.1: Write the failing tests**

Create `backend/tests/test_theme_graph_builder.py`. Reuse the env-var preamble and row factories from `test_supply_chain_multi_hop.py` (copy `_make_rel` / `_make_filing` / `_result` — they are module-local there, not importable). The builder issues exactly 3 `db.execute` calls in fixed order (theme lookup → all-themes seeds for tracked set → relationships join), so `side_effect` lists work; no WHERE-clause inspection needed.

```python
"""Pins services/supply_chain.py::build_theme_graph — the theme-wide graph
builder behind GET /api/relationships/theme-graph/{theme_id}.

Mocks at the SQLAlchemy execute() boundary. build_theme_graph issues exactly
3 execute() calls in fixed order:
  1. select(Theme).where(id)            -> .scalar_one_or_none()
  2. select(Theme.seed_tickers) (all)   -> .all()  (tracked-union helper)
  3. select(Relationship, Filing) join  -> .all()
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
from backend.app.models.theme import Theme
from backend.app.services.supply_chain import MAX_THEME_NODES, build_theme_graph


def _result(rows=None, scalar_value=...):
    r = MagicMock()
    r.all.return_value = rows or []
    if scalar_value is not ...:
        r.scalar_one_or_none = MagicMock(return_value=scalar_value)
    return r


def _make_rel(*, ticker, counterparty_name, relationship_type,
              resolved_to_ticker=None, resolved_to_cik=None, unnamed=False,
              magnitude_pct=None, confirmed_bilateral=False):
    return Relationship(
        id=str(uuid4()), filing_id=str(uuid4()), ticker=ticker.upper(),
        section_key="item_1", source_type="filing",
        counterparty_name=counterparty_name,
        relationship_type=relationship_type, magnitude_pct=magnitude_pct,
        unnamed=unnamed, verbatim_quote="some quote",
        confirmed_bilateral=confirmed_bilateral,
        resolved_to_cik=resolved_to_cik,
        resolved_to_ticker=resolved_to_ticker.upper() if resolved_to_ticker else None,
    )


def _make_filing(ticker, accession="0000000000-00-000000"):
    return Filing(id=str(uuid4()), ticker=ticker.upper(),
                  accession_number=accession, form_type="10-K",
                  filing_date=date(2025, 1, 1), cik="0000000001")


def _make_theme(seeds):
    t = MagicMock(spec=Theme)
    t.id = "theme-1"
    t.name = "AI infra"
    t.seed_tickers = seeds
    return t


def _db(theme, all_seeds, rel_rows):
    """AsyncMock db with the 3 fixed-order execute results."""
    db = AsyncMock()
    db.execute.side_effect = [
        _result(scalar_value=theme),
        _result(rows=[(s,) for s in all_seeds]),
        _result(rows=rel_rows),
    ]
    return db


class ThemeGraphBuilderTests(unittest.IsolatedAsyncioTestCase):
    async def test_unknown_theme_returns_none(self):
        db = AsyncMock()
        db.execute.side_effect = [_result(scalar_value=None)]
        self.assertIsNone(await build_theme_graph("nope", db=db))

    async def test_empty_seeds_returns_empty_graph(self):
        theme = _make_theme([])
        db = AsyncMock()
        db.execute.side_effect = [_result(scalar_value=theme)]
        g = await build_theme_graph("theme-1", db=db)
        self.assertEqual(g.nodes, [])
        self.assertEqual(g.edges, [])
        self.assertFalse(g.too_dense)

    async def test_basic_graph_seed_filer_and_resolved_counterparty(self):
        # NVDA (seed) discloses TSM as supplier (resolved).
        rel = _make_rel(ticker="NVDA", counterparty_name="Taiwan Semi",
                        relationship_type="supplier", resolved_to_ticker="TSM",
                        resolved_to_cik="0001046179")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            "theme-1", db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        ids = {n.id for n in g.nodes}
        self.assertEqual(ids, {"ticker:NVDA", "ticker:TSM"})
        nvda = next(n for n in g.nodes if n.id == "ticker:NVDA")
        tsm = next(n for n in g.nodes if n.id == "ticker:TSM")
        self.assertTrue(nvda.in_selected_theme)
        self.assertEqual(nvda.hop, 0)
        self.assertFalse(tsm.in_selected_theme)
        self.assertEqual(tsm.hop, 1)
        self.assertEqual(len(g.edges), 1)
        e = g.edges[0]
        self.assertEqual((e.from_id, e.to_id), ("ticker:NVDA", "ticker:TSM"))
        self.assertEqual(e.direction, "out")
        self.assertEqual(g.node_count, 2)
        self.assertEqual(g.edge_count, 1)

    async def test_filer_and_counterparty_identity_unify_by_ticker(self):
        # ORCL appears as a filer AND as MSFT's resolved counterparty —
        # must be ONE node keyed ticker:ORCL, not ticker:ORCL + cik:....
        rel_a = _make_rel(ticker="MSFT", counterparty_name="Oracle Corp",
                          relationship_type="competitor",
                          resolved_to_ticker="ORCL", resolved_to_cik="0001341439")
        rel_b = _make_rel(ticker="ORCL", counterparty_name="Some Startup",
                          relationship_type="customer")
        theme = _make_theme(["MSFT", "ORCL"])
        g = await build_theme_graph(
            "theme-1",
            db=_db(theme, [["MSFT", "ORCL"]],
                   [(rel_a, _make_filing("MSFT")), (rel_b, _make_filing("ORCL"))]))
        orcl_nodes = [n for n in g.nodes if n.ticker == "ORCL"]
        self.assertEqual(len(orcl_nodes), 1)
        self.assertEqual(orcl_nodes[0].id, "ticker:ORCL")
        # cik learned from the resolved row even if the filer row came first
        self.assertEqual(orcl_nodes[0].cik, "0001341439")

    async def test_unresolved_counterparty_is_terminal_named_node(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="CoreWeave, Inc.",
                        relationship_type="customer")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            "theme-1", db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        unresolved = [n for n in g.nodes if n.id.startswith("unresolved:")]
        self.assertEqual(len(unresolved), 1)
        self.assertIsNone(unresolved[0].ticker)
        self.assertEqual(unresolved[0].name, "CoreWeave, Inc.")

    async def test_resolved_cik_without_ticker_keys_by_cik(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="Private Co",
                        relationship_type="supplier", resolved_to_cik="0009999999")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            "theme-1", db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        self.assertIn("cik:0009999999", {n.id for n in g.nodes})

    async def test_self_edges_skipped(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="NVIDIA Corp",
                        relationship_type="other", resolved_to_ticker="NVDA")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            "theme-1", db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        self.assertEqual(g.edges, [])

    async def test_magnitude_and_bilateral_pass_through(self):
        rel = _make_rel(ticker="NVDA", counterparty_name="Taiwan Semi",
                        relationship_type="supplier", resolved_to_ticker="TSM",
                        magnitude_pct=22.5, confirmed_bilateral=True)
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            "theme-1", db=_db(theme, [["NVDA"]], [(rel, _make_filing("NVDA"))]))
        self.assertEqual(g.edges[0].magnitude_pct, 22.5)
        self.assertTrue(g.edges[0].confirmed_bilateral)

    async def test_tracked_flag_uses_union_of_all_themes(self):
        # TSM is not in this theme but seeded in another theme -> tracked=True.
        rel = _make_rel(ticker="NVDA", counterparty_name="Taiwan Semi",
                        relationship_type="supplier", resolved_to_ticker="TSM")
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph(
            "theme-1",
            db=_db(theme, [["NVDA"], ["TSM"]], [(rel, _make_filing("NVDA"))]))
        tsm = next(n for n in g.nodes if n.id == "ticker:TSM")
        self.assertTrue(tsm.tracked)
        self.assertFalse(tsm.in_selected_theme)

    async def test_too_dense_rail(self):
        # MAX_THEME_NODES+ distinct unresolved counterparties trip the rail.
        rels = [
            (_make_rel(ticker="NVDA", counterparty_name=f"Company {i}",
                       relationship_type="customer"), _make_filing("NVDA"))
            for i in range(MAX_THEME_NODES + 1)
        ]
        theme = _make_theme(["NVDA"])
        g = await build_theme_graph("theme-1", db=_db(theme, [["NVDA"]], rels))
        self.assertTrue(g.too_dense)
        self.assertEqual(g.nodes, [])
        self.assertEqual(g.edges, [])
        self.assertGreater(g.node_count, MAX_THEME_NODES)
        self.assertEqual(g.edge_count, MAX_THEME_NODES + 1)


if __name__ == "__main__":
    unittest.main()
```

Note: the relationships query itself filters `unnamed.is_(False)` in SQL, so no unnamed-exclusion unit test is possible at the mock boundary — the API test in Task 2 and the SQL string are the contract. Document with a comment in the builder.

- [ ] **Step 1.2: Run tests to verify they fail**

```bash
source backend/venv/bin/activate
python -m unittest backend.tests.test_theme_graph_builder -v
```

Expected: `ImportError: cannot import name 'MAX_THEME_NODES'` (or `build_theme_graph`).

- [ ] **Step 1.3: Implement the builder**

In `backend/app/services/supply_chain.py`:

1. Extend the `sqlalchemy` import: `from sqlalchemy import or_, select`.
2. Add after `get_graph` (before the "Bilateral reconciliation" section):

```python
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
```

- [ ] **Step 1.4: Run tests to verify they pass**

```bash
python -m unittest backend.tests.test_theme_graph_builder -v
```

Expected: all PASS (11 tests).

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/services/supply_chain.py backend/tests/test_theme_graph_builder.py
git commit -m "feat(graph): theme-wide supply-chain graph builder"
```

---

### Task 2: Endpoint — `GET /api/relationships/theme-graph/{theme_id}`

**Files:**
- Modify: `backend/app/api/filings.py` (add after `get_ticker_graph`, ~line 632)
- Test: `backend/tests/test_theme_graph_api.py` (create)

- [ ] **Step 2.1: Write the failing tests**

Create `backend/tests/test_theme_graph_api.py` (TestClient + dependency-override convention from `test_catalysts_calendar_api.py`; patch the service, not the DB):

```python
"""Pins the GET /api/relationships/theme-graph/{theme_id} contract:
404 on unknown theme, response shape pass-through, too_dense rail."""
import os
import unittest
from unittest.mock import AsyncMock, patch

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.app.api.filings import router
from backend.app.db import get_db
from backend.app.services.supply_chain import GraphEdge, GraphNode, ThemeGraph


def make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def _graph() -> ThemeGraph:
    return ThemeGraph(
        theme_id="theme-1",
        theme_name="AI infra",
        nodes=[GraphNode(
            id="ticker:NVDA", ticker="NVDA", cik=None, name="NVDA",
            is_root=False, tracked=True, unnamed=False, hop=0,
            in_selected_theme=True,
        )],
        edges=[GraphEdge(
            from_id="ticker:NVDA", to_id="unresolved:coreweave",
            relationship_type="customer", direction="out",
            magnitude_pct=12.0, unnamed=False, confirmed_bilateral=False,
            verbatim_quote="q", source_ticker="NVDA",
            accession_number="0000000000-00-000000",
            filing_date="2025-01-01", section_key="item_1", hop=1,
        )],
        node_count=1, edge_count=1,
    )


class ThemeGraphApiTests(unittest.TestCase):
    def test_unknown_theme_404(self):
        with patch(
            "backend.app.api.filings.build_theme_graph",
            new=AsyncMock(return_value=None),
        ):
            resp = make_client().get("/api/relationships/theme-graph/nope")
        self.assertEqual(resp.status_code, 404)

    def test_graph_passthrough(self):
        with patch(
            "backend.app.api.filings.build_theme_graph",
            new=AsyncMock(return_value=_graph()),
        ):
            resp = make_client().get("/api/relationships/theme-graph/theme-1")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["theme_id"], "theme-1")
        self.assertEqual(body["theme_name"], "AI infra")
        self.assertEqual(body["nodes"][0]["id"], "ticker:NVDA")
        self.assertEqual(body["edges"][0]["relationship_type"], "customer")
        self.assertFalse(body["too_dense"])
        self.assertEqual(body["node_count"], 1)

    def test_too_dense_passthrough(self):
        dense = ThemeGraph(
            theme_id="theme-1", theme_name="AI infra",
            too_dense=True, node_count=450, edge_count=900,
        )
        with patch(
            "backend.app.api.filings.build_theme_graph",
            new=AsyncMock(return_value=dense),
        ):
            resp = make_client().get("/api/relationships/theme-graph/theme-1")
        body = resp.json()
        self.assertTrue(body["too_dense"])
        self.assertEqual(body["nodes"], [])
        self.assertEqual(body["node_count"], 450)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2.2: Run tests to verify they fail**

```bash
python -m unittest backend.tests.test_theme_graph_api -v
```

Expected: FAIL — `ImportError` on `build_theme_graph` from `backend.app.api.filings` (patch target missing) and/or 404→405/404-route mismatches.

- [ ] **Step 2.3: Implement the endpoint**

In `backend/app/api/filings.py`:

1. Add `build_theme_graph` to the existing `from backend.app.services.supply_chain import (...)` block (it currently imports `get_graph`, `reconcile_bilaterals`, `summarize_for_card`).
2. Add after the `get_ticker_graph` endpoint:

```python
class ThemeGraphResponse(BaseModel):
    theme_id: str
    theme_name: str
    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    too_dense: bool
    node_count: int
    edge_count: int


@router.get("/relationships/theme-graph/{theme_id}")
async def get_theme_graph(
    theme_id: str,
    db: AsyncSession = Depends(get_db),
) -> ThemeGraphResponse:
    """Theme-wide supply-chain graph: every named relationship row where the
    filer or the resolved counterparty is in the theme's seed_tickers.

    Unnamed rows are excluded (synthetic per-type buckets are noise in a
    density view — the per-root graph endpoint still includes them). When the
    node count exceeds the hard rail, `too_dense=true` is returned with empty
    nodes/edges and the full counts.
    """
    graph = await build_theme_graph(theme_id, db=db)
    if graph is None:
        raise HTTPException(status_code=404, detail="theme not found")
    return ThemeGraphResponse(
        theme_id=graph.theme_id,
        theme_name=graph.theme_name,
        nodes=[
            GraphNodeResponse(
                id=n.id, ticker=n.ticker, cik=n.cik, name=n.name,
                is_root=n.is_root, tracked=n.tracked, unnamed=n.unnamed,
                hop=n.hop, in_selected_theme=n.in_selected_theme,
            ) for n in graph.nodes
        ],
        edges=[
            GraphEdgeResponse(
                from_id=e.from_id, to_id=e.to_id,
                relationship_type=e.relationship_type, direction=e.direction,
                magnitude_pct=e.magnitude_pct, unnamed=e.unnamed,
                confirmed_bilateral=e.confirmed_bilateral,
                verbatim_quote=e.verbatim_quote, source_ticker=e.source_ticker,
                accession_number=e.accession_number,
                filing_date=e.filing_date, section_key=e.section_key,
                hop=e.hop,
            ) for e in graph.edges
        ],
        too_dense=graph.too_dense,
        node_count=graph.node_count,
        edge_count=graph.edge_count,
    )
```

Route-ordering note: `theme-graph` is a distinct literal segment under `/relationships/` — no conflict with `/relationships/graph/{ticker}`, `/relationships/dismissed`, or any `/{param}` route. No declaration-order constraint.

- [ ] **Step 2.4: Run tests to verify they pass**

```bash
python -m unittest backend.tests.test_theme_graph_api backend.tests.test_theme_graph_builder -v
```

Expected: all PASS.

- [ ] **Step 2.5: Ruff + full backend suite**

```bash
ruff check backend
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```

Expected: ruff clean; full suite green (906 + 14 new).

- [ ] **Step 2.6: Commit**

```bash
git add backend/app/api/filings.py backend/tests/test_theme_graph_api.py
git commit -m "feat(api): theme-graph endpoint for theme-wide supply-chain view"
```

---

### Task 3: Frontend deps + typed client + pure adapter logic

**Files:**
- Modify: `frontend/package.json` (via npm install)
- Modify: `frontend/lib/api/filings.ts` (add `ThemeGraphResponse` + `relationships.getThemeGraph`)
- Create: `frontend/lib/themeGraph.ts`
- Test: `frontend/lib/themeGraph.test.mts` (create)

- [ ] **Step 3.1: Install d3 modular packages**

```bash
cd frontend
npm install d3-force d3-zoom d3-selection
npm install -D @types/d3-force @types/d3-zoom @types/d3-selection
```

Expected: clean install, no peer warnings that matter (d3 v7 modules).

- [ ] **Step 3.2: Add the typed client method**

In `frontend/lib/api/filings.ts`, add below the `SupplyChainGraph` interface (~line 386):

```ts
export interface ThemeGraphResponse {
  theme_id: string;
  theme_name: string;
  nodes: SupplyChainGraphNode[];
  edges: SupplyChainGraphEdge[];
  too_dense: boolean;
  node_count: number;
  edge_count: number;
}
```

And inside the `relationships` object (after `getGraph`):

```ts
  getThemeGraph: (themeId: string) =>
    apiFetch<ThemeGraphResponse>(
      `/api/relationships/theme-graph/${encodeURIComponent(themeId)}`
    ),
```

Then re-export the type from the barrel: in `frontend/lib/api/index.ts`, add `ThemeGraphResponse` to the filings type re-exports (match how `SupplyChainGraph` is re-exported there).

- [ ] **Step 3.3: Write the failing adapter tests**

Create `frontend/lib/themeGraph.test.mts`:

```ts
import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  buildSimGraph,
  edgeColor,
  edgeWidth,
  nodeLabel,
  nodeRadius,
} from "./themeGraph.ts";
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "./api/filings.ts";

function node(over: Partial<SupplyChainGraphNode>): SupplyChainGraphNode {
  return {
    id: "ticker:NVDA", ticker: "NVDA", cik: null, name: "NVDA",
    is_root: false, tracked: true, unnamed: false, hop: 0,
    in_selected_theme: true, ...over,
  };
}

function edge(over: Partial<SupplyChainGraphEdge>): SupplyChainGraphEdge {
  return {
    from_id: "ticker:NVDA", to_id: "ticker:TSM",
    relationship_type: "supplier", direction: "out", magnitude_pct: null,
    unnamed: false, confirmed_bilateral: false, verbatim_quote: null,
    source_ticker: "NVDA", accession_number: "0000000000-00-000000",
    filing_date: "2025-01-01", section_key: "item_1", hop: 1, ...over,
  };
}

test("buildSimGraph computes degree per node", () => {
  const nodes = [
    node({}),
    node({ id: "ticker:TSM", ticker: "TSM", name: "TSM" }),
    node({ id: "unresolved:x", ticker: null, name: "X Corp" }),
  ];
  const edges = [
    edge({}),
    edge({ to_id: "unresolved:x", relationship_type: "customer" }),
  ];
  const { nodes: sim } = buildSimGraph(nodes, edges);
  const byId = new Map(sim.map((n) => [n.id, n]));
  assert.equal(byId.get("ticker:NVDA")!.degree, 2);
  assert.equal(byId.get("ticker:TSM")!.degree, 1);
  assert.equal(byId.get("unresolved:x")!.degree, 1);
});

test("buildSimGraph collapses parallel edges of same (from,to,type)", () => {
  const nodes = [node({}), node({ id: "ticker:TSM", ticker: "TSM" })];
  const edges = [
    edge({ magnitude_pct: 10 }),
    edge({ magnitude_pct: 25 }), // same triple, different filing
    edge({ relationship_type: "customer" }), // different type -> own link
  ];
  const { links } = buildSimGraph(nodes, edges);
  assert.equal(links.length, 2);
  const supplier = links.find((l) => l.type === "supplier")!;
  assert.equal(supplier.count, 2);
  assert.equal(supplier.magnitudePct, 25); // max wins
});

test("buildSimGraph marks bilateral when any collapsed edge is bilateral", () => {
  const nodes = [node({}), node({ id: "ticker:TSM", ticker: "TSM" })];
  const edges = [edge({}), edge({ confirmed_bilateral: true })];
  const { links } = buildSimGraph(nodes, edges);
  assert.equal(links[0].bilateral, true);
});

test("buildSimGraph flags seeds and unresolved nodes", () => {
  const nodes = [
    node({}),
    node({ id: "unresolved:x", ticker: null, in_selected_theme: false }),
  ];
  const { nodes: sim } = buildSimGraph(nodes, []);
  assert.equal(sim[0].isSeed, true);
  assert.equal(sim[0].isUnresolved, false);
  assert.equal(sim[1].isSeed, false);
  assert.equal(sim[1].isUnresolved, true);
});

test("nodeRadius grows with degree and caps", () => {
  assert.ok(nodeRadius(0) < nodeRadius(4));
  assert.ok(nodeRadius(4) < nodeRadius(16));
  assert.equal(nodeRadius(10_000), nodeRadius(9_999)); // capped
});

test("nodeLabel prefers ticker, truncates long names", () => {
  assert.equal(nodeLabel(node({})), "NVDA");
  const long = node({
    id: "unresolved:y", ticker: null,
    name: "Very Long Counterparty Name Incorporated",
  });
  assert.ok(nodeLabel(long).length <= 19); // 18 + ellipsis
  assert.ok(nodeLabel(long).endsWith("…"));
});

test("edgeColor falls back to other for unknown types", () => {
  assert.notEqual(edgeColor("supplier"), edgeColor("other"));
  assert.equal(edgeColor("bogus_type"), edgeColor("other"));
});

test("edgeWidth scales with magnitude and caps", () => {
  assert.equal(edgeWidth(null), 1.5);
  assert.ok(edgeWidth(20) > edgeWidth(null));
  assert.ok(edgeWidth(95) <= 6);
});
```

- [ ] **Step 3.4: Run tests to verify they fail**

```bash
cd frontend && npm test
```

Expected: FAIL — cannot find module `./themeGraph.ts`.

- [ ] **Step 3.5: Implement the adapter**

Create `frontend/lib/themeGraph.ts`:

```ts
/**
 * Pure adapter logic for the theme-wide force graph
 * (/filings/graph/theme). Converts the ThemeGraphResponse payload into
 * d3-force-ready nodes/links and owns the visual-encoding scales.
 * Pure functions only — node-tested via themeGraph.test.mts.
 */
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "./api/filings.ts";

export interface SimNode {
  id: string;
  label: string;
  ticker: string | null;
  name: string;
  isSeed: boolean;
  isUnresolved: boolean;
  tracked: boolean;
  degree: number;
  radius: number;
  // d3-force mutates these in place during layout.
  x?: number;
  y?: number;
}

export interface SimLink {
  source: string;
  target: string;
  type: string;
  /** Distinct underlying relationship rows collapsed into this link. */
  count: number;
  /** Max magnitude among collapsed rows, if any carried one. */
  magnitudePct: number | null;
  bilateral: boolean;
}

export const REL_TYPE_COLORS: Record<string, string> = {
  customer: "#60a5fa",
  supplier: "#34d399",
  partner: "#a78bfa",
  competitor: "#f87171",
  licensor: "#fbbf24",
  licensee: "#fbbf24",
  distributor: "#2dd4bf",
  reseller: "#2dd4bf",
  joint_venture: "#f472b6",
  other: "#9ca3af",
};

export function edgeColor(type: string): string {
  return REL_TYPE_COLORS[type] ?? REL_TYPE_COLORS.other;
}

export function edgeWidth(magnitudePct: number | null): number {
  if (magnitudePct == null) return 1.5;
  return Math.min(6, 1.5 + magnitudePct / 15);
}

const MAX_LABEL = 18;

export function nodeLabel(node: SupplyChainGraphNode): string {
  if (node.ticker) return node.ticker;
  if (node.name.length <= MAX_LABEL) return node.name;
  return `${node.name.slice(0, MAX_LABEL)}…`;
}

export function nodeRadius(degree: number): number {
  return Math.min(18, 6 + 2 * Math.sqrt(degree));
}

export function buildSimGraph(
  nodes: SupplyChainGraphNode[],
  edges: SupplyChainGraphEdge[],
): { nodes: SimNode[]; links: SimLink[] } {
  const degree = new Map<string, number>();
  for (const e of edges) {
    degree.set(e.from_id, (degree.get(e.from_id) ?? 0) + 1);
    degree.set(e.to_id, (degree.get(e.to_id) ?? 0) + 1);
  }

  const linkIndex = new Map<string, SimLink>();
  for (const e of edges) {
    const key = `${e.from_id}|${e.to_id}|${e.relationship_type}`;
    const existing = linkIndex.get(key);
    if (existing) {
      existing.count += 1;
      existing.bilateral = existing.bilateral || e.confirmed_bilateral;
      if (e.magnitude_pct != null) {
        existing.magnitudePct = Math.max(
          existing.magnitudePct ?? -Infinity,
          e.magnitude_pct,
        );
      }
    } else {
      linkIndex.set(key, {
        source: e.from_id,
        target: e.to_id,
        type: e.relationship_type,
        count: 1,
        magnitudePct: e.magnitude_pct,
        bilateral: e.confirmed_bilateral,
      });
    }
  }

  return {
    nodes: nodes.map((n) => {
      const d = degree.get(n.id) ?? 0;
      return {
        id: n.id,
        label: nodeLabel(n),
        ticker: n.ticker,
        name: n.name,
        isSeed: n.in_selected_theme,
        isUnresolved: n.id.startsWith("unresolved:"),
        tracked: n.tracked,
        degree: d,
        radius: nodeRadius(d),
      };
    }),
    links: [...linkIndex.values()],
  };
}
```

- [ ] **Step 3.6: Run tests + typecheck to verify they pass**

```bash
cd frontend && npm test && npm run typecheck
```

Expected: all node suites PASS (existing 6 + this one); tsc clean.

- [ ] **Step 3.7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/lib/api/filings.ts frontend/lib/api/index.ts frontend/lib/themeGraph.ts frontend/lib/themeGraph.test.mts
git commit -m "feat(frontend): theme-graph client method + force-graph adapter logic"
```

---

### Task 4: Force-graph canvas + side panel + view + page

**Files:**
- Create: `frontend/components/filings/ForceGraphCanvas.tsx`
- Create: `frontend/components/filings/ThemeGraphSidePanel.tsx`
- Create: `frontend/components/filings/ThemeGraphView.tsx`
- Create: `frontend/app/filings/graph/theme/page.tsx`

Before writing: skim `frontend/node_modules/next/dist/docs/` for App Router page/client-component conventions (AGENTS.md mandate) and `MultiHopGraphView.tsx` for the URL-sync pattern (`useSearchParams` + `router.replace`) and the dark-token CSS variable names (`--color-border`, `--color-surface`, `--color-text-muted`, `--color-accent`, `--color-bg`, `--color-text-primary` — match them exactly).

- [ ] **Step 4.1: Create `ForceGraphCanvas.tsx`**

```tsx
"use client";

/**
 * SVG force-graph renderer. Layout is computed synchronously (d3-force
 * ticked to convergence in a useMemo) — no live physics, which avoids
 * per-tick React re-renders. Interactions: d3-zoom pan/zoom on the svg
 * root (the only d3-selection use), pointer-drag to reposition a node,
 * click to select.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";
import { select } from "d3-selection";
import { zoom, zoomIdentity, type ZoomTransform } from "d3-zoom";
import { edgeColor, edgeWidth, type SimLink, type SimNode } from "@/lib/themeGraph";

type LayoutNode = SimNode & SimulationNodeDatum;
type LayoutLink = Omit<SimLink, "source" | "target"> &
  SimulationLinkDatum<LayoutNode>;

interface Props {
  nodes: SimNode[];
  links: SimLink[];
  selectedId: string | null;
  onSelect: (id: string | null) => void;
}

const WIDTH = 960;
const HEIGHT = 640;

export default function ForceGraphCanvas({
  nodes, links, selectedId, onSelect,
}: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);
  // Manual drag overrides, keyed by node id.
  const [overrides, setOverrides] = useState<Map<string, { x: number; y: number }>>(
    new Map(),
  );
  const dragRef = useRef<{ id: string; moved: boolean } | null>(null);

  const layout = useMemo(() => {
    // d3-force mutates node/link objects — work on copies.
    const simNodes: LayoutNode[] = nodes.map((n) => ({ ...n }));
    const simLinks: LayoutLink[] = links.map((l) => ({ ...l }));
    const sim = forceSimulation(simNodes)
      .force(
        "link",
        forceLink<LayoutNode, LayoutLink>(simLinks)
          .id((d) => d.id)
          .distance(70),
      )
      .force("charge", forceManyBody().strength(-180))
      .force("center", forceCenter(0, 0))
      .force("collide", forceCollide<LayoutNode>().radius((d) => d.radius + 6))
      .stop();
    sim.tick(300);
    return { simNodes, simLinks };
  }, [nodes, links]);

  useEffect(() => {
    if (!svgRef.current) return;
    const behavior = zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.2, 6])
      .filter((event) => !(event.type === "mousedown" && dragRef.current))
      .on("zoom", (event) => setTransform(event.transform));
    const sel = select(svgRef.current);
    sel.call(behavior);
    return () => {
      sel.on(".zoom", null);
    };
  }, []);

  const pos = (n: LayoutNode) =>
    overrides.get(n.id) ?? { x: n.x ?? 0, y: n.y ?? 0 };

  const toGraphCoords = (clientX: number, clientY: number) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const sx = ((clientX - rect.left) / rect.width) * WIDTH - WIDTH / 2;
    const sy = ((clientY - rect.top) / rect.height) * HEIGHT - HEIGHT / 2;
    return {
      x: (sx - transform.x) / transform.k,
      y: (sy - transform.y) / transform.k,
    };
  };

  const nodeById = useMemo(
    () => new Map(layout.simNodes.map((n) => [n.id, n])),
    [layout],
  );

  return (
    <svg
      ref={svgRef}
      viewBox={`${-WIDTH / 2} ${-HEIGHT / 2} ${WIDTH} ${HEIGHT}`}
      className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]"
      style={{ height: "640px", cursor: "grab" }}
      onPointerMove={(e) => {
        const drag = dragRef.current;
        if (!drag) return;
        drag.moved = true;
        const { x, y } = toGraphCoords(e.clientX, e.clientY);
        setOverrides((prev) => new Map(prev).set(drag.id, { x, y }));
      }}
      onPointerUp={() => {
        const drag = dragRef.current;
        dragRef.current = null;
        if (drag && !drag.moved) {
          onSelect(selectedId === drag.id ? null : drag.id);
        }
      }}
      onClick={(e) => {
        // Background click clears selection (node clicks stopPropagation).
        if (e.target === svgRef.current) onSelect(null);
      }}
    >
      <g transform={transform.toString()}>
        {layout.simLinks.map((l, i) => {
          // After forceLink(...).id(...) + tick(), d3 has replaced the string
          // source/target with node object references — the cast is sound.
          const s = l.source as LayoutNode;
          const t = l.target as LayoutNode;
          const sp = pos(s);
          const tp = pos(t);
          const w = edgeWidth(l.magnitudePct);
          return (
            <g key={`${s.id}|${t.id}|${l.type}|${i}`}>
              <line
                x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                stroke={edgeColor(l.type)}
                strokeWidth={l.bilateral ? w + 2 : w}
                strokeOpacity={0.55}
              />
              {l.bilateral && (
                <line
                  x1={sp.x} y1={sp.y} x2={tp.x} y2={tp.y}
                  stroke="var(--color-bg)"
                  strokeWidth={Math.max(0.75, w - 1)}
                  strokeOpacity={1}
                />
              )}
            </g>
          );
        })}
        {layout.simNodes.map((n) => {
          const p = pos(n);
          const selected = n.id === selectedId;
          return (
            <g
              key={n.id}
              transform={`translate(${p.x},${p.y})`}
              style={{ cursor: "pointer" }}
              onPointerDown={(e) => {
                e.stopPropagation();
                dragRef.current = { id: n.id, moved: false };
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <circle
                r={n.radius}
                fill={n.isSeed ? "var(--color-accent)" : "var(--color-surface)"}
                stroke={selected ? "#fff" : "var(--color-border)"}
                strokeWidth={selected ? 2.5 : 1.25}
                opacity={n.isUnresolved ? 0.55 : 1}
              />
              <text
                y={n.radius + 11}
                textAnchor="middle"
                className="select-none"
                fill="var(--color-text-primary)"
                fontSize={10}
                opacity={n.isUnresolved ? 0.6 : 0.9}
              >
                {n.label}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
```

Note: `nodeById` is kept for potential future use by callers needing id-keyed lookups during render; if the typechecker flags it unused, delete the memo rather than suppressing.

- [ ] **Step 4.2: Create `ThemeGraphSidePanel.tsx`**

```tsx
"use client";

/**
 * Detail panel for a selected node on the theme force graph: outbound and
 * inbound relationship buckets grouped by type, with quotes, magnitude
 * chips, bilateral badges, and a root-graph deep link for tracked tickers.
 */
import Link from "next/link";
import type {
  SupplyChainGraphEdge,
  SupplyChainGraphNode,
} from "@/lib/api";

interface Props {
  node: SupplyChainGraphNode;
  edges: SupplyChainGraphEdge[];
  nodesById: Map<string, SupplyChainGraphNode>;
  onClose: () => void;
}

function groupByType(rows: SupplyChainGraphEdge[]) {
  const groups = new Map<string, SupplyChainGraphEdge[]>();
  for (const e of rows) {
    const list = groups.get(e.relationship_type) ?? [];
    list.push(e);
    groups.set(e.relationship_type, list);
  }
  return [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
}

function EdgeRow({
  edge, other,
}: { edge: SupplyChainGraphEdge; other: SupplyChainGraphNode | undefined }) {
  return (
    <li className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2.5 py-2">
      <div className="flex items-center gap-2 text-sm">
        <span className="font-medium text-[var(--color-text-primary)]">
          {other?.ticker ?? other?.name ?? "?"}
        </span>
        {edge.magnitude_pct != null && (
          <span className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] font-mono">
            {edge.magnitude_pct}%
          </span>
        )}
        {edge.confirmed_bilateral && (
          <span className="rounded bg-[var(--color-surface)] px-1.5 py-0.5 text-[11px] text-[var(--color-text-muted)]">
            bilateral
          </span>
        )}
        <span className="ml-auto text-[11px] text-[var(--color-text-muted)]">
          {edge.filing_date}
        </span>
      </div>
      {edge.verbatim_quote && (
        <p className="mt-1 line-clamp-2 text-xs text-[var(--color-text-muted)]">
          “{edge.verbatim_quote}”
        </p>
      )}
    </li>
  );
}

export default function ThemeGraphSidePanel({
  node, edges, nodesById, onClose,
}: Props) {
  const outbound = edges.filter((e) => e.from_id === node.id);
  const inbound = edges.filter((e) => e.to_id === node.id);

  return (
    <aside className="w-full lg:w-96 shrink-0 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-4 max-h-[640px] overflow-y-auto">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="text-base font-semibold text-[var(--color-text-primary)]">
            {node.ticker ?? node.name}
          </h3>
          {node.ticker && node.name !== node.ticker && (
            <p className="text-xs text-[var(--color-text-muted)]">{node.name}</p>
          )}
        </div>
        <button
          onClick={onClose}
          className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text-primary)]"
        >
          ✕
        </button>
      </div>

      {node.ticker && node.tracked && (
        <Link
          href={`/filings/graph?root=${encodeURIComponent(node.ticker)}`}
          className="inline-block text-sm text-[var(--color-accent)] hover:underline"
        >
          Open root graph →
        </Link>
      )}

      {([["Discloses", outbound], ["Disclosed by", inbound]] as const).map(
        ([title, rows]) =>
          rows.length > 0 && (
            <section key={title}>
              <h4 className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
                {title}
              </h4>
              {groupByType(rows).map(([type, group]) => (
                <div key={type} className="mt-2">
                  <p className="text-xs font-medium text-[var(--color-text-primary)] capitalize">
                    {type.replace("_", " ")} · {group.length}
                  </p>
                  <ul className="mt-1 space-y-1.5">
                    {group.map((e, i) => (
                      <EdgeRow
                        key={`${e.from_id}|${e.to_id}|${e.section_key}|${i}`}
                        edge={e}
                        other={nodesById.get(
                          title === "Discloses" ? e.to_id : e.from_id,
                        )}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          ),
      )}
    </aside>
  );
}
```

- [ ] **Step 4.3: Create `ThemeGraphView.tsx`**

```tsx
"use client";

/**
 * Theme-wide force-graph view (/filings/graph/theme). URL is the state:
 * ?theme=<id>. Owns the fetch, the selected-node state, and the
 * empty/loading/too-dense rails.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { relationships } from "@/lib/api";
import type { Theme, ThemeGraphResponse } from "@/lib/api";
import { buildSimGraph, REL_TYPE_COLORS } from "@/lib/themeGraph";
import ForceGraphCanvas from "./ForceGraphCanvas";
import ThemeGraphSidePanel from "./ThemeGraphSidePanel";

export default function ThemeGraphView({ themes }: { themes: Theme[] }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const themeId = searchParams.get("theme") ?? "";

  const [graph, setGraph] = useState<ThemeGraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const setThemeParam = useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      if (id) params.set("theme", id);
      else params.delete("theme");
      const qs = params.toString();
      router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
    },
    [searchParams, pathname, router],
  );

  useEffect(() => {
    if (!themeId) {
      setGraph(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    setSelectedId(null);
    relationships
      .getThemeGraph(themeId)
      .then((g) => {
        if (!cancelled) setGraph(g);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [themeId]);

  const sim = useMemo(
    () => (graph ? buildSimGraph(graph.nodes, graph.edges) : null),
    [graph],
  );
  const nodesById = useMemo(
    () => new Map((graph?.nodes ?? []).map((n) => [n.id, n])),
    [graph],
  );
  const selectedNode = selectedId ? nodesById.get(selectedId) ?? null : null;

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 flex flex-wrap items-center gap-3">
        <label className="flex items-center gap-2">
          <span className="text-[11px] font-semibold uppercase text-[var(--color-text-muted)]">
            Theme
          </span>
          <select
            value={themeId}
            onChange={(e) => setThemeParam(e.target.value)}
            className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1.5 text-sm"
          >
            <option value="">Pick a theme…</option>
            {themes.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {graph && !graph.too_dense && (
          <span className="text-xs text-[var(--color-text-muted)]">
            {graph.node_count} nodes · {graph.edge_count} edges
          </span>
        )}
        <div className="ml-auto flex flex-wrap items-center gap-2">
          {Object.entries(REL_TYPE_COLORS)
            .filter(([t]) => !["licensee", "reseller", "other"].includes(t))
            .map(([type, color]) => (
              <span key={type} className="flex items-center gap-1 text-[11px] text-[var(--color-text-muted)]">
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: color }}
                />
                {type.replace("_", " ")}
              </span>
            ))}
        </div>
      </div>

      {!themeId && (
        <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            Pick a theme to see its relationship universe.
          </p>
        </div>
      )}
      {loading && (
        <p className="text-sm text-[var(--color-text-muted)]">Loading…</p>
      )}
      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}
      {graph?.too_dense && (
        <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            Too dense to render ({graph.node_count} nodes,{" "}
            {graph.edge_count} edges — cap is 300 nodes). Narrow the theme.
          </p>
        </div>
      )}
      {graph && !graph.too_dense && graph.edge_count === 0 && !loading && (
        <div className="rounded-xl border-2 border-dashed border-[var(--color-border)] py-12 text-center">
          <p className="text-sm text-[var(--color-text-muted)]">
            No extracted relationships for this theme yet. Run a fan-out from
            the Filings page first.
          </p>
        </div>
      )}
      {graph && !graph.too_dense && graph.edge_count > 0 && sim && (
        <div className="flex flex-col lg:flex-row gap-4">
          <div className="min-w-0 flex-1">
            <ForceGraphCanvas
              nodes={sim.nodes}
              links={sim.links}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </div>
          {selectedNode && (
            <ThemeGraphSidePanel
              node={selectedNode}
              edges={graph.edges}
              nodesById={nodesById}
              onClose={() => setSelectedId(null)}
            />
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4.4: Create the page**

Create `frontend/app/filings/graph/theme/page.tsx` (mirrors `frontend/app/filings/graph/page.tsx` exactly — server component, themes fetch, error rail):

```tsx
/**
 * Page — /filings/graph/theme
 *
 * Theme-wide force-directed supply-chain graph. Server component fetches
 * the theme list; ThemeGraphView owns ?theme= URL state and the graph
 * fetch + rendering.
 */
import Link from "next/link";
import { themes as themesApi } from "@/lib/api";
import type { Theme } from "@/lib/api";
import ThemeGraphView from "@/components/filings/ThemeGraphView";

export const dynamic = "force-dynamic";

export default async function ThemeGraphPage() {
  let allThemes: Theme[] = [];
  let error: string | null = null;

  try {
    allThemes = await themesApi.list();
  } catch {
    error = "Could not connect to backend. Is the FastAPI server running?";
  }

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text)]">
            Theme graph map
          </h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            Force-directed view of every extracted relationship touching a
            theme&apos;s tickers. Hubs and dense clusters surface structure
            the per-ticker view hides.
          </p>
        </div>
        <Link
          href="/filings/graph"
          className="shrink-0 text-sm text-[var(--color-accent)] hover:underline"
        >
          Root graph view →
        </Link>
      </div>

      {error && (
        <div className="rounded-lg border border-[var(--error-border)] bg-[var(--error-bg)] px-4 py-3 text-sm text-[var(--error-text)]">
          {error}
        </div>
      )}

      <ThemeGraphView themes={allThemes} />
    </div>
  );
}
```

Note: header uses `--text` / `--text-muted` to match the existing graph page header exactly (it uses that namespace at the h1 level), while inner components use `--color-*` to match `MultiHopGraphView` — both namespaces are live (CLAUDE.md notes the dual namespace). Copy whatever the existing page actually uses at each spot.

- [ ] **Step 4.5: Gates**

```bash
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

Expected: all clean. If `useSearchParams` triggers a missing-Suspense build error on `/filings/graph/theme`, wrap `<ThemeGraphView …/>` in `<Suspense>` (the `force-dynamic` export on the existing graph page avoids it there — mirror whichever the build accepts).

- [ ] **Step 4.6: Commit**

```bash
git add frontend/components/filings/ForceGraphCanvas.tsx frontend/components/filings/ThemeGraphSidePanel.tsx frontend/components/filings/ThemeGraphView.tsx frontend/app/filings/graph/theme/page.tsx
git commit -m "feat(frontend): D3 force-directed theme graph view"
```

---

### Task 5: Entry points

**Files:**
- Modify: `frontend/app/filings/graph/page.tsx` (header link)
- Modify: `frontend/components/GlobalCommandPalette.tsx` (~line 33, surfaces list)

- [ ] **Step 5.1: Cross-link from the root graph page**

In `frontend/app/filings/graph/page.tsx`, restructure the header div to add the link (mirror the theme page's header flex):

```tsx
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-[var(--text)]">
            Supply-chain graph
          </h1>
          <p className="text-sm text-[var(--text-muted)] mt-0.5">
            Multi-hop counterparty relationships extracted from SEC filings.
            Pick a ticker as the root; expand into a theme to see its 2-hop
            neighbourhood.
          </p>
        </div>
        <Link
          href="/filings/graph/theme"
          className="shrink-0 text-sm text-[var(--color-accent)] hover:underline"
        >
          Theme map →
        </Link>
      </div>
```

Add `import Link from "next/link";` at the top.

- [ ] **Step 5.2: Add the ⌘K surface**

In `frontend/components/GlobalCommandPalette.tsx`, in the surfaces array after `{ title: "Filings graph", href: "/filings/graph" }`:

```ts
  { title: "Theme graph map", href: "/filings/graph/theme" },
```

If CLAUDE.md's "13 surfaces" claim is pinned anywhere in a test, update the count there too (check with `grep -rn "13 surfaces" frontend/ backend/ CLAUDE.md`).

- [ ] **Step 5.3: Gates + commit**

```bash
cd frontend && npm run typecheck && npm run lint && npm run build
git add frontend/app/filings/graph/page.tsx frontend/components/GlobalCommandPalette.tsx
git commit -m "feat(frontend): entry points for theme graph map"
```

---

### Task 6: Live verification on the test DB

- [ ] **Step 6.1: Start both servers against the test snapshot**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
source backend/venv/bin/activate
DATABASE_URL="postgresql+asyncpg://ericwyluda@localhost:5432/sector_research_test" \
  uvicorn backend.app.main:app --port 8000 &
cd frontend && NEXT_PUBLIC_API_URL="http://127.0.0.1:8000" npm run dev &
```

(127.0.0.1, not localhost — Docker steals IPv6 localhost:8000.)

- [ ] **Step 6.2: API smoke**

```bash
THEME_ID=$(psql -h localhost -d sector_research_test -t -A -c "SELECT id FROM themes WHERE name LIKE 'Power%' LIMIT 1;")
curl -s "http://127.0.0.1:8000/api/relationships/theme-graph/$THEME_ID" | python3 -m json.tool | head -40
curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8000/api/relationships/theme-graph/bogus-id"
```

Expected: JSON with nodes/edges/counts; second call prints `404`.

- [ ] **Step 6.3: Playwright walk**

Using the playwright MCP tools: navigate to `http://localhost:3000/filings/graph/theme`, pick the Power & energy theme from the dropdown, screenshot (graph renders, legend visible, counts shown), click a high-degree node, verify the side panel opens with grouped buckets + quotes, click "Open root graph →" and verify it lands on `/filings/graph?root=<ticker>`. Verify the "Theme map →" link on `/filings/graph` and the ⌘K "Theme graph map" entry.

- [ ] **Step 6.4: Kill servers, run full gates one more time**

```bash
ruff check backend
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
cd frontend && npm run typecheck && npm run lint && npm test && npm run build
```

Expected: everything green.

---

### Task 7: Docs + PR

- [ ] **Step 7.1: Update CLAUDE.md and TODO.md**

- CLAUDE.md: in the Phase D section, add the theme-graph endpoint + `/filings/graph/theme` page as consumer #3 of the graph infra; update the ⌘K surface count if stated.
- TODO.md: move "Interactive D3 force-directed full-graph viewer" from Backlog / v3 to Done (recent) with a summary line; note the v3-graph-pack spec path.

- [ ] **Step 7.2: Commit docs, push, open PR**

```bash
git add CLAUDE.md TODO.md
git commit -m "docs: theme graph viewer shipped; TODO/CLAUDE.md updated"
git push -u origin feat/theme-graph-viewer
gh pr create --title "feat: theme-wide D3 force-directed supply-chain graph viewer" --body "..."
```

(Memory note: `gh` API 401s have occurred on PR *merges* — creation works; merge via git/SSH if needed.)

---

## Self-review notes

- **Spec coverage:** builder ✓ (Task 1), endpoint ✓ (Task 2), deps/adapter ✓ (Task 3), force view + side panel + rails ✓ (Task 4), entry points ✓ (Task 5), live smoke ✓ (Task 6). Spec's "edge width by magnitude / bilateral doubled / unresolved muted / seed tint / too-dense rail / no second fetch for panel" all present.
- **Type consistency:** `SimNode`/`SimLink`/`buildSimGraph`/`edgeColor`/`edgeWidth`/`nodeLabel`/`nodeRadius` defined in Task 3, consumed in Task 4 with matching names. `ThemeGraph`/`build_theme_graph`/`MAX_THEME_NODES` defined Task 1, consumed Task 2.
- **Known judgment calls for the executor:** the ForceGraphCanvas link source/target cast (see Step 4.1 warning — use the clean cast); the dual CSS-variable namespace (copy what the neighbouring file uses); Suspense-wrap only if the build demands it.
