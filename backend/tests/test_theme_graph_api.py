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
