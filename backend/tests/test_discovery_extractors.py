"""The _extract_* FMP helpers: happy path, None on bad data, and (new) logged tracebacks."""
import unittest

from backend.app.services.discovery import (
    _extract_gross_margin,
    _extract_revenue_growth,
    _extract_roic,
)


class TestExtractHelpersHappyPath(unittest.TestCase):
    def test_gross_margin(self):
        income = [{"revenue": 200.0, "grossProfit": 120.0}]
        self.assertEqual(_extract_gross_margin(income), 0.6)

    def test_revenue_growth(self):
        income = [{"revenue": 110.0}, {"revenue": 100.0}]
        self.assertEqual(_extract_revenue_growth(income), 0.1)

    def test_roic(self):
        balance = [{"totalEquity": 800.0, "longTermDebt": 200.0}]
        cashflow = [{"operatingCashFlow": 100.0}]
        self.assertEqual(_extract_roic(balance, cashflow), 0.1)


class TestExtractHelpersFailuresAreLogged(unittest.TestCase):
    def test_gross_margin_bad_data_returns_none_and_logs(self):
        # revenue is a truthy string -> division raises TypeError
        income = [{"revenue": "N/A", "grossProfit": 5.0}]
        with self.assertLogs("backend.app.services.discovery", level="WARNING"):
            self.assertIsNone(_extract_gross_margin(income))

    def test_revenue_growth_bad_data_returns_none_and_logs(self):
        income = [{"revenue": "N/A"}, {"revenue": "N/A"}]
        with self.assertLogs("backend.app.services.discovery", level="WARNING"):
            self.assertIsNone(_extract_revenue_growth(income))

    def test_roic_bad_data_returns_none_and_logs(self):
        balance = [{"totalEquity": "N/A", "longTermDebt": 1.0}]
        cashflow = [{"operatingCashFlow": 1.0}]
        with self.assertLogs("backend.app.services.discovery", level="WARNING"):
            self.assertIsNone(_extract_roic(balance, cashflow))

    def test_empty_input_still_returns_none_without_exception_noise(self):
        # Guarded early-return paths (no data) are NOT exceptions -> nothing logged.
        with self.assertNoLogs("backend.app.services.discovery"):
            self.assertIsNone(_extract_gross_margin([]))
            self.assertIsNone(_extract_revenue_growth([{"revenue": 1.0}]))
            self.assertIsNone(_extract_roic([], []))


if __name__ == "__main__":
    unittest.main()
