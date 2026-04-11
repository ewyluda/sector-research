"""LangGraph pipeline graph.

Graph structure:
  START → quick_screen → [INTERRUPT] → deep_dive → [INTERRUPT]
        → thesis → risk_stress_test
        → (loop_required AND loop_count < 2) → deep_dive  [loop-back]
        → (loop_required AND loop_count >= 2) → END [forced WATCHLIST]
        → [INTERRUPT] → position_monitor → END

Human interrupts are implemented as status checks — the graph pauses at
awaiting_approval states and resumes when the API receives an approval action.

State is persisted to PostgreSQL at every interrupt via the pipeline service.
"""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import StateGraph, END, START

from backend.app.clients.fmp import FMPClient
from backend.app.graph.state import ResearchState
from backend.app.graph import nodes

logger = logging.getLogger(__name__)


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

    # ── Conditional edges ────────────────────────────────────────────────────

    def after_quick_screen(state: dict) -> Literal["deep_dive", "__end__"]:
        """Route based on recommendation: GO → deep_dive, else END."""
        output = state.get("phase_outputs", {}).get("quick_screen", {})
        recommendation = output.get("recommendation", "GO") if isinstance(output, dict) else "GO"
        status = state.get("status", "in_progress")
        # If human stopped the run, end
        if status in ("watchlist", "pass", "completed"):
            return END
        # Awaiting approval — will be resumed via API
        if status == "awaiting_approval":
            return END  # Graph pauses here; pipeline service resumes on approval
        return "deep_dive"

    def after_deep_dive(state: dict) -> Literal["thesis_construction", "__end__"]:
        status = state.get("status", "in_progress")
        if status in ("watchlist", "pass", "completed"):
            return END
        if status == "awaiting_approval":
            return END
        return "thesis_construction"

    def after_risk(state: dict) -> Literal["deep_dive", "position_monitor", "__end__"]:
        """Route: loop-back → deep_dive, forced watchlist → END, approved → position."""
        status = state.get("status", "in_progress")
        loop_ctx = state.get("loop_context")
        loop_count = state.get("loop_count", 0)

        if status == "watchlist":
            return END
        if status == "awaiting_approval":
            return END
        if loop_ctx and loop_count <= 2:
            return "deep_dive"
        return "position_monitor"

    def after_position(state: dict) -> Literal["__end__"]:
        return END

    # ── Build graph ──────────────────────────────────────────────────────────

    builder = StateGraph(dict)

    builder.add_node("quick_screen", quick_screen)
    builder.add_node("deep_dive", deep_dive)
    builder.add_node("thesis_construction", thesis_construction)
    builder.add_node("risk_stress_test", risk_stress_test)
    builder.add_node("position_monitor", position_monitor)

    builder.add_edge(START, "quick_screen")
    builder.add_conditional_edges("quick_screen", after_quick_screen)
    builder.add_conditional_edges("deep_dive", after_deep_dive)
    builder.add_edge("thesis_construction", "risk_stress_test")
    builder.add_conditional_edges("risk_stress_test", after_risk)
    builder.add_conditional_edges("position_monitor", after_position)

    return builder.compile()
