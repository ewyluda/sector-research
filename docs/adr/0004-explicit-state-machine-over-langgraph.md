# 4. The research pipeline is an explicit state machine, not a LangGraph graph

Date: 2026-09-26

## Status

Accepted. Supersedes the LangGraph assumption in the original design spec and
the "6-phase pipeline" framing in ADR-0001.

## Context

The pipeline was designed in April 2026 as a LangGraph `StateGraph` with human
interrupt gates between phases, so a run could pause for approval and resume
from a checkpoint. Two things changed:

1. The approval gates were removed (phases 1–5 now run continuously; phase 6,
   position monitoring, is triggered by `POST /api/runs/{id}/advance`).
2. Execution moved into `PipelineService._run_phase`, a loop that runs one node,
   persists `ResearchState` to `research_runs.state` (JSONB), emits SSE events,
   and asks `next_phase()` where to go.

After that, `make_graph()` was still compiled at startup but never invoked:
there was no `ainvoke`/`astream` call anywhere. The graph had drifted from the
real runtime — its deep-dive wrapper omitted the FRED, signal, EDGAR, filing and
counterparty inputs; it routed risk → position monitor while the service routed
risk → completed; and its edges still handled an `awaiting_approval` status
that no longer exists. A 2026-09-26 portfolio review flagged the README's
"Agent orchestration: LangGraph" as a claim the code did not support.

## Decision

Delete the LangGraph graph and the `langgraph` dependency. The pipeline is an
explicit state machine:

- `backend/app/graph/routing.py` — `PHASE_SEQUENCE` and `next_phase()`, the
  single source of routing truth (pinned by `test_phase_routing.py`).
- `backend/app/services/pipeline.py::_run_phase` — executes one node per step,
  persists state after every phase, and fans out SSE events.
- The nine deep-dive categories fan out with `asyncio.gather`, each under its
  own timeout.

## Why not keep LangGraph

What the graph would have offered, and why the loop already covers it:

- **Durable resume.** Every phase transition is committed to Postgres, so a
  run's state survives a restart; what's missing is a startup reconciler for
  runs left `in_progress`, which is simpler to add to the loop than to adopt a
  checkpointer.
- **Human-in-the-loop interrupts.** There are none left. Phase 6 is a separate
  API call on a completed run, not a paused graph.
- **Parallel fan-out.** `asyncio.gather` over nine independent calls is
  clearer than `Send` for a fixed, known set of branches.
- **Tracing.** Not used. Per-call token, cache and latency logging lives in
  `graph/llm.py`.

A framework that is compiled but never executed is worse than no framework:
it documents a flow that doesn't run, and every change has to keep two models
in sync.

## Consequences

- One runtime model to read and test; ~200 lines and a dependency removed.
- Revisit if the pipeline gains real branching beyond one loop-back, long
  pauses for human input, or tool-using agents whose control flow the model
  decides. Then LangGraph (checkpointer + `interrupt()` + `Send`) is worth its
  weight, and the node functions in `graph/nodes.py` already take and return
  `ResearchState`, so they compose into graph nodes without rework.
