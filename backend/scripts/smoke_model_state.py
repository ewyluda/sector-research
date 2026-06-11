"""Smoke test for model_state Pydantic schemas."""
import sys
from backend.app.models.model_state import (
    ModelState, ModelCell, Period, ModelAssumptions,
    DRIVER_KEYS, LINE_ITEMS_PNL, LINE_ITEMS_BS, LINE_ITEMS_CF,
)


def test_modelcell_roundtrip():
    cell = ModelCell(value=1.5, source="driver", formula=None, citation_id=None)
    raw = cell.model_dump_json()
    back = ModelCell.model_validate_json(raw)
    assert back == cell, f"roundtrip mismatch: {back} != {cell}"


def test_modelstate_minimal():
    state = ModelState(
        periods=[Period(label="2026Q1", kind="Q", is_historical=False, quarter_index=1)],
        drivers={"2026Q1": {k: ModelCell(value=0.0, source="driver") for k in DRIVER_KEYS}},
        income_statement={li: {"2026Q1": ModelCell(value=0.0, source="computed")} for li in LINE_ITEMS_PNL},
        balance_sheet={li: {"2026Q1": ModelCell(value=0.0, source="computed")} for li in LINE_ITEMS_BS},
        cash_flow={li: {"2026Q1": ModelCell(value=0.0, source="computed")} for li in LINE_ITEMS_CF},
        assumptions=ModelAssumptions(
            discount_rate=ModelCell(value=0.10, source="driver"),
            terminal_method="exit_multiple",
            terminal_multiple=ModelCell(value=12.0, source="driver"),
            perpetuity_growth=ModelCell(value=0.025, source="driver"),
            tax_rate=ModelCell(value=0.21, source="driver"),
            plug_priority=["debt_paydown", "buyback", "dividend", "cash"],
        ),
    )
    raw = state.model_dump_json()
    back = ModelState.model_validate_json(raw)
    assert back == state, "ModelState roundtrip failed"


if __name__ == "__main__":
    test_modelcell_roundtrip()
    test_modelstate_minimal()
    print("OK: model_state smoke passed")
    sys.exit(0)
