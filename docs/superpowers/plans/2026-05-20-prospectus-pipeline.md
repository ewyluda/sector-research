# S-1 Prospectus Analysis Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a parallel analytical pipeline that consumes an S-1 prospectus, extracts sections + embedded financials + a counterparty graph, runs seven adapted deep-dive categories (plus a new IPO Mechanics category), and synthesises an IPO verdict + post-IPO research plan.

**Architecture:** New `ProspectusReport` table + `ProspectusService` orchestrator running four sequential steps with SSE streaming. Reuses `EdgarClient`, `filing_sections` table, relationship extractor, and Sonnet/Haiku prompt scaffolding. Public-company pipeline left untouched.

**Tech Stack:** FastAPI + async SQLAlchemy + Alembic + Anthropic SDK (Sonnet/Haiku) + Pydantic v2 + Next.js 16 App Router + Tailwind v4.

**Spec:** `docs/superpowers/specs/2026-05-20-prospectus-pipeline-design.md` (commit `7f54dca`).

**Conventions to obey:**
- All Bash commands assume project root (`/Users/ericwyluda/Development/projects/sector-research`) as cwd unless stated otherwise.
- Backend uses absolute imports rooted at project root (`backend.app.*`). Tests are stdlib `unittest`, invoked as `python -m unittest backend.tests.<module>` from project root with `backend/venv` activated.
- Frontend reads `node_modules/next/dist/docs/` before relying on Next.js APIs from training data (Next 16 has breaking changes).
- Tickers and the synthetic-ticker identifier are always uppercased at write time.
- Every step in this plan ends with a commit. Do not batch.

---

## Phase 1 — Backend foundation

### Task 1: ProspectusReport ORM model + migration

**Files:**
- Create: `backend/app/models/prospectus_report.py`
- Create: `backend/migrations/versions/<auto>_add_prospectus_reports.py`
- Test: `backend/tests/test_prospectus_report_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prospectus_report_model.py`:

```python
"""Smoke test for ProspectusReport ORM mapping."""
import unittest

from backend.app.models.prospectus_report import ProspectusReport


class TestProspectusReportModel(unittest.TestCase):
    def test_defaults(self):
        r = ProspectusReport(
            accession_number="0001628280-26-036936",
            issuer_cik="0001181412",
            issuer_name="Space Exploration Technologies Corp",
        )
        self.assertEqual(r.status, "ingesting")
        self.assertEqual(r.step_outputs, {})
        self.assertIsNone(r.proposed_ticker)
        self.assertIsNone(r.theme_id)
        self.assertIsNone(r.error_message)
        # "SpaceExplorationTechnologiesCorp" alphanumeric-uppercase → first 16 chars
        self.assertEqual(r.synthetic_ticker, "SPACEEXPLORATION")

    def test_synthetic_ticker_uses_proposed(self):
        r = ProspectusReport(
            accession_number="x",
            issuer_cik="0001",
            issuer_name="Some Long Name LLC",
            proposed_ticker="space",
        )
        self.assertEqual(r.synthetic_ticker, "SPACE")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_report_model -v
```

Expected: `ImportError: No module named 'backend.app.models.prospectus_report'`.

- [ ] **Step 3: Implement the ORM model**

Create `backend/app/models/prospectus_report.py`:

```python
"""ProspectusReport — analytical report for an S-1 / S-1/A filing.

Parallel to ResearchRun and WorkspaceRun. step_outputs is a JSONB blob
shaped like WorkspaceRun.step_outputs (one keyed entry per pipeline step).
"""
from uuid import uuid4

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base, TimestampMixin


def _slugify_issuer(name: str) -> str:
    """Uppercase alphanumeric-only, truncated to 16 chars."""
    return "".join(c for c in (name or "").upper() if c.isalnum())[:16]


class ProspectusReport(Base, TimestampMixin):
    __tablename__ = "prospectus_reports"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid4())
    )

    accession_number: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    issuer_cik: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    issuer_name: Mapped[str] = mapped_column(String(256), nullable=False)
    proposed_ticker: Mapped[str | None] = mapped_column(String(16), nullable=True)

    theme_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("themes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ingesting")
    step_outputs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    @property
    def synthetic_ticker(self) -> str:
        """Identifier written into filings.ticker / relationships.ticker.

        See spec — proposed_ticker if disclosed, else uppercase alphanumeric
        slug of issuer_name truncated to 16 chars.
        """
        if self.proposed_ticker:
            return self.proposed_ticker.upper()[:16]
        return _slugify_issuer(self.issuer_name)
```

- [ ] **Step 4: Rerun the test**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_report_model -v
```

Expected: PASS.

- [ ] **Step 5: Generate the migration**

```bash
source backend/venv/bin/activate && cd backend && alembic revision --autogenerate -m "add prospectus_reports"
```

Expected: a new file under `backend/migrations/versions/` is created.

- [ ] **Step 6: Sanity-edit the migration**

Open the generated file. Verify the `op.create_table('prospectus_reports', …)` block matches the model exactly (columns, types, FK to `themes.id` with `ondelete='SET NULL'`, indexes on `accession_number`, `issuer_cik`, `theme_id`). If alembic generated unrelated drops (it sometimes detects stale state), delete them. The file should contain ONLY the create_table + indexes in `upgrade()` and the inverse in `downgrade()`.

- [ ] **Step 7: Apply the migration locally**

```bash
source backend/venv/bin/activate && cd backend && alembic upgrade head
```

Expected: `INFO  [alembic.runtime.migration] Running upgrade <prev> -> <new>, add prospectus_reports`.

- [ ] **Step 8: Confirm downgrade**

```bash
source backend/venv/bin/activate && cd backend && alembic downgrade -1 && alembic upgrade head
```

Expected: clean down + clean up.

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/prospectus_report.py backend/migrations/versions/*_add_prospectus_reports.py backend/tests/test_prospectus_report_model.py
git commit -m "$(cat <<'EOF'
feat(prospectus): add ProspectusReport ORM + migration

ProspectusReport parallels WorkspaceRun — JSONB step_outputs, FK to
themes with ondelete=SET NULL, synthetic_ticker property derives the
identifier written into filings.ticker / relationships.ticker.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Pydantic schemas

**Files:**
- Create: `backend/app/models/prospectus_schemas.py`
- Test: `backend/tests/test_prospectus_schemas.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_prospectus_schemas.py`:

```python
"""Schema round-trip tests for prospectus pipeline outputs."""
import unittest
from pydantic import ValidationError

from backend.app.models.prospectus_schemas import (
    ProspectusFinancials,
    AnnualFinancialRow,
    ProspectusCategoryResult,
    ProspectusThesisOutput,
    PostIPOPlanItem,
    IPOVerdict,
)


class TestProspectusFinancials(unittest.TestCase):
    def test_valid_round_trip(self):
        f = ProspectusFinancials(
            annual=[
                AnnualFinancialRow(
                    period_label="FY2024",
                    revenue=14_000_000_000.0,
                    operating_income=2_000_000_000.0,
                    net_income=1_500_000_000.0,
                    cash_and_equivalents=4_000_000_000.0,
                    source_snippet="Revenues for the year ended December 31, 2024 were $14.0 billion",
                )
            ],
            interim=[],
        )
        d = f.model_dump()
        f2 = ProspectusFinancials.model_validate(d)
        self.assertEqual(f2.annual[0].revenue, 14_000_000_000.0)
        self.assertEqual(f2.interim, [])

    def test_missing_period_label_rejected(self):
        with self.assertRaises(ValidationError):
            AnnualFinancialRow(revenue=1.0, source_snippet="x")  # type: ignore[call-arg]


class TestCategoryResult(unittest.TestCase):
    def test_score_bounds(self):
        with self.assertRaises(ValidationError):
            ProspectusCategoryResult(
                category="Business Quality", content="x", score=150, key_findings=[]
            )


class TestThesisOutput(unittest.TestCase):
    def test_verdict_enum(self):
        with self.assertRaises(ValidationError):
            ProspectusThesisOutput(
                thesis_statement="x",
                key_risks=[],
                ipo_verdict="buy",  # type: ignore[arg-type]
                price_range_commentary=None,
                post_ipo_research_plan=[],
            )

    def test_post_ipo_plan_shape(self):
        out = ProspectusThesisOutput(
            thesis_statement="x",
            key_risks=[],
            ipo_verdict=IPOVerdict.WATCH_POST_LOCKUP,
            price_range_commentary=None,
            post_ipo_research_plan=[
                PostIPOPlanItem(
                    question="What's gross margin trajectory once Starlink subscriber growth normalises?",
                    why_it_matters="Bear thesis on launch unit economics",
                    expected_data_source="FMP quarterly + transcript",
                )
            ],
        )
        self.assertEqual(len(out.post_ipo_research_plan), 1)
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_schemas -v
```

Expected: `ImportError` for `backend.app.models.prospectus_schemas`.

- [ ] **Step 3: Implement the schemas**

Create `backend/app/models/prospectus_schemas.py`:

```python
"""Pydantic schemas for ProspectusReport.step_outputs entries.

One schema per step. All shapes are JSON-serialisable and round-trip
through model_validate / model_dump unchanged so they can be persisted
into and rehydrated from the `prospectus_reports.step_outputs` JSONB
column without custom encoders.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ── Step 1 — ingest ──────────────────────────────────────────────────────────


class ExtractedSectionSummary(BaseModel):
    """One row per filing section extracted from the S-1."""
    section_key: str
    heading: str
    char_count: int


class AnnualFinancialRow(BaseModel):
    period_label: str = Field(..., description="e.g. 'FY2024' or 'Year ended Dec 31, 2024'")
    revenue: float | None = None
    cost_of_revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    cash_and_equivalents: float | None = None
    total_debt: float | None = None
    source_snippet: str = Field(..., description="Verbatim sentence(s) from the S-1 supporting these figures.")


class InterimFinancialRow(BaseModel):
    period_label: str = Field(..., description="e.g. 'Six months ended Jun 30, 2025'")
    revenue: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    source_snippet: str


class ProspectusFinancials(BaseModel):
    annual: list[AnnualFinancialRow] = Field(default_factory=list)
    interim: list[InterimFinancialRow] = Field(default_factory=list)


class IngestStepOutput(BaseModel):
    accession_number: str
    primary_document_url: str
    issuer_cik: str
    issuer_name: str
    proposed_ticker: str | None = None
    form_type: str
    sections: list[ExtractedSectionSummary]
    financials: ProspectusFinancials


# ── Step 2 — relationships ───────────────────────────────────────────────────


class RelationshipSummary(BaseModel):
    counterparty_name: str
    relationship_type: str
    magnitude_pct: float | None = None
    resolved_to_ticker: str | None = None
    verbatim_quote: str


class RelationshipsStepOutput(BaseModel):
    edges_extracted: int
    edges_resolved: int
    edges: list[RelationshipSummary]


# ── Step 3 — categories ──────────────────────────────────────────────────────


class ProspectusCategoryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: str
    content: str
    score: int = Field(..., ge=0, le=100)
    key_findings: list[str] = Field(default_factory=list)


class CategoriesStepOutput(BaseModel):
    results: dict[str, ProspectusCategoryResult]
    failures: dict[str, str] = Field(default_factory=dict)


# ── Step 4 — thesis ──────────────────────────────────────────────────────────


class IPOVerdict(str, Enum):
    PARTICIPATE = "participate"
    WATCH_POST_LOCKUP = "watch_post_lockup"
    PASS = "pass"


class KeyRisk(BaseModel):
    risk: str
    severity: Literal["low", "medium", "high"]
    category_source: str


class PostIPOPlanItem(BaseModel):
    question: str
    why_it_matters: str
    expected_data_source: str


class ProspectusThesisOutput(BaseModel):
    thesis_statement: str
    key_risks: list[KeyRisk]
    ipo_verdict: IPOVerdict
    price_range_commentary: str | None = None
    post_ipo_research_plan: list[PostIPOPlanItem]
```

- [ ] **Step 4: Rerun tests**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_schemas -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/prospectus_schemas.py backend/tests/test_prospectus_schemas.py
git commit -m "$(cat <<'EOF'
feat(prospectus): add Pydantic schemas for step outputs

Four step output shapes (ingest, relationships, categories, thesis)
with IPOVerdict enum. All JSON-round-trippable for persistence into
prospectus_reports.step_outputs JSONB.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 2 — S-1 section extraction

### Task 3: S-1 regex defs in edgar_html.py

**Files:**
- Modify: `backend/app/services/edgar_html.py:42-159` (add `_SECTION_DEFS_S1` and route it in `_pick_section_defs`)
- Test: `backend/tests/test_edgar_html_s1.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_edgar_html_s1.py`:

```python
"""Section extraction tests for S-1 / S-1/A filings."""
import unittest

from backend.app.services.edgar_html import extract_sections


def _fake_s1_html(*, business=True, risks=True, mda=True,
                  proceeds=True, capitalization=True, dilution=True,
                  principal=True, underwriting=True) -> str:
    """Construct a synthetic S-1 HTML body. Each section gets >500 chars so
    extract_sections's MIN_SECTION_CHARS gate is satisfied. Boundary text
    between sections caps the prior section's body.
    """
    pad = " The following paragraph contains substantive narrative content " * 10  # ~640 chars

    parts: list[str] = ["<html><body>"]
    if business:
        parts.append(f"<p>ITEM 1. BUSINESS</p><p>We design, manufacture and launch rockets.{pad}</p>")
    if risks:
        parts.append(f"<p>RISK FACTORS</p><p>Our business is subject to many risks.{pad}</p>")
    if mda:
        parts.append(f"<p>MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS</p>"
                     f"<p>Revenues for the year ended Dec 31, 2024 were $14.0 billion.{pad}</p>")
    if proceeds:
        parts.append(f"<p>USE OF PROCEEDS</p><p>We intend to use the net proceeds for general corporate purposes.{pad}</p>")
    if capitalization:
        parts.append(f"<p>CAPITALIZATION</p><p>The following table sets forth our capitalization.{pad}</p>")
    if dilution:
        parts.append(f"<p>DILUTION</p><p>If you invest in our Class A common stock you will experience dilution.{pad}</p>")
    if principal:
        parts.append(f"<p>PRINCIPAL STOCKHOLDERS</p><p>The following table sets forth our principal stockholders.{pad}</p>")
    if underwriting:
        parts.append(f"<p>UNDERWRITING</p><p>Subject to the terms and conditions of the underwriting agreement.{pad}</p>")
    parts.append("</body></html>")
    return "".join(parts)


class TestS1Sections(unittest.TestCase):
    def test_all_eight_sections_extracted(self):
        sections = extract_sections(_fake_s1_html(), "S-1")
        keys = {s.section_key for s in sections}
        self.assertEqual(keys, {
            "s1_business", "s1_risk_factors", "s1_mda",
            "s1_use_of_proceeds", "s1_capitalization", "s1_dilution",
            "s1_principal_stockholders", "s1_underwriting",
        })

    def test_s1a_uses_same_defs(self):
        sections = extract_sections(_fake_s1_html(), "S-1/A")
        keys = {s.section_key for s in sections}
        self.assertIn("s1_business", keys)
        self.assertIn("s1_underwriting", keys)

    def test_missing_section_silently_skipped(self):
        sections = extract_sections(_fake_s1_html(dilution=False), "S-1")
        keys = {s.section_key for s in sections}
        self.assertNotIn("s1_dilution", keys)
        self.assertIn("s1_business", keys)
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_edgar_html_s1 -v
```

Expected: all tests fail — `extract_sections` returns `[]` for unrecognised form type.

- [ ] **Step 3: Add S-1 defs to edgar_html.py**

Edit `backend/app/services/edgar_html.py`. After the existing `_SECTION_DEFS_DEF14A` block (around line 99-106), append:

```python
_SECTION_DEFS_S1: list[tuple[str, list[str]]] = [
    # Headings on S-1s are not "ITEM N." prefixed — they are standalone
    # section titles in all caps. Anchor each to a word boundary.
    ("s1_business", [r"\bITEM\s*1\.?\s*BUSINESS\b", r"\bBUSINESS\b"]),
    ("s1_risk_factors", [
        r"\bITEM\s*1A\.?\s*RISK\s+FACTORS\b",
        r"\bRISK\s+FACTORS\b",
    ]),
    ("s1_mda", [
        r"\bMANAGEMENT['’]?S\s+DISCUSSION\s+AND\s+ANALYSIS"
        r"(?:\s+O\s*F\s+FINANCIAL\s+CONDITION\s+AND\s+RESULTS\s+O\s*F\s+OPERATIONS)?",
    ]),
    ("s1_use_of_proceeds", [r"\bUSE\s+OF\s+PROCEEDS\b"]),
    ("s1_capitalization", [r"\bCAPITALIZATION\b"]),
    ("s1_dilution", [r"\bDILUTION\b"]),
    ("s1_principal_stockholders", [
        r"\bPRINCIPAL\s+(?:AND\s+SELLING\s+)?STOCKHOLDERS\b",
    ]),
    ("s1_underwriting", [
        r"\bUNDERWRITING\b",
        r"\bPLAN\s+OF\s+DISTRIBUTION\b",
    ]),
]
```

Then update `_pick_section_defs` (around line 151-159):

```python
def _pick_section_defs(form_type: str) -> list[tuple[str, list[str]]]:
    key = form_type.upper().replace(" ", "").replace("/", "")
    if "10-K" in key or "10K" in key:
        return _SECTION_DEFS_10K
    if "10-Q" in key or "10Q" in key:
        return _SECTION_DEFS_10Q
    if "DEF14A" in key:
        return _SECTION_DEFS_DEF14A
    if key.startswith("S-1") or key.startswith("S1"):
        return _SECTION_DEFS_S1
    return []
```

- [ ] **Step 4: Rerun the test**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_edgar_html_s1 -v
```

Expected: all tests PASS. If they don't, the issue is almost certainly the heading-vs-body length picker — read the section "best_by_key" logic in `extract_sections` and verify the synthetic HTML's section bodies exceed `MIN_SECTION_CHARS` (500). Add more `pad` repetitions until they do.

- [ ] **Step 5: Run the full existing edgar_html / sections test suite to confirm no regressions**

```bash
source backend/venv/bin/activate && python -m unittest discover -s backend/tests -p 'test_*.py' -v 2>&1 | tail -30
```

Expected: existing tests still pass (no `_SECTION_DEFS_10K` regression).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/edgar_html.py backend/tests/test_edgar_html_s1.py
git commit -m "$(cat <<'EOF'
feat(prospectus): add S-1 section regex defs to edgar_html

Eight S-1-specific section keys: Business, Risk Factors, MD&A,
Use of Proceeds, Capitalization, Dilution, Principal Stockholders,
Underwriting. Handles S-1 and S-1/A form variants.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Prospectus ingest service

**Files:**
- Create: `backend/app/services/prospectus_ingest.py`
- Test: `backend/tests/test_prospectus_ingest.py`

The ingest service: resolves either a URL or an accession number to a CIK + primary doc URL, fetches the HTML via `EdgarClient`, extracts sections via `extract_sections`, persists a `Filing` row keyed to the synthetic ticker, persists each `FilingSection`, and returns an `IngestStepOutput` (without `financials` — that comes in Task 5).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prospectus_ingest.py`:

```python
"""Tests for prospectus_ingest.ingest_prospectus."""
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date

from backend.app.services.prospectus_ingest import (
    parse_source_input,
    SourceInput,
)


class TestParseSourceInput(unittest.TestCase):
    def test_url_form(self):
        url = ("https://www.sec.gov/Archives/edgar/data/1181412/"
               "000162828026036936/spaceexplorationtechnologi.htm")
        src = parse_source_input(url)
        self.assertEqual(src.cik_trimmed, "1181412")
        self.assertEqual(src.accession_number, "0001628280-26-036936")
        self.assertEqual(src.primary_document, "spaceexplorationtechnologi.htm")

    def test_accession_form(self):
        src = parse_source_input("0001628280-26-036936")
        self.assertEqual(src.accession_number, "0001628280-26-036936")
        self.assertIsNone(src.cik_trimmed)
        self.assertIsNone(src.primary_document)

    def test_invalid_input_raises(self):
        with self.assertRaises(ValueError):
            parse_source_input("not an accession or url")
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_ingest -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the service**

Create `backend/app/services/prospectus_ingest.py`:

```python
"""Ingest an S-1 / S-1/A prospectus from EDGAR.

Mirrors edgar_sections_ingest.py but for prospectus filings:
  * Accepts either a primary-document URL or a bare accession number.
  * Resolves issuer (CIK, name) and primary document via EdgarClient.
  * Persists the filing under a synthetic ticker so the existing
    filings/filing_sections/relationships pipeline works unchanged.
  * Does NOT do embedded-financials extraction (that lives in
    prospectus_financials.py — separate Sonnet call).

The caller (ProspectusService) owns the session and the commit.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.clients.edgar import EdgarClient, EdgarClientError
from backend.app.models.filing import Filing, FilingSection
from backend.app.models.prospectus_schemas import (
    ExtractedSectionSummary,
    IngestStepOutput,
    ProspectusFinancials,
)
from backend.app.services.edgar_html import extract_sections

logger = logging.getLogger(__name__)

PROSPECTUS_FORM_TYPES: tuple[str, ...] = ("S-1", "S-1/A")


@dataclass
class SourceInput:
    accession_number: str
    cik_trimmed: str | None
    primary_document: str | None


_URL_PATTERN = re.compile(
    r"sec\.gov/Archives/edgar/data/(?P<cik>\d+)/(?P<accn_nodash>\d{18})/(?P<doc>[^/?\s]+)",
    re.IGNORECASE,
)
_ACCN_PATTERN = re.compile(r"^\d{10}-\d{2}-\d{6}$")


def parse_source_input(text: str) -> SourceInput:
    text = text.strip()
    m = _URL_PATTERN.search(text)
    if m:
        accn_nodash = m.group("accn_nodash")
        return SourceInput(
            accession_number=f"{accn_nodash[:10]}-{accn_nodash[10:12]}-{accn_nodash[12:]}",
            cik_trimmed=m.group("cik"),
            primary_document=m.group("doc"),
        )
    if _ACCN_PATTERN.match(text):
        return SourceInput(accession_number=text, cik_trimmed=None, primary_document=None)
    raise ValueError(f"Could not parse {text!r} as an EDGAR URL or accession number")


async def _resolve_issuer_from_submissions(
    edgar: EdgarClient, cik_trimmed: str
) -> tuple[str, str]:
    """Return (cik_padded, issuer_name) for a trimmed CIK."""
    cik_padded = cik_trimmed.zfill(10)
    submissions, _ = await edgar.get_submissions(cik_padded)
    name = submissions.get("name") or submissions.get("entityName") or ""
    return cik_padded, name


async def _find_filing_in_submissions(submissions: dict, accession_number: str) -> dict | None:
    """Walk the submissions feed (recent + paginated older files) and return
    the entry for this accession. Returns None if not found."""
    recent = submissions.get("filings", {}).get("recent", {}) or {}
    accessions = recent.get("accessionNumber", []) or []
    for i, acc in enumerate(accessions):
        if acc == accession_number:
            return {
                "form": recent.get("form", [])[i],
                "primary_document": recent.get("primaryDocument", [])[i],
                "filing_date": recent.get("filingDate", [])[i],
                "period_of_report": recent.get("reportDate", [])[i] or None,
            }
    return None


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        from datetime import datetime
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


async def ingest_prospectus(
    *,
    source: SourceInput,
    synthetic_ticker: str,
    issuer_cik: str | None,
    db: AsyncSession,
    edgar: EdgarClient,
) -> tuple[Filing, IngestStepOutput]:
    """Resolve, fetch, extract sections, persist. Returns (Filing, IngestStepOutput)
    with `financials` defaulted to empty (caller fills it in via Task 5).

    `issuer_cik` if supplied is treated as authoritative. Otherwise we infer
    from `source.cik_trimmed` (URL parse).
    """
    cik_trimmed = (
        str(int(issuer_cik)) if issuer_cik
        else source.cik_trimmed
    )
    if not cik_trimmed:
        raise ValueError(
            "Cannot resolve issuer CIK — supply issuer_cik or pass a full URL"
        )

    cik_padded, issuer_name = await _resolve_issuer_from_submissions(edgar, cik_trimmed)

    submissions, _ = await edgar.get_submissions(cik_padded)
    entry = await _find_filing_in_submissions(submissions, source.accession_number)
    if entry is None:
        raise ValueError(
            f"Accession {source.accession_number} not found in submissions feed for CIK {cik_padded}"
        )

    form_type = entry["form"]
    if form_type not in PROSPECTUS_FORM_TYPES:
        raise ValueError(
            f"Filing {source.accession_number} is form '{form_type}', not S-1 / S-1/A"
        )

    primary_document = source.primary_document or entry["primary_document"]
    if not primary_document:
        raise ValueError(f"No primary document for {source.accession_number}")

    accn_no_dash = source.accession_number.replace("-", "")
    primary_url = (
        f"https://www.sec.gov/Archives/edgar/data/{cik_trimmed}/"
        f"{accn_no_dash}/{primary_document}"
    )

    # Upsert Filing row (under synthetic ticker so downstream code paths work)
    existing = await db.execute(
        select(Filing).where(Filing.accession_number == source.accession_number)
    )
    filing = existing.scalar_one_or_none()
    filing_date = _parse_date(entry["filing_date"]) or date.today()
    if filing is None:
        filing = Filing(
            accession_number=source.accession_number,
            cik=cik_padded,
            ticker=synthetic_ticker,
            form_type=form_type[:16],
            filing_date=filing_date,
            period_of_report=_parse_date(entry.get("period_of_report")),
            primary_document_url=primary_url,
        )
        db.add(filing)
        await db.flush()
    elif not filing.primary_document_url:
        filing.primary_document_url = primary_url

    # Fetch HTML and extract sections
    try:
        html, _ = await edgar.fetch_document(primary_url)
    except EdgarClientError as e:
        raise RuntimeError(f"Failed to fetch primary document: {e}") from e

    sections = extract_sections(html, form_type)

    # Persist sections idempotently
    existing_keys_rows = await db.execute(
        select(FilingSection.section_key).where(FilingSection.filing_id == filing.id)
    )
    existing_keys = set(existing_keys_rows.scalars().all())
    summaries: list[ExtractedSectionSummary] = []
    for section in sections:
        if section.section_key not in existing_keys:
            db.add(FilingSection(
                filing_id=filing.id,
                ticker=synthetic_ticker,
                section_key=section.section_key,
                heading=section.heading,
                text=section.text,
                char_count=section.char_count,
                extraction_method=section.extraction_method,
            ))
        summaries.append(ExtractedSectionSummary(
            section_key=section.section_key,
            heading=section.heading,
            char_count=section.char_count,
        ))
    await db.flush()

    out = IngestStepOutput(
        accession_number=source.accession_number,
        primary_document_url=primary_url,
        issuer_cik=cik_padded,
        issuer_name=issuer_name,
        proposed_ticker=None,  # not derivable from S-1 metadata; set by API caller
        form_type=form_type,
        sections=summaries,
        financials=ProspectusFinancials(),  # populated by Task 5
    )
    return filing, out
```

- [ ] **Step 4: Rerun the parse_source_input tests**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_ingest -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prospectus_ingest.py backend/tests/test_prospectus_ingest.py
git commit -m "$(cat <<'EOF'
feat(prospectus): ingest service for S-1 / S-1/A filings

parse_source_input accepts URL or bare accession. ingest_prospectus
resolves issuer via EdgarClient submissions feed, fetches the primary
document, extracts sections, persists Filing + FilingSection rows under
the synthetic ticker. Caller owns the session and commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 3 — Embedded financials extraction

### Task 5: ProspectusFinancials Sonnet extractor

**Files:**
- Create: `backend/app/services/prospectus_financials.py`
- Test: `backend/tests/test_prospectus_financials.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prospectus_financials.py`:

```python
"""Tests for prospectus_financials.extract_financials."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.services.prospectus_financials import extract_financials
from backend.app.models.prospectus_schemas import ProspectusFinancials


class TestExtractFinancials(unittest.TestCase):
    def test_parses_sonnet_response(self):
        mock_response = json.dumps({
            "annual": [
                {
                    "period_label": "FY2024",
                    "revenue": 14000000000.0,
                    "operating_income": 2000000000.0,
                    "net_income": 1500000000.0,
                    "cash_and_equivalents": 4000000000.0,
                    "total_debt": 1000000000.0,
                    "cost_of_revenue": 9000000000.0,
                    "source_snippet": "Revenues for the year ended December 31, 2024 were $14.0 billion"
                }
            ],
            "interim": []
        })
        with patch(
            "backend.app.services.prospectus_financials.complete",
            new=AsyncMock(return_value=mock_response),
        ):
            import asyncio
            fin = asyncio.run(extract_financials(
                mda_text="Some narrative",
                selected_financials_text="Table of figures",
            ))
        self.assertIsInstance(fin, ProspectusFinancials)
        self.assertEqual(len(fin.annual), 1)
        self.assertEqual(fin.annual[0].revenue, 14_000_000_000.0)

    def test_empty_text_returns_empty_struct(self):
        import asyncio
        fin = asyncio.run(extract_financials(mda_text="", selected_financials_text=""))
        self.assertEqual(fin.annual, [])
        self.assertEqual(fin.interim, [])

    def test_garbled_response_returns_empty_struct(self):
        with patch(
            "backend.app.services.prospectus_financials.complete",
            new=AsyncMock(return_value="not json at all"),
        ):
            import asyncio
            fin = asyncio.run(extract_financials(
                mda_text="x", selected_financials_text="y",
            ))
        self.assertEqual(fin.annual, [])
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_financials -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the extractor**

Create `backend/app/services/prospectus_financials.py`:

```python
"""Extract embedded financial figures from S-1 narrative.

S-1s present multi-year financials in three places:
  * Selected Financial Data table (usually right before MD&A)
  * MD&A's "Results of Operations" subsection
  * Consolidated statements at the back

We send Sonnet the MD&A text + any explicitly-collected Selected
Financial Data block and ask for a small, named-key-per-period schema.
A missing year is an explicit null, not a corrupted row.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import ValidationError

from backend.app.graph.llm import SONNET, complete
from backend.app.models.prospectus_schemas import ProspectusFinancials

logger = logging.getLogger(__name__)

CHAR_BUDGET = 25_000

_SYSTEM = """You extract historical financial figures from S-1 / S-1/A prospectus narrative and tables.

Rules:
- Output ONLY valid JSON matching the schema below — no commentary, no markdown fences.
- Currency is whatever the filing reports (dollars, thousands, millions — convert to raw dollars in the output).
- For any field you cannot find with confidence, use null. Do NOT guess.
- `source_snippet` is a verbatim 1-2 sentence quote from the text supporting the row.
- Include up to 3 most-recent annual periods and up to 2 most-recent interim periods.

Schema:
{
  "annual": [
    {
      "period_label": "FY2024",
      "revenue": 14000000000.0,
      "cost_of_revenue": 9000000000.0,
      "operating_income": 2000000000.0,
      "net_income": 1500000000.0,
      "cash_and_equivalents": 4000000000.0,
      "total_debt": 1000000000.0,
      "source_snippet": "Revenues for the year ended December 31, 2024 were $14.0 billion"
    }
  ],
  "interim": [
    {
      "period_label": "Six months ended Jun 30, 2025",
      "revenue": 8000000000.0,
      "operating_income": 1200000000.0,
      "net_income": 900000000.0,
      "source_snippet": "Revenues for the six months ended June 30, 2025 were $8.0 billion"
    }
  ]
}
"""


async def extract_financials(*, mda_text: str, selected_financials_text: str) -> ProspectusFinancials:
    """Return a ProspectusFinancials. Empty when inputs are empty or Sonnet
    returns un-parseable output (caller decides whether that's a soft fail)."""
    body = (selected_financials_text + "\n\n" + mda_text).strip()
    if not body:
        return ProspectusFinancials()

    user = f"Extract financials from the following prospectus narrative.\n\n---\n{body[:CHAR_BUDGET]}\n---"

    try:
        raw = await complete(
            system=_SYSTEM,
            user=user,
            model=SONNET,
            max_tokens=4096,
            assistant_prefill='{"annual":',
        )
    except Exception as e:
        logger.warning("prospectus financials Sonnet call failed: %s", e)
        return ProspectusFinancials()

    # The prefill biases the response to start with `{"annual":` — prepend it
    # back before parsing.
    candidate = raw if raw.lstrip().startswith("{") else '{"annual":' + raw

    try:
        payload: Any = json.loads(candidate)
        return ProspectusFinancials.model_validate(payload)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.warning("prospectus financials parse failed: %s; first 200 chars: %r", e, candidate[:200])
        return ProspectusFinancials()
```

- [ ] **Step 4: Rerun the tests**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_financials -v
```

Expected: all PASS. (The first test patches `complete` and asserts the parse; the second and third assert soft-fail behaviour.)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prospectus_financials.py backend/tests/test_prospectus_financials.py
git commit -m "$(cat <<'EOF'
feat(prospectus): Sonnet extractor for embedded S-1 financials

Small named-key schema (3 annual + 2 interim rows max). Missing fields
return null rather than guesses. Garbled Sonnet response or call failure
returns an empty ProspectusFinancials so the caller can persist a record
and surface the soft-fail to the UI.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 4 — Relationship extraction (extend existing extractor)

### Task 6: Add S-1 keys to EXTRACTABLE_SECTION_KEYS + use existing extractor

**Files:**
- Modify: `backend/app/services/edgar_relationships.py:34-39` (extend `EXTRACTABLE_SECTION_KEYS`)
- Test: `backend/tests/test_edgar_relationships_s1.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_edgar_relationships_s1.py`:

```python
"""Verify the existing relationship extractor handles S-1 section keys."""
import unittest
from backend.app.services.edgar_relationships import EXTRACTABLE_SECTION_KEYS


class TestS1ExtractableKeys(unittest.TestCase):
    def test_s1_business_extractable(self):
        self.assertIn("s1_business", EXTRACTABLE_SECTION_KEYS)

    def test_s1_risk_factors_extractable(self):
        self.assertIn("s1_risk_factors", EXTRACTABLE_SECTION_KEYS)

    def test_s1_underwriting_not_extractable(self):
        """Underwriting is deal mechanics, not counterparty relationships."""
        self.assertNotIn("s1_underwriting", EXTRACTABLE_SECTION_KEYS)
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_edgar_relationships_s1 -v
```

Expected: first two tests FAIL.

- [ ] **Step 3: Extend the tuple**

Edit `backend/app/services/edgar_relationships.py`. Replace the `EXTRACTABLE_SECTION_KEYS` tuple definition (around line 34-39):

```python
EXTRACTABLE_SECTION_KEYS: tuple[str, ...] = (
    "item_1_business",
    "item_1a_risk_factors",
    "item_7_mda",
    "item_2_mda_10q",
    "s1_business",
    "s1_risk_factors",
)
```

- [ ] **Step 4: Rerun the test + the existing relationship test**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_edgar_relationships_s1 -v && python -m unittest discover -s backend/tests -p 'test_*relation*.py' -v 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/edgar_relationships.py backend/tests/test_edgar_relationships_s1.py
git commit -m "$(cat <<'EOF'
feat(prospectus): route S-1 business + risk-factors through relationship extractor

Two new entries in EXTRACTABLE_SECTION_KEYS. The extractor itself is
already section-key-keyed and form-agnostic, so no logic changes required.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 5 — Category analysis (parallel deep-dive)

### Task 7: Category prompts module

**Files:**
- Create: `backend/app/graph/prospectus_prompts.py`

This file holds the seven category prompts plus the shared user-template formatter. Each prompt is self-contained — no FMP context, no transcripts.

- [ ] **Step 1: Create the prompts module**

Create `backend/app/graph/prospectus_prompts.py`:

```python
"""Prompts for the prospectus pipeline's per-category analyses.

Seven categories. Six are adaptations of the equity deep-dive categories,
limited to what an S-1 actually answers. The seventh ("IPO Mechanics") is
new and scopes deal structure, dilution, lock-ups and use of proceeds.

Each system prompt asks Sonnet to return ONE JSON object matching:

{
  "category": "<name>",
  "content": "<markdown analysis>",
  "score": <0-100>,
  "key_findings": ["...", "..."]
}
"""
from __future__ import annotations

PROSPECTUS_CATEGORIES: tuple[str, ...] = (
    "Business Quality",
    "Risk Assessment",
    "Growth & Earnings",
    "Management & Governance",
    "Future Durability",
    "Macro & Regime",
    "IPO Mechanics",
)


# Sections each category receives. Keys are S-1 section_keys (Task 3) — the
# orchestrator pulls each section's text from filing_sections and renders it
# into {filing_excerpts} via the formatter below.
CATEGORY_SECTION_ROUTING: dict[str, tuple[str, ...]] = {
    "Business Quality": ("s1_business",),
    "Risk Assessment": ("s1_risk_factors", "s1_capitalization", "s1_dilution"),
    "Growth & Earnings": ("s1_mda",),
    "Management & Governance": ("s1_principal_stockholders", "s1_business"),
    "Future Durability": ("s1_business", "s1_use_of_proceeds"),
    "Macro & Regime": (),  # no S-1 sections — runs on FRED only
    "IPO Mechanics": ("s1_underwriting", "s1_use_of_proceeds", "s1_dilution"),
}

# Whether a category receives the counterparty context payload.
CATEGORY_USES_RELATIONSHIPS: frozenset[str] = frozenset({
    "Business Quality", "Risk Assessment", "Future Durability",
})

# Whether a category receives FRED macro data.
CATEGORY_USES_MACRO: frozenset[str] = frozenset({"Macro & Regime", "Future Durability"})

SECTION_BUDGET_CHARS = 8_000


PROSPECTUS_SYSTEM = """You are a fundamental analyst evaluating a company that has just filed an S-1 prospectus to go public.

You will analyse ONE category. Your inputs are verbatim excerpts from the S-1 plus, depending on the category, an extracted counterparty context and macro indicators.

Constraints:
- Be specific. Cite verbatim phrases from the filing in quotes when they support a claim.
- This is a private company about to IPO. There is no analyst consensus, no earnings transcript, no trading history. Do not invent any of those — work strictly from the inputs.
- Output a single JSON object with keys: category, content (markdown), score (0-100), key_findings (list of 3-6 short bullets). No prose outside the JSON.
- Score rubric for an IPO context:
   0-30 = serious concerns / disqualifying weakness
   31-55 = uncertain or below average
   56-75 = competent / typical
   76-100 = standout strength

Category being analysed: {category}
"""


PROSPECTUS_USER = """Category: {category}

{filing_excerpts}

{counterparty_context}

{macro_indicators}

Issuer: {issuer_name} (filing date: {filing_date}, form: {form_type})

Produce the JSON object now."""


# ── Per-category USER refinements (appended to PROSPECTUS_USER) ──────────────

CATEGORY_FOCUS: dict[str, str] = {
    "Business Quality": (
        "Focus on: what does the company actually do, who are its customers, "
        "what are its unit economics, what's the durability of its competitive position, "
        "is the business model proven or experimental."
    ),
    "Risk Assessment": (
        "Focus on: which risk factors are boilerplate vs. concrete; pre-IPO capital "
        "structure (Capitalization); dilution profile post-offering; concentration risks; "
        "regulatory / customer / supplier dependencies. Differentiate severity."
    ),
    "Growth & Earnings": (
        "Focus on: revenue trajectory, gross margin progression, opex leverage, "
        "path to profitability (or commentary on it), and any forward-looking statements "
        "in the MD&A that bound expectations for the next 12-24 months."
    ),
    "Management & Governance": (
        "Focus on: insider ownership concentration, founder / control-person structure "
        "(dual-class, voting agreements), independence of the board, related-party "
        "transactions, executive comp structure."
    ),
    "Future Durability": (
        "Focus on: where the capital raised will be deployed, the addressable-market "
        "narrative, vulnerability to macro / rate regimes, and counterparty concentration "
        "that could break the durability story."
    ),
    "Macro & Regime": (
        "Focus on: where the issuer sits in the current macro regime (rates, growth, "
        "inflation, credit). If the macro inputs are minimal, say so and score conservatively."
    ),
    "IPO Mechanics": (
        "Focus on: deal size, share count, primary vs. secondary mix, underwriter syndicate "
        "quality, use-of-proceeds clarity (concrete vs. 'general corporate purposes'), "
        "dilution to existing holders, lock-up structure (180-day standard? extended? early "
        "release triggers?), and post-offering float."
    ),
}
```

- [ ] **Step 2: Quick import-only sanity test**

```bash
source backend/venv/bin/activate && python -c "from backend.app.graph.prospectus_prompts import PROSPECTUS_CATEGORIES, CATEGORY_SECTION_ROUTING, PROSPECTUS_SYSTEM; assert len(PROSPECTUS_CATEGORIES) == 7; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/graph/prospectus_prompts.py
git commit -m "$(cat <<'EOF'
feat(prospectus): per-category prompts for prospectus deep-dive

Seven categories (six adapted from equity deep-dive + IPO Mechanics).
Section routing table + counterparty / macro toggles + per-category
focus block. JSON output shape matches ProspectusCategoryResult schema.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Category runner service

**Files:**
- Create: `backend/app/services/prospectus_categories.py`
- Test: `backend/tests/test_prospectus_categories.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prospectus_categories.py`:

```python
"""Tests for prospectus_categories.run_categories."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.services.prospectus_categories import run_categories
from backend.app.models.prospectus_schemas import CategoriesStepOutput


def _category_payload(name: str, score: int = 65) -> str:
    return json.dumps({
        "category": name,
        "content": f"## Analysis for {name}\n\nThis is markdown.",
        "score": score,
        "key_findings": [f"{name} finding 1", f"{name} finding 2"],
    })


class TestRunCategories(unittest.IsolatedAsyncioTestCase):
    async def test_all_seven_categories_run(self):
        async def fake_complete(*, system, user, **kw):
            # Extract category name from system prompt
            for cat in (
                "Business Quality", "Risk Assessment", "Growth & Earnings",
                "Management & Governance", "Future Durability",
                "Macro & Regime", "IPO Mechanics",
            ):
                if cat in system:
                    return _category_payload(cat)
            return _category_payload("UNKNOWN")

        with patch("backend.app.services.prospectus_categories.complete",
                   new=AsyncMock(side_effect=fake_complete)):
            out = await run_categories(
                issuer_name="ACME Rockets",
                filing_date="2026-05-20",
                form_type="S-1",
                sections_text={
                    "s1_business": "We build rockets.",
                    "s1_risk_factors": "Risks include unicorn attacks.",
                    "s1_mda": "Revenues grew.",
                    "s1_principal_stockholders": "Founder owns 78%.",
                    "s1_use_of_proceeds": "GP&A.",
                    "s1_capitalization": "Debt is low.",
                    "s1_dilution": "20% dilution.",
                    "s1_underwriting": "Goldman / MS / JPM.",
                },
                counterparty_context="",
                macro_indicators="",
            )

        self.assertIsInstance(out, CategoriesStepOutput)
        self.assertEqual(set(out.results.keys()), {
            "Business Quality", "Risk Assessment", "Growth & Earnings",
            "Management & Governance", "Future Durability",
            "Macro & Regime", "IPO Mechanics",
        })
        self.assertEqual(out.failures, {})

    async def test_one_category_failure_does_not_abort_others(self):
        async def fake_complete(*, system, user, **kw):
            if "Business Quality" in system:
                raise RuntimeError("anthropic 503")
            for cat in (
                "Risk Assessment", "Growth & Earnings",
                "Management & Governance", "Future Durability",
                "Macro & Regime", "IPO Mechanics",
            ):
                if cat in system:
                    return _category_payload(cat)
            return _category_payload("?")

        with patch("backend.app.services.prospectus_categories.complete",
                   new=AsyncMock(side_effect=fake_complete)):
            out = await run_categories(
                issuer_name="X", filing_date="2026-05-20", form_type="S-1",
                sections_text={k: "x" for k in (
                    "s1_business", "s1_risk_factors", "s1_mda",
                    "s1_principal_stockholders", "s1_use_of_proceeds",
                    "s1_capitalization", "s1_dilution", "s1_underwriting",
                )},
                counterparty_context="",
                macro_indicators="",
            )

        self.assertIn("Business Quality", out.failures)
        self.assertEqual(len(out.results), 6)
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_categories -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the runner**

Create `backend/app/services/prospectus_categories.py`:

```python
"""Parallel per-category analysis for a prospectus report.

Mirrors graph/nodes.py::node_deep_dive but skips the FMP/transcripts/
analyst-data scaffolding entirely. Each category gets a self-contained
prompt assembled from the S-1 sections it cares about.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable

from pydantic import ValidationError

from backend.app.graph.llm import SONNET, complete
from backend.app.graph.prospectus_prompts import (
    CATEGORY_SECTION_ROUTING,
    CATEGORY_USES_MACRO,
    CATEGORY_USES_RELATIONSHIPS,
    CATEGORY_FOCUS,
    PROSPECTUS_CATEGORIES,
    PROSPECTUS_SYSTEM,
    PROSPECTUS_USER,
    SECTION_BUDGET_CHARS,
)
from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    ProspectusCategoryResult,
)

logger = logging.getLogger(__name__)


def _render_filing_excerpts(sections_text: dict[str, str], keys: tuple[str, ...]) -> str:
    if not keys:
        return "_No S-1 sections routed to this category._"
    blocks: list[str] = []
    for key in keys:
        text = (sections_text.get(key) or "").strip()
        if not text:
            continue
        blocks.append(f"### {key}\n\n{text[:SECTION_BUDGET_CHARS]}")
    if not blocks:
        return "_The referenced S-1 sections were not extracted from this filing._"
    return "## S-1 Excerpts\n\n" + "\n\n".join(blocks)


async def _run_one_category(
    *,
    category: str,
    issuer_name: str,
    filing_date: str,
    form_type: str,
    sections_text: dict[str, str],
    counterparty_context: str,
    macro_indicators: str,
) -> ProspectusCategoryResult:
    keys = CATEGORY_SECTION_ROUTING.get(category, ())
    focus = CATEGORY_FOCUS.get(category, "")

    user = PROSPECTUS_USER.format(
        category=category,
        filing_excerpts=_render_filing_excerpts(sections_text, keys),
        counterparty_context=(
            "## Counterparty Context\n\n" + counterparty_context
            if category in CATEGORY_USES_RELATIONSHIPS and counterparty_context
            else ""
        ),
        macro_indicators=(
            "## Macro Indicators (FRED)\n\n" + macro_indicators
            if category in CATEGORY_USES_MACRO and macro_indicators
            else ""
        ),
        issuer_name=issuer_name,
        filing_date=filing_date,
        form_type=form_type,
    )
    if focus:
        user = user + "\n\n## Per-category focus\n\n" + focus

    raw = await complete(
        system=PROSPECTUS_SYSTEM.format(category=category),
        user=user,
        model=SONNET,
        max_tokens=3072,
        assistant_prefill='{"category":',
    )
    candidate = raw if raw.lstrip().startswith("{") else '{"category":' + raw
    payload = json.loads(candidate)
    return ProspectusCategoryResult.model_validate(payload)


async def run_categories(
    *,
    issuer_name: str,
    filing_date: str,
    form_type: str,
    sections_text: dict[str, str],
    counterparty_context: str,
    macro_indicators: str,
) -> CategoriesStepOutput:
    """Run all 7 categories in parallel. One failure does not abort the rest."""
    coros = {
        cat: _run_one_category(
            category=cat,
            issuer_name=issuer_name,
            filing_date=filing_date,
            form_type=form_type,
            sections_text=sections_text,
            counterparty_context=counterparty_context,
            macro_indicators=macro_indicators,
        )
        for cat in PROSPECTUS_CATEGORIES
    }
    results: dict[str, ProspectusCategoryResult] = {}
    failures: dict[str, str] = {}
    done = await asyncio.gather(*coros.values(), return_exceptions=True)
    for cat, outcome in zip(coros.keys(), done):
        if isinstance(outcome, Exception):
            logger.warning("[prospectus] category %r failed: %s", cat, outcome)
            failures[cat] = str(outcome)
        else:
            results[cat] = outcome
    return CategoriesStepOutput(results=results, failures=failures)
```

- [ ] **Step 4: Rerun tests**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_categories -v
```

Expected: both tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prospectus_categories.py backend/tests/test_prospectus_categories.py
git commit -m "$(cat <<'EOF'
feat(prospectus): parallel 7-category runner

run_categories fires all seven prospectus categories concurrently via
asyncio.gather(return_exceptions=True); per-category failure is captured
in CategoriesStepOutput.failures rather than aborting the batch.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 6 — Thesis synthesis

### Task 9: Thesis synthesizer

**Files:**
- Create: `backend/app/services/prospectus_thesis.py`
- Test: `backend/tests/test_prospectus_thesis.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prospectus_thesis.py`:

```python
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    IPOVerdict,
    ProspectusCategoryResult,
)
from backend.app.services.prospectus_thesis import synthesize_thesis


def _sample_categories() -> CategoriesStepOutput:
    return CategoriesStepOutput(
        results={
            "Business Quality": ProspectusCategoryResult(
                category="Business Quality", content="strong",
                score=80, key_findings=["bq1", "bq2"],
            ),
            "Risk Assessment": ProspectusCategoryResult(
                category="Risk Assessment", content="moderate",
                score=55, key_findings=["ra1"],
            ),
        },
        failures={},
    )


class TestSynthesizeThesis(unittest.IsolatedAsyncioTestCase):
    async def test_parses_sonnet_thesis_response(self):
        payload = json.dumps({
            "thesis_statement": "ACME has strong unit economics, gated by regulatory risk.",
            "key_risks": [
                {"risk": "FAA approval cadence", "severity": "high", "category_source": "Risk Assessment"},
            ],
            "ipo_verdict": "watch_post_lockup",
            "price_range_commentary": "Range implies 8x forward sales vs peers at 6x.",
            "post_ipo_research_plan": [
                {
                    "question": "Did Q3 launch cadence beat S-1 guidance?",
                    "why_it_matters": "Validates unit economics",
                    "expected_data_source": "FMP quarterly + first earnings call",
                },
            ],
        })
        with patch("backend.app.services.prospectus_thesis.complete",
                   new=AsyncMock(return_value=payload)):
            out = await synthesize_thesis(
                issuer_name="ACME Rockets",
                categories=_sample_categories(),
                financials_json={"annual": []},
            )
        self.assertEqual(out.ipo_verdict, IPOVerdict.WATCH_POST_LOCKUP)
        self.assertEqual(len(out.key_risks), 1)
        self.assertEqual(out.key_risks[0].severity, "high")
        self.assertEqual(len(out.post_ipo_research_plan), 1)
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_thesis -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the thesis synthesizer**

Create `backend/app/services/prospectus_thesis.py`:

```python
"""Final synthesis step — single Sonnet pass over all category outputs."""
from __future__ import annotations

import json
import logging
from typing import Any

from backend.app.graph.llm import SONNET, complete
from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    ProspectusThesisOutput,
)

logger = logging.getLogger(__name__)

THESIS_SYSTEM = """You are a buy-side analyst writing a one-page thesis on a company that has just filed its S-1.

Your inputs are the seven per-category analyses produced earlier in the pipeline, plus the extracted historical financials.

Output ONE JSON object matching this schema — no prose outside the JSON, no markdown fences:

{
  "thesis_statement": "<2-4 sentence thesis>",
  "key_risks": [
    {"risk": "<short label>", "severity": "low|medium|high", "category_source": "<which category surfaced it>"}
  ],
  "ipo_verdict": "participate" | "watch_post_lockup" | "pass",
  "price_range_commentary": "<one paragraph if the S-1 has set a range, else null>",
  "post_ipo_research_plan": [
    {
      "question": "<question to revisit once the company is public>",
      "why_it_matters": "<one sentence>",
      "expected_data_source": "<FMP / transcript / Form 4 / 10-Q / etc.>"
    }
  ]
}

Constraints:
- 3-7 key_risks, sorted by severity (high first).
- 5+ post_ipo_research_plan items. These are the watchlist for re-evaluation post-IPO.
- Verdict rubric:
   participate = thesis works, risks understood, valuation tolerable
   watch_post_lockup = thesis is plausible but you want to see how the float trades and the first earnings print
   pass = something disqualifying — bad governance, broken unit economics, or the deal mechanics are hostile
"""


def _categories_to_prompt_block(categories: CategoriesStepOutput) -> str:
    parts: list[str] = []
    for cat, res in categories.results.items():
        parts.append(
            f"### {cat} (score: {res.score}/100)\n\n"
            f"Key findings:\n" + "\n".join(f"- {kf}" for kf in res.key_findings) + "\n\n"
            f"Analysis:\n{res.content}"
        )
    if categories.failures:
        parts.append("### Category failures (these did not run)")
        for cat, err in categories.failures.items():
            parts.append(f"- {cat}: {err}")
    return "\n\n".join(parts)


async def synthesize_thesis(
    *,
    issuer_name: str,
    categories: CategoriesStepOutput,
    financials_json: dict[str, Any],
) -> ProspectusThesisOutput:
    user = (
        f"Issuer: {issuer_name}\n\n"
        f"## Extracted Financials (JSON)\n\n```json\n{json.dumps(financials_json, indent=2)}\n```\n\n"
        f"## Per-Category Analyses\n\n{_categories_to_prompt_block(categories)}\n\n"
        f"Produce the JSON thesis now."
    )
    raw = await complete(
        system=THESIS_SYSTEM,
        user=user,
        model=SONNET,
        max_tokens=4096,
        assistant_prefill='{"thesis_statement":',
    )
    candidate = raw if raw.lstrip().startswith("{") else '{"thesis_statement":' + raw
    payload = json.loads(candidate)
    return ProspectusThesisOutput.model_validate(payload)
```

- [ ] **Step 4: Rerun tests**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_thesis -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prospectus_thesis.py backend/tests/test_prospectus_thesis.py
git commit -m "$(cat <<'EOF'
feat(prospectus): thesis synthesizer + IPO verdict

Single Sonnet pass over all category outputs produces thesis statement,
ranked key risks, IPO verdict (participate / watch_post_lockup / pass),
optional price-range commentary, and a 5+ item post-IPO research plan.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 7 — Orchestration

### Task 10: ProspectusService

**Files:**
- Create: `backend/app/services/prospectus_service.py`
- Test: `backend/tests/test_prospectus_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prospectus_service.py`:

```python
"""Integration-style test for ProspectusService — mocks every external call."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.app.services.prospectus_service import ProspectusService


def _stub_html() -> str:
    pad = " The following paragraph contains substantive narrative content " * 12
    return (
        "<html><body>"
        f"<p>ITEM 1. BUSINESS</p><p>We design rockets.{pad}</p>"
        f"<p>RISK FACTORS</p><p>Unicorn attacks.{pad}</p>"
        f"<p>MANAGEMENT'S DISCUSSION AND ANALYSIS</p><p>Revenue rose.{pad}</p>"
        f"<p>USE OF PROCEEDS</p><p>General corporate.{pad}</p>"
        f"<p>CAPITALIZATION</p><p>Debt low.{pad}</p>"
        f"<p>DILUTION</p><p>15% dilution.{pad}</p>"
        f"<p>PRINCIPAL STOCKHOLDERS</p><p>Founder 78%.{pad}</p>"
        f"<p>UNDERWRITING</p><p>GS/MS/JPM.{pad}</p>"
        "</body></html>"
    )


def _fake_edgar() -> MagicMock:
    edgar = MagicMock()
    edgar.get_submissions = AsyncMock(return_value=(
        {
            "name": "ACME Rockets Inc",
            "filings": {"recent": {
                "accessionNumber": ["0001628280-26-036936"],
                "form": ["S-1"],
                "primaryDocument": ["acme.htm"],
                "filingDate": ["2026-05-20"],
                "reportDate": [""],
            }},
        },
        MagicMock(),  # citation
    ))
    edgar.fetch_document = AsyncMock(return_value=(_stub_html(), MagicMock()))
    return edgar


class TestProspectusServiceKickoff(unittest.IsolatedAsyncioTestCase):
    async def test_kickoff_returns_report_id(self):
        svc = ProspectusService(edgar=_fake_edgar(), fred=None)

        # Stub the heavy steps so this stays a unit test.
        async def fake_step(self, **kw):
            return None

        with patch.object(ProspectusService, "_run_pipeline",
                          new=AsyncMock(return_value=None)):
            rid = await svc.kick_off(
                url_or_accession=(
                    "https://www.sec.gov/Archives/edgar/data/1181412/"
                    "000162828026036936/acme.htm"
                ),
                theme_id=None,
            )
        self.assertTrue(isinstance(rid, str) and len(rid) >= 32)
```

- [ ] **Step 2: Run to confirm failure**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_service -v
```

Expected: `ImportError`.

- [ ] **Step 3: Implement the orchestrator**

Create `backend/app/services/prospectus_service.py`:

```python
"""ProspectusService — orchestrates the 4-step prospectus pipeline.

Mirrors WorkspaceService:
  - in-memory dict[report_id, asyncio.Queue] for SSE
  - kick_off creates the row + spawns a background task
  - each step runs in its own session with explicit commit
"""
from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any, AsyncIterator
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import unit_of_work
from backend.app.clients.edgar import EdgarClient
from backend.app.models.filing import Filing
from backend.app.models.prospectus_report import ProspectusReport, _slugify_issuer
from backend.app.models.prospectus_schemas import (
    CategoriesStepOutput,
    IngestStepOutput,
    ProspectusThesisOutput,
    RelationshipsStepOutput,
    RelationshipSummary,
)
from backend.app.models.filing import Relationship
from backend.app.services.counterparty_resolver import resolve_ticker_relationships
from backend.app.services.edgar_relationships import extract_ticker_relationships
from backend.app.services.edgar_sections_ingest import get_latest_sections_by_keys
from backend.app.services.prospectus_categories import run_categories
from backend.app.services.prospectus_financials import extract_financials
from backend.app.services.prospectus_ingest import (
    SourceInput,
    ingest_prospectus,
    parse_source_input,
)
from backend.app.services.prospectus_thesis import synthesize_thesis
from backend.app.services.relationship_context import (
    CounterpartyContext,
    get_counterparty_context,
)

logger = logging.getLogger(__name__)

TERMINAL_EVENTS = {"prospectus_complete", "prospectus_failed"}


class ProspectusService:
    def __init__(self, *, edgar: EdgarClient, fred: Any = None) -> None:
        self._edgar = edgar
        self._fred = fred
        self._queues: dict[str, asyncio.Queue] = {}

    # ── SSE plumbing ──────────────────────────────────────────────────────────

    def _q(self, rid: str) -> asyncio.Queue:
        q = self._queues.get(rid)
        if q is None:
            q = asyncio.Queue()
            self._queues[rid] = q
        return q

    def _emit(self, rid: str, evt: dict) -> None:
        try:
            self._q(rid).put_nowait(evt)
        except asyncio.QueueFull:
            logger.warning("prospectus SSE queue full for %s; dropping", rid)

    async def event_stream(self, rid: str) -> AsyncIterator[dict]:
        q = self._q(rid)
        while True:
            evt = await q.get()
            yield evt
            if evt.get("type") in TERMINAL_EVENTS:
                while not q.empty():
                    yield q.get_nowait()
                return

    # ── Kick-off ──────────────────────────────────────────────────────────────

    async def kick_off(self, *, url_or_accession: str, theme_id: str | None) -> str:
        source = parse_source_input(url_or_accession)

        # Resolve issuer first so the row has real values
        cik_trimmed = source.cik_trimmed
        if not cik_trimmed:
            raise ValueError(
                "Bare accession number input not yet supported — please paste the full URL"
            )
        cik_padded = cik_trimmed.zfill(10)
        subs, _ = await self._edgar.get_submissions(cik_padded)
        issuer_name = subs.get("name") or subs.get("entityName") or "(unknown issuer)"

        rid = str(uuid4())
        async with unit_of_work() as db:
            db.add(ProspectusReport(
                id=rid,
                accession_number=source.accession_number,
                issuer_cik=cik_padded,
                issuer_name=issuer_name,
                proposed_ticker=None,
                theme_id=theme_id,
                status="ingesting",
                step_outputs={},
            ))

        asyncio.create_task(self._run_pipeline(rid, source))
        return rid

    # ── Pipeline ─────────────────────────────────────────────────────────────

    async def _run_pipeline(self, rid: str, source: SourceInput) -> None:
        try:
            await self._step_ingest(rid, source)
            await self._step_relationships(rid)
            await self._step_categories(rid)
            await self._step_thesis(rid)
            await self._set_status(rid, "completed")
            self._emit(rid, {"type": "prospectus_complete", "report_id": rid})
        except Exception as e:
            logger.exception("prospectus pipeline failed for %s", rid)
            await self._set_status(rid, "failed", error=f"{e}\n{traceback.format_exc()}")
            self._emit(rid, {"type": "prospectus_failed", "report_id": rid, "error": str(e)})

    async def _load_report(self, db: AsyncSession, rid: str) -> ProspectusReport:
        row = (await db.execute(
            select(ProspectusReport).where(ProspectusReport.id == rid)
        )).scalar_one()
        return row

    async def _set_status(self, rid: str, status: str, *, error: str | None = None) -> None:
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            row.status = status
            if error:
                row.error_message = error
            await db.commit()

    async def _save_step(self, rid: str, step: str, payload: dict) -> None:
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            outputs = dict(row.step_outputs or {})
            outputs[step] = payload
            row.step_outputs = outputs
            await db.commit()

    # ── Steps ────────────────────────────────────────────────────────────────

    async def _step_ingest(self, rid: str, source: SourceInput) -> None:
        self._emit(rid, {"type": "step_start", "step": "ingest"})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            synthetic_ticker = row.synthetic_ticker
            filing, ingest_out = await ingest_prospectus(
                source=source,
                synthetic_ticker=synthetic_ticker,
                issuer_cik=row.issuer_cik,
                db=db,
                edgar=self._edgar,
            )
            # Pull MD&A text for the financials extractor (Selected Financials
            # text lives in s1_mda in the regex defs — there's no separate
            # section_key today; the prompt itself focuses Sonnet on the right
            # parts of the MD&A blob.)
            sections = await get_latest_sections_by_keys(
                synthetic_ticker, ["s1_mda"], db,
            )
            mda_text = (sections.get("s1_mda") or {}).get("text") or ""
            await db.commit()

        financials = await extract_financials(
            mda_text=mda_text, selected_financials_text="",
        )
        ingest_out.financials = financials
        await self._save_step(rid, "ingest", ingest_out.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "ingest"})

    async def _step_relationships(self, rid: str) -> None:
        self._emit(rid, {"type": "step_start", "step": "relationships"})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            synthetic_ticker = row.synthetic_ticker
            extract_summary = await extract_ticker_relationships(
                ticker=synthetic_ticker, db=db, force=False,
            )
            resolve_summary = await resolve_ticker_relationships(
                ticker=synthetic_ticker, db=db, edgar=self._edgar,
            )
            # Pull full Relationship rows directly so we have verbatim_quote;
            # CounterpartyEntry (from get_counterparty_context) doesn't expose it.
            rel_rows = (await db.execute(
                select(Relationship).where(Relationship.ticker == synthetic_ticker)
            )).scalars().all()
            edges = [RelationshipSummary(
                counterparty_name=r.counterparty_name or "",
                relationship_type=r.relationship_type or "other",
                magnitude_pct=r.magnitude_pct,
                resolved_to_ticker=r.resolved_to_ticker,
                verbatim_quote=r.verbatim_quote or "",
            ) for r in rel_rows]
            resolved_count = sum(1 for r in rel_rows if r.resolved_to_ticker)
            await db.commit()

        payload = RelationshipsStepOutput(
            edges_extracted=len(edges),
            edges_resolved=resolved_count,
            edges=edges,
        )
        await self._save_step(rid, "relationships", payload.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "relationships"})

    async def _step_categories(self, rid: str) -> None:
        self._emit(rid, {"type": "step_start", "step": "categories"})
        from backend.app.graph.prospectus_prompts import CATEGORY_SECTION_ROUTING

        all_keys = sorted({k for keys in CATEGORY_SECTION_ROUTING.values() for k in keys})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            synthetic_ticker = row.synthetic_ticker
            sections = await get_latest_sections_by_keys(synthetic_ticker, all_keys, db)
            sections_text = {k: (v.get("text") or "") for k, v in sections.items()}
            ctx = await get_counterparty_context(synthetic_ticker, db)
            issuer_name = row.issuer_name
            filing_date = ""
            outputs = row.step_outputs or {}
            form_type = (outputs.get("ingest") or {}).get("form_type") or "S-1"

        counterparty_blob = self._render_counterparty_blob(ctx)
        macro_blob = await self._fetch_macro_blob()

        out = await run_categories(
            issuer_name=issuer_name,
            filing_date=filing_date,
            form_type=form_type,
            sections_text=sections_text,
            counterparty_context=counterparty_blob,
            macro_indicators=macro_blob,
        )
        await self._save_step(rid, "categories", out.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "categories"})

    async def _step_thesis(self, rid: str) -> None:
        self._emit(rid, {"type": "step_start", "step": "thesis"})
        async with unit_of_work() as db:
            row = await self._load_report(db, rid)
            outputs = row.step_outputs or {}
            issuer_name = row.issuer_name
        categories_payload = outputs.get("categories") or {}
        financials_payload = (outputs.get("ingest") or {}).get("financials") or {}

        thesis = await synthesize_thesis(
            issuer_name=issuer_name,
            categories=CategoriesStepOutput.model_validate(categories_payload),
            financials_json=financials_payload,
        )
        await self._save_step(rid, "thesis", thesis.model_dump(mode="json"))
        self._emit(rid, {"type": "step_complete", "step": "thesis"})

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _render_counterparty_blob(self, ctx: CounterpartyContext) -> str:
        # ctx.outbound is dict[relationship_type, list[CounterpartyEntry]].
        # We render a flat at-a-glance list grouped by type for prospectus
        # categories — full per-type template in relationship_context.py is
        # used by the equity pipeline only.
        if not ctx.has_data:
            return ""
        lines: list[str] = []
        for rel_type, entries in ctx.outbound.items():
            for e in entries:
                name = e.name or "(unnamed)"
                mag = f" ({e.magnitude_pct}%)" if e.magnitude_pct else ""
                ticker = f" [${e.resolved_ticker}]" if e.resolved_ticker else ""
                lines.append(f"- {name}{ticker} — {rel_type}{mag}")
        return "\n".join(lines)

    async def _fetch_macro_blob(self) -> str:
        if self._fred is None or not getattr(self._fred, "available", lambda: False)():
            return ""
        try:
            data, _ = await self._fred.get_all_macro()
        except Exception as e:
            logger.warning("FRED fetch failed for prospectus: %s", e)
            return ""
        # Compact one-line-per-series summary: latest observation only.
        lines: list[str] = []
        for series, points in (data or {}).items():
            if not points:
                continue
            latest = points[-1]
            val = latest.get("value")
            dt = latest.get("date")
            if val is not None and dt:
                lines.append(f"- {series}: {val} ({dt})")
        return "\n".join(lines)
```

- [ ] **Step 4: Run the orchestrator unit test**

```bash
source backend/venv/bin/activate && python -m unittest backend.tests.test_prospectus_service -v
```

Expected: PASS (test only exercises `kick_off`; `_run_pipeline` is patched out).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/prospectus_service.py backend/tests/test_prospectus_service.py
git commit -m "$(cat <<'EOF'
feat(prospectus): ProspectusService orchestrator

Four sequential steps (ingest → relationships → categories → thesis)
spawned as a background task per report. SSE event types: step_start,
step_complete, prospectus_complete, prospectus_failed. Each step runs in
its own unit_of_work session with an explicit commit.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: API router

**Files:**
- Create: `backend/app/api/prospectus.py`

- [ ] **Step 1: Implement the router**

Create `backend/app/api/prospectus.py`:

```python
"""HTTP surface for prospectus reports."""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.db import get_db
from backend.app.models.prospectus_report import ProspectusReport
from backend.app.services.prospectus_service import ProspectusService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/prospectus", tags=["prospectus"])


class CreateReportRequest(BaseModel):
    url_or_accession: str
    theme_id: str | None = None


def get_prospectus_service(request: Request) -> ProspectusService:
    svc = getattr(request.app.state, "prospectus", None)
    if svc is None:
        raise HTTPException(status_code=500, detail="prospectus service not initialized")
    return svc


@router.post("", status_code=202)
async def create_report(
    body: CreateReportRequest,
    svc: ProspectusService = Depends(get_prospectus_service),
):
    try:
        rid = await svc.kick_off(
            url_or_accession=body.url_or_accession, theme_id=body.theme_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"report_id": rid}


@router.get("/{report_id}")
async def get_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        select(ProspectusReport).where(ProspectusReport.id == str(report_id))
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="prospectus report not found")
    return _serialize(row)


@router.get("/{report_id}/stream")
async def stream_report(
    report_id: UUID, svc: ProspectusService = Depends(get_prospectus_service)
):
    async def gen():
        try:
            async for evt in svc.event_stream(str(report_id)):
                yield f"data: {json.dumps(evt)}\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("")
async def list_reports(db: AsyncSession = Depends(get_db), limit: int = 50):
    rows = (await db.execute(
        select(ProspectusReport)
        .order_by(ProspectusReport.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return [_serialize(r) for r in rows]


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: UUID, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        delete(ProspectusReport).where(ProspectusReport.id == str(report_id))
    )
    if res.rowcount == 0:
        raise HTTPException(status_code=404, detail="prospectus report not found")
    await db.commit()
    return None


def _serialize(r: ProspectusReport) -> dict:
    return {
        "id": str(r.id),
        "accession_number": r.accession_number,
        "issuer_cik": r.issuer_cik,
        "issuer_name": r.issuer_name,
        "proposed_ticker": r.proposed_ticker,
        "synthetic_ticker": r.synthetic_ticker,
        "theme_id": str(r.theme_id) if r.theme_id else None,
        "status": r.status,
        "step_outputs": r.step_outputs,
        "error_message": r.error_message,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }
```

- [ ] **Step 2: Confirm the router imports cleanly**

```bash
source backend/venv/bin/activate && python -c "from backend.app.api.prospectus import router; print(router.routes)" | head -10
```

Expected: prints a non-empty route list (POST, GET, etc.).

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/prospectus.py
git commit -m "$(cat <<'EOF'
feat(prospectus): HTTP surface — POST/GET/stream/list/delete

Standard CRUD plus SSE under /api/prospectus. POST returns 202 with
report_id and kicks off the background pipeline via ProspectusService.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 12: Wire ProspectusService into main.py

**Files:**
- Modify: `backend/app/main.py` (lifespan + router registration)

- [ ] **Step 1: Read the current main.py wiring**

```bash
sed -n '40,80p' /Users/ericwyluda/Development/projects/sector-research/backend/app/main.py
```

Note the exact lines where `app.state.workspace = WorkspaceService(...)` is assigned and where routers are included.

- [ ] **Step 2: Add the import**

Edit `backend/app/main.py`. Near the other service imports (top of file, currently importing `WorkspaceService`, `FanoutService`, etc.) add:

```python
from backend.app.services.prospectus_service import ProspectusService
from backend.app.api import prospectus as prospectus_api
```

- [ ] **Step 3: Construct ProspectusService inside lifespan**

In the `lifespan` function, after the existing `app.state.workspace = WorkspaceService(...)` block (around line 69-71), add:

```python
    app.state.prospectus = ProspectusService(
        edgar=app.state.edgar, fred=app.state.fred,
    )
```

- [ ] **Step 4: Register the router**

After the existing `app.include_router(transcripts_delta_api.router)` line (around line 174), add:

```python
app.include_router(prospectus_api.router)
```

- [ ] **Step 5: Smoke-test the import + server boot**

```bash
source backend/venv/bin/activate && python -c "from backend.app.main import app; print([r.path for r in app.routes if hasattr(r, 'path') and '/prospectus' in r.path])"
```

Expected: list shows the four prospectus routes (POST `/api/prospectus`, GET `/api/prospectus/{report_id}`, GET stream, GET list, DELETE).

- [ ] **Step 6: Boot the dev server in background and hit list endpoint**

```bash
source backend/venv/bin/activate && (uvicorn backend.app.main:app --port 8000 > /tmp/prospectus_boot.log 2>&1 &) && sleep 3 && curl -s http://127.0.0.1:8000/api/prospectus | head -c 200 && echo && pkill -f 'uvicorn backend.app.main' || true
```

Expected: `[]` (empty list) and the server boot log shows no tracebacks. If the boot log shows an error, fix before committing.

- [ ] **Step 7: Commit**

```bash
git add backend/app/main.py
git commit -m "$(cat <<'EOF'
feat(prospectus): wire ProspectusService + router into main app

ProspectusService constructed once in lifespan with shared EdgarClient
and FREDClient. Router included after the existing transcripts_delta_api
registration.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 8 — Frontend

### Task 13: Add prospectusApi to lib/api.ts

**Files:**
- Modify: `frontend/lib/api.ts` (append a new section)

- [ ] **Step 1: Append the types + client**

Open `frontend/lib/api.ts`. After the `transcriptDeltaApi` block (around line 1787), append:

```ts
// ============================================================================
// Prospectus reports
// ============================================================================

export type IPOVerdict = "participate" | "watch_post_lockup" | "pass";
export type ProspectusStatus = "ingesting" | "analyzing" | "completed" | "failed";

export interface ExtractedSectionSummary {
  section_key: string;
  heading: string;
  char_count: number;
}

export interface AnnualFinancialRow {
  period_label: string;
  revenue: number | null;
  cost_of_revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  cash_and_equivalents: number | null;
  total_debt: number | null;
  source_snippet: string;
}

export interface InterimFinancialRow {
  period_label: string;
  revenue: number | null;
  operating_income: number | null;
  net_income: number | null;
  source_snippet: string;
}

export interface ProspectusFinancials {
  annual: AnnualFinancialRow[];
  interim: InterimFinancialRow[];
}

export interface IngestStepOutput {
  accession_number: string;
  primary_document_url: string;
  issuer_cik: string;
  issuer_name: string;
  proposed_ticker: string | null;
  form_type: string;
  sections: ExtractedSectionSummary[];
  financials: ProspectusFinancials;
}

export interface RelationshipSummary {
  counterparty_name: string;
  relationship_type: string;
  magnitude_pct: number | null;
  resolved_to_ticker: string | null;
  verbatim_quote: string;
}

export interface RelationshipsStepOutput {
  edges_extracted: number;
  edges_resolved: number;
  edges: RelationshipSummary[];
}

export interface ProspectusCategoryResult {
  category: string;
  content: string;
  score: number;
  key_findings: string[];
}

export interface CategoriesStepOutput {
  results: Record<string, ProspectusCategoryResult>;
  failures: Record<string, string>;
}

export interface KeyRisk {
  risk: string;
  severity: "low" | "medium" | "high";
  category_source: string;
}

export interface PostIPOPlanItem {
  question: string;
  why_it_matters: string;
  expected_data_source: string;
}

export interface ProspectusThesisOutput {
  thesis_statement: string;
  key_risks: KeyRisk[];
  ipo_verdict: IPOVerdict;
  price_range_commentary: string | null;
  post_ipo_research_plan: PostIPOPlanItem[];
}

export interface ProspectusReport {
  id: string;
  accession_number: string;
  issuer_cik: string;
  issuer_name: string;
  proposed_ticker: string | null;
  synthetic_ticker: string;
  theme_id: string | null;
  status: ProspectusStatus;
  step_outputs: {
    ingest?: IngestStepOutput;
    relationships?: RelationshipsStepOutput;
    categories?: CategoriesStepOutput;
    thesis?: ProspectusThesisOutput;
  };
  error_message: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export const prospectusApi = {
  create: async (
    body: { url_or_accession: string; theme_id?: string | null },
  ): Promise<{ report_id: string }> => {
    const r = await fetch(`${BASE}/api/prospectus`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) throw new Error(`prospectus create failed: ${r.status} ${await r.text()}`);
    return r.json();
  },
  get: async (reportId: string): Promise<ProspectusReport> => {
    const r = await fetch(`${BASE}/api/prospectus/${reportId}`);
    if (!r.ok) throw new Error(`prospectus get failed: ${r.status}`);
    return r.json();
  },
  list: async (limit = 50): Promise<ProspectusReport[]> => {
    const r = await fetch(`${BASE}/api/prospectus?limit=${limit}`);
    if (!r.ok) throw new Error(`prospectus list failed: ${r.status}`);
    return r.json();
  },
  remove: async (reportId: string): Promise<void> => {
    const r = await fetch(`${BASE}/api/prospectus/${reportId}`, { method: "DELETE" });
    if (!r.ok && r.status !== 204) throw new Error(`prospectus delete failed: ${r.status}`);
  },
  streamUrl: (reportId: string) => `${BASE}/api/prospectus/${reportId}/stream`,
};
```

- [ ] **Step 2: Type-check the frontend**

```bash
cd frontend && npm run lint 2>&1 | tail -20
```

Expected: no errors related to the new code. (Pre-existing warnings in other files are OK.)

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api.ts
git commit -m "$(cat <<'EOF'
feat(prospectus): TS client + types in lib/api.ts

prospectusApi (create/get/list/remove/streamUrl) plus the full set of
step-output types mirroring backend Pydantic schemas.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 14: Nav entry

**Files:**
- Modify: `frontend/components/Nav.tsx`

- [ ] **Step 1: Add the link**

Edit `frontend/components/Nav.tsx`. Insert the new entry between `Status` and `Workspace`:

```tsx
  { href: "/status",        label: "Status"   },
  { href: "/prospectus",    label: "Prospectus" },
  { href: "/workspace",     label: "Workspace" },
```

- [ ] **Step 2: Verify lint passes**

```bash
cd frontend && npm run lint 2>&1 | tail -10
```

Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/Nav.tsx
git commit -m "$(cat <<'EOF'
feat(prospectus): add /prospectus to top nav

Inserted between Status and Workspace.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: /prospectus list page

**Files:**
- Create: `frontend/app/prospectus/page.tsx`
- Create: `frontend/components/prospectus/ProspectusList.tsx`
- Create: `frontend/components/prospectus/VerdictPill.tsx`

- [ ] **Step 1: Create the verdict pill**

Create `frontend/components/prospectus/VerdictPill.tsx`:

```tsx
import type { IPOVerdict } from "@/lib/api";

const STYLES: Record<IPOVerdict, string> = {
  participate: "bg-emerald-950 text-emerald-300 border-emerald-800",
  watch_post_lockup: "bg-amber-950 text-amber-300 border-amber-800",
  pass: "bg-red-950 text-red-300 border-red-800",
};

const LABELS: Record<IPOVerdict, string> = {
  participate: "Participate",
  watch_post_lockup: "Watch post-lockup",
  pass: "Pass",
};

export function VerdictPill({ verdict }: { verdict: IPOVerdict | null | undefined }) {
  if (!verdict) {
    return (
      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-[var(--surface)] text-[var(--text-muted)] border border-[var(--border)]">
        Pending
      </span>
    );
  }
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full border ${STYLES[verdict]}`}>
      {LABELS[verdict]}
    </span>
  );
}
```

- [ ] **Step 2: Create the list component**

Create `frontend/components/prospectus/ProspectusList.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { prospectusApi, type ProspectusReport } from "@/lib/api";
import { VerdictPill } from "./VerdictPill";

const STATUS_LABEL: Record<string, string> = {
  ingesting: "Ingesting",
  analyzing: "Analyzing",
  completed: "Completed",
  failed: "Failed",
};

export function ProspectusList() {
  const [rows, setRows] = useState<ProspectusReport[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    prospectusApi
      .list()
      .then((list) => { if (alive) setRows(list); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : String(e)); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  if (loading) return <div className="text-[var(--text-muted)] text-sm">Loading…</div>;
  if (error) {
    return (
      <div className="p-4 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
        {error}
      </div>
    );
  }
  if (rows.length === 0) {
    return (
      <div className="text-[var(--text-muted)] text-sm">
        No prospectus reports yet. Create one from the Filings page.
      </div>
    );
  }

  return (
    <table className="w-full text-sm">
      <thead className="text-[var(--text-muted)] text-xs uppercase tracking-wider">
        <tr>
          <th className="text-left py-2 px-2">Issuer</th>
          <th className="text-left py-2 px-2">Form</th>
          <th className="text-left py-2 px-2">Status</th>
          <th className="text-left py-2 px-2">Verdict</th>
          <th className="text-left py-2 px-2">Created</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => {
          const verdict = r.step_outputs?.thesis?.ipo_verdict ?? null;
          const formType = r.step_outputs?.ingest?.form_type ?? "S-1";
          return (
            <tr key={r.id} className="border-t border-[var(--border)] hover:bg-[var(--surface)]">
              <td className="py-2 px-2">
                <Link href={`/prospectus/${r.id}`} className="text-blue-400 hover:underline">
                  {r.issuer_name}
                </Link>
              </td>
              <td className="py-2 px-2 text-[var(--text-muted)]">{formType}</td>
              <td className="py-2 px-2 text-[var(--text-muted)]">{STATUS_LABEL[r.status] ?? r.status}</td>
              <td className="py-2 px-2"><VerdictPill verdict={verdict} /></td>
              <td className="py-2 px-2 text-[var(--text-muted)]">
                {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 3: Create the page**

Create `frontend/app/prospectus/page.tsx`:

```tsx
import { ProspectusList } from "@/components/prospectus/ProspectusList";

export const dynamic = "force-dynamic";

export default function ProspectusIndexPage() {
  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <div className="mx-auto max-w-5xl p-6 space-y-6">
        <div>
          <h1 className="text-3xl font-semibold text-[var(--text)]">Prospectus Reports</h1>
          <p className="text-[var(--text-muted)] text-sm mt-2">
            Analytical reports synthesised from S-1 / S-1/A registrations.
          </p>
        </div>
        <ProspectusList />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Smoke-test the build**

```bash
cd frontend && npm run lint 2>&1 | tail -10 && npm run build 2>&1 | tail -20
```

Expected: build succeeds, no new lint warnings.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/prospectus/page.tsx frontend/components/prospectus/ProspectusList.tsx frontend/components/prospectus/VerdictPill.tsx
git commit -m "$(cat <<'EOF'
feat(prospectus): /prospectus list page + VerdictPill

Client-rendered table over prospectusApi.list with verdict pill from
the thesis step output. Empty state directs the user to /filings for
creating a new report.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 16: /prospectus/[reportId] page + SSE hydrator

**Files:**
- Create: `frontend/app/prospectus/[reportId]/page.tsx`
- Create: `frontend/components/prospectus/ProspectusReport.tsx`

- [ ] **Step 1: Create the page**

Create `frontend/app/prospectus/[reportId]/page.tsx`:

```tsx
import { ProspectusReportView } from "@/components/prospectus/ProspectusReport";

export default async function ProspectusReportPage(
  { params }: { params: Promise<{ reportId: string }> },
) {
  const { reportId } = await params;
  return <ProspectusReportView reportId={reportId} />;
}
```

Note: Next 16 App Router unwraps dynamic params via Promise — match the existing pattern. If unsure, check `frontend/app/workspace/[runId]/page.tsx` for the established shape.

- [ ] **Step 2: Create the hydrator component**

Create `frontend/components/prospectus/ProspectusReport.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { prospectusApi, type ProspectusReport } from "@/lib/api";
import { IngestSummaryCard } from "./StepCards/IngestSummaryCard";
import { RelationshipsCard } from "./StepCards/RelationshipsCard";
import { CategoryCard } from "./StepCards/CategoryCard";
import { ThesisCard } from "./StepCards/ThesisCard";

export function ProspectusReportView({ reportId }: { reportId: string }) {
  const [report, setReport] = useState<ProspectusReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    prospectusApi
      .get(reportId)
      .then((r) => { if (alive) setReport(r); })
      .catch((e) => { if (alive) setError(e instanceof Error ? e.message : String(e)); });

    const es = new EventSource(prospectusApi.streamUrl(reportId));
    es.onmessage = async (evt) => {
      try {
        const parsed = JSON.parse(evt.data);
        if (parsed.type === "step_complete" || parsed.type === "prospectus_complete") {
          const fresh = await prospectusApi.get(reportId);
          if (alive) setReport(fresh);
        }
        if (parsed.type === "prospectus_complete" || parsed.type === "prospectus_failed") {
          es.close();
        }
      } catch {
        // ignore malformed events
      }
    };
    es.onerror = () => es.close();
    return () => { alive = false; es.close(); };
  }, [reportId]);

  if (error) {
    return (
      <div className="mx-auto max-w-4xl p-6">
        <div className="p-4 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
          {error}
        </div>
      </div>
    );
  }
  if (!report) {
    return <div className="mx-auto max-w-4xl p-6 text-[var(--text-muted)]">Loading…</div>;
  }

  const { step_outputs: s, issuer_name, accession_number, status } = report;
  const categoryNames = s.categories ? Object.keys(s.categories.results) : [];

  const promoteHref = report.proposed_ticker
    ? `/pipeline/new?ticker=${encodeURIComponent(report.proposed_ticker)}${report.theme_id ? `&theme_id=${encodeURIComponent(report.theme_id)}` : ""}`
    : null;

  return (
    <div className="min-h-screen bg-[var(--bg)]">
      <div className="mx-auto max-w-5xl p-6 space-y-6">
        <header className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-semibold text-[var(--text)]">{issuer_name}</h1>
            <p className="text-[var(--text-muted)] text-sm mt-1">
              {accession_number} · status: {status}
            </p>
          </div>
          {promoteHref && status === "completed" && (
            <a
              href={promoteHref}
              className="text-sm px-3 py-1.5 rounded-md border border-[var(--border)] hover:bg-[var(--surface)] whitespace-nowrap"
            >
              Promote to research run →
            </a>
          )}
        </header>

        {s.thesis && <ThesisCard thesis={s.thesis} />}
        {s.ingest && <IngestSummaryCard ingest={s.ingest} />}
        {s.relationships && <RelationshipsCard rel={s.relationships} />}

        {categoryNames.length > 0 && (
          <section className="space-y-4">
            <h2 className="text-xl font-semibold">Category analyses</h2>
            {categoryNames.map((name) => (
              <CategoryCard key={name} result={s.categories!.results[name]} />
            ))}
            {s.categories && Object.keys(s.categories.failures).length > 0 && (
              <div className="p-3 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
                <div className="font-medium mb-1">Category failures</div>
                <ul className="list-disc pl-5 space-y-0.5">
                  {Object.entries(s.categories.failures).map(([cat, err]) => (
                    <li key={cat}><span className="font-medium">{cat}:</span> {err}</li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit (stub StepCards added in next task — build will fail until then; that's OK, we're staging)**

```bash
git add frontend/app/prospectus/[reportId]/page.tsx frontend/components/prospectus/ProspectusReport.tsx
git commit -m "$(cat <<'EOF'
feat(prospectus): report detail page + dual-hydrating REST+SSE consumer

Mirrors WorkspaceReport — initial REST fetch on mount + EventSource over
streamUrl. On each step_complete event, refetches the row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 17: StepCards

**Files:**
- Create: `frontend/components/prospectus/StepCards/IngestSummaryCard.tsx`
- Create: `frontend/components/prospectus/StepCards/RelationshipsCard.tsx`
- Create: `frontend/components/prospectus/StepCards/CategoryCard.tsx`
- Create: `frontend/components/prospectus/StepCards/ThesisCard.tsx`

- [ ] **Step 1: IngestSummaryCard**

Create `frontend/components/prospectus/StepCards/IngestSummaryCard.tsx`:

```tsx
import type { IngestStepOutput } from "@/lib/api";

function fmtMoney(n: number | null): string {
  if (n === null || n === undefined) return "—";
  if (Math.abs(n) >= 1e9) return `$${(n / 1e9).toFixed(2)}B`;
  if (Math.abs(n) >= 1e6) return `$${(n / 1e6).toFixed(2)}M`;
  return `$${n.toLocaleString()}`;
}

export function IngestSummaryCard({ ingest }: { ingest: IngestStepOutput }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <h2 className="text-xl font-semibold mb-3">S-1 ingest</h2>
      <p className="text-sm text-[var(--text-muted)] mb-3">
        Form {ingest.form_type} · CIK {ingest.issuer_cik}
        {ingest.proposed_ticker && <> · proposed ticker {ingest.proposed_ticker}</>}
      </p>
      <a href={ingest.primary_document_url} target="_blank" rel="noopener noreferrer"
         className="text-blue-400 hover:underline text-sm">
        Open primary document ↗
      </a>

      <h3 className="text-sm font-semibold mt-4 mb-1">Extracted sections</h3>
      <ul className="text-sm space-y-0.5">
        {ingest.sections.map((s) => (
          <li key={s.section_key} className="flex justify-between border-b border-[var(--border)] py-1">
            <span className="text-[var(--text)]">{s.heading}</span>
            <span className="text-[var(--text-muted)]">{s.char_count.toLocaleString()} chars</span>
          </li>
        ))}
      </ul>

      {ingest.financials.annual.length > 0 && (
        <>
          <h3 className="text-sm font-semibold mt-4 mb-1">Annual financials</h3>
          <table className="w-full text-sm">
            <thead className="text-xs uppercase text-[var(--text-muted)]">
              <tr>
                <th className="text-left py-1">Period</th>
                <th className="text-right py-1">Revenue</th>
                <th className="text-right py-1">Op Income</th>
                <th className="text-right py-1">Net Income</th>
              </tr>
            </thead>
            <tbody>
              {ingest.financials.annual.map((r) => (
                <tr key={r.period_label} className="border-t border-[var(--border)]">
                  <td className="py-1">{r.period_label}</td>
                  <td className="py-1 text-right">{fmtMoney(r.revenue)}</td>
                  <td className="py-1 text-right">{fmtMoney(r.operating_income)}</td>
                  <td className="py-1 text-right">{fmtMoney(r.net_income)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
```

- [ ] **Step 2: RelationshipsCard**

Create `frontend/components/prospectus/StepCards/RelationshipsCard.tsx`:

```tsx
import type { RelationshipsStepOutput } from "@/lib/api";

export function RelationshipsCard({ rel }: { rel: RelationshipsStepOutput }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <h2 className="text-xl font-semibold mb-1">Counterparty relationships</h2>
      <p className="text-sm text-[var(--text-muted)] mb-3">
        {rel.edges_extracted} extracted · {rel.edges_resolved} resolved to known tickers
      </p>
      {rel.edges.length === 0 ? (
        <p className="text-sm text-[var(--text-muted)]">No counterparty edges extracted.</p>
      ) : (
        <ul className="space-y-2">
          {rel.edges.map((e, i) => (
            <li key={i} className="text-sm border-b border-[var(--border)] pb-2">
              <div>
                <span className="font-medium">{e.counterparty_name || "(unnamed)"}</span>
                <span className="text-[var(--text-muted)]"> — {e.relationship_type}</span>
                {e.resolved_to_ticker && (
                  <span className="text-blue-400 ml-2">${e.resolved_to_ticker}</span>
                )}
                {e.magnitude_pct !== null && (
                  <span className="text-[var(--text-muted)] ml-2">{e.magnitude_pct}%</span>
                )}
              </div>
              {e.verbatim_quote && (
                <blockquote className="italic text-[var(--text-muted)] mt-1 text-xs">
                  &ldquo;{e.verbatim_quote}&rdquo;
                </blockquote>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
```

- [ ] **Step 3: CategoryCard**

Create `frontend/components/prospectus/StepCards/CategoryCard.tsx`:

```tsx
import type { ProspectusCategoryResult } from "@/lib/api";

function scoreColor(score: number): string {
  if (score >= 76) return "bg-emerald-950 text-emerald-300 border-emerald-800";
  if (score >= 56) return "bg-blue-950 text-blue-300 border-blue-800";
  if (score >= 31) return "bg-amber-950 text-amber-300 border-amber-800";
  return "bg-red-950 text-red-300 border-red-800";
}

export function CategoryCard({ result }: { result: ProspectusCategoryResult }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <header className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold">{result.category}</h3>
        <span className={`text-xs px-2 py-0.5 rounded-full border ${scoreColor(result.score)}`}>
          {result.score}/100
        </span>
      </header>
      {result.key_findings.length > 0 && (
        <ul className="mb-3 list-disc pl-5 text-sm space-y-0.5">
          {result.key_findings.map((kf, i) => <li key={i}>{kf}</li>)}
        </ul>
      )}
      <div className="prose prose-invert prose-sm max-w-none whitespace-pre-wrap text-[var(--text)]">
        {result.content}
      </div>
    </section>
  );
}
```

- [ ] **Step 4: ThesisCard**

Create `frontend/components/prospectus/StepCards/ThesisCard.tsx`:

```tsx
import type { ProspectusThesisOutput } from "@/lib/api";
import { VerdictPill } from "../VerdictPill";

const SEVERITY_COLOR: Record<string, string> = {
  high: "text-red-400",
  medium: "text-amber-400",
  low: "text-blue-400",
};

export function ThesisCard({ thesis }: { thesis: ProspectusThesisOutput }) {
  return (
    <section className="border border-[var(--border)] rounded-lg p-5 bg-[var(--surface)]">
      <header className="flex items-center justify-between mb-3">
        <h2 className="text-xl font-semibold">Thesis</h2>
        <VerdictPill verdict={thesis.ipo_verdict} />
      </header>
      <p className="text-[var(--text)] mb-4">{thesis.thesis_statement}</p>

      {thesis.price_range_commentary && (
        <div className="mb-4">
          <h3 className="text-sm font-semibold mb-1">Price range commentary</h3>
          <p className="text-sm text-[var(--text-muted)]">{thesis.price_range_commentary}</p>
        </div>
      )}

      {thesis.key_risks.length > 0 && (
        <div className="mb-4">
          <h3 className="text-sm font-semibold mb-1">Key risks</h3>
          <ul className="text-sm space-y-0.5">
            {thesis.key_risks.map((r, i) => (
              <li key={i}>
                <span className={`uppercase text-xs mr-2 ${SEVERITY_COLOR[r.severity] ?? ""}`}>
                  {r.severity}
                </span>
                <span>{r.risk}</span>
                <span className="text-[var(--text-muted)] text-xs ml-1">({r.category_source})</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {thesis.post_ipo_research_plan.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold mb-1">Post-IPO research plan</h3>
          <ul className="text-sm space-y-2">
            {thesis.post_ipo_research_plan.map((p, i) => (
              <li key={i} className="border-l-2 border-[var(--border)] pl-3">
                <div className="font-medium">{p.question}</div>
                <div className="text-[var(--text-muted)] text-xs">
                  {p.why_it_matters} · expects: {p.expected_data_source}
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Lint + build**

```bash
cd frontend && npm run lint 2>&1 | tail -10 && npm run build 2>&1 | tail -20
```

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/prospectus/StepCards/
git commit -m "$(cat <<'EOF'
feat(prospectus): step cards (Ingest, Relationships, Category, Thesis)

Four presentational cards consumed by ProspectusReportView. Score colour
tiers mirror the equity deep-dive palette (40/55/70/76 thresholds);
severity colours on key risks distinguish high/medium/low.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 18: Filings page entry-point modal

**Files:**
- Modify: `frontend/app/filings/page.tsx`
- Create: `frontend/components/prospectus/NewProspectusButton.tsx`

- [ ] **Step 1: Create the button + modal**

Create `frontend/components/prospectus/NewProspectusButton.tsx`:

```tsx
"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { prospectusApi } from "@/lib/api";

export function NewProspectusButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const { report_id } = await prospectusApi.create({
        url_or_accession: value.trim(),
        theme_id: null,
      });
      router.push(`/prospectus/${report_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-sm px-3 py-1.5 rounded-md border border-[var(--border)] hover:bg-[var(--surface)]"
      >
        + New prospectus report
      </button>

      {open && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setOpen(false)}>
          <div className="bg-[var(--surface)] border border-[var(--border)] rounded-lg p-5 max-w-lg w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-2">New prospectus report</h2>
            <p className="text-sm text-[var(--text-muted)] mb-3">
              Paste the SEC URL or accession number of an S-1 / S-1/A filing.
            </p>
            <input
              type="text"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="https://www.sec.gov/Archives/edgar/data/…/…/….htm"
              className="w-full bg-[var(--bg)] border border-[var(--border)] rounded-md px-3 py-2 text-sm mb-3"
              autoFocus
            />
            {error && (
              <div className="mb-3 p-2 bg-red-950 border border-red-800 rounded-md text-red-300 text-sm">
                {error}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button type="button" onClick={() => setOpen(false)} className="text-sm px-3 py-1.5 rounded-md hover:bg-[var(--bg)]">
                Cancel
              </button>
              <button
                type="button"
                onClick={submit}
                disabled={busy || !value.trim()}
                className="text-sm px-3 py-1.5 rounded-md bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50"
              >
                {busy ? "Starting…" : "Start report"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
```

- [ ] **Step 2: Wire the button into the filings page**

Read the top of `frontend/app/filings/page.tsx` to find where the page header sits, then add the button to the header bar. Open the file:

```bash
head -40 frontend/app/filings/page.tsx
```

Edit the page to import `NewProspectusButton` from `@/components/prospectus/NewProspectusButton` and render it inside the existing top-of-page heading group. The exact diff depends on what's there today — keep the change surgical (one new import, one new JSX node next to the existing title). If you can't find a sensible insertion point, add a `<div className="flex items-center justify-between">` wrapper around the existing `<h1>` and place the button on the right.

- [ ] **Step 3: Lint + build**

```bash
cd frontend && npm run lint 2>&1 | tail -10 && npm run build 2>&1 | tail -20
```

Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/filings/page.tsx frontend/components/prospectus/NewProspectusButton.tsx
git commit -m "$(cat <<'EOF'
feat(prospectus): + New prospectus report button on /filings

Client-side modal that POSTs to prospectusApi.create and routes to the
report detail page once the backend returns a report id.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Phase 9 — Integration smoke

### Task 19: End-to-end smoke against the SpaceX S-1

**Files:** none created (manual smoke test)

This is a manual smoke test that exercises the entire pipeline against the real S-1. Run with care — this will hit Anthropic, FRED, and SEC EDGAR.

- [ ] **Step 1: Start backend + frontend**

In one terminal:

```bash
source backend/venv/bin/activate && uvicorn backend.app.main:app --reload
```

In another:

```bash
cd frontend && npm run dev
```

- [ ] **Step 2: Open /prospectus in a browser, click "New prospectus report" on /filings**

Paste:

```
https://www.sec.gov/Archives/edgar/data/1181412/000162828026036936/spaceexplorationtechnologi.htm
```

Submit. Expected: redirect to `/prospectus/<id>`; page progressively populates as steps complete (ingest → relationships → categories → thesis).

- [ ] **Step 3: Verify success criteria from the spec**

Check that:
- The `ingest` card shows ≥6 of the 8 S-1 sections extracted, and ≥2 annual financial rows.
- The `relationships` card shows ≥20 edges.
- All 7 category cards render with non-empty content and 0–100 scores.
- The thesis card shows a non-null verdict and ≥5 post-IPO plan items.

If any of these fail, note which step and capture the relevant section of `backend.app.services.prospectus_*` to debug — most likely culprits in order: (a) S-1 regex defs needing tightening for SpaceX's specific heading style, (b) Sonnet returning unexpected JSON shape (check `assistant_prefill` interplay), (c) `_render_counterparty_blob` returning empty when it should not.

- [ ] **Step 4: Verify public-company pipeline is unaffected**

Navigate to `/` (themes), open any existing theme, kick off a research run on a public ticker. Expected: quick_screen + deep_dive run as before, no regressions.

Run the full backend test suite:

```bash
source backend/venv/bin/activate && python -m unittest discover -s backend/tests -p 'test_*.py' 2>&1 | tail -5
```

Expected: same pass count as before this branch, plus the new prospectus tests.

- [ ] **Step 5: Document smoke results in the spec**

Edit `docs/superpowers/specs/2026-05-20-prospectus-pipeline-design.md` and append a `## Implementation notes` section at the end with anything you discovered during the smoke that future-you should know (e.g. "the SpaceX S-1 has its Risk Factors heading rendered as `R i s k   F a c t o r s` — the existing tolerant pattern handles it" or "had to bump SECTION_BUDGET_CHARS from 8000 to 12000 for Business Quality").

- [ ] **Step 6: Final commit**

```bash
git add docs/superpowers/specs/2026-05-20-prospectus-pipeline-design.md
git commit -m "$(cat <<'EOF'
docs(prospectus): implementation notes from SpaceX smoke

Append findings from end-to-end smoke test against the SpaceX S-1.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Done

After Task 19 the feature is complete and live in the local environment. Next steps (out of v1, captured in the spec for future work): post-IPO promotion button, S-1/A amendment diffing, theme attachment surfaced on the list page.
