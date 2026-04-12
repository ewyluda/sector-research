"""Standalone verification for parse_structured_output + PositionMonitorOutput.

Run from project root:
    python -m backend.scripts.verify_position_parser

Exits non-zero on any assertion failure.
"""

from __future__ import annotations

import json
import sys

from backend.app.graph.output_parser import parse_structured_output
from backend.app.models.phase_schemas import PositionMonitorOutput


def _make_good_json(**overrides) -> str:
    payload = {
        "entry_price_low": "$142",
        "entry_price_high": "$155",
        "entry_rationale": "Technical support at $142 (200-day MA) with fundamental floor from DCF at $138. Upper bound reflects 2% premium to current price for momentum confirmation.",
        "position_size_pct": 3.5,
        "sizing_rationale": "Conviction score of 72 warrants a mid-size allocation. Higher than starter (2%) given strong fundamentals, but below full-size (5%) due to valuation premium vs peers.",
        "add_triggers": [
            "Break above $160 on 2x average volume",
            "Q2 earnings beat with raised guidance",
            "Insider buying above $1M aggregate",
        ],
        "stop_loss_level": "$128 (-12% from midpoint entry)",
        "stop_loss_rationale": "Below 200-day MA and key support at $130. A close below $128 invalidates the technical structure underpinning the entry thesis.",
        "invalidation_conditions": [
            "Revenue growth decelerates below 15% YoY for two consecutive quarters",
            "Key customer loss representing >10% of revenue",
            "CEO or CTO departure without clear succession",
        ],
        "monitoring": [
            {"metric": "Quarterly revenue growth", "cadence": "Quarterly", "threshold": "Below 15% YoY"},
            {"metric": "Gross margin trend", "cadence": "Quarterly", "threshold": "Below 62% (200bps compression)"},
            {"metric": "Price vs 200-day MA", "cadence": "Weekly", "threshold": "Sustained close below MA"},
            {"metric": "Insider transactions", "cadence": "Monthly", "threshold": "Net selling >$5M"},
        ],
        "exit_conditions": [
            "Price target of $195 reached (30% upside)",
            "Thesis-breaking fundamental deterioration (see invalidation conditions)",
            "Better risk/reward opportunity identified in same sector",
        ],
        "time_horizon": "6-12 months",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_1_well_formed_json() -> None:
    raw = _make_good_json()
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None
    assert parsed.position_size_pct == 3.5
    assert parsed.entry_price_low == "$142"
    assert len(parsed.monitoring) == 4
    assert parsed.time_horizon == "6-12 months"


def test_2_json_with_markdown_fences() -> None:
    raw = f"```json\n{_make_good_json()}\n```"
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None
    assert parsed.position_size_pct == 3.5


def test_3_json_with_prose_preamble() -> None:
    raw = f"Here is the position plan:\n\n{_make_good_json()}\n\nEnd of plan."
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None


def test_4_minimum_lists() -> None:
    """Minimum valid: 1 add_trigger, 1 invalidation, 2 monitoring, 1 exit."""
    raw = _make_good_json(
        add_triggers=["Break above resistance on volume"],
        invalidation_conditions=["Revenue growth drops below 10%"],
        monitoring=[
            {"metric": "Quarterly revenue", "cadence": "Quarterly", "threshold": "Below 10% YoY"},
            {"metric": "Price action", "cadence": "Weekly", "threshold": "Close below stop"},
        ],
        exit_conditions=["Target price reached"],
    )
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None
    assert len(parsed.add_triggers) == 1
    assert len(parsed.monitoring) == 2


def test_5_too_few_monitoring() -> None:
    """Monitoring needs min 2 items."""
    raw = _make_good_json(
        monitoring=[{"metric": "Revenue", "cadence": "Quarterly", "threshold": "Below 10%"}],
    )
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert parsed is None
    assert err is not None


def test_6_position_size_out_of_range() -> None:
    raw = _make_good_json(position_size_pct=150.0)
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert parsed is None
    assert err is not None


def test_7_position_size_zero() -> None:
    """Zero percent is valid (cash position / no allocation)."""
    raw = _make_good_json(position_size_pct=0.0)
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert err is None, f"expected no error, got: {err}"
    assert parsed is not None
    assert parsed.position_size_pct == 0.0


def test_8_missing_required_field() -> None:
    payload = json.loads(_make_good_json())
    del payload["entry_price_low"]
    raw = json.dumps(payload)
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert parsed is None
    assert err is not None


def test_9_empty_input() -> None:
    parsed, err = parse_structured_output("", PositionMonitorOutput)
    assert parsed is None
    assert err == "empty response"


def test_10_malformed_garbage() -> None:
    parsed, err = parse_structured_output("not json at all", PositionMonitorOutput)
    assert parsed is None
    assert err is not None
    assert "json" in err.lower()


def test_11_empty_add_triggers() -> None:
    """add_triggers needs at least 1 item."""
    raw = _make_good_json(add_triggers=[])
    parsed, err = parse_structured_output(raw, PositionMonitorOutput)
    assert parsed is None
    assert err is not None


def main() -> int:
    tests = [
        test_1_well_formed_json, test_2_json_with_markdown_fences,
        test_3_json_with_prose_preamble, test_4_minimum_lists,
        test_5_too_few_monitoring, test_6_position_size_out_of_range,
        test_7_position_size_zero, test_8_missing_required_field,
        test_9_empty_input, test_10_malformed_garbage,
        test_11_empty_add_triggers,
    ]
    failures = 0
    for fn in tests:
        try:
            fn()
            print(f"  \u2713 {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"  \u2717 {fn.__name__}: {e}")
        except Exception as e:
            failures += 1
            print(f"  ! {fn.__name__}: unexpected {type(e).__name__}: {e}")
    print()
    if failures:
        print(f"FAILED: {failures}/{len(tests)}")
        return 1
    print(f"OK: {len(tests)}/{len(tests)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
