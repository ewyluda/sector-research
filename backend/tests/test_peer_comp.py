import unittest
from unittest.mock import AsyncMock, MagicMock
from backend.app.services.peer_comp import build_peer_comp_table


class TestPeerComp(unittest.IsolatedAsyncioTestCase):
    async def test_builds_table_and_median(self):
        # Mock FMP returning known metrics for 3 peers + focus
        fmp = AsyncMock()

        async def km(ticker):
            data = {
                "NVDA": {
                    "peRatioTTM": 30.0,
                    "enterpriseValueOverEBITDATTM": 25.0,
                    "priceToBookRatioTTM": 12.0,
                    "priceToFreeCashFlowsRatioTTM": 28.0,
                    "priceToSalesRatioTTM": 20.0,
                    "roeTTM": 0.5,
                },
                "AMD": {
                    "peRatioTTM": 40.0,
                    "enterpriseValueOverEBITDATTM": 28.0,
                    "priceToBookRatioTTM": 5.0,
                    "priceToFreeCashFlowsRatioTTM": 35.0,
                    "priceToSalesRatioTTM": 8.0,
                    "roeTTM": 0.2,
                },
                "INTC": {
                    "peRatioTTM": 18.0,
                    "enterpriseValueOverEBITDATTM": 10.0,
                    "priceToBookRatioTTM": 1.5,
                    "priceToFreeCashFlowsRatioTTM": 15.0,
                    "priceToSalesRatioTTM": 2.5,
                    "roeTTM": 0.05,
                },
                "MU": {
                    "peRatioTTM": 22.0,
                    "enterpriseValueOverEBITDATTM": 12.0,
                    "priceToBookRatioTTM": 2.0,
                    "priceToFreeCashFlowsRatioTTM": 18.0,
                    "priceToSalesRatioTTM": 3.0,
                    "roeTTM": 0.1,
                },
            }
            return data[ticker], MagicMock()

        async def fg(ticker):
            data = {
                "NVDA": [
                    {
                        "revenueGrowth": 0.6,
                        "epsGrowth": 0.8,
                    }
                ],
                "AMD": [
                    {
                        "revenueGrowth": 0.2,
                        "epsGrowth": 0.3,
                    }
                ],
                "INTC": [
                    {
                        "revenueGrowth": -0.1,
                        "epsGrowth": -0.2,
                    }
                ],
                "MU": [
                    {
                        "revenueGrowth": 0.3,
                        "epsGrowth": 0.4,
                    }
                ],
            }
            return data[ticker], MagicMock()

        fmp.get_key_metrics_ttm = km
        fmp.get_financial_growth = fg

        table, errors = await build_peer_comp_table(
            focus_ticker="NVDA", peer_tickers=["AMD", "INTC", "MU"], fmp=fmp
        )

        self.assertEqual(table.focus_ticker, "NVDA")
        self.assertEqual(len(table.rows), 4)  # focus + 3 peers
        # Median PE of peers (AMD, INTC, MU) = 22.0 (sorted: 18, 22, 40)
        self.assertEqual(table.median.pe, 22.0)
        self.assertEqual(errors, [])

    async def test_per_peer_failure_recorded(self):
        fmp = AsyncMock()

        async def km(ticker):
            if ticker == "BADCO":
                raise RuntimeError("FMP 404")
            return {
                "peRatioTTM": 20.0,
                "enterpriseValueOverEBITDATTM": 12.0,
                "priceToBookRatioTTM": 2.0,
                "priceToFreeCashFlowsRatioTTM": 15.0,
                "priceToSalesRatioTTM": 2.5,
                "roeTTM": 0.1,
            }, MagicMock()

        async def fg(ticker):
            return [
                {
                    "revenueGrowth": 0.1,
                    "epsGrowth": 0.1,
                }
            ], MagicMock()

        fmp.get_key_metrics_ttm = km
        fmp.get_financial_growth = fg

        table, errors = await build_peer_comp_table(
            focus_ticker="X", peer_tickers=["GOOD", "BADCO"], fmp=fmp
        )
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].peer_ticker, "BADCO")
        # Focus + 1 successful peer = 2 rows
        self.assertEqual(len(table.rows), 2)

    async def test_zero_peers_returns_none(self):
        fmp = AsyncMock()
        table, errors = await build_peer_comp_table(
            focus_ticker="X", peer_tickers=[], fmp=fmp
        )
        self.assertIsNone(table)
        self.assertEqual(errors, [])
