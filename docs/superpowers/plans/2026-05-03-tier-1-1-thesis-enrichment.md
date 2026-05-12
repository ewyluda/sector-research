# Tier 1.1 Thesis Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add pre-mortem, kill criteria, and enriched catalyst fields to the structured thesis output of `node_thesis_construction`, with frontend rendering in the existing `ThesisCard`.

**Architecture:** Single Sonnet call extension — no new pipeline nodes, no new DB tables, no Alembic migration. New Pydantic models live alongside existing ones in `phase_schemas.py`. Frontend reuses the existing `ThesisCard` parent and adds two collapsible sections via the existing `usePersistedCollapse` hook. State for pillar-link hover highlighting lives in `ThesisCard` (already the parent of both `CatalystList` and `BullBearColumns`).

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy 2 / LangGraph / Pydantic / Anthropic SDK (Sonnet 4.6) on the backend; Next.js 16 / React 19 / Tailwind v4 / TypeScript on the frontend.

**Verification convention:** No backend test framework is configured per CLAUDE.md, and no frontend test runner is referenced. Each task uses targeted manual verification (Python import smoke check, `npm run lint`, dev server visual check) instead of automated tests. Steps are still bite-sized: change → verify command → expected output → commit.

**Spec:** `docs/superpowers/specs/2026-05-03-tier-1-1-thesis-enrichment-design.md`

---

## File map

**Backend (3 files modified, 0 created):**
- `backend/app/models/phase_schemas.py` — extend `Catalyst`; add `KillCriterion`, `FailureMode`, `PreMortem`; extend `ThesisOutput`.
- `backend/app/graph/prompts.py` — extend `THESIS_SYSTEM` JSON schema spec + calibration rules.
- `backend/app/graph/nodes.py` — bump `max_tokens=4000` → `6000` in `node_thesis_construction`.

**Frontend (4 files modified, 0 created):**
- `frontend/lib/api.ts` — extend `ThesisStructured`, `Catalyst` interfaces; add `KillCriterion`, `FailureMode`, `PreMortem` interfaces.
- `frontend/components/BullBearColumns.tsx` — accept `highlightedPillar?: string | null` prop; apply ring on match.
- `frontend/components/CatalystList.tsx` — type badge, signposts expand, `linked_pillar` chip; emit `onPillarHover`.
- `frontend/components/ThesisCard.tsx` — `useState<string | null>` for `highlightedPillar`; two collapsible sections for `kill_criteria` and `pre_mortem`; wire props through.

---

## Task 1: Backend Pydantic schema

**Files:**
- Modify: `backend/app/models/phase_schemas.py:76-95`

- [ ] **Step 1.1: Extend the existing `Catalyst` class and add new classes**

In `backend/app/models/phase_schemas.py`, locate the existing `Catalyst` class (lines 76-79). Replace the entire block from the `Catalyst` class definition through the end of `ThesisOutput` with this:

```python
class Catalyst(BaseModel):
    """A catalyst event with timeframe, type, and watchable signposts."""
    timeframe: str = Field(..., min_length=1, max_length=60)
    description: str = Field(..., min_length=1, max_length=600)
    type: Literal[
        "earnings", "product", "regulatory", "m_and_a", "macro", "other"
    ] | None = None
    signposts: list[str] = Field(default_factory=list, max_length=3)
    linked_pillar: str | None = Field(
        default=None, pattern=r"^(bull|bear):[1-5]$"
    )


class KillCriterion(BaseModel):
    """A falsifiable thesis-killer with an observable trigger."""
    condition: str = Field(..., min_length=1, max_length=300)
    threshold: str = Field(..., min_length=1, max_length=300)
    monitoring_source: str = Field(..., min_length=1, max_length=200)
    kills_pillar: str | None = Field(
        default=None, pattern=r"^(bull|bear):[1-5]$"
    )


class FailureMode(BaseModel):
    """A specific way the thesis could be killed in the next 18 months."""
    mode: str = Field(..., min_length=1, max_length=300)
    leading_indicator: str = Field(..., min_length=1, max_length=300)
    probability: Literal["Low", "Medium", "High"]


class PreMortem(BaseModel):
    """Devil's-advocate analysis: assume the thesis is dead — what killed it?"""
    framing: str = Field(..., min_length=1, max_length=300)
    failure_modes: list[FailureMode] = Field(..., min_length=3, max_length=5)


class ThesisOutput(BaseModel):
    # Sonnet 4.6 is naturally verbose — generous limits to avoid
    # ValidationError rejections on well-formed but wordy output.
    core_thesis: str = Field(..., min_length=1, max_length=4000)
    bull_case: list[ThesisPoint] = Field(..., min_length=2, max_length=5)
    bear_case: list[ThesisPoint] = Field(..., min_length=2, max_length=5)
    variant_perception: str = Field(..., min_length=1, max_length=2000)
    catalysts: list[Catalyst] = Field(..., min_length=3, max_length=5)
    conviction_score: int = Field(..., ge=0, le=100)
    conviction_rationale: str = Field(..., min_length=1, max_length=2000)
    # New (optional for backwards compatibility with old runs):
    kill_criteria: list[KillCriterion] = Field(default_factory=list, max_length=5)
    pre_mortem: PreMortem | None = None
```

If the file does not already import `Literal`, add it to the existing typing import. The current import line is `from typing import Literal` near the top — it should already be there since `RiskEntry.probability` uses it. If not, add `Literal` to the existing typing import.

- [ ] **Step 1.2: Verify the module imports cleanly**

Run from project root:

```bash
source backend/venv/bin/activate
python -c "
from backend.app.models.phase_schemas import (
    Catalyst, KillCriterion, FailureMode, PreMortem, ThesisOutput
)
print('Catalyst fields:', list(Catalyst.model_fields.keys()))
print('ThesisOutput fields:', list(ThesisOutput.model_fields.keys()))
"
```

Expected output:

```
Catalyst fields: ['timeframe', 'description', 'type', 'signposts', 'linked_pillar']
ThesisOutput fields: ['core_thesis', 'bull_case', 'bear_case', 'variant_perception', 'catalysts', 'conviction_score', 'conviction_rationale', 'kill_criteria', 'pre_mortem']
```

- [ ] **Step 1.3: Verify a sample valid payload parses**

```bash
python -c "
from backend.app.models.phase_schemas import ThesisOutput
import json
sample = {
    'core_thesis': 'Test thesis.',
    'bull_case': [
        {'title': 'Strong moat', 'evidence': 'Has 70 percent gross margins.'},
        {'title': 'Growing TAM', 'evidence': 'Market expands 20 percent yoy.'},
    ],
    'bear_case': [
        {'title': 'Concentration', 'evidence': 'Top customer is 40 percent.'},
        {'title': 'Valuation', 'evidence': 'Trades at 35x EV/EBITDA.'},
    ],
    'variant_perception': 'Consensus underweights customer stickiness.',
    'catalysts': [
        {'timeframe': 'Q2 2026', 'description': 'Earnings print', 'type': 'earnings', 'signposts': ['Pre-announce revenue beat'], 'linked_pillar': 'bull:1'},
        {'timeframe': 'H2 2026', 'description': 'Product launch', 'type': 'product', 'signposts': [], 'linked_pillar': None},
        {'timeframe': '2027', 'description': 'Regulatory approval', 'type': 'regulatory'},
    ],
    'conviction_score': 72,
    'conviction_rationale': 'Strong fundamentals balance valuation risk.',
    'kill_criteria': [
        {'condition': 'Margin compression', 'threshold': 'GM under 60 percent for 2 quarters', 'monitoring_source': '10-Q income statement', 'kills_pillar': 'bull:1'},
    ],
    'pre_mortem': {
        'framing': 'Imagine 18 months from now this thesis is dead. What killed it?',
        'failure_modes': [
            {'mode': 'Top customer in-houses production', 'leading_indicator': 'Customer announces own platform', 'probability': 'Medium'},
            {'mode': 'New entrant undercuts pricing', 'leading_indicator': 'GM drops 200bps QoQ', 'probability': 'Low'},
            {'mode': 'Regulatory tariff shock', 'leading_indicator': 'Trade rules tightening', 'probability': 'Low'},
        ],
    },
}
parsed = ThesisOutput.model_validate(sample)
print('OK; kill_criteria count =', len(parsed.kill_criteria))
print('pre_mortem failure modes =', len(parsed.pre_mortem.failure_modes))
"
```

Expected output:

```
OK; kill_criteria count = 1
pre_mortem failure modes = 3
```

- [ ] **Step 1.4: Verify an old payload (no new fields) still parses**

```bash
python -c "
from backend.app.models.phase_schemas import ThesisOutput
sample = {
    'core_thesis': 'Test thesis.',
    'bull_case': [
        {'title': 'A', 'evidence': 'AA'},
        {'title': 'B', 'evidence': 'BB'},
    ],
    'bear_case': [
        {'title': 'C', 'evidence': 'CC'},
        {'title': 'D', 'evidence': 'DD'},
    ],
    'variant_perception': 'Variant.',
    'catalysts': [
        {'timeframe': 'Q1 2026', 'description': 'Cat 1'},
        {'timeframe': 'Q2 2026', 'description': 'Cat 2'},
        {'timeframe': 'Q3 2026', 'description': 'Cat 3'},
    ],
    'conviction_score': 50,
    'conviction_rationale': 'Mid.',
}
parsed = ThesisOutput.model_validate(sample)
print('OK old payload; kill_criteria =', parsed.kill_criteria, '; pre_mortem =', parsed.pre_mortem)
"
```

Expected output:

```
OK old payload; kill_criteria = [] ; pre_mortem = None
```

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/models/phase_schemas.py
git commit -m "feat(thesis): extend Catalyst + add KillCriterion / PreMortem schemas

Adds optional kill_criteria and pre_mortem fields to ThesisOutput. Catalyst
gains type, signposts, and linked_pillar fields. Pillar references use the
'bull:N' / 'bear:N' format (1-indexed, regex-validated, max 5).

All new fields are optional or have defaults so old runs in phase_outputs
JSONB continue to parse without migration.

Part of Tier 1.1 thesis enrichment.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Backend prompt extension

**Files:**
- Modify: `backend/app/graph/prompts.py:180-265` (the `THESIS_SYSTEM` and `THESIS_USER` block)

- [ ] **Step 2.1: Replace the `THESIS_SYSTEM` JSON schema block and calibration rules**

Open `backend/app/graph/prompts.py`. Find `THESIS_SYSTEM = """...` starting at line 180. Replace the entire `THESIS_SYSTEM` triple-quoted string with:

```python
THESIS_SYSTEM = """You are constructing a formal investment thesis from completed due diligence research.

Your thesis must be:
- Evidence-grounded: every claim traces back to a category analysis
- Falsifiable: explicit conditions under which the thesis is wrong
- Time-bound: specific catalysts with expected timeframes
- Variant: articulate what you believe that consensus does not

## Output format — JSON only, no preamble, no markdown fences:

{
  "core_thesis": "<1 paragraph, 2-5 sentences — the central investment argument>",
  "bull_case": [
    {"title": "<short headline ~60 chars>", "evidence": "<supporting evidence with source>"},
    ... 2-5 points total
  ],
  "bear_case": [
    {"title": "<short headline ~60 chars>", "evidence": "<supporting evidence with source>"},
    ... 2-5 points total
  ],
  "variant_perception": "<what you believe that consensus does not — 1-3 sentences>",
  "catalysts": [
    {
      "timeframe": "<e.g. 'Next 1-3 mo', 'Q2 2026', '6-12 mo'>",
      "description": "<catalyst event>",
      "type": "earnings" | "product" | "regulatory" | "m_and_a" | "macro" | "other",
      "signposts": ["<leading indicator 1>", "<leading indicator 2>"],
      "linked_pillar": "bull:N" | "bear:N" | null
    },
    ... 3-5 catalysts
  ],
  "conviction_score": <int 0-100>,
  "conviction_rationale": "<why this specific score — 1-3 sentences>",
  "kill_criteria": [
    {
      "condition": "<what would falsify the thesis>",
      "threshold": "<observable numeric/factual trigger>",
      "monitoring_source": "<where this is observed: 10-Q, transcript, EDGAR XBRL, etc>",
      "kills_pillar": "bull:N" | "bear:N" | null
    },
    ... 3-5 kill criteria
  ],
  "pre_mortem": {
    "framing": "Imagine it's 18 months from now and this thesis is dead. What killed it?",
    "failure_modes": [
      {
        "mode": "<concrete cause>",
        "leading_indicator": "<what we'd see first>",
        "probability": "Low" | "Medium" | "High"
      },
      ... 3-5 failure modes
    ]
  }
}

## Rules
- Output ONLY the JSON object. No backticks, no commentary, no preamble.
- Be calibrated. A conviction of 70 means genuinely good, not great. 85+ means exceptional with clear catalysts.
- Bull and bear points must have specific evidence, not generic statements.
- Catalysts must have concrete timeframes, not vague "eventually".
- Every claim must trace to a category analysis from the deep dive results below.
- Do NOT restate observations already documented in the established findings. Reference categories by name (e.g. "as shown in Financial Health"). Only introduce new observations if the data reveals something the category analyses missed.

## Catalyst calibration
- type must be exactly one of the literals listed.
- signposts are LEADING indicators ("what we'd see first") — concrete and observable. 1-3 per catalyst. Empty list allowed only if no good leading indicator exists.
- linked_pillar is optional. Use it when a catalyst directly tests one bull or bear pillar. Format: "bull:N" or "bear:N" where N is the 1-indexed position in bull_case / bear_case. Use null otherwise.

## Kill criteria calibration
- Produce 3-5 criteria. Each MUST be falsifiable.
- threshold must specify a numeric or factual trigger, not a feeling. Reject "if competition increases" — require "if market share drops below X% for 2 consecutive quarters."
- monitoring_source must name the document or feed where the trigger is observed (10-Q, 10-K, transcript, EDGAR XBRL, FMP, news).
- kills_pillar uses the same "bull:N" / "bear:N" format as linked_pillar; null when the criterion kills the whole thesis rather than one pillar.

## Pre-mortem calibration
- The framing string is fixed: "Imagine it's 18 months from now and this thesis is dead. What killed it?"
- Produce 3-5 failure_modes. Each mode is a concrete cause; each leading_indicator is what we'd see first.
- probability reflects today's odds of that specific failure mode materialising in 18 months. Be calibrated — most failure modes are Low or Medium."""
```

The `THESIS_USER` block immediately below remains unchanged.

- [ ] **Step 2.2: Bump `max_tokens` in `node_thesis_construction`**

Open `backend/app/graph/nodes.py`. Find `node_thesis_construction` at line 1218. Inside it, locate the `await complete(...)` call (around line 1257-1264) and change `max_tokens=4000` to `max_tokens=6000`.

The line currently looks like:

```python
        response = await complete(
            system=THESIS_SYSTEM,
            user=THESIS_USER.format(
                ...
            ),
            model=SONNET,
            max_tokens=4000,
        )
```

Change to:

```python
        response = await complete(
            system=THESIS_SYSTEM,
            user=THESIS_USER.format(
                ...
            ),
            model=SONNET,
            max_tokens=6000,
        )
```

- [ ] **Step 2.3: Verify the module imports cleanly**

```bash
source backend/venv/bin/activate
python -c "
from backend.app.graph.prompts import THESIS_SYSTEM, THESIS_USER
from backend.app.graph.nodes import node_thesis_construction
assert 'kill_criteria' in THESIS_SYSTEM
assert 'pre_mortem' in THESIS_SYSTEM
assert 'failure_modes' in THESIS_SYSTEM
assert 'linked_pillar' in THESIS_SYSTEM
assert 'signposts' in THESIS_SYSTEM
print('Prompt + node import OK')
print('Prompt length:', len(THESIS_SYSTEM), 'chars')
"
```

Expected output (length value will vary slightly but should be 4000-5500):

```
Prompt + node import OK
Prompt length: <some number around 4500>
```

- [ ] **Step 2.4: Commit**

```bash
git add backend/app/graph/prompts.py backend/app/graph/nodes.py
git commit -m "feat(thesis): teach Sonnet to emit kill criteria, pre-mortem, enriched catalysts

Extends THESIS_SYSTEM with the new fields' JSON schema and calibration rules:
- catalysts gain type, signposts, linked_pillar
- kill_criteria as a 3-5 item falsifiable list with observable thresholds
- pre_mortem with the fixed 18-month framing and 3-5 failure modes

Bumps max_tokens 4000 -> 6000 to absorb the larger structured output.

Part of Tier 1.1 thesis enrichment.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Backend smoke test on a real thesis run

**Files:** none modified — verification only.

- [ ] **Step 3.1: Start the backend and trigger a fresh thesis run**

Start the backend from project root:

```bash
source backend/venv/bin/activate
uvicorn backend.app.main:app --reload
```

Wait for startup. In another shell, trigger a new run on a known ticker. Use the existing UI at `http://localhost:3000/pipeline/new` (start the frontend separately with `cd frontend && npm run dev`), OR via API:

```bash
curl -X POST http://localhost:8000/api/runs \
  -H 'Content-Type: application/json' \
  -d '{"ticker": "MSFT", "theme_id": "<an existing theme id>"}'
```

Note the returned `run_id`.

- [ ] **Step 3.2: Wait for the thesis_construction phase to complete and inspect the output**

The pipeline auto-advances. After ~2-3 minutes the thesis phase completes. Pull the structured output:

```bash
curl -s http://localhost:8000/api/runs/<run_id>/report | \
  python -c "
import json, sys
report = json.load(sys.stdin)
thesis = report.get('phases', {}).get('thesis', {})
structured = thesis.get('structured') or {}
print('catalysts (count):', len(structured.get('catalysts', [])))
print('first catalyst:', json.dumps(structured.get('catalysts', [{}])[0], indent=2))
print('kill_criteria (count):', len(structured.get('kill_criteria', [])))
print('first kill criterion:', json.dumps(structured.get('kill_criteria', [{}])[0], indent=2))
print('pre_mortem framing:', (structured.get('pre_mortem') or {}).get('framing'))
print('failure modes (count):', len((structured.get('pre_mortem') or {}).get('failure_modes', [])))
"
```

Expected: `catalysts` count is 3-5, each catalyst has `type`, `signposts`, `linked_pillar` fields. `kill_criteria` count is 3-5 with `condition`, `threshold`, `monitoring_source`, `kills_pillar`. `pre_mortem.framing` matches the fixed string. Failure modes count is 3-5.

- [ ] **Step 3.3: Capture verification notes**

If any field is missing or vague, note it for the "Open Questions" follow-up in the spec (e.g., bump prompt with one-shot example). If everything looks good, no commit needed — this is a verification gate, not a code change. Continue to Task 4.

If the prompt produced malformed output and `parsed` is None in the run record, check `phase_outputs.thesis.parse_error` for the validation message and adjust the prompt rules accordingly before continuing.

---

## Task 4: Frontend TypeScript types

**Files:**
- Modify: `frontend/lib/api.ts:530-552`

- [ ] **Step 4.1: Replace the existing thesis-related interfaces**

Open `frontend/lib/api.ts`. Find the `// ── Thesis Construction structured output ────────...` block at line ~530. Replace from `export interface ThesisPoint` through `export interface ThesisStructured` (inclusive) with:

```typescript
// ── Thesis Construction structured output ─────────────────────────────────────

export interface ThesisPoint {
  title: string;
  evidence: string;
}

export type CatalystType =
  | "earnings"
  | "product"
  | "regulatory"
  | "m_and_a"
  | "macro"
  | "other";

export interface Catalyst {
  timeframe: string;
  description: string;
  type?: CatalystType | null;
  signposts?: string[];
  linked_pillar?: string | null; // "bull:N" or "bear:N"
}

export interface KillCriterion {
  condition: string;
  threshold: string;
  monitoring_source: string;
  kills_pillar?: string | null; // "bull:N" or "bear:N"
}

export interface FailureMode {
  mode: string;
  leading_indicator: string;
  probability: "Low" | "Medium" | "High";
}

export interface PreMortem {
  framing: string;
  failure_modes: FailureMode[];
}

export interface ThesisStructured {
  core_thesis: string;
  bull_case: ThesisPoint[];
  bear_case: ThesisPoint[];
  variant_perception: string;
  catalysts: Catalyst[];
  conviction_score: number;
  conviction_rationale: string;
  kill_criteria?: KillCriterion[];
  pre_mortem?: PreMortem | null;
}
```

- [ ] **Step 4.2: Verify types compile and lint is clean**

```bash
cd frontend
npm run lint
```

Expected: lint exits 0 with no errors. (Warnings are tolerated; errors are not.)

Run a typecheck via the build:

```bash
npm run build
```

Expected: build completes without TypeScript errors. (You can stop the build once it has passed type checking; you don't need to wait for it to finish optimizing if it's slow — the type errors surface early.)

- [ ] **Step 4.3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "feat(api): extend ThesisStructured TS types with new thesis fields

Adds Catalyst.type/signposts/linked_pillar (optional), KillCriterion,
FailureMode, PreMortem interfaces, and kill_criteria + pre_mortem on
ThesisStructured. All new fields are optional so the type matches old
backend payloads as well as new ones.

Part of Tier 1.1 thesis enrichment.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: BullBearColumns highlight prop

**Files:**
- Modify: `frontend/components/BullBearColumns.tsx`

- [ ] **Step 5.1: Replace the file**

Replace the entire contents of `frontend/components/BullBearColumns.tsx` with:

```tsx
/**
 * Two-column renderer for bull vs bear thesis points.
 * Left column: olive-tinted cards (--success) for bull case.
 * Right column: magenta-tinted cards (--error) for bear case.
 * Variable-length: handles 2-5 items per side.
 *
 * highlightedPillar: when set to "bull:N" or "bear:N" (1-indexed), the matching
 * card receives a ring/glow. Used by chip-hover handlers in CatalystList and
 * the kill-criteria list inside ThesisCard.
 */

import type { ThesisPoint } from "@/lib/api";

function PointCard({
  point,
  variant,
  highlighted,
}: {
  point: ThesisPoint;
  variant: "bull" | "bear";
  highlighted: boolean;
}) {
  const bg =
    variant === "bull"
      ? "bg-[var(--success)]/4 border-[var(--success)]/22"
      : "bg-[var(--error)]/4 border-[var(--error)]/22";

  const ring = highlighted
    ? variant === "bull"
      ? "ring-2 ring-[var(--success)]/60 shadow-lg shadow-[var(--success)]/10"
      : "ring-2 ring-[var(--error)]/60 shadow-lg shadow-[var(--error)]/10"
    : "";

  return (
    <div className={`rounded-md border p-2.5 transition-shadow duration-150 ${bg} ${ring}`}>
      <div className="text-[11px] font-semibold text-[var(--text)] leading-snug">
        {point.title}
      </div>
      <div className="text-[10px] text-[var(--text-muted)] mt-1 leading-relaxed">
        {point.evidence}
      </div>
    </div>
  );
}

export function BullBearColumns({
  bull,
  bear,
  highlightedPillar = null,
}: {
  bull: ThesisPoint[];
  bear: ThesisPoint[];
  highlightedPillar?: string | null;
}) {
  const matched = highlightedPillar?.match(/^(bull|bear):(\d+)$/);
  const highlightSide = (matched?.[1] ?? null) as "bull" | "bear" | null;
  const highlightIndex = matched ? Number(matched[2]) - 1 : -1;

  return (
    <div className="grid grid-cols-2 gap-3">
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--success)]" />
          <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--success)]">
            Bull Case
          </span>
        </div>
        {bull.map((p, i) => (
          <PointCard
            key={i}
            point={p}
            variant="bull"
            highlighted={highlightSide === "bull" && highlightIndex === i}
          />
        ))}
      </div>
      <div className="flex flex-col gap-1.5">
        <div className="flex items-center gap-2 mb-1">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--error)]" />
          <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--error)]">
            Bear Case
          </span>
        </div>
        {bear.map((p, i) => (
          <PointCard
            key={i}
            point={p}
            variant="bear"
            highlighted={highlightSide === "bear" && highlightIndex === i}
          />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 5.2: Verify lint passes**

```bash
cd frontend
npm run lint
```

Expected: exits 0.

- [ ] **Step 5.3: Commit**

```bash
git add frontend/components/BullBearColumns.tsx
git commit -m "feat(thesis): BullBearColumns accepts highlightedPillar prop

Adds optional highlightedPillar prop (e.g. 'bull:2'). The matching pillar
card gets a ring/glow class. No-op when prop is null/undefined, preserving
existing visual.

Part of Tier 1.1 thesis enrichment.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: CatalystList enrichment

**Files:**
- Modify: `frontend/components/CatalystList.tsx`

- [ ] **Step 6.1: Replace the file**

Replace the entire contents of `frontend/components/CatalystList.tsx` with:

```tsx
/**
 * Catalyst timeline list for the ThesisCard.
 * Renders 3-5 catalyst rows. Each row shows:
 *   - timeframe label (left, fixed width)
 *   - description (right)
 *   - type badge (small pill, color-coded by type)
 *   - signposts (revealed by an inline expand toggle)
 *   - linked_pillar chip (hover lifts state to highlight the bull/bear card)
 */

import { useState } from "react";
import type { Catalyst, CatalystType } from "@/lib/api";

const TYPE_COLORS: Record<CatalystType, string> = {
  earnings:   "bg-[var(--primary)]/10 text-[var(--primary)] border-[var(--primary)]/30",
  product:    "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  regulatory: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  m_and_a:    "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
  macro:      "bg-[var(--text-muted)]/10 text-[var(--text-muted)] border-[var(--text-muted)]/30",
  other:      "bg-[var(--surface-alt)] text-[var(--text-faint)] border-[var(--border)]",
};

const TYPE_LABELS: Record<CatalystType, string> = {
  earnings:   "EARNINGS",
  product:    "PRODUCT",
  regulatory: "REGULATORY",
  m_and_a:    "M&A",
  macro:      "MACRO",
  other:      "OTHER",
};

export function CatalystList({
  catalysts,
  onPillarHover,
}: {
  catalysts: Catalyst[];
  onPillarHover?: (pillar: string | null) => void;
}) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const toggle = (i: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  return (
    <div className="w-full">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Key Catalysts
        </span>
        <span className="flex-1 h-px bg-[var(--border)]" />
      </div>
      <div>
        {catalysts.map((c, i) => {
          const hasSignposts = (c.signposts ?? []).length > 0;
          const isOpen = expanded.has(i);
          return (
            <div
              key={i}
              className={`grid grid-cols-[140px_1fr] gap-3 py-2 items-baseline ${
                i > 0 ? "border-t border-[var(--border)]/50" : ""
              }`}
            >
              <span className="text-[10px] font-semibold font-mono text-[var(--primary)] uppercase">
                {c.timeframe}
              </span>
              <div className="flex flex-col gap-1.5">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="text-[11px] text-[var(--text)] leading-snug">
                    {c.description}
                  </span>
                  {c.type && (
                    <span className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wider ${TYPE_COLORS[c.type]}`}>
                      {TYPE_LABELS[c.type]}
                    </span>
                  )}
                  {c.linked_pillar && onPillarHover && (
                    <button
                      type="button"
                      onMouseEnter={() => onPillarHover(c.linked_pillar ?? null)}
                      onMouseLeave={() => onPillarHover(null)}
                      onFocus={() => onPillarHover(c.linked_pillar ?? null)}
                      onBlur={() => onPillarHover(null)}
                      className="px-1.5 py-0.5 rounded border text-[9px] font-mono text-[var(--text-muted)] border-[var(--border)] hover:bg-[var(--surface-alt)] cursor-default"
                    >
                      tests {c.linked_pillar}
                    </button>
                  )}
                  {hasSignposts && (
                    <button
                      type="button"
                      onClick={() => toggle(i)}
                      className="text-[9px] font-mono text-[var(--text-faint)] hover:text-[var(--primary)] underline-offset-2"
                    >
                      {isOpen ? "− signposts" : `+ ${(c.signposts ?? []).length} signpost${(c.signposts ?? []).length === 1 ? "" : "s"}`}
                    </button>
                  )}
                </div>
                {hasSignposts && isOpen && (
                  <ul className="ml-3 list-disc text-[10px] text-[var(--text-muted)] leading-relaxed">
                    {(c.signposts ?? []).map((s, j) => (
                      <li key={j}>{s}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 6.2: Verify lint passes**

```bash
cd frontend
npm run lint
```

Expected: exits 0.

- [ ] **Step 6.3: Commit**

```bash
git add frontend/components/CatalystList.tsx
git commit -m "feat(thesis): enrich CatalystList with type badge, signposts, pillar chip

Each catalyst row now renders an inline type badge (earnings/product/etc),
a per-row expand toggle revealing signposts (leading indicators), and a
'tests bull:N' chip that emits onPillarHover so the parent can highlight
the linked bull/bear card.

All new visual elements are conditional on the optional fields existing,
so old runs render exactly as before.

Part of Tier 1.1 thesis enrichment.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: ThesisCard accordions and state wiring

**Files:**
- Modify: `frontend/components/ThesisCard.tsx`

- [ ] **Step 7.1: Replace the file**

Replace the entire contents of `frontend/components/ThesisCard.tsx` with:

```tsx
/**
 * Analyst Memo dashboard for the Thesis Construction phase output.
 *
 * Layout (top to bottom):
 *   1. Header — ScoreRing (conviction) + ticker + thesis status badge
 *   2. Core thesis callout (teal-tinted, left-bordered)
 *   3. Bull/Bear columns (symmetric two-column layout)
 *   4. Variant perception callout (rust-tinted, left-bordered)
 *   5. Catalyst list (timeframe + description rows)
 *   6. Kill criteria — collapsible (default closed)
 *   7. Pre-mortem — collapsible (default closed)
 *   8. Conviction rationale footer
 *   9. Citation list footer
 *
 * State: highlightedPillar tracks "bull:N"|"bear:N" hovers from the
 * pillar-link chips in CatalystList and the kill criteria list, and is
 * passed down to BullBearColumns to apply a ring/glow.
 */

"use client";

import { useState } from "react";
import type {
  ThesisStructured,
  Citation,
  KillCriterion,
  FailureMode,
  PreMortem,
} from "@/lib/api";
import ScoreRing from "@/components/ScoreRing";
import { BullBearColumns } from "@/components/BullBearColumns";
import { CatalystList } from "@/components/CatalystList";
import { CitationList } from "@/components/CitationList";
import { usePersistedCollapse } from "@/components/deep-dive/usePersistedCollapse";

const STATUS_COLORS: Record<string, string> = {
  "ON TRACK": "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  DRIFTING:   "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  BROKEN:     "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
  PENDING:    "bg-[var(--surface)] text-[var(--text-faint)] border-[var(--border)]",
};

const PROBABILITY_COLORS: Record<FailureMode["probability"], string> = {
  Low:    "bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/30",
  Medium: "bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/30",
  High:   "bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/30",
};

interface Props {
  structured: ThesisStructured;
  citations?: Citation[];
  ticker: string;
  thesisStatus: string;
}

function PillarChip({
  pillar,
  prefix,
  onHover,
}: {
  pillar: string;
  prefix: string;
  onHover: (p: string | null) => void;
}) {
  return (
    <button
      type="button"
      onMouseEnter={() => onHover(pillar)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(pillar)}
      onBlur={() => onHover(null)}
      className="px-1.5 py-0.5 rounded border text-[9px] font-mono text-[var(--text-muted)] border-[var(--border)] hover:bg-[var(--surface-alt)] cursor-default"
    >
      {prefix} {pillar}
    </button>
  );
}

function KillCriteriaSection({
  items,
  onPillarHover,
}: {
  items: KillCriterion[];
  onPillarHover: (p: string | null) => void;
}) {
  const [collapsed, setCollapsed] = usePersistedCollapse(
    "thesis-kill-criteria",
    true,
  );
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3.5 py-2.5"
      >
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Kill Criteria · {items.length}
        </span>
        <span className="text-[10px] text-[var(--text-faint)] font-mono">
          {collapsed ? "+" : "−"}
        </span>
      </button>
      {!collapsed && (
        <div className="px-3.5 pb-3 flex flex-col gap-2">
          {items.map((k, i) => (
            <div
              key={i}
              className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 flex flex-col gap-1"
            >
              <div className="text-[11px] font-semibold text-[var(--text)] leading-snug">
                {k.condition}
              </div>
              <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
                <span className="font-mono text-[var(--text-faint)]">trigger</span>{" "}
                {k.threshold}
              </div>
              <div className="flex items-center gap-2 flex-wrap mt-0.5">
                <span className="text-[9px] font-mono text-[var(--text-faint)]">
                  watch: {k.monitoring_source}
                </span>
                {k.kills_pillar && (
                  <PillarChip
                    pillar={k.kills_pillar}
                    prefix="kills"
                    onHover={onPillarHover}
                  />
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PreMortemSection({ data }: { data: PreMortem }) {
  const [collapsed, setCollapsed] = usePersistedCollapse(
    "thesis-pre-mortem",
    true,
  );
  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between px-3.5 py-2.5"
      >
        <span className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)]">
          Pre-Mortem · {data.failure_modes.length}
        </span>
        <span className="text-[10px] text-[var(--text-faint)] font-mono">
          {collapsed ? "+" : "−"}
        </span>
      </button>
      {!collapsed && (
        <div className="px-3.5 pb-3 flex flex-col gap-2">
          <div className="text-[11px] italic text-[var(--text-muted)] leading-snug">
            {data.framing}
          </div>
          {data.failure_modes.map((fm, i) => (
            <div
              key={i}
              className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 flex flex-col gap-1"
            >
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-semibold text-[var(--text)] leading-snug">
                  {fm.mode}
                </span>
                <span
                  className={`px-1.5 py-0.5 rounded border text-[9px] font-semibold tracking-wider ${PROBABILITY_COLORS[fm.probability]}`}
                >
                  {fm.probability.toUpperCase()}
                </span>
              </div>
              <div className="text-[10px] text-[var(--text-muted)] leading-relaxed">
                <span className="font-mono text-[var(--text-faint)]">leading:</span>{" "}
                {fm.leading_indicator}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ThesisCard({
  structured,
  citations = [],
  ticker,
  thesisStatus,
}: Props) {
  const statusColor = STATUS_COLORS[thesisStatus] ?? STATUS_COLORS.PENDING;
  const [highlightedPillar, setHighlightedPillar] = useState<string | null>(null);

  const killCriteria = structured.kill_criteria ?? [];
  const preMortem = structured.pre_mortem ?? null;

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--surface)] p-5 flex flex-col gap-4">
      {/* Header row */}
      <div className="flex items-center gap-4 pb-4 border-b border-[var(--border)]">
        <ScoreRing score={structured.conviction_score} size={86} />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-3 mb-1">
            <span className="text-2xl font-mono font-bold text-[var(--text)] tracking-wide">
              {ticker}
            </span>
            <span
              className={`px-3 py-0.5 rounded-full border text-[11px] font-semibold tracking-wider ${statusColor}`}
            >
              {thesisStatus === "ON TRACK" ? "● ON TRACK" : thesisStatus}
            </span>
          </div>
          <div className="text-xs text-[var(--text-muted)]">
            Thesis Construction · Conviction {structured.conviction_score}/100
          </div>
        </div>
      </div>

      {/* Core thesis callout */}
      <div
        className="rounded-lg border border-[var(--primary)]/20 bg-[var(--primary)]/5 p-3.5"
        style={{ borderLeft: "3px solid var(--primary)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--primary)] mb-1.5">
          Core Thesis
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.core_thesis}
        </div>
      </div>

      {/* Bull / Bear columns */}
      <BullBearColumns
        bull={structured.bull_case}
        bear={structured.bear_case}
        highlightedPillar={highlightedPillar}
      />

      {/* Variant perception callout */}
      <div
        className="rounded-lg border border-[var(--warning)]/20 bg-[var(--warning)]/4 p-3.5"
        style={{ borderLeft: "3px solid var(--warning)" }}
      >
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--warning)] mb-1.5">
          ◆ Variant Perception
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.variant_perception}
        </div>
      </div>

      {/* Catalyst list */}
      <CatalystList
        catalysts={structured.catalysts}
        onPillarHover={setHighlightedPillar}
      />

      {/* Kill criteria — only if present */}
      {killCriteria.length > 0 && (
        <KillCriteriaSection
          items={killCriteria}
          onPillarHover={setHighlightedPillar}
        />
      )}

      {/* Pre-mortem — only if present */}
      {preMortem && <PreMortemSection data={preMortem} />}

      {/* Conviction rationale footer */}
      <div className="rounded-lg bg-[var(--surface-alt)] border border-[var(--border)] p-3.5">
        <div className="text-[10px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1">
          Why {structured.conviction_score}?
        </div>
        <div className="text-xs text-[var(--text)] leading-relaxed">
          {structured.conviction_rationale}
        </div>
      </div>

      {/* Citation footer */}
      <CitationList citations={citations} />
    </div>
  );
}
```

- [ ] **Step 7.2: Verify lint passes**

```bash
cd frontend
npm run lint
```

Expected: exits 0.

- [ ] **Step 7.3: Commit**

```bash
git add frontend/components/ThesisCard.tsx
git commit -m "feat(thesis): ThesisCard renders kill criteria and pre-mortem sections

Adds two collapsible sections (default collapsed via usePersistedCollapse,
keys 'thesis-kill-criteria' / 'thesis-pre-mortem'). Both sections only
render when the underlying field is populated, so old runs are unaffected.

Adds local state for highlightedPillar; pillar-link chips in
CatalystList and the new kill-criteria list lift hover events here, and
the value flows down to BullBearColumns to apply a ring on the matching
bull/bear card.

Part of Tier 1.1 thesis enrichment.
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Task 8: End-to-end frontend verification

**Files:** none modified — verification only.

- [ ] **Step 8.1: Start the dev server and view the new run from Task 3**

```bash
cd frontend
npm run dev
```

In the browser, navigate to `http://localhost:3000/pipeline/<run_id>` where `<run_id>` is the run created in Task 3.

- [ ] **Step 8.2: Confirm the new fields render correctly**

Verify all of the following on the thesis card:

- Each catalyst row shows a colored type badge next to the description (e.g. blue "EARNINGS").
- Catalysts that have signposts show a `+ N signpost` toggle; clicking it reveals a bulleted list.
- A catalyst with `linked_pillar` set shows a `tests bull:N` (or `tests bear:N`) chip.
- Hovering the `tests bull:1` chip causes the corresponding bull pillar card to gain a ring/glow.
- A `Kill Criteria · N` collapsible section appears below the catalyst list. It is collapsed by default. Clicking the header reveals the criteria.
- Each kill criterion shows the condition, the trigger threshold, the watch source, and (when set) a `kills bull:N` chip. The chip-hover similarly highlights the pillar.
- A `Pre-Mortem · N` collapsible section appears below the kill criteria. It shows the framing line and N failure-mode cards, each with a colored probability badge.
- Reload the page; both collapse states persist.

- [ ] **Step 8.3: Confirm backwards compatibility on an old run**

Open an older run that pre-dates this change (any run from before this branch). Confirm:

- The thesis card renders without runtime errors (no React error overlay; no empty placeholders).
- The catalyst rows look exactly as before — no dangling `+ 0 signposts` or empty type badges.
- No `Kill Criteria` or `Pre-Mortem` collapsibles are rendered (since the fields are absent).

- [ ] **Step 8.4: Capture any issues**

If anything renders incorrectly, debug from the violating component and fix in place. Re-run lint and commit any fixes as a follow-up commit. If everything looks good, no commit needed — Task 8 is a verification gate.

---

## Self-review checklist (post-implementation)

- [ ] Sonnet reliably emits the new fields populated (re-run thesis on 2-3 different tickers; spot-check `kill_criteria.threshold` for vagueness, `linked_pillar` index in range).
- [ ] If pillar references drift out of range (e.g., `bull:6` on a 5-item bull_case), add a one-shot tightening to the prompt or a post-parse validator.
- [ ] If `max_tokens=6000` is occasionally hit, bump to 8000.
- [ ] No TODOs left in the codebase referencing this work.
