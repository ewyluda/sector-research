# 1. Workspace runs have no human interrupts

Date: 2026-05-09

## Status

Accepted

## Context

The original `2026-05-03-model-workspace-plan.md` design specified three human interrupts inside a workspace run: after Step 1 (review diff), after Step 3 (review reverse-DCF), and after Step 4 (review challenge output). It also specified building the workspace as a LangGraph `StateGraph` with checkpoint-based resume — the same pattern used by the 6-phase pipeline at `backend/app/graph/pipeline.py`.

The 6-phase pipeline justifies that machinery: it produces the *primary* research artifact, runs for several minutes, costs real money in LLM tokens, and feeds downstream features (deep-dive dashboard, status board, financial model seeding). Stopping mid-run to confirm direction is worth the friction.

A workspace run is structurally different. It is *derivative* — it operates on top of an existing completed `research_run` and an existing `ticker_models` row, neither of which it overwrites. The only mutating steps are Step 1 (creates a new `ticker_models` row when actuals actually changed) and Step 4 (writebacks to `kill_criterion_state`). Both are versioned/idempotent at the row level — there is no destructive operation to gate. The whole loop runs in roughly 90 seconds.

For a single-user personal tool, gating each step on a manual confirmation produces high friction with low safety payoff. The user's preferred interaction is "run the whole loop, see all five outputs at once, decide whether to re-run after editing model state."

## Decision

Workspace runs execute as one continuous async task with no human interrupts. `services/workspace.py::run_steps_in_sequence` is a plain `for` loop over the five step functions. Per-step exceptions are caught and recorded in `step_outputs[name]["error"]`; the loop continues to the next step. The run completes (status `completed`) as long as the orchestrator itself doesn't crash.

There is no LangGraph `StateGraph` for the workspace, no checkpoint persistence, no `awaiting_review` status, and no `/resume` endpoint. The API surface is kick-off + poll + SSE stream + history.

## Consequences

- The workspace flow is much simpler to reason about — one task, one row, one terminal event.
- Re-running is cheap and expected. If Step 4's verdict looks wrong, you re-run instead of resuming.
- A bad call inside one step doesn't cascade: subsequent steps still run with the data the broken step couldn't produce (they read from `prior_research_run` / `prior_ticker_model`, not from the current run's `step_outputs`).
- We give up the ability to inject feedback mid-run. If that ever becomes wanted, we re-introduce LangGraph + interrupts as a v2 — the current step functions are pure relative to `WorkspaceContext` and would compose into nodes without rework.
- This decision applies *only* to workspace runs. The 6-phase pipeline's interrupt model is unchanged.
