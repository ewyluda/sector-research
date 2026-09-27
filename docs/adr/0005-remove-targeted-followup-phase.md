# 5. Remove the automatic targeted-follow-up phase

Date: 2026-09-26

## Status

Accepted.

## Context

`targeted_followup` (PR #23, 2026-05-06) sat between the deep dive and the
thesis. It picked up to three questions the deep dive had marked priority 1
**and** `auto_answerable`, and asked the model to answer each from the same
data payload.

The eligibility rule contradicts itself. The deep-dive prompt asks for
*unresolved* questions, then allows `auto_answerable: true` only when the
answer is *already in the data payload*. A model that could answer from the
payload would have answered, so it almost never sets the flag: across every
run in the database, 0 of 273 priority-1 questions qualified, and only 2 of
393 questions were ever auto-answerable. The phase ran on every run and never
made an LLM call. Its call site also used assistant prefill on Sonnet 4.6, a
guaranteed 400 had it ever fired.

## Decision

Remove the phase from the pipeline (`deep_dive → thesis_construction`) and
delete its node and prompt. Keep what still earns its place:

- the manual **Retry auto** action on the Questions page
  (`services/questions.py::retry_auto_answer`), now on structured outputs;
- the per-category routed context it reads (`targeted_followup_context`) and
  the `TargetedAnswer` schema;
- prior open questions re-injected into later deep dives, which is how 37
  questions have actually been resolved (`deep_dive_resurfaced`).

## Consequences

- One fewer phase per run; no behavior lost, since the phase never acted.
- The real version of this idea needs *new* information, not a second look at
  the same payload: a bounded, tool-using follow-up that can fetch a filing
  section, an XBRL fact or a transcript excerpt to answer a specific
  question. That is a deliberate agentic design (tool schemas, a call budget,
  an eval), recorded as a Phase 2 candidate, not a patch to this phase.
