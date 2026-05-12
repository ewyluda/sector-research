# 2. Step 2 (Research) runs without new sources in v1

Date: 2026-05-09

## Status

Accepted (interim)

## Context

Step 2 of the workspace loop is "Research triage": Haiku reads new filing/transcript text against the prior thesis and emits highlights + new open questions. The plan doc framed Step 2 as the analytical bridge that turns Step 1's freshly-fetched material into thesis updates.

The current implementation does not deliver that. `services/workspace_steps.py::_gather_new_sources_text` returns `""` unconditionally; its docstring explicitly defers the work to "v1.5". The reason is structural — workspace steps are designed as pure functions of `WorkspaceContext`, and the orchestrator (`run_steps_in_sequence`) collects each step's Pydantic output into a `dict[str, dict]` *after* the step returns. There is no inter-step communication channel: Step 1 cannot stash filing text where Step 2 can read it without either (a) mutating `WorkspaceContext`, breaking its read-only invariant, or (b) reaching through the database, which Step 1 doesn't currently do (it pulls FMP financials and an EDGAR filing *index*, not section text).

In practice, Step 2's prompt today reads:
- prior thesis ✓
- existing open questions ✓
- "(no new filing/transcript text available)"

Haiku then either correctly says it has no new information, or hallucinates plausible-sounding highlights. Neither outcome is useful, but neither is harmful either — Step 4's challenge logic operates on Step 1's diff directly, not on Step 2's output, so a degenerate Step 2 doesn't poison downstream steps.

## Decision

Ship the workspace loop with Step 2 in its current degenerate state. Document the gap so the next reader doesn't mistake "Step 2 returned a summary" for "Step 2 found something new." Treat the real fix as a separate branch, scoped as:

> Step 1 hits the existing `services/edgar_sections_ingest.py` path to persist section text into `filing_sections`. Step 2 queries `filing_sections` for rows newer than the prior workspace run's `created_at` (or, for the first run on a ticker, newer than the prior `research_run.created_at`). This makes the workspace consistent with how the deep-dive pipeline already consumes filings, instead of building a parallel ingestion path on `WorkspaceContext`.

## Consequences

- The `/workspace/{runId}` page shows a Step 2 card that is correct but thin. We do not ship UI suggesting Step 2 found new material when it did not.
- Step 4 (Challenge) is the actual analytical work in v1: it sees Step 1's deltas and the prior thesis, and that combination is enough to produce a meaningful verdict. Step 2 is decorative until the follow-up lands.
- The `WorkspaceContext` invariant (read-only carrier passed to each step; orchestrator owns persistence) is preserved.
- We do *not* introduce an `outputs: dict` parameter into the step signature as a stopgap — partial inter-step plumbing would entrench an interim shape we'd rip out when Step 2 is properly wired through `filing_sections`.

## Amendment — 2026-05-12

Step 2 is no longer fully degenerate. As of PR #30 (transcript delta analysis), `step_research` makes a best-effort call to `transcript_delta.compute_delta(ticker, force=False)` before composing its prompt, and prepends a summary block of the populated axes into the otherwise-empty `new_sources` slot.

This is **complementary, not a substitute** for the `filing_sections` path named above. Specifically:

- The block is a *derived signal* (Haiku-summarized QoQ language shifts), not raw filing/transcript text. The slot continues to read `(no new filing/transcript text available)` whenever the transcript delta is absent or empty.
- The `filing_sections` route remains the planned source-text path. When that lands, both signals will coexist: Step 2 will see the derived transcript delta *and* newly-ingested section text from `filing_sections`.
- The `WorkspaceContext` invariant is preserved — the new call goes through `ctx.db` and `ctx.fmp`; nothing is mutated on the context.
- The enrichment is wrapped in `except Exception` and degrades silently to the empty-slot behavior, so a FMP outage or LLM failure cannot poison Step 2.

The `Transcript delta` glossary entry in `CONTEXT.md` distinguishes this signal from the model delta Step 1 emits.
