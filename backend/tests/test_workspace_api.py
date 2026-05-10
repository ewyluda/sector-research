import os
import unittest
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from fastapi.testclient import TestClient
from backend.app.main import app
from backend.app.api.workspace import get_workspace_service
from backend.app.services.workspace import WorkspaceRunInFlight


class TestWorkspaceAPI(unittest.TestCase):
    def _make_mock_svc(self, return_value=None, side_effect=None):
        mock_svc = AsyncMock()
        if side_effect is not None:
            mock_svc.kick_off = AsyncMock(side_effect=side_effect)
        else:
            mock_svc.kick_off = AsyncMock(return_value=return_value)
        return mock_svc

    def test_post_run_returns_run_id(self):
        mock_svc = self._make_mock_svc(return_value="abc-123")
        app.dependency_overrides[get_workspace_service] = lambda: mock_svc
        try:
            with TestClient(app) as client:
                resp = client.post("/api/workspace/NVDA/runs")
                self.assertEqual(resp.status_code, 202)
                self.assertEqual(resp.json()["run_id"], "abc-123")
        finally:
            app.dependency_overrides.pop(get_workspace_service, None)

    def test_post_run_400_when_no_research_run(self):
        mock_svc = self._make_mock_svc(
            side_effect=ValueError("no completed research_run for ticker NVDA")
        )
        app.dependency_overrides[get_workspace_service] = lambda: mock_svc
        try:
            with TestClient(app) as client:
                resp = client.post("/api/workspace/NVDA/runs")
                self.assertEqual(resp.status_code, 400)
                self.assertIn("no completed research_run", resp.json()["detail"])
        finally:
            app.dependency_overrides.pop(get_workspace_service, None)

    def test_post_run_409_when_run_already_in_flight(self):
        mock_svc = self._make_mock_svc(
            side_effect=WorkspaceRunInFlight(run_id="existing-run-xyz")
        )
        app.dependency_overrides[get_workspace_service] = lambda: mock_svc
        try:
            with TestClient(app) as client:
                resp = client.post("/api/workspace/NVDA/runs")
                self.assertEqual(resp.status_code, 409)
                detail = resp.json()["detail"]
                self.assertEqual(detail["run_id"], "existing-run-xyz")
                self.assertIn("already in flight", detail["message"])
        finally:
            app.dependency_overrides.pop(get_workspace_service, None)

    def test_ticker_path_normalizes_lowercase(self):
        mock_svc = self._make_mock_svc(return_value="abc-123")
        app.dependency_overrides[get_workspace_service] = lambda: mock_svc
        try:
            with TestClient(app) as client:
                resp = client.post("/api/workspace/nvda/runs")
                self.assertEqual(resp.status_code, 202)
                # Verify the service was called with uppercased ticker
                call_args = mock_svc.kick_off.await_args
                self.assertEqual(
                    call_args.kwargs.get("ticker") or call_args.args[0], "NVDA"
                )
        finally:
            app.dependency_overrides.pop(get_workspace_service, None)

    def test_post_run_passes_research_run_id_when_provided(self):
        """Buttons on a specific report send research_run_id so the workspace
        attaches to the clicked thesis, not the latest completed run for the
        ticker."""
        mock_svc = self._make_mock_svc(return_value="abc-123")
        app.dependency_overrides[get_workspace_service] = lambda: mock_svc
        try:
            with TestClient(app) as client:
                resp = client.post(
                    "/api/workspace/NVDA/runs?research_run_id=run-xyz"
                )
                self.assertEqual(resp.status_code, 202)
                call_args = mock_svc.kick_off.await_args
                self.assertEqual(call_args.kwargs.get("research_run_id"), "run-xyz")
        finally:
            app.dependency_overrides.pop(get_workspace_service, None)

    def test_post_run_omits_research_run_id_when_absent(self):
        mock_svc = self._make_mock_svc(return_value="abc-123")
        app.dependency_overrides[get_workspace_service] = lambda: mock_svc
        try:
            with TestClient(app) as client:
                resp = client.post("/api/workspace/NVDA/runs")
                self.assertEqual(resp.status_code, 202)
                call_args = mock_svc.kick_off.await_args
                # Service falls back to latest-completed when research_run_id is None
                self.assertIsNone(call_args.kwargs.get("research_run_id"))
        finally:
            app.dependency_overrides.pop(get_workspace_service, None)
