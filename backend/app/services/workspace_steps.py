"""Five workspace step functions. Stubs for Phase 1; real implementations land in Phases 2-6."""
from __future__ import annotations
from typing import Callable
from backend.app.services.workspace_context import WorkspaceContext
from backend.app.models.workspace_schemas import (
    UpdateRefreshOutput, ResearchOutput, ValidationOutput,
    ChallengeOutput, DifferentiationOutput,
)


async def step_update_refresh(ctx: WorkspaceContext) -> UpdateRefreshOutput:
    raise NotImplementedError("Phase 2")


async def step_research(ctx: WorkspaceContext) -> ResearchOutput:
    raise NotImplementedError("Phase 3")


async def step_validation(ctx: WorkspaceContext) -> ValidationOutput:
    raise NotImplementedError("Phase 4")


async def step_challenge(ctx: WorkspaceContext) -> ChallengeOutput:
    raise NotImplementedError("Phase 5")


async def step_differentiation(ctx: WorkspaceContext) -> DifferentiationOutput:
    raise NotImplementedError("Phase 6")


STEP_NAMES = ["update_refresh", "research", "validation", "challenge", "differentiation"]
STEP_FUNCTIONS = {
    "update_refresh": step_update_refresh,
    "research": step_research,
    "validation": step_validation,
    "challenge": step_challenge,
    "differentiation": step_differentiation,
}


async def run_steps_in_sequence(ctx: WorkspaceContext, emit: Callable[[dict], None]) -> dict:
    """Run all 5 steps in order. Per-step errors do NOT abort; output dict is keyed by step name."""
    outputs: dict = {}
    for name in STEP_NAMES:
        emit({"type": "step_start", "step": name})
        try:
            result = await STEP_FUNCTIONS[name](ctx)
            outputs[name] = result.model_dump(mode="json")
            emit({"type": "step_complete", "step": name, "output": outputs[name]})
        except NotImplementedError as e:
            outputs[name] = {"error": f"not_implemented: {e}"}
            emit({"type": "step_failed", "step": name, "error": str(e)})
        except Exception as e:  # noqa: BLE001 - intentional broad catch per spec
            outputs[name] = {"error": str(e)}
            emit({"type": "step_failed", "step": name, "error": str(e)})
    return outputs
