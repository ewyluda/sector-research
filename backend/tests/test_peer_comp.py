import unittest
from unittest.mock import AsyncMock, MagicMock

from backend.app.services.peer_comp import build_peer_comp_table

# Per-ticker fake payloads for the four endpoints _fetch_one now hits.
KM = {
    "NVDA": {"returnOnEquityTTM": 0.5, "returnOnInvestedCapitalTTM": 0.4,
             "returnOnAssetsTTM": 0.3},
    "AMD":  {"returnOnEquityTTM": 0.2, "returnOnInvestedCapitalTTM": 0.15,
             "returnOnAssetsTTM": 0.1},
    "INTC": {"returnOnEquityTTM": 0.05, "returnOnInvestedCapitalTTM": 0.04,
             "returnOnAssetsTTM": 0.03},
    "MU":   {"returnOnEquityTTM": 0.1, "returnOnInvestedCapitalTTM": 0.08,
             "returnOnAssetsTTM": 0.06},
}
RATIOS = {
    "NVDA": {"priceToEarningsRatioTTM": 30.0, "enterpriseValueMultipleTTM": 25.0,
             "priceToBookRatioTTM": 12.0, "priceToFreeCashFlowRatioTTM": 28.0,
             "priceToSalesRatioTTM": 20.0, "priceToEarningsGrowthRatioTTM": 1.1,
             "grossProfitMarginTTM": 0.75, "operatingProfitMarginTTM": 0.60,
             "ebitdaMarginTTM": 0.62},
    "AMD":  {"priceToEarningsRatioTTM": 40.0, "enterpriseValueMultipleTTM": 28.0,
             "priceToBookRatioTTM": 5.0, "priceToFreeCashFlowRatioTTM": 35.0,
             "priceToSalesRatioTTM": 8.0, "priceToEarningsGrowthRatioTTM": 1.5,
             "grossProfitMarginTTM": 0.50, "operatingProfitMarginTTM": 0.20,
             "ebitdaMarginTTM": 0.25},
    "INTC": {"priceToEarningsRatioTTM": 18.0, "enterpriseValueMultipleTTM": 10.0,
             "priceToBookRatioTTM": 1.5, "priceToFreeCashFlowRatioTTM": 15.0,
             "priceToSalesRatioTTM": 2.5, "priceToEarningsGrowthRatioTTM": 2.0,
             "grossProfitMarginTTM": 0.40, "operatingProfitMarginTTM": 0.05,
             "ebitdaMarginTTM": 0.15},
    "MU":   {"priceToEarningsRatioTTM": 22.0, "enterpriseValueMultipleTTM": 12.0,
             "priceToBookRatioTTM": 2.0, "priceToFreeCashFlowRatioTTM": 18.0,
             "priceToSalesRatioTTM": 3.0, "priceToEarningsGrowthRatioTTM": 1.8,
             "grossProfitMarginTTM": 0.35, "operatingProfitMarginTTM": 0.18,
             "ebitdaMarginTTM": 0.40},
}
GROWTH = {
    "NVDA": [{"revenueGrowth": 0.6, "epsGrowth": 0.8}],
    "AMD":  [{"revenueGrowth": 0.2, "epsGrowth": 0.3}],
    "INTC": [{"revenueGrowth": -0.1, "epsGrowth": -0.2}],
    "MU":   [{"revenueGrowth": 0.3, "epsGrowth": 0.4}],
}
PROFILE = {
    "NVDA": {"marketCap": 2.5e12},
    "AMD":  {"marketCap": 3.0e11},
    "INTC": {"marketCap": 1.5e11},
    "MU":   {"marketCap": 1.2e11},
}


def make_fake_fmp(fail: set[str] | None = None) -> AsyncMock:
    """Fake FMP client serving the four endpoints from the dicts above.
    Tickers in `fail` raise on key-metrics (simulating an FMP error)."""
    fail = fail or set()
    fmp = AsyncMock()

    async def km(ticker):
        if ticker in fail:
            raise RuntimeError("FMP 404")
        return KM.get(ticker, {}), MagicMock()

    async def ratios(ticker):
        return RATIOS.get(ticker, {}), MagicMock()

    async def fg(ticker):
        return GROWTH.get(ticker, []), MagicMock()

    async def profile(ticker):
        return PROFILE.get(ticker, {}), MagicMock()

    fmp.get_key_metrics_ttm = km
    fmp.get_ratios_ttm = ratios
    fmp.get_financial_growth = fg
    fmp.get_company_profile = profile
    return fmp


class TestPeerComp(unittest.IsolatedAsyncioTestCase):
    async def test_builds_table_and_median(self):
        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD", "INTC", "MU"],
            fmp=make_fake_fmp(),
        )
        self.assertEqual(table.focus_ticker, "NVDA")
        self.assertEqual(len(table.rows), 4)
        # Median PE of peers (AMD, INTC, MU) = 22.0 (sorted: 18, 22, 40)
        self.assertEqual(table.median.pe, 22.0)
        self.assertEqual(errors, [])

    async def test_new_fields_mapped(self):
        table, _ = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD"], fmp=make_fake_fmp(),
        )
        focus = next(r for r in table.rows if r.ticker == "NVDA")
        self.assertEqual(focus.peg, 1.1)
        self.assertEqual(focus.gross_margin, 0.75)
        self.assertEqual(focus.operating_margin, 0.60)
        self.assertEqual(focus.ebitda_margin, 0.62)
        # fcf_margin: freeCashFlowMarginTTM absent from FMP live API — degrades to None
        self.assertIsNone(focus.fcf_margin)
        self.assertEqual(focus.roic, 0.4)
        self.assertEqual(focus.roa, 0.3)
        self.assertEqual(focus.market_cap, 2.5e12)

    async def test_median_over_new_fields(self):
        table, _ = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD", "INTC", "MU"],
            fmp=make_fake_fmp(),
        )
        # Median gross margin of peers (0.50, 0.40, 0.35) = 0.40
        self.assertEqual(table.median.gross_margin, 0.40)
        # Median market cap of peers (3.0e11, 1.5e11, 1.2e11) = 1.5e11
        self.assertEqual(table.median.market_cap, 1.5e11)

    async def test_missing_wire_fields_become_none(self):
        """A ticker absent from the fake payload dicts maps to all-None metrics."""
        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["ZZZQ"], fmp=make_fake_fmp(),
        )
        self.assertEqual(errors, [])
        zzzq = next(r for r in table.rows if r.ticker == "ZZZQ")
        self.assertIsNone(zzzq.pe)
        self.assertIsNone(zzzq.gross_margin)
        self.assertIsNone(zzzq.market_cap)

    async def test_per_peer_failure_recorded(self):
        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD", "BADCO"],
            fmp=make_fake_fmp(fail={"BADCO"}),
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].peer_ticker, "BADCO")
        self.assertEqual(len(table.rows), 2)  # focus + AMD

    async def test_all_peers_fail_returns_none(self):
        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["BAD1", "BAD2"],
            fmp=make_fake_fmp(fail={"BAD1", "BAD2"}),
        )
        self.assertIsNone(table)
        self.assertEqual({e.peer_ticker for e in errors}, {"BAD1", "BAD2"})

    async def test_focus_failure_raises(self):
        with self.assertRaises(RuntimeError):
            await build_peer_comp_table(
                focus_ticker="BADCO", peer_tickers=["AMD"],
                fmp=make_fake_fmp(fail={"BADCO"}),
            )

    async def test_zero_peers_returns_none(self):
        table, errors = await build_peer_comp_table(
            focus_ticker="X", peer_tickers=[], fmp=AsyncMock(),
        )
        self.assertIsNone(table)
        self.assertEqual(errors, [])

    async def test_fetch_concurrency_capped(self):
        """No more than FETCH_CONCURRENCY tickers are in flight at once —
        a full 13-ticker compare must not burst 50+ FMP calls."""
        import asyncio

        from backend.app.services.peer_comp import FETCH_CONCURRENCY

        active = 0
        peak = 0

        fmp = AsyncMock()

        async def km(ticker):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return {}, MagicMock()

        async def empty(ticker):
            return {}, MagicMock()

        async def empty_list(ticker):
            return [], MagicMock()

        fmp.get_key_metrics_ttm = km
        fmp.get_ratios_ttm = empty
        fmp.get_financial_growth = empty_list
        fmp.get_company_profile = empty

        await build_peer_comp_table(
            focus_ticker="T0",
            peer_tickers=[f"T{i}" for i in range(1, 13)],
            fmp=fmp,
        )
        self.assertLessEqual(peak, FETCH_CONCURRENCY)


if __name__ == "__main__":
    unittest.main()
