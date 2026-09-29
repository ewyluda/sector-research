---
name: repo-audit
description: Principal-engineer-grade repository audit that ends in a runnable improvement campaign — inventory the repo, produce an honest findings report with open questions for the owner, then fold their answers into a dated, session-sequenced campaign doc that later sessions execute one item at a time. Use when the user invokes /repo-audit, asks for a "full audit", "honest review of this codebase/repo", "what should we improve", "find the loose ends / uncompleted work", or wants an improvement plan they can burn down across sessions. Works on code repos and knowledge repos alike.
---

# Repo audit → improvement campaign

Formalizes the audit prompt that used to be pasted by hand. The output contract matters as
much as the analysis: a **dated markdown campaign doc** that a fresh session can pick up with
"read <doc> and begin the next session" — because that's exactly how these campaigns get
executed. Work the phases in order; don't skip ahead.

## Phase 1 — Inventory (facts, no judgments)

Map what exists: structure, entry points, automation (CI, launchd/cron, hooks), tests, docs,
open branches/PRs/worktrees, TODO/backlog files, uncommitted work, stale artifacts. Use
subagents for breadth on large repos. Note the repo's own conventions (CLAUDE.md/AGENTS.md)
— audit against *its* rules, not generic taste.

## Phase 2 — Honest audit

Judge, with evidence (file:line or file references for every claim):

- **Correctness & robustness** — bugs, silent failure modes, drift between doc and behavior.
- **Architecture** — friction, duplication, dead weight, things fighting the grain.
- **UX / consumability** — for apps: flows and navigation; for knowledge repos: findability,
  naming-convention violations, orphan notes/artifacts.
- **Docs & agent-guidance health** — stale CLAUDE.md/README claims, bloat (an oversized
  CLAUDE.md is a per-session context tax), missing runbooks.
- **Loose ends** — deferred items buried in Done logs, half-merged work, unfinished
  campaigns, expiring credentials/keys.

Rank findings by value-to-owner, not by how interesting they are. Say what's *good* too —
one paragraph — so the owner can trust the criticism.

## Phase 3 — Open questions

List the decisions only the owner can make (keep/kill calls, taste questions, unknown
intent), numbered, each with your recommendation. **Stop and present Phases 1–3.** Do not
start fixing.

## Phase 4 — Campaign doc (after answers)

Fold the owner's answers in and write `docs/<YYYY-MM-DD>-improvement-campaign.md` (or the
repo's planning-docs home):

- Resolved-questions section — each answer recorded so no future session re-asks.
- Sequenced sessions (A1, A2, B1 …), each: goal, scope, files, verification step, and an
  explicit done-condition. Size sessions to be completable in one sitting.
- A status line per session (`pending / in progress / done`) that executing sessions update
  — the doc is the cross-session state, treat it as append-truth.

Offer to begin session A1 immediately or leave the doc for a fresh session.
