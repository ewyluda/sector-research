"""Integration-style test for ProspectusService — mocks every external call."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services.prospectus_service import ProspectusService


def _stub_html() -> str:
    pad = " The following paragraph contains substantive narrative content " * 12
    return (
        "<html><body>"
        f"<p>ITEM 1. BUSINESS</p><p>We design rockets.{pad}</p>"
        f"<p>RISK FACTORS</p><p>Unicorn attacks.{pad}</p>"
        f"<p>MANAGEMENT'S DISCUSSION AND ANALYSIS</p><p>Revenue rose.{pad}</p>"
        f"<p>USE OF PROCEEDS</p><p>General corporate.{pad}</p>"
        f"<p>CAPITALIZATION</p><p>Debt low.{pad}</p>"
        f"<p>DILUTION</p><p>15% dilution.{pad}</p>"
        f"<p>PRINCIPAL STOCKHOLDERS</p><p>Founder 78%.{pad}</p>"
        f"<p>UNDERWRITING</p><p>GS/MS/JPM.{pad}</p>"
        "</body></html>"
    )


def _fake_edgar() -> MagicMock:
    edgar = MagicMock()
    edgar.get_submissions = AsyncMock(return_value=(
        {
            "name": "ACME Rockets Inc",
            "filings": {"recent": {
                "accessionNumber": ["0001628280-26-036936"],
                "form": ["S-1"],
                "primaryDocument": ["acme.htm"],
                "filingDate": ["2026-05-20"],
                "reportDate": [""],
            }},
        },
        MagicMock(),  # citation
    ))
    edgar.fetch_document = AsyncMock(return_value=(_stub_html(), MagicMock()))
    return edgar


class TestProspectusServiceKickoff(unittest.IsolatedAsyncioTestCase):
    async def test_kickoff_returns_report_id(self):
        svc = ProspectusService(edgar=_fake_edgar(), fred=None)

        # Stub unit_of_work so kick_off does not hit a real DB.
        mock_db = MagicMock()
        mock_db.add = MagicMock()
        mock_uow_cm = MagicMock()
        mock_uow_cm.__aenter__ = AsyncMock(return_value=mock_db)
        mock_uow_cm.__aexit__ = AsyncMock(return_value=False)

        with patch("backend.app.services.prospectus_service.unit_of_work",
                   return_value=mock_uow_cm), \
             patch.object(ProspectusService, "_run_pipeline",
                          new=AsyncMock(return_value=None)):
            rid = await svc.kick_off(
                url_or_accession=(
                    "https://www.sec.gov/Archives/edgar/data/1181412/"
                    "000162828026036936/acme.htm"
                ),
                theme_id=None,
            )
        self.assertTrue(isinstance(rid, str) and len(rid) >= 32)
