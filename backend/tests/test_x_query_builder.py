"""Tests for XClient query builder.

The builder must handle themes that mix simple keywords with rich X-search
syntax (quoted phrases, hashtags, cashtags, embedded OR operators) without
introducing the doubled-quote bug that previously broke the
"Power & energy bottleneck" theme.
"""

import unittest
from unittest.mock import patch

from backend.app.clients.x_client import XClient


class FakeSettings:
    x_bearer_token = "test"
    x_base_url = "https://example.test/2"


def _client() -> XClient:
    with patch("backend.app.clients.x_client.get_settings", return_value=FakeSettings()):
        return XClient()


class BuildThemeQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.x = _client()

    def test_empty_terms_returns_empty(self):
        self.assertEqual(self.x._build_theme_query([]), "")

    def test_bare_keyword(self):
        q = self.x._build_theme_query(["SMR"])
        self.assertEqual(q, "(SMR) -is:retweet lang:en")

    def test_plain_phrase_gets_quoted(self):
        q = self.x._build_theme_query(["AI capex"])
        self.assertEqual(q, '("AI capex") -is:retweet lang:en')

    def test_pre_quoted_phrase_not_double_quoted(self):
        q = self.x._build_theme_query(['"Grid Cliff"'])
        self.assertNotIn('""', q)
        self.assertIn('"Grid Cliff"', q)

    def test_hashtag_passes_through(self):
        q = self.x._build_theme_query(["#DataCenterPower"])
        self.assertEqual(q, "(#DataCenterPower) -is:retweet lang:en")

    def test_cashtag_passes_through(self):
        q = self.x._build_theme_query(["$BE"])
        self.assertEqual(q, "($BE) -is:retweet lang:en")

    def test_embedded_or_wrapped_in_parens(self):
        q = self.x._build_theme_query(['#LiquidCooling OR "AI Density"'])
        self.assertIn('(#LiquidCooling OR "AI Density")', q)
        self.assertNotIn('"#', q)  # no double-quoting around the whole thing

    def test_mixed_neoclouds_theme(self):
        # Mirrors the Neo-clouds theme: bare keywords + cashtags + a phrase
        q = self.x._build_theme_query(["neocloud", "AI capex", "NBIS", "CRWV"])
        self.assertEqual(q, '(neocloud OR "AI capex" OR NBIS OR CRWV) -is:retweet lang:en')

    def test_power_energy_theme_no_doubled_quotes(self):
        """The original bug: pre-quoted phrases got wrapped in another set of quotes."""
        terms = [
            '"Power Scarcity" 2026',
            '"AI-Energy Infrastructure Gap"',
            '"Grid Cliff"',
            "#DataCenterPower",
            "#AIEnergy",
            '"Prime Power" data centers',
            '#LiquidCooling OR "AI Density"',
            '"Solid Oxide Fuel Cells" OR SOFC',
            '$BE "Island Mode" orders',
        ]
        q = self.x._build_theme_query(terms)
        # The cardinal sin we are preventing
        self.assertNotIn('""', q)
        # All the literal phrases survive intact
        self.assertIn('"Power Scarcity"', q)
        self.assertIn('"Grid Cliff"', q)
        self.assertIn("#DataCenterPower", q)
        self.assertIn("$BE", q)
        # OR-bearing terms are grouped
        self.assertIn('(#LiquidCooling OR "AI Density")', q)
        self.assertIn('("Solid Oxide Fuel Cells" OR SOFC)', q)

    def test_caps_at_ten_terms(self):
        terms = [f"k{i}" for i in range(15)]
        q = self.x._build_theme_query(terms)
        # Only first 10 should be present
        self.assertIn("k9", q)
        self.assertNotIn("k10", q)

    def test_skips_empty_strings(self):
        q = self.x._build_theme_query(["SMR", "", "  ", "BWXT"])
        self.assertEqual(q, "(SMR OR BWXT) -is:retweet lang:en")


if __name__ == "__main__":
    unittest.main()
