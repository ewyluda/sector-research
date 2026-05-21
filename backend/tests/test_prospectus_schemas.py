"""Schema round-trip tests for prospectus pipeline outputs."""
import unittest
from pydantic import ValidationError

from backend.app.models.prospectus_schemas import (
    ProspectusFinancials,
    AnnualFinancialRow,
    ProspectusCategoryResult,
    ProspectusThesisOutput,
    PostIPOPlanItem,
    IPOVerdict,
)


class TestProspectusFinancials(unittest.TestCase):
    def test_valid_round_trip(self):
        f = ProspectusFinancials(
            annual=[
                AnnualFinancialRow(
                    period_label="FY2024",
                    revenue=14_000_000_000.0,
                    operating_income=2_000_000_000.0,
                    net_income=1_500_000_000.0,
                    cash_and_equivalents=4_000_000_000.0,
                    source_snippet="Revenues for the year ended December 31, 2024 were $14.0 billion",
                )
            ],
            interim=[],
        )
        d = f.model_dump()
        f2 = ProspectusFinancials.model_validate(d)
        self.assertEqual(f, f2)

    def test_missing_period_label_rejected(self):
        with self.assertRaises(ValidationError):
            AnnualFinancialRow(revenue=1.0, source_snippet="x")  # type: ignore[call-arg]


class TestCategoryResult(unittest.TestCase):
    def test_score_bounds(self):
        with self.assertRaises(ValidationError):
            ProspectusCategoryResult(
                category="Business Quality", content="x", score=150, key_findings=[]
            )


class TestThesisOutput(unittest.TestCase):
    def test_verdict_enum(self):
        with self.assertRaises(ValidationError):
            ProspectusThesisOutput(
                thesis_statement="x",
                key_risks=[],
                ipo_verdict="buy",  # type: ignore[arg-type]
                price_range_commentary=None,
                post_ipo_research_plan=[],
            )

    def test_verdict_string_accepted(self):
        out = ProspectusThesisOutput(
            thesis_statement="x",
            key_risks=[],
            ipo_verdict="participate",  # string form, not enum member
            price_range_commentary=None,
            post_ipo_research_plan=[],
        )
        self.assertEqual(out.ipo_verdict, IPOVerdict.PARTICIPATE)

    def test_post_ipo_plan_shape(self):
        out = ProspectusThesisOutput(
            thesis_statement="x",
            key_risks=[],
            ipo_verdict=IPOVerdict.WATCH_POST_LOCKUP,
            price_range_commentary=None,
            post_ipo_research_plan=[
                PostIPOPlanItem(
                    question="What's gross margin trajectory once Starlink subscriber growth normalises?",
                    why_it_matters="Bear thesis on launch unit economics",
                    expected_data_source="FMP quarterly + transcript",
                )
            ],
        )
        self.assertEqual(len(out.post_ipo_research_plan), 1)
