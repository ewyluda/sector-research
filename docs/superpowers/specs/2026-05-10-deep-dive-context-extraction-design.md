# DeepDiveContext extraction — handoff

**Date:** 2026-05-10
**Status:** Design / handoff. Not started.
**Estimate:** 3–4 hours of careful work + verification against a real run.
**Originating note:** TODO.md "Done (recent)" entry for the routing-tables refactor — explicitly defers this follow-up.

---

## Goal

Lift the seven per-category context-builder closures out of `node_deep_dive` (in `backend/app/graph/nodes.py`) into module-level pure functions, organised behind a `DeepDiveContext` dataclass that carries the data they need. This finishes items #4 and #5 of the original architecture audit; the routing tables and two helpers were already extracted in a prior pass.

The current `node_deep_dive` is **466 lines** (lines 776–1242 of `nodes.py`). Most of that volume is the seven nested `def _build_*_context(...)` closures, which each capture 1–4 outer-scope variables and produce a string for one slot of the `DEEP_DIVE_USER` prompt. Lifting them out shrinks the node to its actual orchestration shape (fetch → run categories → score), makes each builder unit-testable in isolation, and removes the implicit dependency surface on `state` / `signals` / `edgar_facts` / `filing_sections` / `counterparty_context`.

## Non-goals

- **Don't change prompt output.** Verification is byte-for-byte equality of the `targeted_context` string for at least one ticker before/after.
- **Don't change routing tables.** They live in `deep_dive_routing.py` and stay there.
- **Don't promote `_fmt_fundamentals` or `_build_curated_financials`.** They're already module-level and orthogonal.
- **Don't refactor the targeted-followup builders** (`_build_targeted_followup_user_msg`, `node_targeted_followup`). Out of scope.
- **Don't refactor the asyncio.gather data-fetch block** at lines 825–882. That's part of the orchestration shape.

## Current state — what exists today

### Already extracted (prior pass)

- `backend/app/graph/deep_dive_routing.py` — five routing tables (`TRANSCRIPT_ROUTING`, `MACRO_ROUTING`, `EDGAR_ROUTING`, `FILING_EXCERPT_ROUTING`, `RELATIONSHIP_ROUTING`), `FILING_EXCERPT_BUDGET_CHARS`, `CategoryRouting` dataclass, `routing_for(category)` accessor.
- `backend/app/graph/deep_dive_helpers.py` — `unwrap_gather_result(result, default)` and `format_fact_value(value, unit)`. Both unit-tested in `backend/tests/test_deep_dive_helpers.py`.

### The seven closures — all defined inside `node_deep_dive`

| # | Closure | Defined at | Outer-scope reads | Routing source |
| - | ------- | ---------- | ----------------- | -------------- |
| 1 | `_build_transcript_context` | `nodes.py:937` | `state.transcript_analysis` | `TRANSCRIPT_ROUTING` |
| 2 | `_build_macro_context` | `nodes.py:952` | `state.curated_financials` (`macro_indicators` key) | `MACRO_ROUTING` |
| 3 | `_build_technical_context` | `nodes.py:971` | `state.curated_financials` (`daily_prices` key) | category == `"Technical & Market Structure"` |
| 4 | `_build_sentiment_context` | `nodes.py:997` | `signals` (param) | category == `"Sentiment & Narrative"` |
| 5 | `_build_edgar_context` | `nodes.py:1023` | `edgar_facts` (param) | `EDGAR_ROUTING` |
| 6 | `_build_filing_excerpt_context` | `nodes.py:1052` | `filing_sections` (param) | `FILING_EXCERPT_ROUTING` |
| 7 | `_build_counterparty_context` | `nodes.py:1080` | `counterparty_context` (param), `state.ticker` | `RELATIONSHIP_ROUTING` |

All seven take a single `category: str` argument and return `str` (empty string when the category is not routed or the data source is empty — the empty-string convention is what makes the slot drop out cleanly in `DEEP_DIVE_USER`).

The contexts are then materialised once per category in a dict at `nodes.py:1140`:

```python
category_contexts: dict[str, dict[str, str]] = {}
for cat in categories_to_run:
    category_contexts[cat] = {
        "transcript": _build_transcript_context(cat),
        "macro": _build_macro_context(cat),
        "technical": _build_technical_context(cat),
        "sentiment": _build_sentiment_context(cat),
        "edgar": _build_edgar_context(cat),
        "filing": _build_filing_excerpt_context(cat),
        "counterparty": _build_counterparty_context(cat),
    }
```

…and consumed in `_build_targeted_context_for_category` at `nodes.py:1152` to produce the final prompt string.

## Proposed shape

### Step 1 — Define the dataclass

New file `backend/app/graph/deep_dive_context.py`:

```python
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class DeepDiveContext:
    """Frozen bundle of every input the per-category builders need.

    Built once per node_deep_dive invocation, after all data fetches resolve.
    Each builder is a pure function over (DeepDiveContext, category) -> str.
    """
    ticker: str
    categories: list[str]
    transcript_analysis: dict | None
    curated_financials: dict | None      # macro_indicators + daily_prices live here
    signals: dict | None
    edgar_facts: dict | None
    filing_sections: dict | None
    counterparty_context: Any            # CounterpartyContext | None — same loose typing as node_deep_dive
```

`Any` for `counterparty_context` matches the existing typing comment at `nodes.py:783` ("typed loosely to avoid import cycle risk"). Don't tighten it without a separate audit of imports.

### Step 2 — Extract the seven builders as module-level pure functions

Each becomes:

```python
def build_transcript_context(ctx: DeepDiveContext, category: str) -> str:
    if not ctx.transcript_analysis or isinstance(ctx.transcript_analysis, str):
        return ""
    passes = TRANSCRIPT_ROUTING.get(category)
    ...
```

Drop the leading underscore — these are the public surface of the new module. Keep the empty-string-when-no-data convention.

### Step 3 — Optional: a single dispatcher

```python
CONTEXT_KINDS = ("transcript", "macro", "technical", "sentiment", "edgar", "filing", "counterparty")

def build_all_contexts(ctx: DeepDiveContext) -> dict[str, dict[str, str]]:
    return {
        cat: {
            "transcript": build_transcript_context(ctx, cat),
            "macro": build_macro_context(ctx, cat),
            "technical": build_technical_context(ctx, cat),
            "sentiment": build_sentiment_context(ctx, cat),
            "edgar": build_edgar_context(ctx, cat),
            "filing": build_filing_excerpt_context(ctx, cat),
            "counterparty": build_counterparty_context(ctx, cat),
        }
        for cat in ctx.categories
    }
```

Then `node_deep_dive` collapses lines 937–1150 (~213 lines) to:

```python
ctx = DeepDiveContext(
    ticker=state.ticker,
    categories=categories_to_run,
    transcript_analysis=state.transcript_analysis,
    curated_financials=state.curated_financials,
    signals=signals,
    edgar_facts=edgar_facts,
    filing_sections=filing_sections,
    counterparty_context=counterparty_context,
)
category_contexts = build_all_contexts(ctx)
```

`_build_targeted_context_for_category` (currently `nodes.py:1152`) stays inside the node — it's already a thin wrapper and depends on `data_text` which is built locally from the gather result, not a long-lived input.

### Step 4 — Tests

New `backend/tests/test_deep_dive_context.py`. For each builder:

- **Empty-input case** — returns `""`.
- **Routed-category case** — produces the expected formatted string against a fixture payload.
- **Unrouted-category case** — returns `""` even with data present.
- **Edge cases per builder** — e.g. `_build_macro_context` skips series whose `points` is empty; `_build_filing_excerpt_context` truncates at `FILING_EXCERPT_BUDGET_CHARS` and emits the `(truncated to N chars)` header; `_build_counterparty_context` formats `$TICKER — name — type` for resolved entries and bare names for unresolved.

Pin the byte-for-byte format of `_build_counterparty_context` since the prompt instruction depends on the `$TICKER` notation rendering exactly as documented in CLAUDE.md.

## Verification protocol

This is the load-bearing part. The closures embed prompt strings; a regression silently degrades model output for the next month before anyone notices.

1. **Snapshot before.** Pick a real ticker that exercises every builder — ORCL is the canonical one (resolved counterparties, transcripts, macro, EDGAR XBRL facts, filing sections, signals). Run `node_deep_dive` against the prior code path and dump `category_contexts` to a JSON fixture. Either temporarily monkey-patch `node_deep_dive` to write the dict to disk after construction, or trigger via a smoke script.
2. **Apply the refactor.** All seven closures gone, dataclass + module-level functions in place.
3. **Snapshot after.** Same ticker, same input data — easiest path is to mock the data fetches deterministically, harder but more rigorous is to capture real fetched payloads to fixtures and replay.
4. **Diff.** `category_contexts_before == category_contexts_after` — no diffs allowed. If there are diffs, the refactor changed behaviour.
5. **Full test suite.** `python -m unittest discover -s backend/tests` from project root with venv active. Currently 144/144 pass per memory; that count must hold (plus whatever new tests the new module adds).
6. **One real end-to-end run.** Trigger an actual deep-dive via `POST /api/runs` against a low-cost ticker, confirm phases complete and the report renders.

## Risks and gotchas

- **`state` is a `ResearchState` mutable.** The closures only read from it. Don't accidentally make the dataclass hold a reference and then mutate through it elsewhere — keep the extraction read-only by design (frozen dataclass enforces this for top-level fields, not nested dicts; convention covers the rest).
- **`counterparty_context.has_data`** is a method-style check. The dataclass field stays loosely typed (`Any`). Don't import `CounterpartyContext` at module top-level inside `deep_dive_context.py` unless you've checked the import graph for cycles — the existing comment at `nodes.py:783` is there for a reason.
- **`_build_counterparty_context` reads `state.ticker`.** It becomes `ctx.ticker` — make sure the dataclass build site at the top of `node_deep_dive` passes `state.ticker` not the local `ticker` (there isn't one, but watch for it during the refactor).
- **`_build_macro_context` and `_build_technical_context` both read `state.curated_financials`.** That dict is mutated by the FRED fetch block (`nodes.py:912–924`) **after** the gather but **before** the contexts are built. Build the dataclass after the FRED block, not before.
- **Loop-back runs reuse `categories_to_run` from `state.loop_context`.** That's already handled at `nodes.py:818–822`; pass the already-resolved list into the dataclass, don't re-derive it.
- **Don't get cute with `functools.partial`.** A single dispatcher loop is clearer than seven partials in a dict.

## Files that will change

- `backend/app/graph/nodes.py` — delete the seven nested closures (~213 lines), replace with the dataclass-build + dispatcher (~12 lines). Net: ~−200 lines from `node_deep_dive`.
- `backend/app/graph/deep_dive_context.py` — new file (~150 lines including dataclass, seven builders, dispatcher).
- `backend/tests/test_deep_dive_context.py` — new file (~250 lines for the test matrix).
- No migration. No API change. No frontend change. CLAUDE.md needs a small note pointing at the new module under "Deep-dive data routing".

## Out of scope (deferred deeper refactors)

- **Splitting `node_deep_dive` further** — the asyncio.gather payload + `_fmt_fundamentals` are tangled together; splitting them is its own task.
- **Citation contract uniformity** — the original audit's #2. Skipped per the prior pass: ~80 call sites for marginal benefit.
- **Targeted-followup builders** — `_build_targeted_followup_user_msg` (line 1242) has a similar shape but reads from different state and runs in a different node. Don't bundle it in.
- **Pulling `_fmt_fundamentals` into `deep_dive_context.py`** — it's already module-level and is consumed by the data-fetch block, not the per-category routing. Leave it.

## Definition of done

- [ ] `node_deep_dive` no longer contains any nested `def _build_*_context` closures.
- [ ] `backend/app/graph/deep_dive_context.py` exists with `DeepDiveContext` + 7 module-level builders + `build_all_contexts`.
- [ ] `backend/tests/test_deep_dive_context.py` covers each builder's empty / routed / unrouted / edge cases.
- [ ] Full backend test suite passes (current floor: 144 tests).
- [ ] Snapshot diff (before/after) for ORCL is empty across all 9 categories × 7 context kinds.
- [ ] One real `POST /api/runs` against a real ticker completes end-to-end without regression.
- [ ] CLAUDE.md "Deep-dive data routing" section gains a one-line pointer at `deep_dive_context.py`.
