# Tier 1.2 — Question log + targeted second-pass deep dive

**Status:** Approved 2026-05-05 evening. Implementation pending plan.
**Roadmap context:** Tier 1.2 in `2026-05-03-framework-improvements-roadmap-design.md`. Steps 3 (Foundational DD) + 5 (Key Driver Deep Dive). Last remaining Tier 1 item.

## Problem

The existing pipeline produces a thesis from one shot of deep-dive analysis. When a category Sonnet call hits a real gap — "I can't tell what the customer concentration is from this data" — the gap currently dies inside that category's `key_findings`, never resurfaced. There's no first-class artifact that says "these 7 things are still unanswered about NVDA"; no mechanism to retry them on the next run; no fleet-level view of where diligence is thin.

Tier 1.2 closes this gap. LLM extracts open questions during deep dive, the cheap auto-answerable ones get resolved inline, the rest become a persistent per-ticker queue surfaced both per-run and at fleet level.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Q1 — Scope | **Hybrid (C):** extract questions; auto-resolve high-priority + auto-answerable inline; rest queue for triage |
| Q2 — Persistence | **Per-ticker (B):** survive across runs; new runs see prior open questions as context |
| Q3 — Extraction surface | **Per deep-dive category (A):** each of 9 Sonnet calls emits `questions[]` in structured output |
| Q4 — Second-pass mechanics | **Hybrid by priority (C):** priority-1 + auto_answerable resolves inline in pipeline; rest on-demand |
| Q5 — Cross-run handling | **Resurface in deep-dive prompts (B):** open priority-1/2 questions injected into next run's category prompts |
| Q6 — UI surface | **Per-run panel + dedicated `/questions` page (B):** mirrors `/status` and `/catalysts` |

## Data model

New `questions` table (per-ticker, theme-scoped):

```
id              uuid primary key
ticker          str not null (denormalized for fleet queries)
theme_id        uuid? fk → themes (nullable; null = ticker-wide)
category        str not null  (one of the 9 deep-dive display names)
question_text   text not null
priority        int not null  (1=high/thesis-load-bearing, 2=med, 3=nice-to-have)
auto_answerable bool not null
status          str not null  (open | resolved_auto | resolved_inline | resolved_manual | dismissed)
answer_text     text?
answer_source   str?          (targeted_followup | deep_dive_resurfaced | manual)
created_run_id  uuid not null fk → research_runs ON DELETE CASCADE
resolved_run_id uuid? fk → research_runs ON DELETE SET NULL
created_at      timestamptz not null default now()
resolved_at     timestamptz?
dismissed_at    timestamptz?
dismiss_note    text?
```

**Indexes:**
- `idx_questions_ticker_status` on `(ticker, status)` — drives `/questions` rollup
- `idx_questions_ticker_theme_status` on `(ticker, theme_id, status)` — drives per-run panel + cross-run resurfacing query
- `idx_questions_status_priority` on `(status, priority)` — drives fleet filters

**No unique constraint on text.** Sonnet rephrasing the same question across runs is signal that the question is genuinely hard, not noise to dedup. Both rows persist; the UI can show "this question has been raised N times" if it ever matters.

**Cascade behavior:** Deleting a run drops the questions it created (`ON DELETE CASCADE`). Resolving questions don't disappear when their resolving run is deleted — `resolved_run_id` goes to NULL but the answer text and source stay (`SET NULL`).

**`linked_pillar` deferred.** Questions emit at deep-dive time, before thesis pillars exist. Adding it would require a Haiku backfill pass after `node_thesis`, plus a migration for an additional column. Category provides sufficient grouping for v1. Reconsider in v2 if fleet-level "all questions linked to pillar X" becomes a real workflow need.

## Pipeline changes

### Extraction (per-category, in `node_deep_dive`)

Each of the 9 Sonnet category calls already returns a `CategoryResult` Pydantic model. Add two fields:

```python
class ExtractedQuestion(BaseModel):
    question_text: str
    priority: Literal[1, 2, 3]
    auto_answerable: bool

class ResolvedQuestion(BaseModel):
    question_id: UUID
    answer_text: str

class CategoryResult(BaseModel):
    # existing fields unchanged
    questions: list[ExtractedQuestion] = []
    resolved_questions: list[ResolvedQuestion] = []
```

**Prompt addition** to each category's user message (placed after the existing "key findings" instruction):

> Emit up to **3** unresolved questions whose answers would materially change your analysis. Mark `auto_answerable=true` only if the answer can be derived from the data payload above (financials, transcripts, filing excerpts, EDGAR facts, counterparty context) without external research. Priority 1 = thesis-load-bearing; 2 = important context; 3 = nice-to-have. If nothing is unresolved, emit an empty list.

The cap of 3 per category × 9 categories = 27 max new questions per run (much less in practice). This is the cost ceiling the user specified.

### Cross-run resurfacing (in `node_deep_dive`, before each category call)

Before invoking each category's Sonnet call, query:

```sql
SELECT id, question_text, priority, created_at
FROM questions
WHERE ticker = :ticker
  AND category = :category
  AND status = 'open'
  AND priority IN (1, 2)
ORDER BY created_at DESC
LIMIT 5;
```

Inject into the category prompt as a `{prior_questions}` slot (positioned after `{counterparty_context}`):

> **Previously unresolved questions for this pillar.** If the current data permits answering them, emit them in `resolved_questions` with `question_id` and `answer_text`. Otherwise, you may restate them — that's signal they're genuinely hard and external research is needed.
>
> [list of prior questions with UUIDs]

If no open prior questions, the slot drops out cleanly (empty string in the format).

On merge: each `ResolvedQuestion` updates the source row to `status='resolved_inline'`, `answer_source='deep_dive_resurfaced'`, `resolved_run_id=current_run.id`, `answer_text=<answer>`, `resolved_at=now()`.

### Targeted follow-up node (new, between `deep_dive` and `thesis`)

`node_targeted_followup` in `graph/pipeline.py` and `graph/nodes.py`:

1. Query newly-created questions from current run: `WHERE created_run_id = :run_id AND priority = 1 AND auto_answerable = true AND status = 'open'`
2. Cap at top 3 ordered by `(category alphabetical, created_at)` — the spec's stated cost ceiling
3. Run them in parallel via `asyncio.gather`. One focused Sonnet call per question:
   - System prompt: existing deep-dive system minus the multi-category framing, plus "answer this single question with the data provided; if the data is insufficient, say so explicitly rather than speculating"
   - User prompt: question text + that category's `key_findings` + relevant data-payload slices (financials snapshot + filing excerpt for that category + counterparty context if relationship-routed)
   - Response: structured `{answer_text: str}`. No separate confidence field for v1 — Sonnet is instructed to express uncertainty in prose. Add a `confidence` column in v2 if the prose form proves hard to triage.
4. Update each row: `status='resolved_auto'`, `answer_source='targeted_followup'`, `resolved_run_id=current`, `answer_text=<answer>`, `resolved_at=now()`
5. State update: `state.questions_resolved_this_run = [(question_text, answer_text), ...]` so `node_thesis` can see them

If zero eligible questions, node is a no-op — keeps graph shape simple.

**Always-on, not feature-flagged.** Cost ceiling is bounded (≤3 Sonnet calls). If a user finds it unhelpful, the in-graph hook is one edge in `pipeline.py` to remove.

### Thesis prompt update

`node_thesis`'s prompt gains a new `{questions_resolved}` slot rendered from `state.questions_resolved_this_run`:

> **Questions answered this run** (use as supporting evidence; don't re-derive):
>
> - Q: …  → A: …

Empty when no questions were resolved in this run.

## API endpoints (`api/questions.py`)

```
GET  /api/questions
  query: ticker?, theme_id?, status?, priority?, category?, limit=100
  returns: { questions: Question[] } sorted by priority asc, created_at desc

GET  /api/questions/by-ticker
  query: theme_id?
  returns: { tickers: { ticker, open_count, p1_count, p2_count, p3_count }[] }
  sorted by p1_count desc, then open_count desc

POST /api/questions/{id}/dismiss
  body: { note?: string }
  side effects: status='dismissed', dismissed_at=now(), dismiss_note=note
  returns: Question

POST /api/questions/{id}/resolve
  body: { answer_text: string }
  side effects: status='resolved_manual', answer_source='manual',
                answer_text=body.answer_text, resolved_at=now()
  returns: Question

POST /api/questions/{id}/retry-auto
  side effects: runs the same logic as node_targeted_followup for one question,
                regardless of its auto_answerable flag
                (covers user disagreement with Sonnet's auto_answerable=false call)
  returns: Question (with answer_text populated if successful, or 502 on Sonnet error)
```

**Idempotency:**
- `dismiss` and `resolve` on already-resolved/dismissed questions return 409
- `retry-auto` on already-resolved questions returns 409

**Report endpoint extension.** `GET /api/runs/{id}/report` already returns the run's full data; add `questions: Question[]` listing all questions linked to this run via either `created_run_id` or `resolved_run_id`. Lets the per-run panel render in one fetch.

**Important Python/FastAPI note:** Per the same footgun documented in `api/status.py` and `api/read_through.py` for PR #21, `api/questions.py` must **omit `from __future__ import annotations`**. FastAPI 0.115 + Python 3.12 evaluates `-> None` returns as the string `"None"` and trips an internal assertion when the future import is present.

## Frontend

### Types (`lib/api.ts`)

```typescript
export type QuestionStatus = "open" | "resolved_auto" | "resolved_inline" | "resolved_manual" | "dismissed";
export type QuestionAnswerSource = "targeted_followup" | "deep_dive_resurfaced" | "manual" | null;

export interface Question {
  id: string;
  ticker: string;
  theme_id: string | null;
  category: string;
  question_text: string;
  priority: 1 | 2 | 3;
  auto_answerable: boolean;
  status: QuestionStatus;
  answer_text: string | null;
  answer_source: QuestionAnswerSource;
  created_run_id: string;
  resolved_run_id: string | null;
  created_at: string;
  resolved_at: string | null;
  dismissed_at: string | null;
  dismiss_note: string | null;
}

export interface QuestionTickerRollup {
  ticker: string;
  open_count: number;
  p1_count: number;
  p2_count: number;
  p3_count: number;
}

export const questions = {
  list: (params: { ticker?: string; theme_id?: string; status?: QuestionStatus; priority?: 1|2|3; category?: string; limit?: number }) => apiFetch<{ questions: Question[] }>(...),
  byTicker: (params: { theme_id?: string }) => apiFetch<{ tickers: QuestionTickerRollup[] }>(...),
  dismiss: (id: string, note?: string) => apiFetch<Question>(...),
  resolve: (id: string, answer_text: string) => apiFetch<Question>(...),
  retryAuto: (id: string) => apiFetch<Question>(...),
};
```

### Per-run panel

New section in `frontend/app/pipeline/[runId]/page.tsx` (between Risk Assessment and Position Monitor):

- Title: "Open Questions" with count badge
- Grouped by category (alphabetical within group)
- Each row: question text, priority chip (slate/amber/red for 3/2/1), status badge, expandable answer (collapsed by default), `Dismiss` / `Mark resolved` / `Retry auto` action buttons
- Action buttons tagged `data-print-hide="true"` to drop out of PDF
- Status colors mirror existing `/status` palette: emerald for resolved, amber for open, slate for dismissed

### `/questions` page

New top-level page `frontend/app/questions/page.tsx`. Two tabs:

- **By ticker** (default): `QuestionTickerRollup[]` rendered as a table. Columns: Ticker, P1, P2, P3, Total open. Sorted by `p1_count desc, open_count desc`. Click a row → `/questions?ticker=X` (filtered flat view). Theme filter at top.
- **By question**: flat `Question[]` list. Filter chips: theme, priority (1/2/3/all), status (open default; resolved/dismissed/all toggleable), category (multi-select). Each row: question text, ticker badge, category badge, priority chip, age, run-id link, inline actions.

Polling: 60s `setInterval` while `document.visibilityState === "visible"`. Same pause-on-hidden pattern as `/status`.

### Nav

Add "Questions" link to `Nav.tsx` between "Status" and "Catalysts" (or wherever fits the existing order).

## State / serialization

`ResearchState` in `graph/state.py` gains:

```python
questions_extracted: list[StateQuestion] = field(default_factory=list)  # staged this run, written to DB at merge
questions_resolved_this_run: list[StateResolvedQuestion] = field(default_factory=list)  # used by node_thesis prompt
```

Both have `to_dict()`/`from_dict()` to round-trip through JSONB. Existing `__type__` discriminator pattern (used by `CategoryResult` and `CategoryError`) doesn't apply — these are flat dataclasses.

## Testing

Smoke script at `backend/scripts/smoke_question_log.py`. Self-cleaning on success **and** `ValueError` (matches the pattern from `smoke_earnings_navigator.py`):

1. Synthesize a `CategoryResult` for ticker `ZZZQ` with 2 questions: priority-1 auto_answerable, priority-3 not.
2. Persist via the same merge logic as `node_deep_dive` → assert 2 rows in `questions` with status='open'.
3. Run `node_targeted_followup` against the synthetic run → assert priority-1 row → status='resolved_auto' with non-empty `answer_text` and `answer_source='targeted_followup'`. Assert priority-3 row still 'open'.
4. `POST /api/questions/{p3_id}/dismiss` with note → assert status='dismissed', dismiss_note populated.
5. Synthesize a third open question for `ZZZQ` (priority 2).
6. Build the prior-questions slot via the same query the production node uses → assert it returns the priority-2 question.
7. Cleanup: delete all `ZZZQ` questions and the synthetic run on success or any caught exception.

No real LLM calls in the smoke (mock at the `complete()` boundary). The targeted-followup integration is exercised via a separate manual test against a real ticker (per the existing pattern — smoke tests pipeline scaffolding, not LLM behavior).

## Migration

New alembic revision `<hash>_add_questions_table.py`:
- Up: `CREATE TABLE questions` with columns above + 3 indexes
- Down: `DROP TABLE questions` (no FK from other tables to reverse)
- `down_revision = '771650442ce6'` (current head — earnings navigator)

## Cost analysis

**Per-run delta:**
- Each of 9 deep-dive Sonnet calls: +~150 tokens output (3 questions × ~50 tok/question) + ~200 tokens input (resurfacing slot) = ~350 × 9 = ~3K incremental tokens. Negligible vs. the existing ~50K per category.
- `node_targeted_followup`: 0–3 focused Sonnet calls. Each ~5K input + ~500 output. Bounded ceiling: ~17K tokens.
- Thesis prompt: +~500 tokens for `{questions_resolved}` slot.

Order of magnitude: +3-5% deep-dive token cost, +1 phase that costs ≤17K tokens. Acceptable.

**Frontend:** no new chart libraries. Reuses existing slate/emerald palette and table components.

## Out of scope (v1)

- **No web search / external research** in `node_targeted_followup`. The follow-up Sonnet call sees only existing state. If many questions get rated `auto_answerable=false` purely for missing fresh data, v2 can add the Anthropic web tool to the focused call.
- **No question similarity / dedup.** Sonnet restating ≈ signal per Q5-B.
- **No `linked_pillar`.** Deferred — would need Haiku backfill after thesis_construction.
- **No per-question audit trail** beyond the timestamp columns. Multiple resolution attempts overwrite `answer_text`.
- **No bulk dismiss.** UI dismisses one at a time. If triage UX becomes painful, add `POST /api/questions/dismiss-many` in v2.
- **No question export.** No CSV/markdown render. The `/questions` page is the only consumer.
- **No catalyst linkage.** A question like "does the Fed cut in March?" doesn't auto-attach to a catalyst row. Possible v2 enrichment.

## Files touched

**Backend:**
- `backend/app/models/question.py` (new)
- `backend/app/models/__init__.py` (export)
- `backend/migrations/versions/<hash>_add_questions_table.py` (new)
- `backend/app/graph/state.py` (StateQuestion, StateResolvedQuestion + ResearchState fields)
- `backend/app/graph/nodes.py` (extraction prompt, resurfacing query, targeted-followup node, thesis prompt update)
- `backend/app/graph/pipeline.py` (wire `node_targeted_followup` between deep_dive and thesis)
- `backend/app/services/pipeline.py` (`_next_phase` updated for new node — parallel source of truth per CLAUDE.md note)
- `backend/app/services/questions.py` (new — query helpers, retry-auto orchestration)
- `backend/app/api/questions.py` (new — 5 endpoints)
- `backend/app/api/pipeline.py` (extend `/runs/{id}/report` to include questions)
- `backend/app/main.py` (register `questions` router)
- `backend/scripts/smoke_question_log.py` (new)

**Frontend:**
- `frontend/lib/api.ts` (Question types + client)
- `frontend/app/questions/page.tsx` (new)
- `frontend/app/pipeline/[runId]/page.tsx` (per-run "Open Questions" section)
- `frontend/components/Nav.tsx` (Questions link)
- `frontend/components/questions/QuestionRow.tsx` (new — shared row component)
- `frontend/components/questions/QuestionTickerRollupTable.tsx` (new)

## Done criteria

- All 9 deep-dive categories emit `questions[]` in their structured output and persist to the table.
- Open priority-1/2 questions from prior runs surface in the next run's category prompts.
- Priority-1 + auto-answerable questions get resolved inline by `node_targeted_followup` and feed forward into thesis.
- `/questions` page renders the fleet view; per-run panel renders in `/pipeline/[runId]`.
- Smoke 3/3 green.
- One real run executed end-to-end against an active theme ticker; manual eyeball confirms questions are sensible (not garbage like "what is gross margin?" when GM is in the data) and the auto-resolved answers cite the data correctly.
