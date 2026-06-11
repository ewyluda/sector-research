"""LangGraph pipeline graph.

Graph structure:
  START → quick_screen → deep_dive → targeted_followup
        → thesis_construction → risk_stress_test
        → (loop_context AND loop_count <= 2) → deep_dive  [loop-back]
        → else → position_monitor → END

Phases 1–5 run continuously (no interrupt gates). The service routes
risk_stress_test → completed rather than position_monitor; phase 6
(position_monitor) is manually triggered via the /advance API on a completed
run. The graph models all edges including the manually-gated phase 6 as
structural documentation.

The single source of routing truth is PHASE_SEQUENCE / next_phase below.
services/pipeline.py::_next_phase delegates here; test_phase_routing.py pins
the contract so divergence is caught at CI time.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END, START

from backend.app.clients.fmp import FMPClient
from backend.app.graph.state import ResearchState
from backend.app.graph import nodes

logger = logging.getLogger(__name__)


# ── Single source of routing truth ───────────────────────────────────────────

# Linear successors for phases 1–4. risk_stress_test has branching logic
# handled by next_phase() below.
PHASE_SEQUENCE: dict[str, str] = {
    "quick_screen":        "deep_dive",
    "deep_dive":           "targeted_followup",
    "targeted_followup":   "thesis_construction",
    "thesis_construction": "risk_stress_test",
}


def next_phase(phase: str, *, loop_context: object, loop_count: int) -> str:
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


# ── Module-level conditional edges (pure functions of state dict) ─────────────
# These are used by make_graph() and also tested directly in test_phase_routing.py.
# Their "continue" targets are derived from PHASE_SEQUENCE / next_phase so that
# adding a new phase only requires updating this file.

def after_quick_screen(state: dict) -> Literal["deep_dive", "__end__"]:
    """Route based on recommendation: GO → deep_dive, else END."""
    status = state.get("status", "in_progress")
    if status in ("watchlist", "pass", "completed"):
        return END
    if status == "awaiting_approval":
        return END  # Graph pauses here; pipeline service resumes on approval
    return PHASE_SEQUENCE["quick_screen"]


def after_deep_dive(state: dict) -> Literal["targeted_followup", "__end__"]:
    status = state.get("status", "in_progress")
    if status in ("watchlist", "pass", "completed"):
        return END
    if status == "awaiting_approval":
        return END
    return PHASE_SEQUENCE["deep_dive"]


def after_targeted_followup(state: dict) -> Literal["thesis_construction", "__end__"]:
    status = state.get("status", "in_progress")
    if status in ("watchlist", "pass", "completed"):
        return END
    if status == "awaiting_approval":
        return END
    return PHASE_SEQUENCE["targeted_followup"]


def after_thesis(state: dict) -> Literal["risk_stress_test", "__end__"]:
    """Route: awaiting approval → END (graph pauses), else → risk."""
    status = state.get("status", "in_progress")
    if status in ("watchlist", "pass", "completed"):
        return END
    if status == "awaiting_approval":
        return END
    return PHASE_SEQUENCE["thesis_construction"]


def after_risk(state: dict) -> Literal["deep_dive", "position_monitor", "__end__"]:
    """Route: loop-back → deep_dive, forced watchlist → END, approved → position.

    Note: the service routes risk_stress_test → 'completed' (not position_monitor)
    because phase 6 is manually gated via POST /api/runs/{id}/advance on a completed
    run. This graph edge models the full structural flow including the manually-gated
    phase 6; the divergence is intentional and documented in CLAUDE.md.
    """
    status = state.get("status", "in_progress")
    loop_ctx = state.get("loop_context")
    loop_count = state.get("loop_count", 0)

    if status == "watchlist":
        return END
    if status == "awaiting_approval":
        return END
    # Derive loop-back decision from next_phase to keep logic in one place
    if next_phase("risk_stress_test", loop_context=loop_ctx, loop_count=loop_count) == "deep_dive":
        return "deep_dive"
    return "position_monitor"


def after_position(state: dict) -> Literal["__end__"]:
    return END


# ── Node wrappers (bind FMP client) ──────────────────────────────────────────

def make_graph(fmp: FMPClient) -> StateGraph:
    """Build and compile the research pipeline graph."""

    # We use a dict-based state for LangGraph compatibility
    # ResearchState is serialised/deserialised at the boundary

    async def quick_screen(state: dict) -> dict:
        rs = ResearchState.from_dict(state)
        rs = await nodes.node_quick_screen(rs, fmp)
        return rs.to_dict()

    async def deep_dive(state: dict) -> dict:
        rs = ResearchState.from_dict(state)
        rs = await nodes.node_deep_dive(rs, fmp)
        return rs.to_dict()

    async def targeted_followup(state: dict) -> dict:
        rs = ResearchState.from_dict(state)
        rs = await nodes.node_targeted_followup(rs)
        return rs.to_dict()

    async def thesis_construction(state: dict) -> dict:
        rs = ResearchState.from_dict(state)
        rs = await nodes.node_thesis_construction(rs)
        return rs.to_dict()

    async def risk_stress_test(state: dict) -> dict:
        rs = ResearchState.from_dict(state)
        rs = await nodes.node_risk_stress_test(rs)
        return rs.to_dict()

    async def position_monitor(state: dict) -> dict:
        rs = ResearchState.from_dict(state)
        rs = await nodes.node_position_monitor(rs)
        return rs.to_dict()

    # ── Build graph ──────────────────────────────────────────────────────────

    builder = StateGraph(dict)

    builder.add_node("quick_screen", quick_screen)
    builder.add_node("deep_dive", deep_dive)
    builder.add_node("targeted_followup", targeted_followup)
    builder.add_node("thesis_construction", thesis_construction)
    builder.add_node("risk_stress_test", risk_stress_test)
    builder.add_node("position_monitor", position_monitor)

    builder.add_edge(START, "quick_screen")
    builder.add_conditional_edges("quick_screen", after_quick_screen)
    builder.add_conditional_edges("deep_dive", after_deep_dive)
    builder.add_conditional_edges("targeted_followup", after_targeted_followup)
    builder.add_conditional_edges("thesis_construction", after_thesis)
    builder.add_conditional_edges("risk_stress_test", after_risk)
    builder.add_conditional_edges("position_monitor", after_position)

    return builder.compile()
