"""Research-pipeline phase routing — the single source of routing truth.

The pipeline is an explicit state machine, not a LangGraph graph (see
docs/adr/0004-explicit-state-machine-over-langgraph.md):

  quick_screen → deep_dive → targeted_followup → thesis_construction
      → risk_stress_test ─┬─ loop_context and loop_count <= 2 → deep_dive
                          └─ else → completed
  position_monitor (phase 6) is triggered manually via POST /advance.

`PipelineService._run_phase` executes one node per step and persists
`ResearchState` to Postgres after every phase; it asks `next_phase` where to
go. test_phase_routing.py pins this contract.
"""

from __future__ import annotations

# Linear successors for phases 1–4. risk_stress_test branches in next_phase().
PHASE_SEQUENCE: dict[str, str] = {
    "quick_screen":        "deep_dive",
    "deep_dive":           "targeted_followup",
    "targeted_followup":   "thesis_construction",
    "thesis_construction": "risk_stress_test",
}


def next_phase(phase: str, *, loop_context: dict | None, loop_count: int) -> str:
    """Return the successor phase for the pipeline service.

    For risk_stress_test: loops back to deep_dive when loop_context is truthy
    and loop_count <= 2; otherwise returns 'completed'.

    For all other known phases: looks up PHASE_SEQUENCE.
    Unknown phases → 'completed'.
    """
    if phase == "risk_stress_test":
        if loop_context and loop_count <= 2:
            return "deep_dive"
        return "completed"
    return PHASE_SEQUENCE.get(phase, "completed")


# ── Risk loop-back policy (decided in code, not by the model) ────────────────

MAX_RISK_LOOPS = 2
# A thesis whose reward/risk is already >= this doesn't need a deeper look.
LOOP_RR_THRESHOLD = 2.0


def should_loop(
    *, model_wants_loop: bool, categories: list[str], loop_count: int, rr: float | None,
) -> bool:
    """Whether risk_stress_test sends the run back to deep_dive.

    The model proposes (loop_required + which categories); code disposes: at
    least one valid category, under the loop cap, and reward/risk not already
    comfortable. Before 2026-09-26 the prompt asked the model to apply these
    rules itself, and 18 of 22 runs looped.
    """
    if not model_wants_loop or not categories or loop_count >= MAX_RISK_LOOPS:
        return False
    return rr is None or rr < LOOP_RR_THRESHOLD
