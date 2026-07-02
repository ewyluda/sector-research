"""calendar_events service: pure builders, universe derivation, catalyst
range SQL pin, and merge orchestration with partial-failure warnings."""
import os
import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

os.environ.setdefault("FMP_API_KEY", "test")
os.environ.setdefault("X_BEARER_TOKEN", "test")
os.environ.setdefault("ANTHROPIC_API_KEY", "test")
os.environ.setdefault("SEC_USER_AGENT", "test")
os.environ.setdefault("FRED_API_KEY", "test")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x/x")
os.environ.setdefault("DATABASE_URL_SYNC", "postgresql://x/x")

from backend.app.models.citation import Citation
from backend.app.services import calendar_events as ce
from backend.app.services.universe import Universe


def _cit() -> Citation:
    return Citation(
        value="2026-06-08..2026-06-22",
        metric="Economic Calendar",
        source_name="FMP /economic-calendar",
        source_url="https://example/economic-calendar",
        tier=1,
    )


class EconEventsTests(unittest.TestCase):
    def test_keeps_only_us_high_impact(self):
        rows = [
            {"country": "US", "impact": "High", "event": "CPI YoY (May)",
             "date": "2026-06-10 12:30:00", "estimate": 4.2, "previous": 3.8,
             "actual": None, "unit": "%"},
            {"country": "US", "impact": "Medium", "event": "CFTC Nasdaq",
             "date": "2026-06-12 19:30:00"},
            {"country": "DE", "impact": "High", "event": "German CPI",
             "date": "2026-06-10 06:00:00"},
        ]
        events = ce._econ_events(rows, _cit())
        self.assertEqual(len(events), 1)
        ev = events[0]
        self.assertEqual(ev.kind, "economic")
        self.assertEqual(ev.title, "CPI YoY (May)")
        self.assertEqual(ev.date, date(2026, 6, 10))
        self.assertEqual(
            ev.timestamp, datetime(2026, 6, 10, 12, 30, tzinfo=timezone.utc)
        )
        self.assertIsNone(ev.ticker)
        self.assertEqual(ev.detail["estimate"], 4.2)
        self.assertEqual(ev.detail["previous"], 3.8)
        self.assertIsNone(ev.detail["actual"])
        self.assertEqual(ev.citation.source_name, "FMP /economic-calendar")
        self.assertIsInstance(ev.citation.value, str)

    def test_unparseable_date_row_is_skipped(self):
        rows = [{"country": "US", "impact": "High", "event": "X", "date": "junk"}]
        self.assertEqual(ce._econ_events(rows, _cit()), [])

    def test_date_only_string_parses_with_null_timestamp(self):
        rows = [{"country": "US", "impact": "High", "event": "X",
                 "date": "2026-06-10"}]
        events = ce._econ_events(rows, _cit())
        self.assertEqual(events[0].date, date(2026, 6, 10))
        self.assertIsNone(events[0].timestamp)

    def test_non_string_date_value_is_handled(self):
        # Drivers may hand back datetime objects; str() renders them
        # parseable ("YYYY-MM-DD HH:MM:SS") instead of raising TypeError.
        rows = [{"country": "US", "impact": "High", "event": "X",
                 "date": datetime(2026, 6, 10, 12, 30)}]
        events = ce._econ_events(rows, _cit())
        self.assertEqual(events[0].date, date(2026, 6, 10))


class EarningsEventsTests(unittest.TestCase):
    def _universe(self):
        return Universe(
            tickers={"NVDA", "ASML"},
            thesis_runs={"NVDA": "run-nvda-1"},
        )

    def test_filters_firehose_to_universe_and_flags_thesis(self):
        rows = [
            {"symbol": "NVDA", "date": "2026-06-10", "epsEstimated": 1.62,
             "epsActual": None, "revenueEstimated": 6.2e10, "revenueActual": None},
            {"symbol": "ASML", "date": "2026-06-09", "epsEstimated": 4.21,
             "epsActual": None, "revenueEstimated": None, "revenueActual": None},
            {"symbol": "3988.T", "date": "2026-06-12"},
        ]
        events = ce._earnings_events(rows, self._universe(), _cit())
        self.assertEqual({e.ticker for e in events}, {"NVDA", "ASML"})
        nvda = next(e for e in events if e.ticker == "NVDA")
        self.assertEqual(nvda.kind, "earnings")
        self.assertEqual(nvda.date, date(2026, 6, 10))
        self.assertTrue(nvda.detail["has_thesis"])
        self.assertEqual(nvda.detail["run_id"], "run-nvda-1")
        asml = next(e for e in events if e.ticker == "ASML")
        self.assertFalse(asml.detail["has_thesis"])
        self.assertIsNone(asml.detail["run_id"])

    def test_lowercase_symbol_matches_universe(self):
        rows = [{"symbol": "nvda", "date": "2026-06-10"}]
        events = ce._earnings_events(rows, self._universe(), _cit())
        self.assertEqual(events[0].ticker, "NVDA")

    def test_bad_date_row_is_skipped(self):
        rows = [{"symbol": "NVDA", "date": "not-a-date"}]
        self.assertEqual(ce._earnings_events(rows, self._universe(), _cit()), [])


class _Result:
    """Mimics the two access patterns the service uses on db.execute results."""

    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)

    def mappings(self):
        return SimpleNamespace(all=lambda: self._rows)


class CitationOutTests(unittest.TestCase):
    def test_float_value_coerced_to_str(self):
        cit = Citation(
            value=4.2,
            metric="Economic Calendar",
            source_name="FMP /economic-calendar",
            source_url="https://example/economic-calendar",
            tier=1,
        )
        self.assertEqual(ce._citation_out(cit).value, "4.2")


class CatalystRangeSqlTests(unittest.TestCase):
    def test_sql_pins_latest_thesis_cte_and_range_overlap(self):
        sql = ce.CATALYST_RANGE_SQL
        # Same latest-run semantics as the List view (api/catalysts.py)
        self.assertIn(
            "jsonb_typeof(state->'phase_outputs'->'thesis'->'structured') = 'object'",
            sql,
        )
        # Windowed rows: overlap test; dated rows: BETWEEN
        self.assertIn("c.expected_window_end >= :start_date", sql)
        self.assertIn("BETWEEN :start_date AND :end_date", sql)

    def test_latest_cte_identical_to_list_view(self):
        # The "kept in sync by the pin test" comment in calendar_events.py
        # is enforced here: the latest-run CTE must stay character-identical
        # (modulo whitespace) to the List view's run_id-less branch.
        from backend.app.api.catalysts import _build_list_catalysts_sql

        def _cte(sql: str) -> str:
            normalized = " ".join(sql.split())
            start = normalized.index("WITH latest AS (")
            end = normalized.index(")", normalized.index("ORDER BY ticker, created_at DESC"))
            return normalized[start:end + 1]

        list_sql, _ = _build_list_catalysts_sql(ticker=None, run_id=None)
        self.assertEqual(_cte(ce.CATALYST_RANGE_SQL), _cte(list_sql))


class CatalystEventsTests(unittest.TestCase):
    def _row(self, **overrides):
        base = {
            "id": "cat-1", "run_id": "run-1", "ticker": "NVDA",
            "ordinal": 1, "timeframe": "Q3 2026", "description": "Rubin volume ship",
            "type": "product", "linked_pillar": None,
            "expected_date": date(2026, 8, 15),
            "expected_window_start": None, "expected_window_end": None,
        }
        base.update(overrides)
        return base

    def test_dated_row_maps_to_event(self):
        events = ce._catalyst_events([self._row()])
        ev = events[0]
        self.assertEqual(ev.kind, "catalyst")
        self.assertEqual(ev.date, date(2026, 8, 15))
        self.assertEqual(ev.ticker, "NVDA")
        self.assertEqual(ev.title, "Rubin volume ship")
        self.assertEqual(ev.detail["run_id"], "run-1")
        self.assertEqual(ev.detail["catalyst_id"], "cat-1")
        self.assertFalse(ev.detail["windowed"])
        self.assertIsNone(ev.citation)  # catalysts cite via their run

    def test_windowed_row_flagged_and_carries_window(self):
        events = ce._catalyst_events([self._row(
            expected_window_start=date(2026, 7, 1),
            expected_window_end=date(2026, 9, 30),
        )])
        ev = events[0]
        self.assertTrue(ev.detail["windowed"])
        self.assertEqual(ev.detail["window_start"], "2026-07-01")
        self.assertEqual(ev.detail["window_end"], "2026-09-30")

    def test_windowed_row_without_midpoint_uses_window_end_as_date(self):
        events = ce._catalyst_events([self._row(
            expected_date=None,
            expected_window_start=date(2026, 7, 1),
            expected_window_end=date(2026, 9, 30),
        )])
        self.assertEqual(events[0].date, date(2026, 9, 30))


class GetCalendarEventsTests(unittest.IsolatedAsyncioTestCase):
    def _db(self):
        db = AsyncMock()
        db.execute.side_effect = [
            # select(Theme) rows → Theme-shaped objects
            _Result([SimpleNamespace(id="t1", seed_tickers=["NVDA"])]),
            _Result([{"ticker": "NVDA", "id": "run-1"}]),         # latest runs
            _Result([]),                                          # catalysts
        ]
        return db

    async def test_partial_failure_warns_and_returns_other_sources(self):
        fmp = AsyncMock()
        fmp.get_economic_calendar.side_effect = RuntimeError("FMP down")
        fmp.get_earnings_calendar_range.return_value = (
            [{"symbol": "NVDA", "date": "2026-06-10", "epsEstimated": 1.0}],
            _cit(),
        )

        resp = await ce.get_calendar_events(
            self._db(), fmp, date(2026, 6, 8), date(2026, 6, 22)
        )

        self.assertEqual(len(resp.warnings), 1)
        self.assertIn("Economic calendar unavailable", resp.warnings[0])
        self.assertEqual([e.kind for e in resp.events], ["earnings"])
        self.assertEqual(resp.universe_size, 1)

    async def test_earnings_failure_warns_and_returns_other_sources(self):
        fmp = AsyncMock()
        fmp.get_economic_calendar.return_value = (
            [{"country": "US", "impact": "High", "event": "CPI",
              "date": "2026-06-10 12:30:00"}],
            _cit(),
        )
        fmp.get_earnings_calendar_range.side_effect = RuntimeError("FMP down")

        resp = await ce.get_calendar_events(
            self._db(), fmp, date(2026, 6, 8), date(2026, 6, 22)
        )

        self.assertEqual(len(resp.warnings), 1)
        self.assertIn("Earnings calendar unavailable", resp.warnings[0])
        self.assertEqual([e.kind for e in resp.events], ["economic"])

    async def test_events_sorted_by_date_then_kind(self):
        fmp = AsyncMock()
        fmp.get_economic_calendar.return_value = (
            [{"country": "US", "impact": "High", "event": "CPI",
              "date": "2026-06-10 12:30:00"}],
            _cit(),
        )
        fmp.get_earnings_calendar_range.return_value = (
            [{"symbol": "NVDA", "date": "2026-06-09"},
             {"symbol": "NVDA", "date": "2026-06-10"}],
            _cit(),
        )

        resp = await ce.get_calendar_events(
            self._db(), fmp, date(2026, 6, 8), date(2026, 6, 22)
        )

        self.assertEqual(
            [(e.date.isoformat(), e.kind) for e in resp.events],
            [("2026-06-09", "earnings"),
             ("2026-06-10", "economic"),
             ("2026-06-10", "earnings")],
        )


    async def test_catalyst_rows_merged_and_params_are_date_objects(self):
        db = AsyncMock()
        db.execute.side_effect = [
            _Result([SimpleNamespace(id="t1", seed_tickers=["NVDA"])]),
            _Result([{"ticker": "NVDA", "id": "run-1"}]),
            _Result([{
                "id": "cat-1", "run_id": "run-1", "ticker": "NVDA",
                "ordinal": 1, "timeframe": "June 2026",
                "description": "Rubin launch", "type": "product",
                "linked_pillar": None,
                "expected_date": date(2026, 6, 10),
                "expected_window_start": None, "expected_window_end": None,
            }]),
        ]
        fmp = AsyncMock()
        fmp.get_economic_calendar.return_value = ([], _cit())
        fmp.get_earnings_calendar_range.return_value = (
            [{"symbol": "NVDA", "date": "2026-06-10"}], _cit()
        )

        resp = await ce.get_calendar_events(
            db, fmp, date(2026, 6, 8), date(2026, 6, 22)
        )

        self.assertEqual(
            [e.kind for e in resp.events], ["earnings", "catalyst"]
        )
        catalyst_params = db.execute.call_args_list[2].args[1]
        self.assertEqual(catalyst_params["start_date"], date(2026, 6, 8))
        self.assertEqual(catalyst_params["end_date"], date(2026, 6, 22))


class LatestRunsSqlContractTests(unittest.TestCase):
    def test_status_board_sql_emits_columns_and_archive_filter(self):
        # resolve_universe reads r["ticker"] / r["id"] off this SQL and relies
        # on include_archived=False excluding archived runs. Pin the contract.
        from backend.app.services.universe import latest_runs_sql

        sql, params = latest_runs_sql(theme_id=None, include_archived=False)
        self.assertIn("r.id", sql)
        self.assertIn("r.ticker", sql)
        self.assertIn("archived_at IS NULL", sql)
        self.assertEqual(params, {})


if __name__ == "__main__":
    unittest.main()
