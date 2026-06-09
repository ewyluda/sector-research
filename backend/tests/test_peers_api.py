"""Pins the /api/peers contract: route ordering (/compare is NOT swallowed
by /{ticker} — 'compare' parses as a valid ticker symbol!), param
validation, seed-on-GET with route-owned commit, PUT error mapping, and
empty-set comp shape."""

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

from backend.app.api.peers import router
from backend.app.db import get_db
from backend.app.models.peer_comp import PeerCompRow, PeerCompTable


def make_client() -> tuple[TestClient, AsyncMock]:
    """Returns (client, db) — db is the AsyncMock session the routes receive."""
    app = FastAPI()
    app.include_router(router)
    db = AsyncMock()

    async def _fake_db():
        yield db

    app.dependency_overrides[get_db] = _fake_db
    app.state.fmp = AsyncMock()
    return TestClient(app), db


def _fake_table(focus="NVDA", peers=("AMD",)):
    rows = [PeerCompRow(ticker=focus)] + [PeerCompRow(ticker=p) for p in peers]
    return PeerCompTable(
        focus_ticker=focus,
        rows=rows,
        median=PeerCompRow(ticker="__median__"),
        delta_vs_median_pct=PeerCompRow(ticker="__delta__"),
    )


class CompareRouteTests(unittest.TestCase):
    def test_compare_not_shadowed_by_ticker_route(self):
        """'compare' is a valid-looking ticker — without correct route
        ordering, GET /api/peers/compare would hit /{ticker} and return a
        peer-set payload instead of a 422 for the missing tickers param."""
        client, _ = make_client()
        resp = client.get("/api/peers/compare")
        self.assertEqual(resp.status_code, 422)  # missing required ?tickers=

    def test_compare_builds_table_with_default_focus(self):
        client, _ = make_client()
        with patch(
            "backend.app.api.peers.build_peer_comp_table",
            new=AsyncMock(return_value=(_fake_table(), [])),
        ) as build:
            resp = client.get("/api/peers/compare?tickers=nvda,AMD")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["table"]["focus_ticker"], "NVDA")
        self.assertEqual(body["errors"], [])
        # default focus = first ticker, normalized; peers exclude focus
        kwargs = build.await_args.kwargs
        self.assertEqual(kwargs["focus_ticker"], "NVDA")
        self.assertEqual(kwargs["peer_tickers"], ["AMD"])

    def test_compare_rejects_invalid_ticker(self):
        client, _ = make_client()
        resp = client.get("/api/peers/compare?tickers=NVDA,NOT%20A%20TICKER")
        self.assertEqual(resp.status_code, 400)

    def test_compare_rejects_over_cap(self):
        client, _ = make_client()
        tickers = ",".join(f"T{i}" for i in range(13))
        resp = client.get(f"/api/peers/compare?tickers={tickers}")
        self.assertEqual(resp.status_code, 400)

    def test_compare_rejects_focus_not_in_tickers(self):
        client, _ = make_client()
        resp = client.get("/api/peers/compare?tickers=NVDA,AMD&focus=INTC")
        self.assertEqual(resp.status_code, 400)

    def test_compare_focus_failure_maps_to_502(self):
        client, _ = make_client()
        with patch(
            "backend.app.api.peers.build_peer_comp_table",
            new=AsyncMock(side_effect=RuntimeError("FMP down")),
        ):
            resp = client.get("/api/peers/compare?tickers=NVDA,AMD")
        self.assertEqual(resp.status_code, 502)


class PeerSetRouteTests(unittest.TestCase):
    def test_get_seeds_returns_and_commits(self):
        client, db = make_client()
        with patch(
            "backend.app.api.peers.get_or_seed_peer_set",
            new=AsyncMock(return_value=(["AMD", "INTC"], True)),
        ):
            resp = client.get("/api/peers/nvda")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.json(), {"ticker": "NVDA", "peers": ["AMD", "INTC"], "seeded": True}
        )
        db.commit.assert_awaited_once()  # route owns the commit on the seed path

    def test_get_hit_path_does_not_commit(self):
        client, db = make_client()
        with patch(
            "backend.app.api.peers.get_or_seed_peer_set",
            new=AsyncMock(return_value=(["AMD"], False)),
        ):
            resp = client.get("/api/peers/NVDA")
        self.assertEqual(resp.status_code, 200)
        db.commit.assert_not_awaited()

    def test_get_rejects_garbage_ticker(self):
        client, _ = make_client()
        resp = client.get("/api/peers/NOT%20A%20TICKER")
        self.assertEqual(resp.status_code, 400)

    def test_put_replaces_and_commits(self):
        client, db = make_client()
        with patch(
            "backend.app.api.peers.update_peer_set",
            new=AsyncMock(return_value=["AMD"]),
        ):
            resp = client.put("/api/peers/NVDA", json={"peers": ["amd"]})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["peers"], ["AMD"])
        db.commit.assert_awaited_once()

    def test_put_maps_value_error_to_400_without_commit(self):
        client, db = make_client()
        with patch(
            "backend.app.api.peers.update_peer_set",
            new=AsyncMock(side_effect=ValueError("invalid ticker symbol")),
        ):
            resp = client.put("/api/peers/NVDA", json={"peers": ["bad!!"]})
        self.assertEqual(resp.status_code, 400)
        db.commit.assert_not_awaited()

    def test_comp_empty_set_returns_null_table(self):
        client, _ = make_client()
        with patch(
            "backend.app.api.peers.get_or_seed_peer_set",
            new=AsyncMock(return_value=([], True)),
        ):
            resp = client.get("/api/peers/NVDA/comp")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"table": None, "errors": []})

    def test_comp_builds_from_persisted_set(self):
        client, _ = make_client()
        with patch(
            "backend.app.api.peers.get_or_seed_peer_set",
            new=AsyncMock(return_value=(["AMD"], False)),
        ), patch(
            "backend.app.api.peers.build_peer_comp_table",
            new=AsyncMock(return_value=(_fake_table(), [])),
        ):
            resp = client.get("/api/peers/NVDA/comp")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["table"]["focus_ticker"], "NVDA")


if __name__ == "__main__":
    unittest.main()
