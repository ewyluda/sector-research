"""Recorded-payload tests pinning the FMP metric-scaling convention.

Convention: the backend emits fraction-form ratios (0.683 = 68.3%); the
frontend multiplies by 100 exactly once (formatStat.ts / PeerCompTable.tsx).

Payloads below are trimmed copies of live /stable/ responses (ratios-ttm,
key-metrics-ttm, financial-growth) recorded 2026-06-11. They pin:

- fraction convention for sane tickers (MSFT gross ~0.683, not 68.3)
- tier-1 guard: ORCL's corrupt grossProfitMarginTTM=1.1815 → None + warning
- tier-2 guard: CORZ's genuine netProfitMarginTTM=-3.43 passes through (+ warning)
- CAGR semantics: five/tenYRevenueGrowthPerShare are CUMULATIVE → annualized
- fcf_margin = p_s / p_fcf derivation (real ORCL inputs, negative TTM FCF)
"""
import os
import unittest

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")

from backend.app.services.company_snapshot import (
    CompanyOverview,
    _annualize_cumulative,
    build_company_overview,
)
from backend.app.services.metric_guards import guard_margin
from backend.app.services.peer_comp import (
    NM_GROWTH_THRESHOLD,
    _compute_delta,
    _compute_median,
    _fetch_one,
)

GUARD_LOGGER = "backend.app.services.metric_guards"

# ── Trimmed live /stable/ payloads (recorded 2026-06-11) ────────────────────

RATIOS = {
    # Sane large-cap: all margins in fraction form, well inside [-5.0, 1.5].
    "MSFT": {
        "grossProfitMarginTTM": 0.6830928165442874,
        "operatingProfitMarginTTM": 0.4680164512855316,
        "ebitdaMarginTTM": 0.6314044860858445,
        "pretaxProfitMarginTTM": 0.48544174340896024,
        "netProfitMarginTTM": 0.39342325613545603,
        "priceToEarningsRatioTTM": 23.565641451571686,
        "priceToBookRatioTTM": 7.121212258698208,
        "priceToSalesRatioTTM": 9.274305218475963,
        "priceToFreeCashFlowRatioTTM": 40.481663075319545,
        "priceToEarningsGrowthRatioTTM": 0.7930509908184347,
        "enterpriseValueMultipleTTM": 14.812080796580396,
    },
    # Corrupt: gross margin 1.1815 (>1.0 is arithmetically impossible —
    # negative cost of revenue). Rendered as 118.1% before the guard.
    "ORCL": {
        "grossProfitMarginTTM": 1.1814780723893228,
        "operatingProfitMarginTTM": 0.3059176341340301,
        "ebitdaMarginTTM": 0.09206033433296713,
        "pretaxProfitMarginTTM": 0.29031443926482375,
        "netProfitMarginTTM": 0.2536743965082099,
        "priceToEarningsRatioTTM": 33.898652776964944,
        "priceToBookRatioTTM": 13.452858602749908,
        "priceToSalesRatioTTM": 8.593381899106268,
        "priceToFreeCashFlowRatioTTM": -24.437769904584986,
        "priceToEarningsGrowthRatioTTM": 1.0215404823328618,
        "enterpriseValueMultipleTTM": 113.48702111917433,
    },
    # Deep-loss company: pretax/net margins of -3.43 are GENUINE (must not
    # be nulled), but sit outside the tier-2 sanity window → warning only.
    "CORZ": {
        "grossProfitMarginTTM": 0.16754055105458113,
        "operatingProfitMarginTTM": -0.2888554369703838,
        "ebitdaMarginTTM": 0.2508696559150697,
        "pretaxProfitMarginTTM": -3.4265260558496693,
        "netProfitMarginTTM": -3.4292830201444446,
        "priceToSalesRatioTTM": 23.02113910266168,
        "priceToFreeCashFlowRatioTTM": -17.331150638155187,
    },
}

KM = {
    "MSFT": {
        "returnOnEquityTTM": 0.3313037398539619,
        "returnOnAssetsTTM": 0.1803672568666202,
        "returnOnInvestedCapitalTTM": 0.21313559289430895,
        "evToEBITDATTM": 14.812080796580396,
        "netDebtToEBITDATTM": 0.4078350670341544,
        "marketCap": 2951760944800,
    },
    "ORCL": {
        "returnOnEquityTTM": 0.5038332252167247,
        "returnOnAssetsTTM": 0.06527760268032809,
        "returnOnInvestedCapitalTTM": 0.07925101567123531,
        "evToEBITDATTM": 113.48702111917433,
        "netDebtToEBITDATTM": 2.0193241886555748,
        "marketCap": 578833017960,
    },
    "CORZ": {
        "returnOnEquityTTM": 1.0907689696065128,
        "returnOnAssetsTTM": -0.3963093781396967,
        "returnOnInvestedCapitalTTM": -0.07310135725623786,
        "marketCap": 8166472843,
    },
}

GROWTH = {
    # five/tenYRevenueGrowthPerShare are CUMULATIVE per-share growth over the
    # window: MSFT 1.0168 = revenue/share roughly doubled over 5y (~15%/yr),
    # not 101.7%/yr.
    "MSFT": [{
        "revenueGrowth": 0.1493215623240672,
        "epsgrowth": 0.1551433389544688,
        "freeCashFlowGrowth": -0.0332113782721983,
        "ebitdaGrowth": 0.2041666353404657,
        "fiveYRevenueGrowthPerShare": 1.0167997532375588,
        "tenYRevenueGrowthPerShare": 2.3118500881868194,
    }],
    "ORCL": [{
        "revenueGrowth": 0.17346992107876444,
        "epsgrowth": 0.33183856502242165,
        # Tiny-base artifact: -5911.7% YoY — frontend renders "n/m" (|x| > 10).
        "freeCashFlowGrowth": -59.11675126903553,
        "ebitdaGrowth": -0.7406741385078621,
        "fiveYRevenueGrowthPerShare": 0.7027113175869072,
        "tenYRevenueGrowthPerShare": 1.7164449538612683,
    }],
    "CORZ": [{
        "revenueGrowth": -0.37529568881787134,
        "epsgrowth": 0.8287937743190662,
        "freeCashFlowGrowth": -7.657447421492365,
        "ebitdaGrowth": 0.8752146799140849,
        "fiveYRevenueGrowthPerShare": 5.316292482084474,
        "tenYRevenueGrowthPerShare": 5.400866262106001,
    }],
}

PROFILE = {
    "MSFT": {"marketCap": 2951760944800, "sector": "Technology"},
    "ORCL": {"marketCap": 578833017960, "sector": "Technology"},
    "CORZ": {"marketCap": 8166472843, "sector": "Technology"},
}


class _StubFMP:
    """Serves the recorded payloads via the (data, citation) tuple convention."""

    async def get_company_profile(self, ticker):
        return PROFILE.get(ticker, {}), None

    async def get_key_metrics_ttm(self, ticker):
        return KM.get(ticker, {}), None

    async def get_ratios_ttm(self, ticker):
        return RATIOS.get(ticker, {}), None

    async def get_financial_growth(self, ticker, period="annual", limit=5):
        return GROWTH.get(ticker, []), None

    async def get_historical_price_adjusted(self, ticker, start, end):
        return [], None


def _stat(overview: CompanyOverview, group: str, label: str):
    for g in overview.stats:
        if g.title == group:
            for it in g.items:
                if it.label == label:
                    return it.value
    raise AssertionError(f"stat {group}/{label} not found")


class FractionConventionTest(unittest.IsolatedAsyncioTestCase):
    """Sane tickers: values stay in fraction form, no guard warnings."""

    async def test_msft_overview_margins_are_fractions(self):
        with self.assertNoLogs(GUARD_LOGGER, level="WARNING"):
            ov = await build_company_overview(_StubFMP(), "MSFT")
        gross = _stat(ov, "Margins", "Gross")
        self.assertTrue(0.6 < gross < 0.75, gross)  # 0.683, NOT 68.3
        net = _stat(ov, "Margins", "Net")
        self.assertTrue(0.3 < net < 0.45, net)
        roe = _stat(ov, "Returns (TTM)", "ROE")
        self.assertTrue(0.25 < roe < 0.4, roe)

    async def test_msft_peer_row_margins_are_fractions(self):
        with self.assertNoLogs(GUARD_LOGGER, level="WARNING"):
            row = await _fetch_one("MSFT", _StubFMP())
        self.assertTrue(0.6 < row.gross_margin < 0.75, row.gross_margin)
        self.assertTrue(0.4 < row.operating_margin < 0.55, row.operating_margin)
        self.assertTrue(0.25 < row.roe < 0.4, row.roe)


class ImpossibleGrossMarginTest(unittest.IsolatedAsyncioTestCase):
    """Tier 1: ORCL's corrupt gross margin (1.1815 > 1.0) → None + warning."""

    async def test_overview_nulls_corrupt_gross(self):
        with self.assertLogs(GUARD_LOGGER, level="WARNING") as cm:
            ov = await build_company_overview(_StubFMP(), "ORCL")
        self.assertIsNone(_stat(ov, "Margins", "Gross"))
        self.assertIn("impossible grossProfitMarginTTM", "\n".join(cm.output))
        # Sibling margins untouched.
        self.assertAlmostEqual(
            _stat(ov, "Margins", "Operating"), 0.3059176341340301
        )

    async def test_peer_row_nulls_corrupt_gross(self):
        with self.assertLogs(GUARD_LOGGER, level="WARNING") as cm:
            row = await _fetch_one("ORCL", _StubFMP())
        self.assertIsNone(row.gross_margin)
        self.assertIn("impossible grossProfitMarginTTM", "\n".join(cm.output))
        self.assertIsNone(row.ebitda_margin)

    async def test_overview_nulls_correlated_ebitda_metrics(self):
        with self.assertLogs(GUARD_LOGGER, level="WARNING"):
            ov = await build_company_overview(_StubFMP(), "ORCL")
        self.assertIsNone(_stat(ov, "Margins", "EBITDA"))
        self.assertIsNone(_stat(ov, "Valuation (TTM)", "EV/EBITDA"))
        self.assertIsNone(_stat(ov, "Financial Health", "Net Debt/EBITDA"))
        # Operating is not EBITDA-derived — still passes through.
        self.assertAlmostEqual(_stat(ov, "Margins", "Operating"), 0.3059176341340301)

    async def test_clean_ticker_keeps_ebitda_metrics(self):
        ov = await build_company_overview(_StubFMP(), "MSFT")
        self.assertAlmostEqual(_stat(ov, "Margins", "EBITDA"), 0.6314044860858445)
        self.assertAlmostEqual(_stat(ov, "Valuation (TTM)", "EV/EBITDA"), 14.812080796580396)
        self.assertAlmostEqual(_stat(ov, "Financial Health", "Net Debt/EBITDA"), 0.4078350670341544)

    async def test_peer_row_nulls_correlated_ebitda_metrics(self):
        with self.assertLogs(GUARD_LOGGER, level="WARNING"):
            row = await _fetch_one("ORCL", _StubFMP())
        self.assertIsNone(row.ebitda_margin)
        self.assertIsNone(row.ev_ebitda)


class DeepLossMarginPassthroughTest(unittest.IsolatedAsyncioTestCase):
    """Tier 2: deep-loss margins are real and must NOT be nulled.

    CORZ's genuine -3.43 net margin sits INSIDE the sane window [-5.0, 1.5],
    so it passes through silently. The tier-2 warning only fires outside that
    window — and even then the value passes through unchanged.
    """

    async def test_corz_net_margin_passes_through(self):
        with self.assertNoLogs(GUARD_LOGGER, level="WARNING"):
            ov = await build_company_overview(_StubFMP(), "CORZ")
        self.assertAlmostEqual(_stat(ov, "Margins", "Net"), -3.4292830201444446)
        self.assertAlmostEqual(_stat(ov, "Margins", "Pre-Tax"), -3.4265260558496693)

    def test_out_of_window_margin_warns_but_passes_through(self):
        with self.assertLogs(GUARD_LOGGER, level="WARNING") as cm:
            v = guard_margin(-6.0, metric="netProfitMarginTTM", ticker="ZZZ")
        self.assertEqual(v, -6.0)  # tier 2 never nulls
        out = "\n".join(cm.output)
        self.assertIn("netProfitMarginTTM", out)
        self.assertNotIn("nulled", out)


class CagrAnnualizationTest(unittest.IsolatedAsyncioTestCase):
    """FMP's five/tenYRevenueGrowthPerShare are cumulative → annualize."""

    async def test_orcl_cumulative_0_7027_annualizes_to_11_2_pct(self):
        ov = await build_company_overview(_StubFMP(), "ORCL")
        self.assertAlmostEqual(
            _stat(ov, "Growth", "Rev 5Y CAGR"), 0.11231605175948767, places=6
        )
        self.assertAlmostEqual(
            _stat(ov, "Growth", "Rev 10Y CAGR"), 0.10509621360817101, places=6
        )

    async def test_msft_cumulative_1_0168_annualizes_to_15_1_pct(self):
        ov = await build_company_overview(_StubFMP(), "MSFT")
        self.assertAlmostEqual(
            _stat(ov, "Growth", "Rev 5Y CAGR"), 0.1506216883937348, places=6
        )

    def test_annualize_edge_cases(self):
        self.assertIsNone(_annualize_cumulative(None, 5))
        self.assertIsNone(_annualize_cumulative(-1.0, 5))  # wipeout/garbage
        self.assertIsNone(_annualize_cumulative(-1.5, 5))
        self.assertAlmostEqual(_annualize_cumulative(0.0, 5), 0.0)


class FcfMarginDerivationTest(unittest.IsolatedAsyncioTestCase):
    """fcf_margin = p_s ÷ p_fcf (FMP serves no FCF-margin field) — real ORCL
    inputs with negative TTM FCF: 8.5934 / -24.4378 ≈ -0.352."""

    async def test_orcl_fcf_margin_derived(self):
        row = await _fetch_one("ORCL", _StubFMP())
        self.assertAlmostEqual(row.fcf_margin, -0.3516434573473084, places=6)
        self.assertAlmostEqual(row.p_s, 8.593381899106268)
        self.assertAlmostEqual(row.p_fcf, -24.437769904584986)


class TinyBaseDeltaSuppressionTest(unittest.IsolatedAsyncioTestCase):
    """_compute_delta must return None for growth fields whose focus value is a
    tiny-base artifact (|value| > NM_GROWTH_THRESHOLD), even when the median
    is well-defined and non-zero.

    Real payload: ORCL eps_yoy = −59.117 (a tiny-base artifact from near-zero
    prior-year EPS).  Without the guard the delta leaks the absurd number even
    though the table cell renders "n/m".
    """

    async def test_tiny_base_focus_revenue_yoy_delta_is_none(self):
        """Focus revenue_yoy = −59.117 → delta None (tiny-base artifact)."""
        focus = await _fetch_one("ORCL", _StubFMP())
        # Substitute a known tiny-base value directly.
        focus = focus.model_copy(update={"revenue_yoy": -59.117})
        med = _compute_median([focus])
        # Use a peer row with a sane value so median is well-defined.
        sane_peer = (await _fetch_one("MSFT", _StubFMP())).model_copy(
            update={"revenue_yoy": 0.15}
        )
        med = _compute_median([sane_peer])
        delta = _compute_delta(focus, med)
        self.assertIsNone(delta.revenue_yoy)

    async def test_tiny_base_focus_eps_yoy_delta_is_none(self):
        """Focus eps_yoy = −59.117 → delta None."""
        focus = (await _fetch_one("ORCL", _StubFMP())).model_copy(
            update={"eps_yoy": -59.117}
        )
        sane_peer = (await _fetch_one("MSFT", _StubFMP())).model_copy(
            update={"eps_yoy": 0.155}
        )
        med = _compute_median([sane_peer])
        delta = _compute_delta(focus, med)
        self.assertIsNone(delta.eps_yoy)

    async def test_sane_eps_yoy_delta_is_computed(self):
        """Sane focus eps_yoy (e.g. 0.155) → delta is a non-None number."""
        focus = (await _fetch_one("MSFT", _StubFMP())).model_copy(
            update={"eps_yoy": 0.155}
        )
        peer = (await _fetch_one("ORCL", _StubFMP())).model_copy(
            update={"eps_yoy": 0.05}
        )
        med = _compute_median([peer])
        delta = _compute_delta(focus, med)
        self.assertIsNotNone(delta.eps_yoy)
        # (0.155 - 0.05) / 0.05 * 100 = 210.0
        self.assertAlmostEqual(delta.eps_yoy, 210.0, places=1)

    def test_nm_growth_threshold_constant(self):
        """NM_GROWTH_THRESHOLD must equal 10.0 (mirrored frontend value)."""
        self.assertEqual(NM_GROWTH_THRESHOLD, 10.0)


if __name__ == "__main__":
    unittest.main()
