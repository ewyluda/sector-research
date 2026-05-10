import unittest

from backend.app.models.workspace_schemas import (
    UpdateRefreshOutput,
    ResearchOutput,
    ValidationOutput,
    ChallengeOutput,
    DifferentiationOutput,
    ChangedCell,
    KillCriterionWrite,
    PeerCompTable,
    WorkspaceVerdict,
    PeerCompRow,
)


class TestWorkspaceSchemas(unittest.TestCase):
    def test_update_refresh_round_trip(self):
        """Test UpdateRefreshOutput serialization and deserialization."""
        out = UpdateRefreshOutput(
            version_before=3,
            version_after=4,
            changed_cells=[
                ChangedCell(
                    cell_path="income_statement.revenue.2026Q1",
                    prior_value=100.0,
                    new_value=110.0,
                    source="historical",
                    citation_id="c1",
                )
            ],
            new_filings=[],
            consensus_delta=None,
            summary="loaded latest 10-Q",
        )
        round_tripped = UpdateRefreshOutput.model_validate(out.model_dump())
        self.assertEqual(round_tripped.version_after, 4)
        self.assertEqual(round_tripped.changed_cells[0].new_value, 110.0)

    def test_update_refresh_removed_cells_warning(self):
        """removed_cells defaults to [] and accepts cell-path strings when populated."""
        out_default = UpdateRefreshOutput(version_before=1, summary="x")
        self.assertEqual(out_default.removed_cells, [])

        out_with_removed = UpdateRefreshOutput(
            version_before=1,
            summary="x",
            removed_cells=["income_statement.interest_income.2026Q1"],
        )
        round_tripped = UpdateRefreshOutput.model_validate(out_with_removed.model_dump())
        self.assertEqual(
            round_tripped.removed_cells,
            ["income_statement.interest_income.2026Q1"],
        )

    def test_challenge_writeback_shape(self):
        """Test ChallengeOutput with kill criterion and verdict."""
        out = ChallengeOutput(
            stress_test_summary="thesis intact",
            kill_criterion_writes=[
                KillCriterionWrite(ordinal=1, status="armed", note=None)
            ],
            catalyst_updates=[],
            proposed_verdict=WorkspaceVerdict.HEALTHY,
        )
        self.assertEqual(out.proposed_verdict, WorkspaceVerdict.HEALTHY)

    def test_verdict_enum_string_serialization(self):
        """Test WorkspaceVerdict enum serializes to string value."""
        out = ChallengeOutput(
            stress_test_summary="x",
            kill_criterion_writes=[],
            catalyst_updates=[],
            proposed_verdict=WorkspaceVerdict.TRIGGERED,
        )
        dumped = out.model_dump(mode="json")
        self.assertEqual(dumped["proposed_verdict"], "triggered")

    def test_research_output_highlights(self):
        """Test ResearchOutput with highlights and open questions."""
        out = ResearchOutput(
            highlights=[],
            new_open_questions=[],
            summary="Research findings indicate stable thesis.",
        )
        self.assertEqual(out.summary, "Research findings indicate stable thesis.")

    def test_validation_output_full_payload(self):
        """Test ValidationOutput with multiple sensitivity grids."""
        out = ValidationOutput(
            implied_drivers=[],
            implied_irr=0.12,
            sensitivity_grids=[],
            thesis_vs_priced_in=[],
            current_price=150.0,
            citation_ids=[],
        )
        self.assertEqual(out.current_price, 150.0)
        self.assertEqual(out.implied_irr, 0.12)

    def test_differentiation_output_peer_comp(self):
        """Test DifferentiationOutput with peer comparison table."""
        peer_row = PeerCompRow(ticker="AAPL", pe=25.0, roe=0.42)
        median_row = PeerCompRow(ticker="MEDIAN", pe=24.0, roe=0.40)
        delta_row = PeerCompRow(ticker="DELTA", pe=1.0, roe=2.0)

        peer_comp = PeerCompTable(
            focus_ticker="MSFT",
            rows=[peer_row],
            median=median_row,
            delta_vs_median_pct=delta_row,
        )

        out = DifferentiationOutput(
            peer_comp=peer_comp,
            read_throughs=[],
            per_peer_errors=[],
        )

        self.assertEqual(out.peer_comp.focus_ticker, "MSFT")
        self.assertEqual(out.peer_comp.rows[0].ticker, "AAPL")


if __name__ == "__main__":
    unittest.main()
