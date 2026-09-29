# How I build with agents

> **Draft for you to rewrite in your own voice.** Every fact below is from the repo (commits, ADRs,
> PRs, the changelog); the `[bracketed prompts]` mark where only you can supply the words. Delete
> this note when it's yours.

## My role and the agents'

[In a few sentences: what you do vs. what Claude Code does. Suggested shape — "I decide what to
build and why, write or approve the spec, choose between designs, and verify the result. Agents
draft plans, write most of the code and tests, and run the checks." Add where you come from: you
build cost, schedule and risk reporting for data-center construction by day, you're self-taught in
software through agentic tools, and this is where you push that furthest.]

Numbers from the history: 657 commits since April 2026, 82% co-authored with Claude; 34 specs and
39 implementation plans; five ADRs; four full audits of my own code (June 9 repo audit, June 10 UX
audit, June 15 architecture audit, the September portfolio review).

## The loop

1. **Spec.** What problem, for which workflow, and what "done" looks like. [Example you're proud of.]
2. **Plan.** Sequenced, file-level steps with a verification per step, reviewed before code.
3. **Build.** Agents implement on a branch; each finished chunk is its own commit.
4. **Review before merge.** A review pass on the diff; findings are reproduced before they're fixed,
   because reviews produce plausible-but-wrong findings (the `ship-pr` skill in `.claude/skills/`).
5. **Audit.** Every few weeks, a full audit of what the agents built against what the docs claim
   (`repo-audit`), turned into a campaign that later sessions burn down.
6. **Hand off.** Each session ends with the TODO and a handoff updated so the next one starts cold
   (`session-wrapup`).

## Where I overrode the plan

- **No human interrupts in the workspace loop** ([ADR-0001](docs/adr/0001-workspace-runs-have-no-human-interrupts.md)).
  The plan specified three review gates and a LangGraph state graph with checkpoint resume. A
  workspace run is derivative, idempotent and takes about 90 seconds, so the gates were friction
  without safety; it became a plain loop. [Why this mattered to you as the user.]
- **Redesigning a feature against the real data** (PR #60). The backlog asked for a revenue Sankey;
  checking the data first showed no ticker had two named revenue customers with magnitudes. What
  existed was unnamed concentration disclosures ("three suppliers accounted for 23%, 20%, 17%"),
  duplicated across filings and cost-side rather than revenue. The feature was redesigned around
  that, and review caught a layout overflow bug before merge.
- **Checking premises live before building.** The 13F plan called for a filer-side polling pipeline;
  a live probe showed FMP's ticker-side endpoints now worked, so it shipped as a thin path instead.
  The congressional-trading plan relied on Capitol Trades' unofficial API, which turned out to be
  dead; it was rebuilt on FMP's official feeds.
- **Deleting what looked finished** ([ADR-0004](docs/adr/0004-explicit-state-machine-over-langgraph.md),
  [ADR-0005](docs/adr/0005-remove-targeted-followup-phase.md)). LangGraph was compiled but never
  invoked, and a follow-up phase ran on every research run without once doing anything (0 of 273
  qualifying questions). Both came out.

[Add one or two of your own — a moment an agent was confidently wrong and how you noticed.]

## What went wrong, and the guard each left behind

| What happened | How it was found | Guard now |
|---|---|---|
| Assistant prefill 400s on newer Claude models; fixed in April, back at five call sites later | September audit, then the stored errors in the database | native structured outputs; a test that fails if any code passes a prefill; a nightly live call on every model path |
| Naive `utcnow()` timestamps stored 4–5 hours late | audit; confirmed against Postgres | a test that fails on `utcnow(`; a one-off correction applied to 4,175 rows |
| No research run recorded an outcome after May | tracing why the Performance page had 19 rows, all from May 11 | the daily job creates pending outcomes; an end-to-end test in CI |
| A snapshot builder read a state attribute that never existed — its tests mocked it | reading the code during the outcome fixes | tests use real state objects |
| Transcript passes truncated on every run once truncation started raising | the first end-to-end live run after the change | larger token budgets; an end-to-end live run after LLM-layer changes |
| Valuations 7× the share price | sanity-checking every saved model after the rebuild | terminal value capped at what the terminal year supports |
| An API key written to a local log by an ad-hoc script | reviewing script output | client errors redact keys; scripts disable request logging |

The pattern: most of these weren't bugs a unit test would catch, because the tests shared the
code's assumptions. What caught them was running the real thing and checking it against reality —
which is why the eval harness, the live smoke and the end-to-end test now exist.

## How I verify agent work

- Live runs against a disposable copy of the database before anything touches the real one.
- `backend/evals`: thesis grounding against raw data, citation and consistency checks, rerun
  dispersion, and a rubric judge on a different model.
- CI: migrations from empty, an end-to-end research run with recorded data, Playwright + axe on
  every page, and a registry that fails when a new model call has no live probe.
- Cost and latency per run from the `llm_calls` table, so "does this change help?" has a number.

## What I'd do differently

[Your call. Candidates from the record: put the eval harness in before the fourth feature, not after
the audit; keep lessons in tests rather than commit messages; ask for the live check up front in
every plan.]
