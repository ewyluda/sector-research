"""Tests for prospectus_ingest.ingest_prospectus."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from backend.app.services.prospectus_ingest import (
    parse_source_input,
    SourceInput,
)


class TestParseSourceInput(unittest.TestCase):
    def test_url_form(self):
        url = ("https://www.sec.gov/Archives/edgar/data/1181412/"
               "000162828026036936/spaceexplorationtechnologi.htm")
        src = parse_source_input(url)
        self.assertEqual(src.cik_trimmed, "1181412")
        self.assertEqual(src.accession_number, "0001628280-26-036936")
        self.assertEqual(src.primary_document, "spaceexplorationtechnologi.htm")

    def test_accession_form(self):
        src = parse_source_input("0001628280-26-036936")
        self.assertEqual(src.accession_number, "0001628280-26-036936")
        self.assertIsNone(src.cik_trimmed)
        self.assertIsNone(src.primary_document)

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            parse_source_input("not an accession or url")
