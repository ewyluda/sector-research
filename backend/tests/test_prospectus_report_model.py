"""Smoke test for ProspectusReport ORM mapping."""
import unittest

from backend.app.models.prospectus_report import ProspectusReport


class TestProspectusReportModel(unittest.TestCase):
    def test_synthetic_ticker_slug_fallback(self):
        r = ProspectusReport(
            accession_number="0001628280-26-036936",
            issuer_cik="0001181412",
            issuer_name="Space Exploration Technologies Corp",
        )
        # "SpaceExplorationTechnologiesCorp" alphanumeric-uppercase → first 16 chars
        self.assertEqual(r.synthetic_ticker, "SPACEEXPLORATION")

    def test_synthetic_ticker_uses_proposed(self):
        r = ProspectusReport(
            accession_number="x",
            issuer_cik="0001",
            issuer_name="Some Long Name LLC",
            proposed_ticker="space",
        )
        self.assertEqual(r.synthetic_ticker, "SPACE")
