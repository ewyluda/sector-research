"""Verify the existing relationship extractor handles S-1 section keys."""
import unittest
from backend.app.services.edgar_relationships import EXTRACTABLE_SECTION_KEYS


class TestS1ExtractableKeys(unittest.TestCase):
    def test_s1_business_extractable(self):
        self.assertIn("s1_business", EXTRACTABLE_SECTION_KEYS)

    def test_s1_risk_factors_extractable(self):
        self.assertIn("s1_risk_factors", EXTRACTABLE_SECTION_KEYS)

    def test_s1_underwriting_not_extractable(self):
        """Underwriting is deal mechanics, not counterparty relationships."""
        self.assertNotIn("s1_underwriting", EXTRACTABLE_SECTION_KEYS)
