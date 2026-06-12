"""Pin add_citation dedupe on (source_url, metric).

Risk-loop re-runs send node_deep_dive back through the same FMP/FRED/
transcript fetches, so every citation is offered to the state a second
time. add_citation must treat (source_url, metric) as the identity key:
a duplicate replaces the existing entry in place (latest fetch wins)
instead of appending a second chip.
"""

import unittest

from backend.app.graph.state import ResearchState, StateCitation


def _make_state() -> ResearchState:
    return ResearchState(ticker="NVDA", theme_id="t1", run_id="r1")


def _citation(metric: str = "income_statement",
              source_url: str = "https://fmp.example/income/NVDA",
              value: str = "100",
              retrieved_at: str = "2026-06-11T00:00:00+00:00") -> StateCitation:
    return StateCitation(
        value=value,
        metric=metric,
        source_name="FMP",
        source_url=source_url,
        tier=1,
        retrieved_at=retrieved_at,
    )


class TestAddCitationDedupe(unittest.TestCase):
    def test_distinct_citations_append(self):
        state = _make_state()
        state.add_citation(_citation(metric="income_statement"))
        state.add_citation(_citation(metric="balance_sheet",
                                     source_url="https://fmp.example/balance/NVDA"))
        self.assertEqual(len(state.citations), 2)

    def test_same_metric_different_url_appends(self):
        state = _make_state()
        state.add_citation(_citation(source_url="https://fmp.example/income/NVDA"))
        state.add_citation(_citation(source_url="https://fmp.example/income/NVDA?period=annual"))
        self.assertEqual(len(state.citations), 2)

    def test_duplicate_key_does_not_append(self):
        state = _make_state()
        state.add_citation(_citation())
        state.add_citation(_citation(retrieved_at="2026-06-11T01:00:00+00:00"))
        self.assertEqual(len(state.citations), 1)

    def test_duplicate_key_replaces_with_latest(self):
        state = _make_state()
        state.add_citation(_citation(value="100"))
        state.add_citation(_citation(value="110",
                                     retrieved_at="2026-06-11T01:00:00+00:00"))
        self.assertEqual(state.citations[0]["value"], "110")
        self.assertEqual(state.citations[0]["retrieved_at"],
                         "2026-06-11T01:00:00+00:00")

    def test_duplicate_replacement_preserves_position(self):
        state = _make_state()
        state.add_citation(_citation(metric="income_statement"))
        state.add_citation(_citation(metric="balance_sheet",
                                     source_url="https://fmp.example/balance/NVDA"))
        state.add_citation(_citation(metric="income_statement", value="120"))
        self.assertEqual(len(state.citations), 2)
        self.assertEqual(state.citations[0]["metric"], "income_statement")
        self.assertEqual(state.citations[0]["value"], "120")
        self.assertEqual(state.citations[1]["metric"], "balance_sheet")

    def test_dict_form_citations_dedupe_too(self):
        state = _make_state()
        state.add_citation(_citation())
        state.add_citation(_citation(value="115").to_dict())
        self.assertEqual(len(state.citations), 1)
        self.assertEqual(state.citations[0]["value"], "115")


if __name__ == "__main__":
    unittest.main()
