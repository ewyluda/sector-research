# Tier 1.2 — Question Log + Targeted Second-Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make LLM-extracted open questions a first-class per-ticker artifact, auto-resolve cheap ones inline, surface the rest in a fleet view.

**Architecture:** Each of the 9 deep-dive Sonnet calls emits a `questions[]` field. New `questions` table persists them per-ticker. Open priority-1/2 questions from prior runs are injected as context into the next run's category prompts (cross-run resurfacing). New `node_targeted_followup` between deep-dive and thesis runs ≤3 focused Sonnet calls to resolve priority-1 + auto-answerable questions inline. UI: per-run panel + dedicated `/questions` page mirroring `/status` and `/catalysts`.

**Tech Stack:** SQLAlchemy async ORM, Alembic, FastAPI, LangGraph, Pydantic v2, Next.js 16 App Router, React 19, Tailwind v4.

**Spec:** `docs/superpowers/specs/2026-05-05-tier-1-2-question-log-design.md`

---

## File structure

**Backend (new):**
- `backend/app/models/question.py` — `Question` ORM model
- `backend/migrations/versions/<hash>_add_questions_table.py` — Alembic migration
- `backend/app/services/questions.py` — query helpers + retry-auto orchestration
- `backend/app/api/questions.py` — 5 REST endpoints
- `backend/scripts/smoke_question_log.py` — end-to-end smoke

**Backend (modified):**
- `backend/app/models/__init__.py` — export `Question`
- `backend/app/graph/state.py` — `StateQuestion`, `StateResolvedQuestion`, `ResearchState.questions_extracted`, `questions_resolved_this_run`
- `backend/app/graph/nodes.py` — extraction prompt addition, resurfacing query, `node_targeted_followup`, thesis prompt update, persistence helpers
- `backend/app/graph/pipeline.py` — wire `targeted_followup` between deep_dive and thesis
- `backend/app/services/pipeline.py` — `_next_phase` updated for new node
- `backend/app/api/pipeline.py` — extend `/runs/{id}/report` with `questions: Question[]`
- `backend/app/main.py` — register `questions_router`

**Frontend (new):**
- `frontend/app/questions/page.tsx` — fleet view (two tabs)
- `frontend/components/questions/QuestionRow.tsx` — shared row component
- `frontend/components/questions/QuestionTickerRollupTable.tsx` — by-ticker tab
- `frontend/components/questions/OpenQuestionsPanel.tsx` — per-run panel embedded in `/pipeline/[runId]`

**Frontend (modified):**
- `frontend/lib/api.ts` — `Question` types + `questions` client + extend report payload type
- `frontend/app/pipeline/[runId]/page.tsx` — embed `OpenQuestionsPanel`
- `frontend/components/Nav.tsx` — add `Questions` link

---

## Task 1: Add `Question` ORM model

**Files:**
- Create: `backend/app/models/question.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: Create the ORM file**

Write `backend/app/models/question.py`:

```python
"""Question ORM — per-ticker LLM-extracted open questions.

Surface for Tier 1.2 question log. Rows survive runs. Lifecycle:
- created during deep-dive (status='open')
- resolved_auto by node_targeted_followup (priority-1 + auto_answerable)
- resolved_inline by next run's deep-dive resurfacing slot
- resolved_manual or dismissed by /questions UI
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )

    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("themes.id", ondelete="SET NULL"),
        nullable=True,
    )

    category: Mapped[str] = mapped_column(String(64), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    created_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    resolved_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="SET NULL"),
        nullable=True,
    )

    # created_at / updated_at come from TimestampMixin
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismiss_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_questions_ticker_status", "ticker", "status"),
        Index("idx_questions_ticker_theme_status", "ticker", "theme_id", "status"),
        Index("idx_questions_status_priority", "status", "priority"),
    )


# TimestampMixin would add updated_at automatically. Compose it onto Question
# at the end so both created_at and updated_at land on the table.
class _QuestionWithTimestamps(TimestampMixin):
    pass


# Re-declare with the mixin via a metaclass-friendly pattern: the cleanest
# expression is for Question to inherit (Base, TimestampMixin) in one shot.
# Replace the class declaration above to: `class Question(Base, TimestampMixin):`
# and remove the explicit `_QuestionWithTimestamps` shim. The implementer
# should write the final class as a single declaration:
#
#     class Question(Base, TimestampMixin):
#         __tablename__ = "questions"
#         ... (all columns above except no manual created_at) ...
#
# (See research_run.py and earnings_print.py for the pattern.)
```

**Note for the implementer:** write the final class as one declaration:

```python
class Question(Base, TimestampMixin):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    ticker: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("themes.id", ondelete="SET NULL"),
        nullable=True,
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    auto_answerable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="open")
    answer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_run_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    resolved_run_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("research_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dismiss_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("idx_questions_ticker_status", "ticker", "status"),
        Index("idx_questions_ticker_theme_status", "ticker", "theme_id", "status"),
        Index("idx_questions_status_priority", "status", "priority"),
    )
```

`created_at` and `updated_at` come from `TimestampMixin` automatically.

- [ ] **Step 2: Export in `__init__.py`**

Add to `backend/app/models/__init__.py`:

```python
from backend.app.models.question import Question  # noqa: F401
```

- [ ] **Step 3: Verify import**

Run: `cd /Users/ericwyluda/Development/projects/sector-research && backend/venv/bin/python -c "from backend.app.models.question import Question; print(Question.__tablename__)"`

Expected: `questions`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/question.py backend/app/models/__init__.py
git commit -m "$(cat <<'EOF'
feat(questions): add Question ORM model

Per-ticker LLM-extracted open questions for Tier 1.2. Lifecycle:
open → resolved_auto/inline/manual or dismissed.
EOF
)"
```

---

## Task 2: Alembic migration for `questions` table

**Files:**
- Create: `backend/migrations/versions/<auto>_add_questions_table.py`

- [ ] **Step 1: Generate migration**

Run from project root:

```bash
cd /Users/ericwyluda/Development/projects/sector-research/backend && PYTHONPATH=/Users/ericwyluda/Development/projects/sector-research ./venv/bin/alembic revision --autogenerate -m "add questions table"
```

Expected: file appears in `backend/migrations/versions/<hash>_add_questions_table.py`.

- [ ] **Step 2: Review the autogenerated up()**

Open the new file. It should reference `op.create_table('questions', ...)` with columns `id`, `ticker`, `theme_id`, `category`, `question_text`, `priority`, `auto_answerable`, `status`, `answer_text`, `answer_source`, `created_run_id`, `resolved_run_id`, `created_at`, `resolved_at`, `dismissed_at`, `dismiss_note`, plus the 3 indexes.

If autogenerate missed the `default='open'` on `status`, the `default=uuid_generate_v4()` on `id`, or any FK ondelete clause, edit the migration to match the ORM. The `down_revision` must point to `'771650442ce6'` (the earnings_prints migration); fix it if alembic chose a different head.

- [ ] **Step 3: Verify the down() fully reverses**

The autogenerated `op.downgrade()` should drop the 3 indexes then drop the table. Confirm; if missing, write:

```python
def downgrade() -> None:
    op.drop_index("idx_questions_status_priority", table_name="questions")
    op.drop_index("idx_questions_ticker_theme_status", table_name="questions")
    op.drop_index("idx_questions_ticker_status", table_name="questions")
    op.drop_table("questions")
```

- [ ] **Step 4: Apply the migration**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/backend && PYTHONPATH=/Users/ericwyluda/Development/projects/sector-research ./venv/bin/alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade 771650442ce6 -> <hash>, add questions table`.

- [ ] **Step 5: Verify the table exists**

```bash
PGPASSWORD=$(grep '^DATABASE_URL_SYNC' .env | cut -d= -f2- | sed 's|.*://[^:]*:||;s|@.*||') psql "$(grep '^DATABASE_URL_SYNC' .env | cut -d= -f2-)" -c "\d questions"
```

Expected: shows the columns + 3 indexes.

If the psql one-liner is too brittle, alternatively run:

```bash
cd /Users/ericwyluda/Development/projects/sector-research/backend && PYTHONPATH=/Users/ericwyluda/Development/projects/sector-research ./venv/bin/alembic current
```

and confirm the new revision is the head.

- [ ] **Step 6: Commit**

```bash
git add backend/migrations/versions/*_add_questions_table.py
git commit -m "$(cat <<'EOF'
feat(questions): alembic migration for questions table

Three indexes: (ticker, status), (ticker, theme_id, status),
(status, priority). FK to research_runs(id) ON DELETE CASCADE
for created_run_id, SET NULL for resolved_run_id.
EOF
)"
```

---

## Task 3: Add state dataclasses for question staging

**Files:**
- Modify: `backend/app/graph/state.py`

- [ ] **Step 1: Add `StateQuestion` and `StateResolvedQuestion` dataclasses**

Insert after `CategoryResult` (around line 56, just before `class StateCitation`):

```python
@dataclass
class StateQuestion:
    """Question extracted by a deep-dive category, staged in state for
    persistence after the deep_dive merge."""
    category: str
    question_text: str
    priority: int  # 1 | 2 | 3
    auto_answerable: bool

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "question_text": self.question_text,
            "priority": self.priority,
            "auto_answerable": self.auto_answerable,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StateQuestion":
        return cls(
            category=d["category"],
            question_text=d["question_text"],
            priority=int(d["priority"]),
            auto_answerable=bool(d["auto_answerable"]),
        )


@dataclass
class StateResolvedQuestion:
    """Question resolved this run — used by node_thesis_construction to
    surface answered context in its prompt."""
    question_text: str
    answer_text: str
    source: str  # "targeted_followup" | "deep_dive_resurfaced"

    def to_dict(self) -> dict:
        return {
            "question_text": self.question_text,
            "answer_text": self.answer_text,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "StateResolvedQuestion":
        return cls(
            question_text=d["question_text"],
            answer_text=d["answer_text"],
            source=d["source"],
        )
```

- [ ] **Step 2: Add fields to `ResearchState`**

In the `class ResearchState:` block (around line 266+), after `transcript_analysis: dict | None = None` (around line 311), insert:

```python
    # Tier 1.2 — questions staged this run, written to DB at deep_dive merge
    questions_extracted: list[dict] = field(default_factory=list)

    # Tier 1.2 — questions resolved this run (auto + resurfaced), used by thesis prompt
    questions_resolved_this_run: list[dict] = field(default_factory=list)
```

These are stored as `list[dict]` (not `list[StateQuestion]`) so they round-trip cleanly through `asdict()` in `to_dict()` and the `**{k: v for k, v in d.items() ...}` constructor in `from_dict()`. The `StateQuestion` / `StateResolvedQuestion` types are used at construction sites (in nodes.py), serialized via `.to_dict()` before going into state.

- [ ] **Step 3: Syntax check**

```bash
backend/venv/bin/python -c "import ast; ast.parse(open('backend/app/graph/state.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Verify state round-trip**

```bash
backend/venv/bin/python <<'EOF'
from backend.app.graph.state import ResearchState, StateQuestion
rs = ResearchState(ticker="NVDA", theme_id="t1", run_id="r1")
rs.questions_extracted.append(StateQuestion("Macro & Regime", "What is X?", 1, True).to_dict())
d = rs.to_dict()
rs2 = ResearchState.from_dict(d)
assert rs2.questions_extracted == rs.questions_extracted
print("OK")
EOF
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/state.py
git commit -m "$(cat <<'EOF'
feat(questions): StateQuestion + StateResolvedQuestion dataclasses

Adds questions_extracted + questions_resolved_this_run fields to
ResearchState for Tier 1.2 question log staging through the pipeline.
EOF
)"
```

---

## Task 4: Extend Pydantic `CategoryResult` with question fields

**Files:**
- Modify: `backend/app/graph/nodes.py`

The deep-dive Sonnet call already returns a Pydantic model parsed via structured output. Find where `DeepDiveCategoryOutput` (or the equivalent class) is defined.

- [ ] **Step 1: Locate the Pydantic schema**

```bash
grep -n "class DeepDiveCategoryOutput\|class CategoryStructured" backend/app/graph/nodes.py
```

Note the line range of the existing class. It currently has fields like `score`, `key_findings`, `analysis`, etc.

- [ ] **Step 2: Add new Pydantic models above `DeepDiveCategoryOutput`**

Insert just before the existing `DeepDiveCategoryOutput` class definition:

```python
class ExtractedQuestion(BaseModel):
    """One question Sonnet didn't have enough info to answer in this category."""
    question_text: str = Field(
        description="Specific question whose answer would materially change your analysis."
    )
    priority: Literal[1, 2, 3] = Field(
        description="1=thesis-load-bearing, 2=important context, 3=nice-to-have"
    )
    auto_answerable: bool = Field(
        description="True only if answerable from data already in the payload "
        "(financials, transcripts, filing excerpts, EDGAR facts, counterparty context) "
        "without external research."
    )


class ResolvedQuestion(BaseModel):
    """A previously-open question that the current run has now answered."""
    question_id: str = Field(description="UUID of the previously-open question.")
    answer_text: str = Field(description="Concise answer using current data.")
```

If `Literal` isn't already imported in `nodes.py`, add it to the existing `from typing import ...` line.

- [ ] **Step 3: Add fields to `DeepDiveCategoryOutput`**

Inside the `DeepDiveCategoryOutput` class, after the existing fields, add:

```python
    questions: list[ExtractedQuestion] = Field(
        default_factory=list,
        description="Up to 3 unresolved questions for this pillar.",
    )
    resolved_questions: list[ResolvedQuestion] = Field(
        default_factory=list,
        description="Previously-unresolved questions that current data lets you answer.",
    )
```

- [ ] **Step 4: Syntax + Pydantic check**

```bash
backend/venv/bin/python -c "from backend.app.graph.nodes import DeepDiveCategoryOutput, ExtractedQuestion, ResolvedQuestion; print(DeepDiveCategoryOutput.model_json_schema()['properties'].keys())"
```

Expected: keys include `questions` and `resolved_questions`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph/nodes.py
git commit -m "$(cat <<'EOF'
feat(questions): extend DeepDiveCategoryOutput with questions fields

Adds ExtractedQuestion + ResolvedQuestion Pydantic models and
questions[] / resolved_questions[] fields on the structured output
each deep-dive category returns.
EOF
)"
```

---

## Task 5: Wire extraction prompt + persistence on deep-dive merge

**Files:**
- Modify: `backend/app/graph/nodes.py`

This task adds the prompt instruction telling Sonnet to emit questions, and the merge logic that persists them to the `questions` table after all 9 categories return.

- [ ] **Step 1: Locate the deep-dive user prompt template**

```bash
grep -n "DEEP_DIVE_USER\|key_findings.*as a list\|Emit your" backend/app/graph/nodes.py | head -20
```

Find the template string (likely a multi-line `f"""..."""` or `.format(...)` builder). Identify the spot where the existing `key_findings` instruction lives.

- [ ] **Step 2: Add the question-extraction instruction**

Append to the same prompt template, after the existing `key_findings` instruction and before any closing JSON-format reminder:

```
Emit up to 3 unresolved questions whose answers would materially change your analysis as `questions[]`. Mark `auto_answerable=true` only if the answer can be derived from the data payload above (financials, transcripts, filing excerpts, EDGAR facts, counterparty context) without external research. Priority 1 = thesis-load-bearing; 2 = important context; 3 = nice-to-have. Empty list is fine if nothing is unresolved.
```

The instruction lives next to the existing key_findings instruction; both are emitted by the same Sonnet call.

- [ ] **Step 3: Locate the deep-dive merge step**

```bash
grep -n "phase_outputs\[result.category\]\|set_category_result\|node_deep_dive" backend/app/graph/nodes.py | head -10
```

Find the place inside `node_deep_dive` where each `CategoryResult` is folded back into state (typically a loop over the 9 category Sonnet calls' results).

- [ ] **Step 4: Stage extracted questions onto state**

Inside the merge loop, after each `result` is processed and added to `phase_outputs`, append:

```python
            structured = result.structured or {}
            for raw_q in structured.get("questions", []) or []:
                state.questions_extracted.append(StateQuestion(
                    category=result.category,
                    question_text=raw_q["question_text"],
                    priority=int(raw_q["priority"]),
                    auto_answerable=bool(raw_q["auto_answerable"]),
                ).to_dict())
```

If `StateQuestion` isn't imported at the top of `nodes.py` yet, add to the existing imports:

```python
from backend.app.graph.state import (
    # ...existing imports...
    StateQuestion,
    StateResolvedQuestion,
)
```

- [ ] **Step 5: Add a helper that persists staged questions to the DB**

Add this helper at the bottom of `nodes.py` (or in a logical spot near other persistence helpers):

```python
async def _persist_extracted_questions(state: ResearchState) -> None:
    """After deep_dive merges, write staged questions to the DB.

    Note: Question.id, theme_id, created_run_id are all UUID(as_uuid=False)
    columns — strings at Python level. State already holds them as strings."""
    from backend.app.db import async_session
    from backend.app.models.question import Question

    if not state.questions_extracted:
        return

    async with async_session() as db:
        for staged in state.questions_extracted:
            q = Question(
                ticker=state.ticker,
                theme_id=state.theme_id or None,
                category=staged["category"],
                question_text=staged["question_text"],
                priority=staged["priority"],
                auto_answerable=staged["auto_answerable"],
                status="open",
                created_run_id=state.run_id,
            )
            db.add(q)
        await db.commit()
    # Clear staging once persisted; the IDs are in the DB now
    state.questions_extracted = []
```

- [ ] **Step 6: Call the helper at the end of `node_deep_dive`**

Inside `node_deep_dive`, after the merge loop completes and before the function returns the updated state, add:

```python
    await _persist_extracted_questions(state)
```

- [ ] **Step 7: Syntax check**

```bash
backend/venv/bin/python -c "import ast; ast.parse(open('backend/app/graph/nodes.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/app/graph/nodes.py
git commit -m "$(cat <<'EOF'
feat(questions): extract + persist questions in node_deep_dive

Sonnet emits up to 3 questions per category as part of structured
output; merge step stages them on state and a new helper writes
to the questions table after all 9 categories return.
EOF
)"
```

---

## Task 6: Cross-run resurfacing — query + prompt slot + resolution merge

**Files:**
- Modify: `backend/app/graph/nodes.py`

Open priority-1/2 questions from prior runs are pulled per category before each Sonnet call, rendered into a `{prior_questions}` prompt slot, and any `resolved_questions[]` Sonnet emits flips those rows to `resolved_inline`.

- [ ] **Step 1: Add the prior-questions query helper**

Add near `_persist_extracted_questions`:

```python
async def _fetch_prior_open_questions(
    ticker: str,
    category: str,
    limit: int = 5,
) -> list[dict]:
    """Top open priority-1/2 questions for (ticker, category) ordered most-recent first.

    Returns list of {id, question_text, priority, created_at_iso} dicts.
    Caller renders these into the {prior_questions} slot."""
    from backend.app.db import async_session
    from backend.app.models.question import Question
    from sqlalchemy import select

    async with async_session() as db:
        stmt = (
            select(Question)
            .where(Question.ticker == ticker)
            .where(Question.category == category)
            .where(Question.status == "open")
            .where(Question.priority.in_([1, 2]))
            .order_by(Question.created_at.desc())
            .limit(limit)
        )
        rows = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": str(r.id),
            "question_text": r.question_text,
            "priority": r.priority,
            "created_at_iso": r.created_at.isoformat() if r.created_at else "",
        }
        for r in rows
    ]
```

- [ ] **Step 2: Add a renderer for the prompt slot**

Add immediately after the query helper:

```python
def _render_prior_questions_slot(prior: list[dict]) -> str:
    """Render the {prior_questions} prompt block. Empty string when no priors."""
    if not prior:
        return ""
    lines = [
        "PREVIOUSLY UNRESOLVED QUESTIONS FOR THIS PILLAR.",
        "If the current data permits answering them, emit them in `resolved_questions` "
        "with `question_id` and `answer_text`. Otherwise, you may restate them — "
        "that's signal they're genuinely hard.",
        "",
    ]
    for q in prior:
        lines.append(f"- [{q['id']}] (P{q['priority']}) {q['question_text']}")
    lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 3: Plumb the slot into the deep-dive prompt**

Find the spot in `node_deep_dive` where each category's user prompt is built (`DEEP_DIVE_USER.format(...)` or similar). Add `prior_questions=` to the format kwargs:

```python
prior = await _fetch_prior_open_questions(state.ticker, category_display_name)
user_prompt = DEEP_DIVE_USER.format(
    # ...existing kwargs...
    prior_questions=_render_prior_questions_slot(prior),
)
```

If `DEEP_DIVE_USER` doesn't currently contain a `{prior_questions}` placeholder, add it to the template string. Position it immediately after the existing `{counterparty_context}` slot (per spec Section "Cross-run resurfacing").

- [ ] **Step 4: Persist resolved questions on merge**

Inside the deep-dive merge loop (same place where `questions[]` are staged in Task 5), after the staging block, append:

```python
            for raw_rq in structured.get("resolved_questions", []) or []:
                state.questions_resolved_this_run.append(StateResolvedQuestion(
                    question_text=f"[{raw_rq['question_id']}] (resurfaced)",
                    answer_text=raw_rq["answer_text"],
                    source="deep_dive_resurfaced",
                ).to_dict())
```

The `[uuid] (resurfaced)` form for `question_text` is intentional — the actual question text is in the DB row keyed by UUID; the resolved-question state entry is just enough for `node_thesis_construction` to render a "questions resolved this run" block. The DB row is updated by the helper in the next step, which has the canonical text.

- [ ] **Step 5: Add a helper to apply resolutions to the DB**

After `_persist_extracted_questions`, add:

```python
async def _apply_resurfaced_resolutions(state: ResearchState) -> None:
    """Mark resurfaced questions as resolved_inline in the DB.

    Reads the freshly-merged state.phase_outputs to find each category's
    resolved_questions list, then updates the corresponding question rows.
    Question IDs and run IDs are strings (UUID(as_uuid=False))."""
    from backend.app.db import async_session
    from backend.app.models.question import Question
    from sqlalchemy import update
    from uuid import UUID

    resolutions: list[tuple[str, str]] = []  # (question_id, answer_text)
    for category, payload in state.phase_outputs.items():
        if not isinstance(payload, dict):
            continue
        if payload.get("__type__") != "CategoryResult":
            continue
        structured = payload.get("structured") or {}
        for rq in structured.get("resolved_questions", []) or []:
            resolutions.append((rq["question_id"], rq["answer_text"]))

    if not resolutions:
        return

    async with async_session() as db:
        for qid_str, answer in resolutions:
            # Validate that the LLM emitted a real UUID; skip junk
            try:
                UUID(qid_str)
            except (ValueError, TypeError):
                continue
            stmt = (
                update(Question)
                .where(Question.id == qid_str)
                .where(Question.status == "open")
                .values(
                    status="resolved_inline",
                    answer_text=answer,
                    answer_source="deep_dive_resurfaced",
                    resolved_run_id=state.run_id,
                    resolved_at=datetime.now(timezone.utc),
                )
            )
            await db.execute(stmt)
        await db.commit()
```

If `datetime` and `timezone` aren't imported in `nodes.py` already, add `from datetime import datetime, timezone`.

- [ ] **Step 6: Call the resolution helper at end of `node_deep_dive`**

Right after the existing `await _persist_extracted_questions(state)` call:

```python
    await _apply_resurfaced_resolutions(state)
```

- [ ] **Step 7: Syntax check**

```bash
backend/venv/bin/python -c "import ast; ast.parse(open('backend/app/graph/nodes.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/app/graph/nodes.py
git commit -m "$(cat <<'EOF'
feat(questions): cross-run resurfacing in deep-dive prompts

Open priority-1/2 questions from prior runs inject into each
category's prompt; Sonnet emits resolved_questions[] which flip
those rows to resolved_inline at merge time.
EOF
)"
```

---

## Task 7: `node_targeted_followup` — auto-resolve priority-1 questions

**Files:**
- Modify: `backend/app/graph/nodes.py`

New pipeline node between `deep_dive` and `thesis_construction`. Picks ≤3 newly-extracted priority-1 + auto_answerable questions and resolves them with focused Sonnet calls.

- [ ] **Step 1: Add the targeted-followup Pydantic schema**

Add near the other `BaseModel` classes:

```python
class TargetedAnswer(BaseModel):
    """Sonnet response to a single targeted-followup question."""
    answer_text: str = Field(
        description="Concise answer using only the data payload provided. "
        "If data is insufficient, say so explicitly rather than speculating."
    )
```

- [ ] **Step 2: Add the system prompt constant**

```python
TARGETED_FOLLOWUP_SYSTEM = """You are a senior equity research analyst answering ONE specific question that surfaced during deep-dive analysis. You have:

- The original category's key findings
- The same data payload the original analyst saw (financials, filing excerpts, transcripts, EDGAR facts, counterparty context as relevant)

Answer the question concisely (3-5 sentences). Cite specific numbers, quotes, or filing line items. If the data is insufficient to answer, say so explicitly rather than speculating — that is itself a useful answer."""
```

- [ ] **Step 3: Add the node implementation**

Add after `node_deep_dive`:

```python
async def node_targeted_followup(state: ResearchState) -> ResearchState:
    """Tier 1.2 targeted second-pass.

    Picks ≤3 priority-1 + auto_answerable questions created this run,
    runs them in parallel through focused Sonnet calls, persists answers
    back to the questions table, and stages StateResolvedQuestion entries
    for node_thesis_construction to see."""
    from backend.app.db import async_session
    from backend.app.graph.llm import SONNET, complete
    from backend.app.models.question import Question
    from sqlalchemy import select, update
    import asyncio

    state.phase = "targeted_followup"

    # 1. Pick eligible questions (priority-1 + auto_answerable + open + this run).
    #    All ID columns are UUID(as_uuid=False) — strings at Python level.
    async with async_session() as db:
        stmt = (
            select(Question)
            .where(Question.created_run_id == state.run_id)
            .where(Question.priority == 1)
            .where(Question.auto_answerable.is_(True))
            .where(Question.status == "open")
            .order_by(Question.category.asc(), Question.created_at.asc())
            .limit(3)
        )
        eligible = (await db.execute(stmt)).scalars().all()
        # Snapshot fields we need; row objects expire after the session closes
        snapshots = [
            {
                "id": q.id,
                "category": q.category,
                "question_text": q.question_text,
            }
            for q in eligible
        ]

    if not snapshots:
        state.status = "in_progress"
        return state

    # 2. Build context for each question — the originating category's findings
    deep = state.get_deep_dive_results()

    async def _answer_one(snap: dict) -> tuple[str, str]:
        cat = snap["category"]
        result = deep.get(cat)
        findings_block = ""
        if result is not None and hasattr(result, "key_findings"):
            findings_block = "\n".join(f"- {f}" for f in result.key_findings or [])
            content = getattr(result, "content", "") or ""
        else:
            content = ""

        user_msg = (
            f"Question: {snap['question_text']}\n\n"
            f"Originating category: {cat}\n\n"
            f"Key findings from that category's deep-dive:\n{findings_block or '(none)'}\n\n"
            f"Full category analysis:\n{content[:6000]}\n"
        )

        try:
            raw = await complete(
                model=SONNET,
                system=TARGETED_FOLLOWUP_SYSTEM,
                user=user_msg,
                max_tokens=600,
                assistant_prefill='{"answer_text":',
            )
            parsed = TargetedAnswer.model_validate_json(raw)
            answer = parsed.answer_text
        except Exception as e:  # noqa: BLE001
            logger.exception("targeted_followup failed for question %s", snap["id"])
            answer = f"[Targeted follow-up failed: {type(e).__name__}]"
        return snap["id"], answer

    # 3. Run all three in parallel
    answers = await asyncio.gather(*(_answer_one(s) for s in snapshots))

    # 4. Persist answers + stage for thesis prompt
    async with async_session() as db:
        for qid, answer in answers:
            stmt = (
                update(Question)
                .where(Question.id == qid)
                .where(Question.status == "open")
                .values(
                    status="resolved_auto",
                    answer_text=answer,
                    answer_source="targeted_followup",
                    resolved_run_id=state.run_id,
                    resolved_at=datetime.now(timezone.utc),
                )
            )
            await db.execute(stmt)
        await db.commit()

    # Stage resolved-this-run entries for thesis prompt (use original question text)
    for snap, (_, answer) in zip(snapshots, answers):
        state.questions_resolved_this_run.append(StateResolvedQuestion(
            question_text=snap["question_text"],
            answer_text=answer,
            source="targeted_followup",
        ).to_dict())

    state.status = "in_progress"
    return state
```

- [ ] **Step 4: Confirm `logger` is imported**

```bash
grep -n "^logger = \|^import logging" backend/app/graph/nodes.py | head -3
```

If not present at module scope, add at the top: `import logging` and `logger = logging.getLogger(__name__)`.

- [ ] **Step 5: Syntax check**

```bash
backend/venv/bin/python -c "import ast; ast.parse(open('backend/app/graph/nodes.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/nodes.py
git commit -m "$(cat <<'EOF'
feat(questions): node_targeted_followup auto-resolves priority-1 questions

Picks <=3 priority-1 + auto_answerable questions per run, runs them
in parallel through focused Sonnet calls with the originating
category's findings + analysis, persists answers as resolved_auto.
EOF
)"
```

---

## Task 8: Wire `targeted_followup` into the LangGraph + pipeline service

**Files:**
- Modify: `backend/app/graph/pipeline.py`
- Modify: `backend/app/services/pipeline.py`

- [ ] **Step 1: Add the wrapper in `pipeline.py`**

Inside `build_research_graph` (around line 40-60), after the `deep_dive` async wrapper, add:

```python
    async def targeted_followup(state: dict) -> dict:
        rs = ResearchState.from_dict(state)
        rs = await nodes.node_targeted_followup(rs)
        return rs.to_dict()
```

- [ ] **Step 2: Update `after_deep_dive` to route to the new node**

Find the existing `after_deep_dive` router (around line 78) and change its return value:

```python
    def after_deep_dive(state: dict) -> Literal["targeted_followup", "__end__"]:
        status = state.get("status", "in_progress")
        if status in ("watchlist", "pass", "completed"):
            return END
        if status == "awaiting_approval":
            return END
        return "targeted_followup"
```

- [ ] **Step 3: Add `after_targeted_followup` router**

Right after `after_deep_dive`:

```python
    def after_targeted_followup(state: dict) -> Literal["thesis_construction", "__end__"]:
        status = state.get("status", "in_progress")
        if status in ("watchlist", "pass", "completed"):
            return END
        if status == "awaiting_approval":
            return END
        return "thesis_construction"
```

- [ ] **Step 4: Register the node + edges in the builder**

After `builder.add_node("deep_dive", deep_dive)` (around line 117), insert:

```python
    builder.add_node("targeted_followup", targeted_followup)
```

Then in the conditional-edge block (around line 124), insert `after_deep_dive` as before, and add:

```python
    builder.add_conditional_edges("targeted_followup", after_targeted_followup)
```

- [ ] **Step 5: Update `_next_phase` in `services/pipeline.py`**

Change the `phase_sequence` dict (line 166):

```python
        phase_sequence = {
            "quick_screen": "deep_dive",
            "deep_dive": "targeted_followup",
            "targeted_followup": "thesis_construction",
            "thesis_construction": "risk_stress_test",
            "risk_stress_test": (
                "deep_dive" if (state.loop_context and state.loop_count <= 2)
                else "completed"
            ),
        }
```

- [ ] **Step 6: Syntax check**

```bash
backend/venv/bin/python -c "import ast; ast.parse(open('backend/app/graph/pipeline.py').read()); ast.parse(open('backend/app/services/pipeline.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 7: Verify graph compiles**

```bash
backend/venv/bin/python -c "from backend.app.graph.pipeline import build_research_graph; from backend.app.clients.fmp_client import FMPClient; build_research_graph(FMPClient()); print('OK')"
```

Expected: `OK`. If it fails because `FMPClient()` requires args, replace with the actual instantiation pattern used elsewhere (check `backend/app/main.py` for the live instantiation).

- [ ] **Step 8: Commit**

```bash
git add backend/app/graph/pipeline.py backend/app/services/pipeline.py
git commit -m "$(cat <<'EOF'
feat(questions): wire node_targeted_followup between deep_dive and thesis

Adds new graph node + conditional edges; updates _next_phase
in services/pipeline.py (parallel source of truth per CLAUDE.md).
EOF
)"
```

---

## Task 9: Thesis prompt — `{questions_resolved}` slot

**Files:**
- Modify: `backend/app/graph/nodes.py`

`node_thesis_construction` already builds a Sonnet user prompt from category outputs. Add a `{questions_resolved}` slot rendered from `state.questions_resolved_this_run`.

- [ ] **Step 1: Locate the thesis user-prompt template**

```bash
grep -n "THESIS_USER\|node_thesis_construction" backend/app/graph/nodes.py | head -10
```

Find the multi-line template (likely `THESIS_USER = """..."""`).

- [ ] **Step 2: Add the slot to the template**

Insert a `{questions_resolved}` placeholder in the template, positioned right before the closing instructions where the model is asked to produce the thesis. Surround with a clear header line, e.g.:

```python
THESIS_USER = """...

QUESTIONS ANSWERED THIS RUN
{questions_resolved}

Now produce the thesis output...
"""
```

- [ ] **Step 3: Add a renderer function**

Add near the other prompt-building helpers in `nodes.py`:

```python
def _render_questions_resolved(staged: list[dict]) -> str:
    """Render state.questions_resolved_this_run for the thesis prompt slot."""
    if not staged:
        return "(none this run)"
    lines = []
    for entry in staged:
        src = entry.get("source", "?")
        text = entry.get("question_text", "?")
        ans = entry.get("answer_text", "?")
        lines.append(f"- [{src}] Q: {text}\n  A: {ans}")
    return "\n".join(lines)
```

- [ ] **Step 4: Wire it into `node_thesis_construction`**

In the `format(...)` call that builds the thesis user prompt, add:

```python
questions_resolved=_render_questions_resolved(state.questions_resolved_this_run),
```

- [ ] **Step 5: Syntax check**

```bash
backend/venv/bin/python -c "import ast; ast.parse(open('backend/app/graph/nodes.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/app/graph/nodes.py
git commit -m "$(cat <<'EOF'
feat(questions): thesis prompt slot for questions resolved this run

Adds {questions_resolved} block to THESIS_USER rendered from
state.questions_resolved_this_run; thesis sees both targeted_followup
and resurfaced answers as supporting context.
EOF
)"
```

---

## Task 10: `services/questions.py` — query helpers + retry-auto

**Files:**
- Create: `backend/app/services/questions.py`

- [ ] **Step 1: Write the service module**

```python
"""Questions service — query helpers + on-demand retry-auto orchestration.

Mirrors the read_through.py / status_board.py pattern: thin DB queries
that the API layer calls; LLM orchestration kept here so api/questions.py
stays HTTP-shape only.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.graph.llm import SONNET, complete
from backend.app.graph.state import ResearchState
from backend.app.models.question import Question
from backend.app.models.research_run import ResearchRun

logger = logging.getLogger(__name__)


# ── Query helpers ────────────────────────────────────────────────────────────


async def list_questions(
    db: AsyncSession,
    *,
    ticker: str | None = None,
    theme_id: UUID | None = None,
    status: str | None = "open",
    priority: int | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[Question]:
    stmt = select(Question)
    if ticker:
        stmt = stmt.where(Question.ticker == ticker.upper())
    if theme_id is not None:
        stmt = stmt.where(Question.theme_id == theme_id)
    if status:
        stmt = stmt.where(Question.status == status)
    if priority is not None:
        stmt = stmt.where(Question.priority == priority)
    if category:
        stmt = stmt.where(Question.category == category)
    stmt = stmt.order_by(Question.priority.asc(), Question.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return list(rows)


async def by_ticker_rollup(
    db: AsyncSession,
    *,
    theme_id: UUID | None = None,
) -> list[dict]:
    p1 = func.count(case((Question.priority == 1, 1), else_=None)).label("p1_count")
    p2 = func.count(case((Question.priority == 2, 1), else_=None)).label("p2_count")
    p3 = func.count(case((Question.priority == 3, 1), else_=None)).label("p3_count")
    total = func.count(Question.id).label("open_count")

    stmt = (
        select(Question.ticker, p1, p2, p3, total)
        .where(Question.status == "open")
        .group_by(Question.ticker)
        .order_by(p1.desc(), total.desc())
    )
    if theme_id is not None:
        stmt = stmt.where(Question.theme_id == theme_id)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "ticker": ticker,
            "p1_count": int(p1c),
            "p2_count": int(p2c),
            "p3_count": int(p3c),
            "open_count": int(total),
        }
        for ticker, p1c, p2c, p3c, total in rows
    ]


# ── Retry-auto: rerun targeted-followup logic for one question ───────────────


class _RetryAnswer(BaseModel):
    answer_text: str = Field(description="Concise answer using current data.")


_RETRY_SYSTEM = """You are a senior equity research analyst answering ONE specific question about a public company. The question previously surfaced during a deep-dive but was not auto-resolved. The user has explicitly asked you to retry.

Answer concisely (3-5 sentences). Cite specific numbers, quotes, or filing line items where possible. If the data available is insufficient, say so explicitly — that is a useful answer."""


async def retry_auto_answer(
    db: AsyncSession,
    question: Question,
) -> Question:
    """On-demand: rerun a focused Sonnet call for one question, regardless
    of its auto_answerable flag. Idempotent guard: only operates on
    open questions; raises ValueError otherwise."""
    if question.status != "open":
        raise ValueError(f"question {question.id} is not open (status={question.status!r})")

    run_stmt = select(ResearchRun).where(ResearchRun.id == question.created_run_id)
    run = (await db.execute(run_stmt)).scalar_one_or_none()
    if run is None:
        raise ValueError(f"originating run {question.created_run_id} not found")

    # Pull category findings from the run's persisted state
    rs = ResearchState.from_dict(run.state) if isinstance(run.state, dict) else None
    findings_block = "(no findings on file)"
    content = ""
    if rs is not None:
        deep = rs.get_deep_dive_results()
        result = deep.get(question.category)
        if result is not None and hasattr(result, "key_findings"):
            findings_block = "\n".join(f"- {f}" for f in (result.key_findings or [])) or "(none)"
            content = (getattr(result, "content", "") or "")[:6000]

    user_msg = (
        f"Question: {question.question_text}\n\n"
        f"Originating category: {question.category}\n\n"
        f"Key findings from that category's deep-dive:\n{findings_block}\n\n"
        f"Full category analysis:\n{content}\n"
    )

    try:
        raw = await complete(
            model=SONNET,
            system=_RETRY_SYSTEM,
            user=user_msg,
            max_tokens=600,
            assistant_prefill='{"answer_text":',
        )
        parsed = _RetryAnswer.model_validate_json(raw)
        answer = parsed.answer_text
    except Exception as e:  # noqa: BLE001
        logger.exception("retry_auto failed for question %s", question.id)
        raise RuntimeError(f"Sonnet error: {type(e).__name__}") from e

    stmt = (
        update(Question)
        .where(Question.id == question.id)
        .where(Question.status == "open")
        .values(
            status="resolved_auto",
            answer_text=answer,
            answer_source="targeted_followup",
            resolved_at=datetime.now(timezone.utc),
            # resolved_run_id stays None — retries aren't tied to a run
        )
        .returning(Question.id)
    )
    res = await db.execute(stmt)
    if res.scalar_one_or_none() is None:
        raise ValueError(f"question {question.id} was concurrently resolved")
    await db.commit()
    await db.refresh(question)
    return question
```

- [ ] **Step 2: Syntax check**

```bash
backend/venv/bin/python -c "import ast; ast.parse(open('backend/app/services/questions.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Import check**

```bash
backend/venv/bin/python -c "from backend.app.services.questions import list_questions, by_ticker_rollup, retry_auto_answer; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/questions.py
git commit -m "$(cat <<'EOF'
feat(questions): services layer with list/rollup/retry-auto helpers

Mirrors read_through.py / status_board.py pattern. retry_auto_answer
re-runs a focused Sonnet call for one question on demand, bypassing
the priority-1 + auto_answerable filter that node_targeted_followup
applies during the pipeline.
EOF
)"
```

---

## Task 11: `api/questions.py` — 5 endpoints

**Files:**
- Create: `backend/app/api/questions.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the API router**

```python
"""Questions API — Tier 1.2 question log + targeted second-pass.

CRITICAL: do NOT add `from __future__ import annotations` to this module.
FastAPI 0.115 + Python 3.12 evaluates `-> None` returns as the string
"None" and trips an internal assertion when the future import is
present. Same constraint applied to api/status.py and api/read_through.py.
"""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.question import Question
from backend.app.services.questions import (
    by_ticker_rollup,
    list_questions,
    retry_auto_answer,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/questions", tags=["questions"])


# ── Response models ──────────────────────────────────────────────────────────


class QuestionResponse(BaseModel):
    id: str
    ticker: str
    theme_id: Optional[str]
    category: str
    question_text: str
    priority: int
    auto_answerable: bool
    status: str
    answer_text: Optional[str]
    answer_source: Optional[str]
    created_run_id: str
    resolved_run_id: Optional[str]
    created_at: str
    resolved_at: Optional[str]
    dismissed_at: Optional[str]
    dismiss_note: Optional[str]


def _serialize(q: Question) -> QuestionResponse:
    return QuestionResponse(
        id=str(q.id),
        ticker=q.ticker,
        theme_id=str(q.theme_id) if q.theme_id else None,
        category=q.category,
        question_text=q.question_text,
        priority=q.priority,
        auto_answerable=q.auto_answerable,
        status=q.status,
        answer_text=q.answer_text,
        answer_source=q.answer_source,
        created_run_id=str(q.created_run_id),
        resolved_run_id=str(q.resolved_run_id) if q.resolved_run_id else None,
        created_at=q.created_at.isoformat() if q.created_at else "",
        resolved_at=q.resolved_at.isoformat() if q.resolved_at else None,
        dismissed_at=q.dismissed_at.isoformat() if q.dismissed_at else None,
        dismiss_note=q.dismiss_note,
    )


class QuestionListResponse(BaseModel):
    questions: list[QuestionResponse]


class TickerRollupRow(BaseModel):
    ticker: str
    p1_count: int
    p2_count: int
    p3_count: int
    open_count: int


class TickerRollupResponse(BaseModel):
    tickers: list[TickerRollupRow]


class DismissBody(BaseModel):
    note: Optional[str] = Field(default=None, max_length=2000)


class ResolveBody(BaseModel):
    answer_text: str = Field(min_length=1, max_length=10000)


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=QuestionListResponse)
async def list_questions_endpoint(
    ticker: Optional[str] = None,
    theme_id: Optional[UUID] = None,
    status: Optional[str] = "open",
    priority: Optional[int] = None,
    category: Optional[str] = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> QuestionListResponse:
    rows = await list_questions(
        db,
        ticker=ticker,
        theme_id=theme_id,
        status=status,
        priority=priority,
        category=category,
        limit=min(limit, 500),
    )
    return QuestionListResponse(questions=[_serialize(r) for r in rows])


@router.get("/by-ticker", response_model=TickerRollupResponse)
async def by_ticker_endpoint(
    theme_id: Optional[UUID] = None,
    db: AsyncSession = Depends(get_db),
) -> TickerRollupResponse:
    rows = await by_ticker_rollup(db, theme_id=theme_id)
    return TickerRollupResponse(tickers=[TickerRollupRow(**r) for r in rows])


@router.post("/{question_id}/dismiss", response_model=QuestionResponse)
async def dismiss_endpoint(
    question_id: UUID,
    body: DismissBody,
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "question not found")
    if q.status != "open":
        raise HTTPException(409, f"question is {q.status}, cannot dismiss")

    stmt = (
        update(Question)
        .where(Question.id == question_id)
        .where(Question.status == "open")
        .values(
            status="dismissed",
            dismissed_at=datetime.now(timezone.utc),
            dismiss_note=body.note,
        )
        .returning(Question.id)
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(409, "question was concurrently modified")
    await db.commit()
    await db.refresh(q)
    return _serialize(q)


@router.post("/{question_id}/resolve", response_model=QuestionResponse)
async def resolve_endpoint(
    question_id: UUID,
    body: ResolveBody,
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "question not found")
    if q.status != "open":
        raise HTTPException(409, f"question is {q.status}, cannot resolve")

    stmt = (
        update(Question)
        .where(Question.id == question_id)
        .where(Question.status == "open")
        .values(
            status="resolved_manual",
            answer_text=body.answer_text,
            answer_source="manual",
            resolved_at=datetime.now(timezone.utc),
        )
        .returning(Question.id)
    )
    if (await db.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(409, "question was concurrently modified")
    await db.commit()
    await db.refresh(q)
    return _serialize(q)


@router.post("/{question_id}/retry-auto", response_model=QuestionResponse)
async def retry_auto_endpoint(
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> QuestionResponse:
    q = (await db.execute(select(Question).where(Question.id == question_id))).scalar_one_or_none()
    if q is None:
        raise HTTPException(404, "question not found")
    try:
        updated = await retry_auto_answer(db, q)
    except ValueError as e:
        raise HTTPException(409, str(e))
    except RuntimeError as e:
        logger.exception("retry-auto Sonnet failure for %s", question_id)
        raise HTTPException(502, str(e))
    return _serialize(updated)
```

- [ ] **Step 2: Register router in `main.py`**

In `backend/app/main.py`, add to the import block (around line 14-23):

```python
from backend.app.api.questions import router as questions_router
```

And in the include_router block (around line 122-131):

```python
app.include_router(questions_router, prefix="/api")
```

- [ ] **Step 3: Boot smoke**

```bash
cd /Users/ericwyluda/Development/projects/sector-research && backend/venv/bin/python -c "from backend.app.main import app; routes = [r.path for r in app.routes]; print([p for p in routes if 'question' in p])"
```

Expected: list including `/api/questions`, `/api/questions/by-ticker`, `/api/questions/{question_id}/dismiss`, `/api/questions/{question_id}/resolve`, `/api/questions/{question_id}/retry-auto`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/questions.py backend/app/main.py
git commit -m "$(cat <<'EOF'
feat(questions): API router with 5 endpoints

GET / list, GET /by-ticker rollup, POST /{id}/dismiss, /resolve,
/retry-auto. Deliberately omits __future__ import (FastAPI 0.115
+ Python 3.12 footgun documented in api/status.py and
api/read_through.py).
EOF
)"
```

---

## Task 12: Extend report endpoint with `questions[]`

**Files:**
- Modify: `backend/app/api/pipeline.py`

The per-run page already calls `GET /api/runs/{id}/report`. Adding `questions: Question[]` to the response lets the per-run "Open Questions" panel render in one fetch.

- [ ] **Step 1: Locate the report endpoint**

```bash
grep -n "/runs/.*/report\|def get_report\|response_model.*Report" backend/app/api/pipeline.py | head -10
```

Find the report endpoint handler and its response model.

- [ ] **Step 2: Add `questions` to the response shape**

Inside the response Pydantic model (likely `ReportResponse` or similar), add:

```python
    questions: list[QuestionResponse] = Field(default_factory=list)
```

Add the import at the top:

```python
from backend.app.api.questions import QuestionResponse, _serialize as _serialize_question
```

- [ ] **Step 3: Populate it in the handler**

Inside the handler, after the existing fields are populated:

```python
    q_stmt = (
        select(Question)
        .where(
            (Question.created_run_id == run_id) | (Question.resolved_run_id == run_id)
        )
        .order_by(Question.priority.asc(), Question.created_at.desc())
    )
    q_rows = (await db.execute(q_stmt)).scalars().all()
    response.questions = [_serialize_question(q) for q in q_rows]
```

If the handler returns a `dict` (not a Pydantic instance), set the key on the dict instead. The exact shape depends on how the existing handler is structured — check it before pasting.

Add the import:

```python
from backend.app.models.question import Question
```

- [ ] **Step 4: Boot smoke**

```bash
cd /Users/ericwyluda/Development/projects/sector-research && backend/venv/bin/python -c "from backend.app.main import app; print('OK')"
```

Expected: `OK` (no import errors).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/pipeline.py
git commit -m "$(cat <<'EOF'
feat(questions): include questions[] in run report payload

Returns all questions linked to this run via either created_run_id
or resolved_run_id so the per-run panel renders in one fetch.
EOF
)"
```

---

## Task 13: Smoke script — full extraction → followup → dismiss → resurface loop

**Files:**
- Create: `backend/scripts/smoke_question_log.py`

- [ ] **Step 1: Write the smoke script**

```python
"""Smoke test for Tier 1.2 question log.

Exercises:
1. Direct DB persist of synthetic extracted questions (mimics deep_dive merge)
2. node_targeted_followup against the synthetic run (Sonnet mocked)
3. Manual dismiss endpoint logic
4. Cross-run resurfacing query

Cleans up synthetic rows on success AND on caught exceptions.

Run:
    PYTHONPATH=. backend/venv/bin/python backend/scripts/smoke_question_log.py
"""
import asyncio
import sys
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

from backend.app.db import async_session
from backend.app.graph import nodes
from backend.app.graph.state import ResearchState
from backend.app.models.question import Question
from backend.app.models.research_run import ResearchRun
from sqlalchemy import select, delete

SYNTH_TICKER = "ZZZQ"


async def _seed_synthetic_run() -> str:
    """Create a minimal ResearchRun row so questions can FK to it.

    Returns the run_id as a string. ResearchRun.theme_id is NOT NULL so we
    pick the first existing theme at runtime; if no themes exist, the smoke
    bails out (a fresh DB is not a supported test substrate)."""
    from backend.app.models.theme import Theme
    async with async_session() as db:
        first_theme = (await db.execute(select(Theme).limit(1))).scalar_one_or_none()
        if first_theme is None:
            raise ValueError("no themes in DB; smoke needs at least one theme to FK against")
        run_id = str(uuid4())
        run = ResearchRun(
            id=run_id,
            ticker=SYNTH_TICKER,
            theme_id=first_theme.id,
            status="completed",
            phase="completed",
            state={"ticker": SYNTH_TICKER, "theme_id": "", "run_id": run_id, "phase_outputs": {}},
        )
        db.add(run)
        await db.commit()
        return run_id


async def _persist_extracted(run_id: str, items: list[dict]) -> list[str]:
    ids: list[str] = []
    async with async_session() as db:
        for it in items:
            q = Question(
                ticker=SYNTH_TICKER,
                theme_id=None,
                category=it["category"],
                question_text=it["text"],
                priority=it["priority"],
                auto_answerable=it["auto_answerable"],
                status="open",
                created_run_id=run_id,
            )
            db.add(q)
            await db.flush()
            ids.append(q.id)
        await db.commit()
    return ids


async def _cleanup(run_id: str) -> None:
    async with async_session() as db:
        await db.execute(delete(Question).where(Question.ticker == SYNTH_TICKER))
        await db.execute(delete(ResearchRun).where(ResearchRun.id == run_id))
        await db.commit()


async def _mock_complete(*args, **kwargs):
    """Return a JSON string matching the TargetedAnswer schema; the assistant_prefill
    ('{"answer_text":') is already included because complete() prepends it back."""
    return '{"answer_text": "MOCK_ANSWER: data shows X."}'


async def main() -> None:
    print("== Tier 1.2 question log smoke ==")
    run_id = await _seed_synthetic_run()
    try:
        # 1. Synthesize extraction: P1+auto and P3+not
        ids = await _persist_extracted(run_id, [
            {"category": "Macro & Regime", "text": "P1 auto Q?", "priority": 1, "auto_answerable": True},
            {"category": "Macro & Regime", "text": "P3 manual Q?", "priority": 3, "auto_answerable": False},
        ])
        p1_id, p3_id = ids
        print(f"  ✓ persisted 2 synthetic questions ({p1_id}, {p3_id})")

        # 2. Run node_targeted_followup with Sonnet mocked
        state = ResearchState(
            ticker=SYNTH_TICKER, theme_id="", run_id=str(run_id),
            phase="targeted_followup",
        )
        # Mock the deep-dive results so the node has context
        from backend.app.graph.state import CategoryResult
        cat_result = CategoryResult(
            category="Macro & Regime",
            content="Mock category content.",
            score=70,
            key_findings=["finding 1", "finding 2"],
        )
        state.phase_outputs["Macro & Regime"] = cat_result.to_dict()

        with patch("backend.app.graph.llm.complete", _mock_complete):
            new_state = await nodes.node_targeted_followup(state)

        # Assert priority-1 row resolved_auto
        async with async_session() as db:
            p1 = (await db.execute(select(Question).where(Question.id == p1_id))).scalar_one()
            assert p1.status == "resolved_auto", f"expected resolved_auto, got {p1.status}"
            assert p1.answer_text and "MOCK_ANSWER" in p1.answer_text, "answer_text not populated"
            assert p1.answer_source == "targeted_followup"
            print(f"  ✓ P1 resolved_auto by node_targeted_followup")

            p3 = (await db.execute(select(Question).where(Question.id == p3_id))).scalar_one()
            assert p3.status == "open", f"expected open, got {p3.status}"
            print(f"  ✓ P3 still open (priority filter)")

        # Assert state.questions_resolved_this_run got the P1 entry
        assert len(new_state.questions_resolved_this_run) == 1
        assert "MOCK_ANSWER" in new_state.questions_resolved_this_run[0]["answer_text"]
        print(f"  ✓ state.questions_resolved_this_run staged for thesis prompt")

        # 3. Manual dismiss the P3 row (via DB, mimics endpoint)
        async with async_session() as db:
            p3 = (await db.execute(select(Question).where(Question.id == p3_id))).scalar_one()
            p3.status = "dismissed"
            p3.dismissed_at = datetime.now(timezone.utc)
            p3.dismiss_note = "smoke dismissal"
            await db.commit()
        print(f"  ✓ P3 dismissed")

        # 4. Synthesize a fresh open P2 question, then test cross-run resurfacing query
        await _persist_extracted(run_id, [
            {"category": "Macro & Regime", "text": "P2 fresh Q?", "priority": 2, "auto_answerable": False},
        ])

        prior = await nodes._fetch_prior_open_questions(SYNTH_TICKER, "Macro & Regime")
        assert len(prior) == 1, f"expected 1 prior open question, got {len(prior)}"
        assert prior[0]["question_text"] == "P2 fresh Q?"
        assert prior[0]["priority"] == 2
        print(f"  ✓ cross-run resurfacing query returns P2 only (P1 resolved, P3 dismissed)")

        rendered = nodes._render_prior_questions_slot(prior)
        assert "P2 fresh Q?" in rendered, "rendered slot missing question text"
        assert prior[0]["id"] in rendered, "rendered slot missing question id"
        print(f"  ✓ prior-questions prompt slot renders correctly")

        print("\n✅ Tier 1.2 smoke 4/4 PASS")
    except (AssertionError, ValueError) as e:
        print(f"\n❌ FAIL: {e}")
        await _cleanup(run_id)
        sys.exit(1)
    except Exception:
        await _cleanup(run_id)
        raise

    await _cleanup(run_id)
    print("✓ cleanup complete")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the smoke**

```bash
cd /Users/ericwyluda/Development/projects/sector-research && PYTHONPATH=. backend/venv/bin/python backend/scripts/smoke_question_log.py
```

Expected output ends with `✅ Tier 1.2 smoke 4/4 PASS` and `✓ cleanup complete`. If anything fails, the smoke prints the failure and cleans up the synthetic ZZZQ rows before exiting non-zero.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/smoke_question_log.py
git commit -m "$(cat <<'EOF'
feat(questions): smoke script for end-to-end question-log loop

Exercises persist → targeted_followup (Sonnet mocked) → dismiss →
cross-run resurfacing. Cleans up synthetic ZZZQ rows on success
and on caught ValueError/AssertionError.
EOF
)"
```

---

## Task 14: Frontend types + `questions` API client

**Files:**
- Modify: `frontend/lib/api.ts`

- [ ] **Step 1: Locate insertion point**

`lib/api.ts` ends at line ~1115 with the `readThroughs` client. Earnings types/client added during Tier 2.5 will be appended somewhere after that. Append the new types at the end of the file.

- [ ] **Step 2: Append types**

Append at the bottom of `frontend/lib/api.ts`:

```typescript
// ── Questions (Tier 1.2) ────────────────────────────────────────────────────

export type QuestionStatus =
  | "open"
  | "resolved_auto"
  | "resolved_inline"
  | "resolved_manual"
  | "dismissed";

export type QuestionAnswerSource =
  | "targeted_followup"
  | "deep_dive_resurfaced"
  | "manual"
  | null;

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
  p1_count: number;
  p2_count: number;
  p3_count: number;
  open_count: number;
}

export const questions = {
  list: async (params: {
    ticker?: string;
    theme_id?: string;
    status?: QuestionStatus;
    priority?: 1 | 2 | 3;
    category?: string;
    limit?: number;
  } = {}): Promise<{ questions: Question[] }> => {
    const qs = new URLSearchParams();
    if (params.ticker) qs.set("ticker", params.ticker);
    if (params.theme_id) qs.set("theme_id", params.theme_id);
    if (params.status) qs.set("status", params.status);
    if (params.priority !== undefined) qs.set("priority", String(params.priority));
    if (params.category) qs.set("category", params.category);
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    return apiFetch<{ questions: Question[] }>(`/questions?${qs.toString()}`);
  },

  byTicker: async (params: { theme_id?: string } = {}): Promise<{ tickers: QuestionTickerRollup[] }> => {
    const qs = new URLSearchParams();
    if (params.theme_id) qs.set("theme_id", params.theme_id);
    return apiFetch<{ tickers: QuestionTickerRollup[] }>(`/questions/by-ticker?${qs.toString()}`);
  },

  dismiss: async (id: string, note?: string): Promise<Question> =>
    apiFetch<Question>(`/questions/${id}/dismiss`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),

  resolve: async (id: string, answer_text: string): Promise<Question> =>
    apiFetch<Question>(`/questions/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({ answer_text }),
    }),

  retryAuto: async (id: string): Promise<Question> =>
    apiFetch<Question>(`/questions/${id}/retry-auto`, { method: "POST" }),
};
```

- [ ] **Step 3: Extend the report payload type**

Find the existing report response type in `lib/api.ts` (search for the type that `pipeline.report(runId)` returns — likely `RunReport`, `ReportPayload`, or similar):

```bash
grep -n "RunReport\|interface Report\|pipeline\.report\|export.*Report" frontend/lib/api.ts | head -10
```

In that interface, add:

```typescript
  questions: Question[];
```

If `Question` isn't yet visible at that point in the file, define the type above the report interface or use a forward reference.

- [ ] **Step 4: TypeScript check**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: zero errors. If pre-existing errors (unrelated to this change) appear, ignore them; only fix errors that reference `Question`, `QuestionStatus`, or the file you just edited.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "$(cat <<'EOF'
feat(questions): typed frontend client + types for question log

Adds Question, QuestionTickerRollup types plus questions client
(list, byTicker, dismiss, resolve, retryAuto). Extends run report
payload with questions[].
EOF
)"
```

---

## Task 15: Per-run "Open Questions" panel

**Files:**
- Create: `frontend/components/questions/QuestionRow.tsx`
- Create: `frontend/components/questions/OpenQuestionsPanel.tsx`
- Modify: `frontend/app/pipeline/[runId]/page.tsx`

- [ ] **Step 1: Create the shared row component**

Write `frontend/components/questions/QuestionRow.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { Question } from "@/lib/api";
import { questions as questionsApi } from "@/lib/api";

const PRIORITY_CHIP: Record<1 | 2 | 3, string> = {
  1: "bg-rose-900/40 text-rose-200 border-rose-700/60",
  2: "bg-amber-900/40 text-amber-200 border-amber-700/60",
  3: "bg-slate-700/40 text-slate-300 border-slate-600/60",
};

const STATUS_CHIP: Record<string, string> = {
  open: "bg-amber-900/40 text-amber-200 border-amber-700/60",
  resolved_auto: "bg-emerald-900/40 text-emerald-200 border-emerald-700/60",
  resolved_inline: "bg-emerald-900/40 text-emerald-200 border-emerald-700/60",
  resolved_manual: "bg-emerald-900/40 text-emerald-200 border-emerald-700/60",
  dismissed: "bg-slate-700/40 text-slate-400 border-slate-600/60",
};

const STATUS_LABEL: Record<string, string> = {
  open: "Open",
  resolved_auto: "Auto-resolved",
  resolved_inline: "Resolved (next run)",
  resolved_manual: "Manually resolved",
  dismissed: "Dismissed",
};

interface Props {
  question: Question;
  onChange?: (q: Question) => void;
}

export function QuestionRow({ question, onChange }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleDismiss = async () => {
    if (busy) return;
    const note = window.prompt("Optional note:") ?? undefined;
    setBusy(true);
    try {
      const updated = await questionsApi.dismiss(question.id, note);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };

  const handleResolve = async () => {
    if (busy) return;
    const answer = window.prompt("Answer text:");
    if (!answer || !answer.trim()) return;
    setBusy(true);
    try {
      const updated = await questionsApi.resolve(question.id, answer);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };

  const handleRetry = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const updated = await questionsApi.retryAuto(question.id);
      onChange?.(updated);
    } finally {
      setBusy(false);
    }
  };

  const isOpen = question.status === "open";

  return (
    <div className="border border-slate-800 rounded-md bg-slate-950/40 p-3 text-sm">
      <div className="flex items-start gap-2">
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${PRIORITY_CHIP[question.priority]}`}>
          P{question.priority}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-xs font-medium border ${STATUS_CHIP[question.status] ?? STATUS_CHIP.open}`}>
          {STATUS_LABEL[question.status] ?? question.status}
        </span>
        <p className="flex-1 text-slate-200">{question.question_text}</p>
      </div>

      {question.answer_text && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="mt-2 text-xs text-slate-400 hover:text-slate-200"
          data-print-hide="true"
        >
          {expanded ? "Hide answer" : "Show answer"}
        </button>
      )}

      {expanded && question.answer_text && (
        <div className="mt-2 p-2 rounded bg-slate-900/60 border border-slate-800 text-slate-300 text-xs whitespace-pre-wrap">
          {question.answer_text}
          {question.answer_source && (
            <p className="mt-1 text-[10px] text-slate-500">— {question.answer_source}</p>
          )}
        </div>
      )}

      {isOpen && (
        <div className="mt-2 flex gap-2" data-print-hide="true">
          <button
            type="button"
            onClick={handleRetry}
            disabled={busy}
            className="px-2 py-1 text-xs rounded border border-emerald-700 text-emerald-200 hover:bg-emerald-900/30 disabled:opacity-50"
          >
            Retry auto
          </button>
          <button
            type="button"
            onClick={handleResolve}
            disabled={busy}
            className="px-2 py-1 text-xs rounded border border-slate-600 text-slate-200 hover:bg-slate-800 disabled:opacity-50"
          >
            Mark resolved
          </button>
          <button
            type="button"
            onClick={handleDismiss}
            disabled={busy}
            className="px-2 py-1 text-xs rounded border border-slate-700 text-slate-400 hover:bg-slate-800 disabled:opacity-50"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create the panel component**

Write `frontend/components/questions/OpenQuestionsPanel.tsx`:

```tsx
"use client";

import { useState } from "react";
import type { Question } from "@/lib/api";
import { QuestionRow } from "./QuestionRow";

interface Props {
  questions: Question[];
}

export function OpenQuestionsPanel({ questions: initial }: Props) {
  const [list, setList] = useState<Question[]>(initial);

  const handleChange = (updated: Question) => {
    setList((prev) => prev.map((q) => (q.id === updated.id ? updated : q)));
  };

  if (list.length === 0) return null;

  // Group by category, then by status (open first)
  const groups: Record<string, Question[]> = {};
  for (const q of list) {
    if (!groups[q.category]) groups[q.category] = [];
    groups[q.category].push(q);
  }
  const categories = Object.keys(groups).sort();

  const openCount = list.filter((q) => q.status === "open").length;

  return (
    <section className="my-6">
      <header className="mb-3 flex items-baseline gap-2">
        <h2 className="text-lg font-semibold text-slate-100">Open Questions</h2>
        <span className="text-xs text-slate-400">
          {openCount} open · {list.length} total
        </span>
      </header>

      <div className="space-y-4">
        {categories.map((cat) => (
          <div key={cat}>
            <h3 className="text-sm font-medium text-slate-300 mb-2">{cat}</h3>
            <div className="space-y-2">
              {groups[cat]
                .sort((a, b) => {
                  if (a.status === "open" && b.status !== "open") return -1;
                  if (a.status !== "open" && b.status === "open") return 1;
                  return a.priority - b.priority;
                })
                .map((q) => (
                  <QuestionRow key={q.id} question={q} onChange={handleChange} />
                ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Embed in `pipeline/[runId]/page.tsx`**

Locate the page file:

```bash
grep -n "ReadThroughDrawer\|deep_dive\|Risk Assessment\|Position Monitor" frontend/app/pipeline/\[runId\]/page.tsx | head -10
```

Find the section between Risk Assessment and Position Monitor (or before Position Monitor if Risk renders inline somewhere distinct). Add:

```tsx
import { OpenQuestionsPanel } from "@/components/questions/OpenQuestionsPanel";
```

at the top, then in the JSX around the spot identified above:

```tsx
<OpenQuestionsPanel questions={report.questions ?? []} />
```

If the report fetch returns a name other than `report`, swap accordingly.

- [ ] **Step 4: TypeScript check**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: zero errors related to the new files.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/questions/ frontend/app/pipeline/\[runId\]/page.tsx
git commit -m "$(cat <<'EOF'
feat(questions): per-run Open Questions panel on /pipeline/[runId]

Grouped by category, status chips, expandable answer view, inline
Dismiss / Mark resolved / Retry auto buttons. data-print-hide on
action buttons drops them from PDF view.
EOF
)"
```

---

## Task 16: `/questions` page + Nav link

**Files:**
- Create: `frontend/app/questions/page.tsx`
- Create: `frontend/components/questions/QuestionTickerRollupTable.tsx`
- Modify: `frontend/components/Nav.tsx`

- [ ] **Step 1: Create the rollup table**

Write `frontend/components/questions/QuestionTickerRollupTable.tsx`:

```tsx
"use client";

import Link from "next/link";
import type { QuestionTickerRollup } from "@/lib/api";

interface Props {
  rollup: QuestionTickerRollup[];
}

export function QuestionTickerRollupTable({ rollup }: Props) {
  if (rollup.length === 0) {
    return <p className="text-slate-500 text-sm">No open questions across the fleet.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead className="text-left text-slate-400 border-b border-slate-800">
        <tr>
          <th className="py-2 pr-4">Ticker</th>
          <th className="py-2 px-3 text-right">P1</th>
          <th className="py-2 px-3 text-right">P2</th>
          <th className="py-2 px-3 text-right">P3</th>
          <th className="py-2 px-3 text-right">Total open</th>
        </tr>
      </thead>
      <tbody>
        {rollup.map((row) => (
          <tr
            key={row.ticker}
            className="border-b border-slate-900 hover:bg-slate-900/40"
          >
            <td className="py-2 pr-4">
              <Link
                href={`/questions?ticker=${row.ticker}`}
                className="text-emerald-300 hover:underline font-mono"
              >
                {row.ticker}
              </Link>
            </td>
            <td className="py-2 px-3 text-right">
              {row.p1_count > 0 ? (
                <span className="text-rose-300 font-semibold">{row.p1_count}</span>
              ) : (
                <span className="text-slate-600">0</span>
              )}
            </td>
            <td className="py-2 px-3 text-right">
              {row.p2_count > 0 ? (
                <span className="text-amber-300">{row.p2_count}</span>
              ) : (
                <span className="text-slate-600">0</span>
              )}
            </td>
            <td className="py-2 px-3 text-right text-slate-400">{row.p3_count}</td>
            <td className="py-2 px-3 text-right text-slate-200 font-semibold">{row.open_count}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 2: Create the page**

Write `frontend/app/questions/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  questions as questionsApi,
  type Question,
  type QuestionStatus,
  type QuestionTickerRollup,
} from "@/lib/api";
import { QuestionRow } from "@/components/questions/QuestionRow";
import { QuestionTickerRollupTable } from "@/components/questions/QuestionTickerRollupTable";

type Tab = "by_ticker" | "by_question";

export default function QuestionsPage() {
  const searchParams = useSearchParams();
  const tickerFilter = searchParams.get("ticker") ?? undefined;

  const [tab, setTab] = useState<Tab>(tickerFilter ? "by_question" : "by_ticker");
  const [rollup, setRollup] = useState<QuestionTickerRollup[]>([]);
  const [list, setList] = useState<Question[]>([]);
  const [statusFilter, setStatusFilter] = useState<QuestionStatus | "all">("open");
  const [priorityFilter, setPriorityFilter] = useState<1 | 2 | 3 | "all">("all");
  const [loading, setLoading] = useState(true);

  const fetchRollup = async () => {
    const r = await questionsApi.byTicker();
    setRollup(r.tickers);
  };

  const fetchList = async () => {
    const r = await questionsApi.list({
      ticker: tickerFilter,
      status: statusFilter === "all" ? undefined : statusFilter,
      priority: priorityFilter === "all" ? undefined : priorityFilter,
      limit: 200,
    });
    setList(r.questions);
  };

  useEffect(() => {
    let mounted = true;

    const load = async () => {
      setLoading(true);
      try {
        if (tab === "by_ticker") {
          await fetchRollup();
        } else {
          await fetchList();
        }
      } finally {
        if (mounted) setLoading(false);
      }
    };

    load();
    const interval = setInterval(() => {
      if (document.visibilityState === "visible") load();
    }, 60_000);

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [tab, tickerFilter, statusFilter, priorityFilter]);

  const handleQuestionChange = (updated: Question) => {
    setList((prev) => prev.map((q) => (q.id === updated.id ? updated : q)));
  };

  return (
    <main className="max-w-5xl mx-auto p-6">
      <header className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-100">Questions</h1>
        <p className="text-slate-400 text-sm mt-1">
          Open analysis gaps across the fleet, surfaced from deep-dive runs.
          {tickerFilter && <> · Filtered to <span className="font-mono">{tickerFilter}</span></>}
        </p>
      </header>

      <div className="flex gap-2 mb-4 border-b border-slate-800">
        <button
          type="button"
          onClick={() => setTab("by_ticker")}
          className={`px-3 py-2 text-sm border-b-2 transition ${
            tab === "by_ticker"
              ? "border-emerald-500 text-emerald-200"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          By ticker
        </button>
        <button
          type="button"
          onClick={() => setTab("by_question")}
          className={`px-3 py-2 text-sm border-b-2 transition ${
            tab === "by_question"
              ? "border-emerald-500 text-emerald-200"
              : "border-transparent text-slate-400 hover:text-slate-200"
          }`}
        >
          By question
        </button>
      </div>

      {tab === "by_question" && (
        <div className="flex flex-wrap gap-2 mb-4 text-xs">
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as QuestionStatus | "all")}
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
          >
            <option value="open">Open</option>
            <option value="resolved_auto">Auto-resolved</option>
            <option value="resolved_inline">Resolved (next run)</option>
            <option value="resolved_manual">Manually resolved</option>
            <option value="dismissed">Dismissed</option>
            <option value="all">All</option>
          </select>
          <select
            value={priorityFilter}
            onChange={(e) =>
              setPriorityFilter(
                e.target.value === "all" ? "all" : (Number(e.target.value) as 1 | 2 | 3),
              )
            }
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-slate-200"
          >
            <option value="all">All priorities</option>
            <option value="1">Priority 1</option>
            <option value="2">Priority 2</option>
            <option value="3">Priority 3</option>
          </select>
        </div>
      )}

      {loading && <p className="text-slate-500 text-sm">Loading…</p>}
      {!loading && tab === "by_ticker" && <QuestionTickerRollupTable rollup={rollup} />}
      {!loading && tab === "by_question" && (
        <div className="space-y-2">
          {list.length === 0 ? (
            <p className="text-slate-500 text-sm">No questions match the current filter.</p>
          ) : (
            list.map((q) => (
              <QuestionRow key={q.id} question={q} onChange={handleQuestionChange} />
            ))
          )}
        </div>
      )}
    </main>
  );
}
```

- [ ] **Step 3: Add the Nav link**

In `frontend/components/Nav.tsx`, find the existing nav links (Status, Catalysts, etc.) and add a `Questions` entry next to them:

```tsx
<Link href="/questions" className="...existing className...">Questions</Link>
```

Match the styling of the existing links exactly. Position the link between `Status` and `Catalysts` (or wherever fits the existing visual order).

- [ ] **Step 4: TypeScript check**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: zero errors related to the new files.

- [ ] **Step 5: Build check**

```bash
cd /Users/ericwyluda/Development/projects/sector-research/frontend && npm run build 2>&1 | tail -20
```

Expected: build succeeds. The `/questions` route should appear in the build output.

- [ ] **Step 6: Commit**

```bash
git add frontend/app/questions/ frontend/components/questions/QuestionTickerRollupTable.tsx frontend/components/Nav.tsx
git commit -m "$(cat <<'EOF'
feat(questions): /questions page + Nav link

Two-tab fleet view: by-ticker rollup + flat by-question filterable
list. 60s polling gated on document.visibilityState. Mirrors /status
and /catalysts UX patterns.
EOF
)"
```

---

## Definition of done

- [ ] All 9 deep-dive categories emit `questions[]` in their structured output and rows persist to the `questions` table after each run.
- [ ] Open priority-1/2 questions from prior runs appear in the next run's category prompts via `{prior_questions}` slot.
- [ ] Priority-1 + auto_answerable questions get resolved by `node_targeted_followup` and feed forward into thesis via `{questions_resolved}` slot.
- [ ] `/questions` page renders the fleet view (both tabs); `/pipeline/[runId]` shows the per-run "Open Questions" panel.
- [ ] `smoke_question_log.py` reports `4/4 PASS` and cleans up.
- [ ] One real run executed end-to-end against an active theme ticker; manual eyeball confirms questions are sensible (not garbage like "what is gross margin?" when GM is in the data) and auto-resolved answers cite the data correctly.
- [ ] `npm run build` succeeds; `tsc --noEmit` returns zero errors related to question files.

## Out of scope (per spec)

- No web search / external research in `node_targeted_followup`
- No question similarity / dedup
- No `linked_pillar` field
- No per-question audit trail beyond timestamps
- No bulk dismiss
- No question export
- No catalyst linkage
