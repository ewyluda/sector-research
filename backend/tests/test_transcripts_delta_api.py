"""Tests for backend.app.api.transcripts_delta."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


class TestGetLatest(unittest.TestCase):
    def test_204_when_no_delta(self):
        from backend.app.main import app

        with patch(
            "backend.app.api.transcripts_delta._fetch_latest",
            new=AsyncMock(return_value=None),
        ):
            client = TestClient(app)
            r = client.get("/api/transcripts/delta/NVDA/latest")
            self.assertEqual(r.status_code, 204)

    def test_200_returns_existing(self):
        from backend.app.main import app

        payload = {
            "id": str(uuid4()),
            "ticker": "NVDA",
            "transcripts_window": [{"year": 2025, "quarter": 4},
                                    {"year": 2025, "quarter": 3}],
            "axes": {k: None for k in (
                "business_quality", "risk_assessment", "growth_earnings",
                "sentiment_narrative", "management_governance",
                "future_durability", "macro_regime", "financial_health",
                "valuation_stage",
            )},
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }
        with patch(
            "backend.app.api.transcripts_delta._fetch_latest",
            new=AsyncMock(return_value=payload),
        ):
            client = TestClient(app)
            r = client.get("/api/transcripts/delta/NVDA/latest")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ticker"], "NVDA")


class TestPostCompute(unittest.TestCase):
    def test_post_returns_200_and_payload(self):
        from backend.app.main import app
        from backend.app.models.transcript_delta import TranscriptDelta

        row = TranscriptDelta(
            id=str(uuid4()), ticker="NVDA",
            transcripts_window=[{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}],
            transcripts_fingerprint="abc",
            axes={k: None for k in (
                "business_quality", "risk_assessment", "growth_earnings",
                "sentiment_narrative", "management_governance",
                "future_durability", "macro_regime", "financial_health",
                "valuation_stage",
            )},
            computed_at=datetime.now(timezone.utc),
        )
        app.state.fmp = MagicMock()
        with patch(
            "backend.app.api.transcripts_delta.transcript_delta.compute_delta",
            new=AsyncMock(return_value=row),
        ):
            client = TestClient(app)
            r = client.post("/api/transcripts/delta/NVDA")
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["ticker"], "NVDA")

    def test_post_404_on_insufficient_transcripts(self):
        from backend.app.main import app
        from backend.app.services.transcript_delta import InsufficientTranscriptsError

        app.state.fmp = MagicMock()
        with patch(
            "backend.app.api.transcripts_delta.transcript_delta.compute_delta",
            new=AsyncMock(side_effect=InsufficientTranscriptsError("NVDA: only 1")),
        ):
            client = TestClient(app)
            r = client.post("/api/transcripts/delta/NVDA")
            self.assertEqual(r.status_code, 404)

    def test_post_force_param_forwarded(self):
        from backend.app.main import app
        from backend.app.models.transcript_delta import TranscriptDelta

        row = TranscriptDelta(
            id=str(uuid4()), ticker="NVDA",
            transcripts_window=[{"year": 2025, "quarter": 4}, {"year": 2025, "quarter": 3}],
            transcripts_fingerprint="abc",
            axes={k: None for k in (
                "business_quality", "risk_assessment", "growth_earnings",
                "sentiment_narrative", "management_governance",
                "future_durability", "macro_regime", "financial_health",
                "valuation_stage",
            )},
            computed_at=datetime.now(timezone.utc),
        )
        app.state.fmp = MagicMock()
        compute_mock = AsyncMock(return_value=row)
        with patch(
            "backend.app.api.transcripts_delta.transcript_delta.compute_delta",
            new=compute_mock,
        ):
            client = TestClient(app)
            r = client.post("/api/transcripts/delta/NVDA?force=true")
            self.assertEqual(r.status_code, 200)
            self.assertTrue(compute_mock.call_args.kwargs["force"])


if __name__ == "__main__":
    unittest.main()
