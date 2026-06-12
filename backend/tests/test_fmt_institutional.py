"""Tests for _section_institutional and the new kwargs on _fmt_fundamentals.

Env preamble: set dummy values for required settings before importing backend modules.
"""

import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.graph.formatters import _fmt_fundamentals, _section_institutional

# ── Fixtures (derived from live FMP payload recorded 2026-06-12) ──────────────

_SUMMARY = {
    "symbol": "NVDA",
    "cik": "0001045810",
    "date": "2026-03-31",
    "investorsHolding": 6215,
    "investorsHoldingChange": -3,
    "numberOf13Fshares": 16101332088,
    "numberOf13FsharesChange": -366099525,
    "totalInvested": 2803367000119,
    "totalInvestedChange": -245672391722,
    "ownershipPercent": 66.2497,
    "ownershipPercentChange": -1.4423,
    "newPositions": 264,
    "increasedPositions": 2990,
    "reducedPositions": 2452,
    "closedPositions": 290,
    "putCallRatio": 1.1465,
    "putCallRatioChange": -5.1283,
}

_HOLDER_BLACKROCK = {
    "investorName": "BLACKROCK, INC.",
    "marketValue": 335812985602,
    "sharesNumber": 1925533174,
    "changeInSharesNumber": -18279710,
    "changeInSharesNumberPercentage": -0.9404,
    "filingDate": "2026-05-13",
    "isNew": False,
}

_HOLDER_VANGUARD = {
    "investorName": "VANGUARD GROUP INC",
    "marketValue": 280000000000,
    "sharesNumber": 1600000000,
    "changeInSharesNumber": 5000000,
    "changeInSharesNumberPercentage": 0.31,
    "filingDate": "2026-05-14",
    "isNew": False,
}

_HOLDER_NEW = {
    "investorName": "NEW INVESTOR FUND LLC",
    "marketValue": 50000000,
    "sharesNumber": 300000,
    "changeInSharesNumber": 300000,
    "changeInSharesNumberPercentage": 100.0,
    "filingDate": "2026-05-15",
    "isNew": True,
}

# Minimal profile/income/balance/cashflow for _fmt_fundamentals tests
_PROFILE = {
    "companyName": "NVIDIA Corp",
    "sector": "Technology",
    "industry": "Semiconductors",
    "marketCap": 3.5e12,
    "beta": 1.7,
    "description": "NVIDIA designs GPUs.",
    "price": 880.0,
}


# ── _section_institutional tests ──────────────────────────────────────────────

class TestSectionInstitutionalBothAbsent(unittest.TestCase):
    def test_returns_empty_string_when_both_none(self):
        self.assertEqual(_section_institutional(None, None), "")

    def test_returns_empty_string_when_summary_none_holders_empty_list(self):
        self.assertEqual(_section_institutional(None, []), "")

    def test_returns_empty_string_when_summary_empty_dict_holders_none(self):
        # An empty dict is falsy — treated as absent
        self.assertEqual(_section_institutional({}, None), "")

    def test_returns_empty_string_when_both_empty(self):
        self.assertEqual(_section_institutional({}, []), "")


class TestSectionInstitutionalSummaryOnly(unittest.TestCase):
    def setUp(self):
        self.result = _section_institutional(_SUMMARY, None)

    def test_contains_header_with_date(self):
        self.assertIn("INSTITUTIONAL OWNERSHIP", self.result)
        self.assertIn("2026-03-31", self.result)
        self.assertIn("filings lag", self.result)

    def test_contains_holder_count(self):
        self.assertIn("6,215", self.result)

    def test_contains_holder_change(self):
        self.assertIn("-3", self.result)

    def test_contains_ownership_percent(self):
        self.assertIn("66.2%", self.result)

    def test_contains_position_churn(self):
        self.assertIn("264 new", self.result)
        self.assertIn("2990 increased", self.result)
        self.assertIn("2452 reduced", self.result)
        self.assertIn("290 closed", self.result)

    def test_contains_put_call_ratio(self):
        self.assertIn("1.15", self.result)
        self.assertIn("-5.1%", self.result)

    def test_no_top_holders_section(self):
        self.assertNotIn("Top holders", self.result)

    def test_13f_shares_humanized(self):
        # 16101332088 → 16.1B
        self.assertIn("16.1B", self.result)

    def test_13f_shares_change_humanized(self):
        # -366099525 → -366.1M
        self.assertIn("-366.1M", self.result)


class TestSectionInstitutionalHoldersOnly(unittest.TestCase):
    def setUp(self):
        self.result = _section_institutional(None, [_HOLDER_BLACKROCK, _HOLDER_VANGUARD])

    def test_contains_header_without_date(self):
        self.assertIn("INSTITUTIONAL OWNERSHIP", self.result)
        self.assertNotIn("2026-03-31", self.result)

    def test_contains_top_holders_section(self):
        self.assertIn("Top holders", self.result)

    def test_blackrock_appears(self):
        self.assertIn("BLACKROCK", self.result)

    def test_sorted_by_market_value_desc(self):
        # Blackrock (335B) should appear before Vanguard (280B)
        idx_bl = self.result.index("BLACKROCK")
        idx_vg = self.result.index("VANGUARD")
        self.assertLess(idx_bl, idx_vg)


class TestSectionInstitutionalFullPayload(unittest.TestCase):
    def setUp(self):
        holders = [_HOLDER_BLACKROCK, _HOLDER_VANGUARD, _HOLDER_NEW]
        self.result = _section_institutional(_SUMMARY, holders)

    def test_header_present(self):
        self.assertIn("INSTITUTIONAL OWNERSHIP", self.result)
        self.assertIn("2026-03-31", self.result)

    def test_summary_lines_present(self):
        self.assertIn("6,215", self.result)
        self.assertIn("66.2%", self.result)
        self.assertIn("Position churn", self.result)
        self.assertIn("put/call", self.result)

    def test_top_holders_section_present(self):
        self.assertIn("Top holders", self.result)
        self.assertIn("BLACKROCK", self.result)
        self.assertIn("VANGUARD", self.result)

    def test_new_flag_present_for_new_holder(self):
        self.assertIn("[NEW]", self.result)

    def test_qoq_change_present_for_nonzero_change(self):
        # Blackrock has -18279710 shares change → should appear
        self.assertIn("-18.3M sh QoQ", self.result)

    def test_positive_qoq_change_present(self):
        # Vanguard has +5000000 shares change
        self.assertIn("5.0M sh QoQ", self.result)

    def test_capped_at_10_holders(self):
        # Build 15 holders with descending market values
        many_holders = [
            {"investorName": f"FUND {i:02d}", "marketValue": (20 - i) * 1e9,
             "sharesNumber": (20 - i) * 1e6, "changeInSharesNumber": 0, "isNew": False}
            for i in range(15)
        ]
        result = _section_institutional(_SUMMARY, many_holders)
        # Count lines starting with "  FUND" — should be exactly 10
        fund_lines = [ln for ln in result.splitlines() if ln.strip().startswith("FUND")]
        self.assertEqual(len(fund_lines), 10)

    def test_name_truncated_at_40_chars(self):
        long_name = "A" * 50
        holder = {"investorName": long_name, "marketValue": 1e9,
                  "sharesNumber": 1e6, "changeInSharesNumber": 0, "isNew": False}
        result = _section_institutional(None, [holder])
        # The name in the result should not exceed 40 chars
        for line in result.splitlines():
            if "A" * 40 in line:
                # the 41st+ chars should NOT appear
                self.assertNotIn("A" * 41, line)
                break

    def test_sorted_desc_by_market_value(self):
        idx_bl = self.result.index("BLACKROCK")
        idx_vg = self.result.index("VANGUARD")
        idx_new = self.result.index("NEW INVESTOR")
        self.assertLess(idx_bl, idx_vg)
        self.assertLess(idx_vg, idx_new)


class TestSectionInstitutionalNullFieldTolerance(unittest.TestCase):
    def test_missing_half_the_summary_keys(self):
        sparse = {
            "date": "2026-03-31",
            "investorsHolding": 5000,
            # no investorsHoldingChange, no numberOf13Fshares, etc.
        }
        result = _section_institutional(sparse, None)
        self.assertIn("INSTITUTIONAL OWNERSHIP", result)
        self.assertIn("5,000", result)
        # Missing fields should not raise — just render em-dash or omit
        self.assertNotIn("None", result)

    def test_null_put_call_ratio_omitted(self):
        summary = dict(_SUMMARY)
        summary.pop("putCallRatio", None)
        result = _section_institutional(summary, None)
        self.assertNotIn("put/call", result)

    def test_null_churn_positions_omitted(self):
        summary = {
            "date": "2026-03-31",
            "investorsHolding": 100,
        }
        result = _section_institutional(summary, None)
        self.assertNotIn("Position churn", result)

    def test_zero_shares_change_no_qoq_suffix(self):
        holder = {"investorName": "STEADY FUND", "marketValue": 1e9,
                  "sharesNumber": 1e6, "changeInSharesNumber": 0, "isNew": False}
        result = _section_institutional(None, [holder])
        self.assertNotIn("QoQ", result)

    def test_none_shares_change_no_qoq_suffix(self):
        holder = {"investorName": "STEADY FUND", "marketValue": 1e9,
                  "sharesNumber": 1e6, "changeInSharesNumber": None, "isNew": False}
        result = _section_institutional(None, [holder])
        self.assertNotIn("QoQ", result)

    def test_no_none_literals_in_output(self):
        # Ensure we never accidentally render the string "None"
        result = _section_institutional(_SUMMARY, [_HOLDER_BLACKROCK])
        self.assertNotIn("None", result)


# ── _fmt_fundamentals identity: new kwargs absent → output unchanged ──────────

class TestFmtFundamentalsInstKwargsIdentity(unittest.TestCase):
    def test_output_identical_with_and_without_inst_kwargs(self):
        """When inst_summary/inst_holders are absent (defaults), output must be
        byte-identical to a call that never passes those kwargs at all."""
        without = _fmt_fundamentals("NVDA", [], [], [], _PROFILE)
        with_defaults = _fmt_fundamentals(
            "NVDA", [], [], [], _PROFILE,
            inst_summary=None, inst_holders=None,
        )
        self.assertEqual(without, with_defaults)

    def test_output_identical_with_empty_list_for_holders(self):
        without = _fmt_fundamentals("NVDA", [], [], [], _PROFILE)
        with_empty = _fmt_fundamentals(
            "NVDA", [], [], [], _PROFILE,
            inst_summary=None, inst_holders=[],
        )
        self.assertEqual(without, with_empty)

    def test_inst_section_appended_when_provided(self):
        result = _fmt_fundamentals(
            "NVDA", [], [], [], _PROFILE,
            inst_summary=_SUMMARY,
            inst_holders=[_HOLDER_BLACKROCK],
        )
        self.assertIn("INSTITUTIONAL OWNERSHIP", result)
        self.assertIn("BLACKROCK", result)


if __name__ == "__main__":
    unittest.main()


class CikFallbackTests(unittest.TestCase):
    def test_empty_investor_name_falls_back_to_cik(self):
        # FMP serves empty investorName for freshly re-registered filer CIKs
        # (live-observed 2026-06-12).
        section = _section_institutional(None, [
            {"investorName": "", "cik": "0002100119",
             "sharesNumber": 1_538_550_382, "marketValue": 268_300_000_000},
        ])
        self.assertIn("CIK 0002100119", section)
        self.assertNotIn("Unknown", section)

    def test_no_name_no_cik_stays_unknown(self):
        section = _section_institutional(None, [
            {"sharesNumber": 100, "marketValue": 1000},
        ])
        self.assertIn("Unknown", section)
