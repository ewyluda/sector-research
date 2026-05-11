"""Tests for backend.app.api.transcripts_delta."""
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
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


if __name__ == "__main__":
    unittest.main()
