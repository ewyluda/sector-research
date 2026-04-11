# Sector Research App — Plan 3: LangGraph Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 6-phase due diligence pipeline as a LangGraph state graph with human-in-the-loop interrupts, PostgreSQL checkpointing for pause/resume, and a FastAPI router that starts runs and handles human approval steps.

**Architecture:** One `StateGraph(ResearchState)` compiled with a `PostgresSaver` checkpointer. Each phase is a node function that fetches data via `FMPClient`, calls Claude Sonnet with the appropriate skill-tree prompt, accumulates citations into state, then calls `interrupt()` at validation gates. The pipeline router exposes three endpoints: start a run, submit a human decision, and stream phase output via SSE. The Phase 5 risk stress-test conditionally loops back to Phase 3 deep-dive when risk/reward < 2:1 — no interrupt on the loop, just a state flag the frontend reads.

**Tech Stack:** LangGraph 0.2+, `psycopg` (v3) for `PostgresSaver`, Anthropic SDK (Claude Sonnet for analysis, Claude Haiku for quick-screen scoring), FastAPI SSE via `sse-starlette`, pytest with mocked LangGraph

**Prereq:** Plans 1 and 2 complete. Add `psycopg[binary]` and `sse-starlette` to Poetry before starting.

**Skill files:** Copy `02_Areas/skills/due-diligence/` from the Obsidian vault into `backend/skills/due-diligence/` so the backend can read them at runtime. These are the system prompts for each phase.

**Spec:** `docs/superpowers/specs/2026-04-10-sector-research-app-design.md` — Section 3

---

## File Map

```
backend/
├── skills/
│   └── due-diligence/            ← COPY from Obsidian vault 02_Areas/skills/due-diligence/
│       ├── framework.md
│       ├── scoring-methodology.md
│       ├── workflows/
│       │   ├── quick-screen.md
│       │   ├── deep-dive.md
│       │   └── ...
│       └── categories/
│           └── ...
├── app/
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── state.py              ← ResearchState TypedDict + Citation accumulator helpers
│   │   ├── graph.py              ← StateGraph assembly + compile()
│   │   ├── checkpointer.py       ← PostgresSaver factory
│   │   └── nodes/
│   │       ├── __init__.py
│   │       ├── quick_screen.py   ← Phase 1+2 node
│   │       ├── deep_dive.py      ← Phase 3 node (9 parallel category calls)
│   │       ├── thesis.py         ← Phase 4 node
│   │       ├── risk_stress.py    ← Phase 5 node (conditional loop edge)
│   │       └── position.py       ← Phase 6 node
│   ├── schemas/
│   │   └── pipeline.py           ← StartRunRequest, ApproveRequest, RunStateResponse
│   └── routers/
│       └── pipeline.py           ← /pipeline/start, /pipeline/{id}/approve, /pipeline/{id}/stream
└── tests/
    ├── test_pipeline_state.py
    ├── test_pipeline_nodes.py
    └── test_pipeline_router.py
```

---

## Task 1: Add Dependencies + Copy Skill Files

**Files:**
- Modify: `backend/pyproject.toml` (via Poetry)
- Create: `backend/skills/due-diligence/` (copied from vault)

- [ ] **Step 1: Add new dependencies**

```bash
cd ~/Development/sector-research/backend
poetry add "psycopg[binary]" sse-starlette
```

- [ ] **Step 2: Copy skill files from the Obsidian vault**

```bash
cp -r ~/Development/followed/obsidian-notes-v2/02_Areas/skills/due-diligence \
      ~/Development/sector-research/backend/skills/due-diligence
```

- [ ] **Step 3: Verify files are present**

```bash
ls ~/Development/sector-research/backend/skills/due-diligence/
```

Expected: `framework.md  scoring-methodology.md  workflows/  categories/  platform-mapping.md`

- [ ] **Step 4: Commit**

```bash
cd ~/Development/sector-research
git add backend/pyproject.toml backend/poetry.lock backend/skills/
git commit -m "chore: add psycopg, sse-starlette, and copy due-diligence skill tree"
```

---

## Task 2: ResearchState and Helpers

**Files:**
- Create: `backend/app/pipeline/__init__.py`
- Create: `backend/app/pipeline/state.py`
- Create: `backend/tests/test_pipeline_state.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_pipeline_state.py`:

```python
from datetime import datetime, timezone
from app.pipeline.state import ResearchState, empty_state, add_citations
from app.clients.citation import Citation


def _make_citation(metric: str, tier: int = 1) -> Citation:
    return Citation(
        value=100.0,
        metric=metric,
        source_name=f"FMP /{metric}",
        source_url=f"https://fmp.com/{metric}",
        tier=tier,
        retrieved_at=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )


def test_empty_state_has_required_keys():
    state = empty_state("AAPL", "theme-id-123")
    assert state["ticker"] == "AAPL"
    assert state["theme_id"] == "theme-id-123"
    assert state["phase"] == "quick_screen"
    assert state["phase_outputs"] == {}
    assert state["citations"] == []
    assert state["scores"] == {}
    assert state["conviction_score"] is None
    assert state["thesis_status"] is None
    assert state["human_feedback"] == {}
    assert state["loop_context"] is None


def test_add_citations_appends_to_state():
    state = empty_state("AAPL", "theme-id")
    c1 = _make_citation("Income Statement")
    c2 = _make_citation("Key Metrics")
    updated = add_citations(state, [c1, c2])
    assert len(updated["citations"]) == 2
    assert updated["citations"][0].metric == "Income Statement"


def test_add_citations_does_not_mutate_original():
    state = empty_state("AAPL", "theme-id")
    c = _make_citation("Revenue")
    add_citations(state, [c])
    assert len(state["citations"]) == 0  # original unchanged


def test_state_serialization_round_trip():
    """State dict must be JSON-serializable (stored in PostgreSQL JSONB via LangGraph checkpointer)."""
    import json
    state = empty_state("AAPL", "theme-id")
    state["phase_outputs"]["quick_screen"] = {"decision": "GO", "score": 85}
    # Citations are dataclasses — must be converted to dicts for serialization
    c = _make_citation("Revenue")
    state["citations"].append(c.to_dict())
    json_str = json.dumps(state)
    restored = json.loads(json_str)
    assert restored["ticker"] == "AAPL"
    assert restored["citations"][0]["metric"] == "Revenue"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd ~/Development/sector-research/backend
poetry run pytest tests/test_pipeline_state.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.pipeline'`

- [ ] **Step 3: Create `backend/app/pipeline/__init__.py`**

```python
```

(empty)

- [ ] **Step 4: Create `backend/app/pipeline/state.py`**

```python
from __future__ import annotations
from typing import TypedDict, Any
from app.clients.citation import Citation


class ResearchState(TypedDict):
    ticker: str
    theme_id: str
    phase: str                        # current phase name
    phase_outputs: dict[str, Any]     # keyed by phase name, accumulated
    citations: list[dict]             # serialized Citation.to_dict() entries
    scores: dict[str, float]          # per-category composite scores 0-100
    conviction_score: int | None      # 0-100 overall
    thesis_status: str | None         # ON TRACK | DRIFTING | BROKEN
    human_feedback: dict[str, Any]    # notes added at each interrupt
    loop_context: dict | None         # set when Phase 5 loops back to Phase 3


def empty_state(ticker: str, theme_id: str) -> ResearchState:
    return ResearchState(
        ticker=ticker,
        theme_id=theme_id,
        phase="quick_screen",
        phase_outputs={},
        citations=[],
        scores={},
        conviction_score=None,
        thesis_status=None,
        human_feedback={},
        loop_context=None,
    )


def add_citations(state: ResearchState, citations: list[Citation]) -> ResearchState:
    """Returns a new state with citations appended (does not mutate original)."""
    return {
        **state,
        "citations": state["citations"] + [c.to_dict() for c in citations],
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_pipeline_state.py -v
```

Expected: `4 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/ backend/tests/test_pipeline_state.py
git commit -m "feat: add ResearchState TypedDict and citation accumulation helpers"
```

---

## Task 3: PostgreSQL Checkpointer

**Files:**
- Create: `backend/app/pipeline/checkpointer.py`

- [ ] **Step 1: Create `backend/app/pipeline/checkpointer.py`**

```python
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection
from app.config import settings

_checkpointer: PostgresSaver | None = None


def get_checkpointer() -> PostgresSaver:
    """
    Returns a singleton PostgresSaver instance.
    Creates the LangGraph checkpoint tables on first call.
    Call this once at app startup.
    """
    global _checkpointer
    if _checkpointer is None:
        conn = Connection.connect(settings.database_url, autocommit=True)
        _checkpointer = PostgresSaver(conn)
        _checkpointer.setup()  # creates langgraph_checkpoints table if not exists
    return _checkpointer
```

- [ ] **Step 2: Wire the checkpointer into app startup**

Edit `backend/app/main.py` — add a lifespan event:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.health import router as health_router
from app.routers.themes import router as themes_router
from app.routers.discovery import router as discovery_router
from app.routers.pipeline import router as pipeline_router
from app.pipeline.checkpointer import get_checkpointer


@asynccontextmanager
async def lifespan(app: FastAPI):
    get_checkpointer()  # initializes checkpoint table on startup
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="Sector Research API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(themes_router)
    app.include_router(discovery_router)
    app.include_router(pipeline_router)

    return app
```

- [ ] **Step 3: Verify health test still passes**

```bash
poetry run pytest tests/test_health.py -v
```

Expected: `2 passed` (lifespan with TestClient does not call startup in sync mode — health tests unaffected)

- [ ] **Step 4: Commit**

```bash
git add backend/app/pipeline/checkpointer.py backend/app/main.py
git commit -m "feat: add postgresql checkpointer for langgraph state persistence"
```

---

## Task 4: Skill File Loader

**Files:**
- Create: `backend/app/pipeline/nodes/__init__.py`
- Create: `backend/app/pipeline/nodes/skill_loader.py`

The phase nodes need to read skill markdown files as system prompt context.

- [ ] **Step 1: Create `backend/app/pipeline/nodes/__init__.py`**

```python
```

(empty)

- [ ] **Step 2: Create `backend/app/pipeline/nodes/skill_loader.py`**

```python
from pathlib import Path

_SKILLS_ROOT = Path(__file__).parent.parent.parent.parent / "skills" / "due-diligence"


def load_skill(relative_path: str) -> str:
    """
    Loads a skill markdown file relative to backend/skills/due-diligence/.
    Example: load_skill("workflows/quick-screen.md")
    Raises FileNotFoundError if the path does not exist.
    """
    full_path = _SKILLS_ROOT / relative_path
    if not full_path.exists():
        raise FileNotFoundError(f"Skill file not found: {full_path}")
    return full_path.read_text(encoding="utf-8")


def load_skills(*relative_paths: str) -> str:
    """Concatenates multiple skill files with a separator."""
    return "\n\n---\n\n".join(load_skill(p) for p in relative_paths)
```

- [ ] **Step 3: Write a quick sanity test**

Add to `backend/tests/test_pipeline_state.py`:

```python
def test_skill_loader_reads_framework():
    from app.pipeline.nodes.skill_loader import load_skill
    content = load_skill("framework.md")
    assert "Phase 1" in content
    assert "Phase 6" in content
```

- [ ] **Step 4: Run the test**

```bash
poetry run pytest tests/test_pipeline_state.py::test_skill_loader_reads_framework -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/nodes/ backend/tests/test_pipeline_state.py
git commit -m "feat: add skill file loader for phase prompt context"
```

---

## Task 5: Quick Screen Node (Phase 1+2)

**Files:**
- Create: `backend/app/pipeline/nodes/quick_screen.py`
- Create: `backend/tests/test_pipeline_nodes.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_pipeline_nodes.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.pipeline.state import empty_state
from app.clients.citation import Citation


def _mock_citation(metric: str) -> Citation:
    return Citation(
        value=100.0, metric=metric, source_name="FMP", source_url="https://fmp.com",
        tier=1, retrieved_at=datetime(2026, 4, 10, tzinfo=timezone.utc)
    )


@pytest.mark.asyncio
async def test_quick_screen_node_populates_phase_output():
    state = empty_state("AAPL", "theme-123")

    mock_profile = {"symbol": "AAPL", "companyName": "Apple Inc.", "mktCap": 3_000_000_000_000, "sector": "Technology", "exchangeShortName": "NASDAQ"}
    mock_metrics = [{"peRatio": 34.5, "evToEbitda": 25.1, "roic": 0.58, "grossProfitMargin": 0.46, "revenueGrowthRate": 0.04}]
    mock_income = [{"revenue": 391_035_000_000, "grossProfit": 180_683_000_000, "operatingIncome": 123_216_000_000}]

    mock_fmp = AsyncMock()
    mock_fmp.get_profile.return_value = (mock_profile, _mock_citation("Profile"))
    mock_fmp.get_key_metrics.return_value = (mock_metrics, _mock_citation("Key Metrics"))
    mock_fmp.get_income_statement.return_value = (mock_income, _mock_citation("Income"))
    mock_fmp.get_balance_sheet.return_value = ([{"totalDebt": 100e9, "totalStockholdersEquity": 50e9}], _mock_citation("Balance Sheet"))

    mock_llm_response = MagicMock()
    mock_llm_response.content = [MagicMock(text='{"decision":"GO","score":82,"rationale":"Strong moat, excellent margins, above WACC ROIC.","dimension_scores":{"data_liquidity":"PASS","business_quality":"PASS","industry_lifecycle":"PASS","valuation":"NEUTRAL","profitability":"PASS","technical_trend":"PASS"}}')]

    with patch("app.pipeline.nodes.quick_screen.FMPClient", return_value=mock_fmp), \
         patch("app.pipeline.nodes.quick_screen.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_llm_response

        # Import after patching
        from app.pipeline.nodes.quick_screen import quick_screen_node
        # quick_screen_node calls interrupt() — mock it to return a GO decision
        with patch("app.pipeline.nodes.quick_screen.interrupt", return_value={"action": "approve", "notes": ""}):
            result = await quick_screen_node(state)

    assert result["phase"] == "deep_dive"
    assert "quick_screen" in result["phase_outputs"]
    output = result["phase_outputs"]["quick_screen"]
    assert output["decision"] == "GO"
    assert output["score"] == 82
    assert len(result["citations"]) >= 3


@pytest.mark.asyncio
async def test_quick_screen_node_watchlist_sets_phase_to_watchlist():
    state = empty_state("WEAK", "theme-123")

    mock_fmp = AsyncMock()
    mock_fmp.get_profile.return_value = ({"symbol": "WEAK", "companyName": "Weak Corp", "mktCap": 500_000_000, "sector": "Energy", "exchangeShortName": "NYSE"}, _mock_citation("Profile"))
    mock_fmp.get_key_metrics.return_value = ([{"peRatio": 80.0, "evToEbitda": 40.0, "roic": 0.02, "grossProfitMargin": 0.08, "revenueGrowthRate": -0.05}], _mock_citation("Metrics"))
    mock_fmp.get_income_statement.return_value = ([{}], _mock_citation("Income"))
    mock_fmp.get_balance_sheet.return_value = ([{}], _mock_citation("Balance"))

    mock_llm_response = MagicMock()
    mock_llm_response.content = [MagicMock(text='{"decision":"WATCHLIST","score":38,"rationale":"Negative growth, low margins.","dimension_scores":{"data_liquidity":"PASS","business_quality":"FAIL","industry_lifecycle":"NEUTRAL","valuation":"FAIL","profitability":"FAIL","technical_trend":"NEUTRAL"}}')]

    with patch("app.pipeline.nodes.quick_screen.FMPClient", return_value=mock_fmp), \
         patch("app.pipeline.nodes.quick_screen.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value = mock_llm_response

        from app.pipeline.nodes.quick_screen import quick_screen_node
        with patch("app.pipeline.nodes.quick_screen.interrupt", return_value={"action": "watchlist", "notes": "revisit if margins recover"}):
            result = await quick_screen_node(state)

    assert result["phase"] == "watchlist"
    assert result["human_feedback"]["quick_screen"]["action"] == "watchlist"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_pipeline_nodes.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.pipeline.nodes.quick_screen'`

- [ ] **Step 3: Create `backend/app/pipeline/nodes/quick_screen.py`**

```python
from __future__ import annotations
import json
import anthropic
from langgraph.types import interrupt
from app.pipeline.state import ResearchState, add_citations
from app.pipeline.nodes.skill_loader import load_skills
from app.clients.fmp import FMPClient
from app.config import settings

_SYSTEM_PROMPT = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = load_skills(
            "framework.md",
            "workflows/quick-screen.md",
            "categories/01-business-quality.md",
            "categories/02-financial-health/valuation-multiples.md",
            "categories/02-financial-health/profitability-analysis.md",
            "scoring-methodology.md",
        )
    return _SYSTEM_PROMPT


async def quick_screen_node(state: ResearchState) -> ResearchState:
    """
    Phase 1+2: Fetch company profile, key metrics, income statement, balance sheet.
    Call Claude Haiku to score 6 dimensions and produce GO/WATCHLIST/PASS decision.
    Interrupt for human review. On resume, route based on human decision.
    """
    ticker = state["ticker"]
    fmp = FMPClient(api_key=settings.fmp_api_key)
    citations = []

    profile, c = await fmp.get_profile(ticker)
    citations.append(c)

    metrics, c = await fmp.get_key_metrics(ticker)
    citations.append(c)

    income, c = await fmp.get_income_statement(ticker, years=2)
    citations.append(c)

    balance, c = await fmp.get_balance_sheet(ticker, years=2)
    citations.append(c)

    await fmp.close()

    # Build data summary for the LLM
    data_summary = {
        "ticker": ticker,
        "profile": profile,
        "key_metrics": metrics[:2] if metrics else [],
        "income_statement": income[:2] if income else [],
        "balance_sheet": balance[:2] if balance else [],
    }

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        system=_get_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Run Phase 1 (Quick Screen) for {ticker}. "
                    f"Data: {json.dumps(data_summary, default=str)}\n\n"
                    "Return a JSON object with keys: decision (GO|WATCHLIST|PASS), "
                    "score (0-100), rationale (2-3 sentences), "
                    "dimension_scores (dict of 6 dimensions each PASS|NEUTRAL|FAIL). "
                    "Respond with JSON only, no markdown."
                ),
            }
        ],
    )

    raw = response.content[0].text.strip()
    try:
        output = json.loads(raw)
    except json.JSONDecodeError:
        output = {"decision": "WATCHLIST", "score": 50, "rationale": raw, "dimension_scores": {}}

    # Interrupt for human review
    human_decision = interrupt({
        "phase": "quick_screen",
        "output": output,
        "prompt": "Review the Quick Screen results. Choose: approve (proceed to deep-dive) / watchlist / pass",
    })

    state = add_citations(state, citations)
    state = {
        **state,
        "phase_outputs": {**state["phase_outputs"], "quick_screen": output},
        "human_feedback": {**state["human_feedback"], "quick_screen": human_decision},
    }

    action = human_decision.get("action", "stop")
    if action == "approve":
        state = {**state, "phase": "deep_dive"}
    else:
        state = {**state, "phase": action}  # "watchlist" or "pass"

    return state
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_pipeline_nodes.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/nodes/quick_screen.py backend/tests/test_pipeline_nodes.py
git commit -m "feat: add quick_screen pipeline node with interrupt and citation accumulation"
```

---

## Task 6: Deep Dive Node (Phase 3)

**Files:**
- Create: `backend/app/pipeline/nodes/deep_dive.py`
- Modify: `backend/tests/test_pipeline_nodes.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_pipeline_nodes.py`:

```python
@pytest.mark.asyncio
async def test_deep_dive_node_runs_all_nine_categories():
    from app.pipeline.state import empty_state
    state = empty_state("AAPL", "theme-123")
    state = {**state, "phase": "deep_dive", "phase_outputs": {"quick_screen": {"decision": "GO", "score": 82}}}

    mock_fmp = AsyncMock()
    mock_fmp.get_income_statement.return_value = ([{"revenue": 391e9}], _mock_citation("Income"))
    mock_fmp.get_key_metrics.return_value = ([{"roic": 0.58}], _mock_citation("Metrics"))
    mock_fmp.get_balance_sheet.return_value = ([{}], _mock_citation("Balance"))
    mock_fmp.get_cash_flow.return_value = ([{}], _mock_citation("CashFlow"))
    mock_fmp.get_dcf.return_value = ({"dcf": 210.0}, _mock_citation("DCF"))
    mock_fmp.get_earnings_transcript.return_value = ([], _mock_citation("Transcript"))
    mock_fmp.get_analyst_estimates.return_value = ([], _mock_citation("Estimates"))
    mock_fmp.get_options_flow.return_value = ([], _mock_citation("Options"))
    mock_fmp.get_profile.return_value = ({"symbol": "AAPL", "companyName": "Apple"}, _mock_citation("Profile"))

    category_response = '{"category_name":"Business Quality","score":88,"summary":"Strong moat.","key_findings":["Dominant ecosystem"],"citations_used":["FMP /key-metrics/AAPL"]}'

    with patch("app.pipeline.nodes.deep_dive.FMPClient", return_value=mock_fmp), \
         patch("app.pipeline.nodes.deep_dive.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value.content = [MagicMock(text=category_response)]

        from app.pipeline.nodes.deep_dive import deep_dive_node
        with patch("app.pipeline.nodes.deep_dive.interrupt", return_value={"action": "approve", "notes": ""}):
            result = await deep_dive_node(state)

    assert result["phase"] == "thesis_construction"
    assert "deep_dive" in result["phase_outputs"]
    categories = result["phase_outputs"]["deep_dive"]
    # All 9 category keys should be present
    assert len(categories) == 9
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
poetry run pytest tests/test_pipeline_nodes.py::test_deep_dive_node_runs_all_nine_categories -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.pipeline.nodes.deep_dive'`

- [ ] **Step 3: Create `backend/app/pipeline/nodes/deep_dive.py`**

```python
from __future__ import annotations
import json
import asyncio
import anthropic
from langgraph.types import interrupt
from app.pipeline.state import ResearchState, add_citations
from app.pipeline.nodes.skill_loader import load_skills, load_skill
from app.clients.fmp import FMPClient
from app.clients.citation import Citation
from app.config import settings

CATEGORIES = [
    ("01-business-quality", ["categories/01-business-quality.md"]),
    ("02-financial-health", ["categories/02-financial-health/valuation-multiples.md", "categories/02-financial-health/profitability-analysis.md", "categories/02-financial-health/dcf-analysis.md", "categories/02-financial-health/balance-sheet-strength.md", "categories/02-financial-health/cash-flow-quality.md"]),
    ("03-growth-earnings", ["categories/03-growth-earnings/revenue-driver-decomposition.md", "categories/03-growth-earnings/earnings-quality.md", "categories/03-growth-earnings/guidance-analysis.md", "categories/03-growth-earnings/analyst-expectations.md"]),
    ("04-management", ["categories/04-management-governance.md"]),
    ("05-technical", ["categories/05-technical-market-structure.md"]),
    ("06-macro-regime", ["categories/06-macro-regime.md"]),
    ("07-sentiment", ["categories/07-sentiment-narrative/news-sentiment.md", "categories/07-sentiment-narrative/social-signals.md", "categories/07-sentiment-narrative/market-narrative.md", "categories/07-sentiment-narrative/institutional-positioning.md"]),
    ("08-risk", ["categories/08-risk-assessment.md"]),
    ("09-durability", ["categories/09-future-durability.md"]),
]


async def _analyze_category(
    category_key: str,
    skill_paths: list[str],
    ticker: str,
    fmp_data: dict,
    client: anthropic.Anthropic,
    loop_focus: list[str] | None,
) -> dict:
    """Runs a single category analysis via Claude Sonnet."""
    if loop_focus and category_key not in loop_focus:
        return None  # Skip categories not targeted in loop

    try:
        skill_context = load_skills(*skill_paths)
    except FileNotFoundError:
        skill_context = f"# {category_key}\nAnalyze this category for {ticker}."

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=skill_context,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyze {ticker} for the {category_key} category. "
                    f"Available data: {json.dumps(fmp_data, default=str)}\n\n"
                    "Return JSON with keys: category_name (str), score (0-100), "
                    "summary (2-3 sentences), key_findings (list of strings, max 5), "
                    "red_flags (list of strings, empty if none), "
                    "citations_used (list of source names). JSON only, no markdown."
                ),
            }
        ],
    )
    raw = response.content[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"category_name": category_key, "score": 50, "summary": raw, "key_findings": [], "red_flags": [], "citations_used": []}


async def deep_dive_node(state: ResearchState) -> ResearchState:
    """
    Phase 3: Run all 9 analytical categories concurrently via Claude Sonnet.
    If loop_context is set (looping from Phase 5), only re-run targeted categories.
    Interrupt for human review before advancing.
    """
    ticker = state["ticker"]
    loop_focus = (state.get("loop_context") or {}).get("categories_to_rerun")

    fmp = FMPClient(api_key=settings.fmp_api_key)
    citations: list[Citation] = []

    # Fetch all data needed across categories in parallel
    results = await asyncio.gather(
        fmp.get_income_statement(ticker, years=3),
        fmp.get_key_metrics(ticker),
        fmp.get_balance_sheet(ticker, years=3),
        fmp.get_cash_flow(ticker, years=3),
        fmp.get_dcf(ticker),
        fmp.get_analyst_estimates(ticker),
        fmp.get_options_flow(ticker),
        fmp.get_profile(ticker),
        return_exceptions=True,
    )
    await fmp.close()

    fmp_data: dict = {}
    data_labels = ["income_statement", "key_metrics", "balance_sheet", "cash_flow", "dcf", "analyst_estimates", "options_flow", "profile"]
    for label, result in zip(data_labels, results):
        if isinstance(result, Exception):
            fmp_data[label] = None
        else:
            data, citation = result
            fmp_data[label] = data
            citations.append(citation)

    llm = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Run all 9 categories concurrently (asyncio.gather over sync Claude calls via run_in_executor)
    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, lambda ck=ck, sp=sp: asyncio.run(
            _analyze_category(ck, sp, ticker, fmp_data, llm, loop_focus)
        ))
        for ck, sp in CATEGORIES
    ]
    category_results = await asyncio.gather(*tasks, return_exceptions=True)

    category_outputs = {}
    for (category_key, _), result in zip(CATEGORIES, category_results):
        if result is None:
            continue  # skipped due to loop_focus
        if isinstance(result, Exception):
            category_outputs[category_key] = {"category_name": category_key, "score": 50, "error": str(result)}
        else:
            category_outputs[category_key] = result

    # Merge with existing outputs if looping
    existing = state["phase_outputs"].get("deep_dive", {})
    merged = {**existing, **category_outputs}

    # Update scores
    scores = {k: v.get("score", 50) for k, v in merged.items() if isinstance(v, dict)}

    # Interrupt for human review
    human_decision = interrupt({
        "phase": "deep_dive",
        "outputs": merged,
        "loop_context": state.get("loop_context"),
        "prompt": "Review the deep-dive category reports. Approve to proceed to thesis construction, or stop to archive.",
    })

    state = add_citations(state, citations)
    state = {
        **state,
        "phase_outputs": {**state["phase_outputs"], "deep_dive": merged},
        "scores": {**state["scores"], **scores},
        "human_feedback": {**state["human_feedback"], "deep_dive": human_decision},
        "loop_context": None,  # clear loop context after re-run
    }

    action = human_decision.get("action", "stop")
    state = {**state, "phase": "thesis_construction" if action == "approve" else "stop"}
    return state
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
poetry run pytest tests/test_pipeline_nodes.py::test_deep_dive_node_runs_all_nine_categories -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/nodes/deep_dive.py backend/tests/test_pipeline_nodes.py
git commit -m "feat: add deep_dive node with parallel category analysis and interrupt"
```

---

## Task 7: Thesis, Risk, and Position Nodes (Phases 4–6)

**Files:**
- Create: `backend/app/pipeline/nodes/thesis.py`
- Create: `backend/app/pipeline/nodes/risk_stress.py`
- Create: `backend/app/pipeline/nodes/position.py`
- Modify: `backend/tests/test_pipeline_nodes.py`

- [ ] **Step 1: Write the failing tests**

Add to `backend/tests/test_pipeline_nodes.py`:

```python
@pytest.mark.asyncio
async def test_thesis_node_produces_bull_bear_base():
    from app.pipeline.state import empty_state
    state = empty_state("AAPL", "theme-123")
    state = {**state, "phase": "thesis_construction", "phase_outputs": {
        "quick_screen": {"decision": "GO", "score": 82},
        "deep_dive": {"01-business-quality": {"score": 88, "summary": "Strong moat."}}
    }, "scores": {"01-business-quality": 88}}

    thesis_response = json.dumps({
        "bull_case": "AI-driven demand for Apple services continues to accelerate.",
        "bear_case": "Hardware commoditization pressures margins.",
        "base_case": "Steady 8-12% EPS growth with expanding services mix.",
        "catalysts": ["Vision Pro adoption", "India expansion", "AI features in iOS"],
        "variant_perception": "Market underestimates services margin expansion.",
        "conviction_score": 78,
        "thesis_status": "ON TRACK"
    })

    with patch("app.pipeline.nodes.thesis.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value.content = [MagicMock(text=thesis_response)]

        from app.pipeline.nodes.thesis import thesis_node
        result = await thesis_node(state)

    assert result["phase"] == "risk_stress_test"
    assert "thesis_construction" in result["phase_outputs"]
    thesis = result["phase_outputs"]["thesis_construction"]
    assert thesis["conviction_score"] == 78
    assert thesis["thesis_status"] == "ON TRACK"
    assert len(thesis["catalysts"]) >= 3


@pytest.mark.asyncio
async def test_risk_stress_node_loops_when_reward_below_threshold():
    from app.pipeline.state import empty_state
    state = empty_state("AAPL", "theme-123")
    state = {**state, "phase": "risk_stress_test", "phase_outputs": {
        "thesis_construction": {"conviction_score": 78, "thesis_status": "ON TRACK"}
    }, "conviction_score": 78}

    risk_response = json.dumps({
        "risk_reward_ratio": 1.4,  # below 2:1 threshold → triggers loop
        "categories_to_rerun": ["08-risk", "02-financial-health"],
        "risk_register": [{"risk": "Regulatory", "severity": "HIGH", "likelihood": "MEDIUM"}],
        "tail_risks": ["DOJ antitrust breakup"],
        "loop_reason": "Risk/reward 1.4:1 is below the 2:1 minimum. Re-investigating risk and financial health categories."
    })

    with patch("app.pipeline.nodes.risk_stress.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value.content = [MagicMock(text=risk_response)]

        from app.pipeline.nodes.risk_stress import risk_stress_node
        result = await risk_stress_node(state)

    # Should loop back to deep_dive, not interrupt
    assert result["phase"] == "deep_dive"
    assert result["loop_context"]["categories_to_rerun"] == ["08-risk", "02-financial-health"]


@pytest.mark.asyncio
async def test_position_node_produces_entry_plan():
    from app.pipeline.state import empty_state
    state = empty_state("AAPL", "theme-123")
    state = {**state, "phase": "position_monitor", "conviction_score": 78,
             "phase_outputs": {"thesis_construction": {"conviction_score": 78}}}

    position_response = json.dumps({
        "entry_zone": "185-195",
        "position_size_pct": 4.5,
        "stop_loss": 170.0,
        "invalidation_condition": "Revenue growth falls below 2% for two consecutive quarters",
        "review_cadence": "Quarterly on earnings",
        "monitoring_triggers": ["Services revenue growth", "India market share", "Vision Pro unit sales"]
    })

    with patch("app.pipeline.nodes.position.anthropic.Anthropic") as MockAnthropic:
        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value.content = [MagicMock(text=position_response)]

        from app.pipeline.nodes.position import position_node
        result = await position_node(state)

    assert result["phase"] == "complete"
    assert "position_monitor" in result["phase_outputs"]
    plan = result["phase_outputs"]["position_monitor"]
    assert plan["position_size_pct"] == 4.5
    assert plan["stop_loss"] == 170.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_pipeline_nodes.py::test_thesis_node_produces_bull_bear_base tests/test_pipeline_nodes.py::test_risk_stress_node_loops_when_reward_below_threshold tests/test_pipeline_nodes.py::test_position_node_produces_entry_plan -v
```

Expected: `FAILED` — missing modules

- [ ] **Step 3: Create `backend/app/pipeline/nodes/thesis.py`**

```python
from __future__ import annotations
import json
import anthropic
from app.pipeline.state import ResearchState
from app.pipeline.nodes.skill_loader import load_skills
from app.config import settings

_SYSTEM_PROMPT = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = load_skills(
            "framework.md",
            "workflows/deep-dive.md",
            "scoring-methodology.md",
        )
    return _SYSTEM_PROMPT


async def thesis_node(state: ResearchState) -> ResearchState:
    """
    Phase 4: Synthesize deep-dive findings into bull/bear/base thesis with catalysts.
    No human interrupt — feeds directly into risk_stress_test.
    """
    ticker = state["ticker"]
    deep_dive_outputs = state["phase_outputs"].get("deep_dive", {})
    quick_screen = state["phase_outputs"].get("quick_screen", {})

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=_get_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Construct the investment thesis for {ticker} (Phase 4). "
                    f"Quick screen score: {quick_screen.get('score', 'N/A')}. "
                    f"Category scores: {json.dumps({k: v.get('score') for k, v in deep_dive_outputs.items()}, default=str)}. "
                    f"Category summaries: {json.dumps({k: v.get('summary', '') for k, v in deep_dive_outputs.items()}, default=str)}\n\n"
                    "Return JSON with keys: bull_case (str), bear_case (str), base_case (str), "
                    "catalysts (list of 3+ strings), variant_perception (str), "
                    "conviction_score (0-100), thesis_status (ON TRACK|DRIFTING|BROKEN). "
                    "JSON only."
                ),
            }
        ],
    )

    raw = response.content[0].text.strip()
    try:
        output = json.loads(raw)
    except json.JSONDecodeError:
        output = {"bull_case": "", "bear_case": "", "base_case": raw, "catalysts": [], "variant_perception": "", "conviction_score": 50, "thesis_status": "DRIFTING"}

    conviction = output.get("conviction_score", 50)
    return {
        **state,
        "phase": "risk_stress_test",
        "phase_outputs": {**state["phase_outputs"], "thesis_construction": output},
        "conviction_score": conviction,
        "thesis_status": output.get("thesis_status", "DRIFTING"),
    }
```

- [ ] **Step 4: Create `backend/app/pipeline/nodes/risk_stress.py`**

```python
from __future__ import annotations
import json
import anthropic
from langgraph.types import interrupt
from app.pipeline.state import ResearchState
from app.pipeline.nodes.skill_loader import load_skills
from app.config import settings

_RISK_REWARD_THRESHOLD = 2.0
_SYSTEM_PROMPT = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = load_skills(
            "framework.md",
            "categories/08-risk-assessment.md",
            "categories/09-future-durability.md",
            "scoring-methodology.md",
        )
    return _SYSTEM_PROMPT


async def risk_stress_node(state: ResearchState) -> ResearchState:
    """
    Phase 5: Stress-test the thesis. If risk/reward < 2:1, loop back to deep_dive
    with targeted categories (no interrupt — automatic with state flag).
    If risk/reward >= 2:1, interrupt for human approval.
    """
    ticker = state["ticker"]
    thesis = state["phase_outputs"].get("thesis_construction", {})
    deep_dive = state["phase_outputs"].get("deep_dive", {})

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2000,
        system=_get_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Stress-test the investment thesis for {ticker} (Phase 5). "
                    f"Thesis: {json.dumps(thesis, default=str)}. "
                    f"Category findings: {json.dumps({k: {'score': v.get('score'), 'red_flags': v.get('red_flags', [])} for k, v in deep_dive.items()}, default=str)}\n\n"
                    "Return JSON with keys: risk_reward_ratio (float), "
                    "categories_to_rerun (list of category keys that need deeper investigation — empty if none), "
                    "risk_register (list of {risk, severity, likelihood}), "
                    "tail_risks (list of strings), "
                    "loop_reason (str — explain why looping, or empty string if not looping). "
                    "JSON only."
                ),
            }
        ],
    )

    raw = response.content[0].text.strip()
    try:
        output = json.loads(raw)
    except json.JSONDecodeError:
        output = {"risk_reward_ratio": 2.5, "categories_to_rerun": [], "risk_register": [], "tail_risks": [], "loop_reason": ""}

    rr_ratio = output.get("risk_reward_ratio", 2.5)
    categories_to_rerun = output.get("categories_to_rerun", [])

    # Automatic loop back to deep_dive if below threshold
    if rr_ratio < _RISK_REWARD_THRESHOLD and categories_to_rerun:
        return {
            **state,
            "phase": "deep_dive",
            "phase_outputs": {**state["phase_outputs"], "risk_stress_test_partial": output},
            "loop_context": {
                "categories_to_rerun": categories_to_rerun,
                "loop_reason": output.get("loop_reason", f"Risk/reward {rr_ratio:.1f}:1 is below the 2:1 minimum."),
            },
        }

    # Risk/reward is acceptable — interrupt for human review
    human_decision = interrupt({
        "phase": "risk_stress_test",
        "output": output,
        "thesis": thesis,
        "prompt": "Review the thesis and risk register. Approve to proceed to position planning, or stop to archive.",
    })

    return {
        **state,
        "phase": "position_monitor" if human_decision.get("action") == "approve" else "stop",
        "phase_outputs": {**state["phase_outputs"], "risk_stress_test": output},
        "human_feedback": {**state["human_feedback"], "risk_stress_test": human_decision},
    }
```

- [ ] **Step 5: Create `backend/app/pipeline/nodes/position.py`**

```python
from __future__ import annotations
import json
import anthropic
from app.pipeline.state import ResearchState
from app.pipeline.nodes.skill_loader import load_skills
from app.config import settings

_SYSTEM_PROMPT = None


def _get_system_prompt() -> str:
    global _SYSTEM_PROMPT
    if _SYSTEM_PROMPT is None:
        _SYSTEM_PROMPT = load_skills("framework.md", "scoring-methodology.md")
    return _SYSTEM_PROMPT


async def position_node(state: ResearchState) -> ResearchState:
    """
    Phase 6: Produce entry zone, position size, stop loss, invalidation condition,
    review cadence, and monitoring triggers. No interrupt — terminal node.
    """
    ticker = state["ticker"]
    thesis = state["phase_outputs"].get("thesis_construction", {})
    risk = state["phase_outputs"].get("risk_stress_test", {})
    conviction = state.get("conviction_score", 50)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1000,
        system=_get_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": (
                    f"Create a position and monitoring plan for {ticker} (Phase 6). "
                    f"Conviction score: {conviction}/100. "
                    f"Thesis: {json.dumps(thesis, default=str)}. "
                    f"Risk register: {json.dumps(risk.get('risk_register', []), default=str)}\n\n"
                    "Return JSON with keys: entry_zone (str price range), "
                    "position_size_pct (float, % of portfolio, 0-10), "
                    "stop_loss (float), invalidation_condition (str), "
                    "review_cadence (str), monitoring_triggers (list of strings, max 5). "
                    "JSON only."
                ),
            }
        ],
    )

    raw = response.content[0].text.strip()
    try:
        output = json.loads(raw)
    except json.JSONDecodeError:
        output = {"entry_zone": "N/A", "position_size_pct": 2.0, "stop_loss": 0.0, "invalidation_condition": raw, "review_cadence": "Quarterly", "monitoring_triggers": []}

    return {
        **state,
        "phase": "complete",
        "phase_outputs": {**state["phase_outputs"], "position_monitor": output},
    }
```

- [ ] **Step 6: Run all node tests**

```bash
poetry run pytest tests/test_pipeline_nodes.py -v
```

Expected: `6 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/pipeline/nodes/thesis.py backend/app/pipeline/nodes/risk_stress.py backend/app/pipeline/nodes/position.py backend/tests/test_pipeline_nodes.py
git commit -m "feat: add thesis, risk_stress, and position pipeline nodes"
```

---

## Task 8: Graph Assembly

**Files:**
- Create: `backend/app/pipeline/graph.py`

- [ ] **Step 1: Create `backend/app/pipeline/graph.py`**

```python
from __future__ import annotations
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.postgres import PostgresSaver
from app.pipeline.state import ResearchState
from app.pipeline.nodes.quick_screen import quick_screen_node
from app.pipeline.nodes.deep_dive import deep_dive_node
from app.pipeline.nodes.thesis import thesis_node
from app.pipeline.nodes.risk_stress import risk_stress_node
from app.pipeline.nodes.position import position_node

_COMPILED_GRAPH = None


def _route_after_quick_screen(state: ResearchState) -> str:
    return state.get("phase", "stop")


def _route_after_deep_dive(state: ResearchState) -> str:
    return state.get("phase", "stop")


def _route_after_risk_stress(state: ResearchState) -> str:
    return state.get("phase", "stop")


def build_graph(checkpointer: PostgresSaver):
    """Builds and compiles the research pipeline graph."""
    graph = StateGraph(ResearchState)

    graph.add_node("quick_screen", quick_screen_node)
    graph.add_node("deep_dive", deep_dive_node)
    graph.add_node("thesis_construction", thesis_node)
    graph.add_node("risk_stress_test", risk_stress_node)
    graph.add_node("position_monitor", position_node)

    graph.set_entry_point("quick_screen")

    graph.add_conditional_edges(
        "quick_screen",
        _route_after_quick_screen,
        {
            "deep_dive": "deep_dive",
            "watchlist": END,
            "pass": END,
            "stop": END,
        },
    )

    graph.add_conditional_edges(
        "deep_dive",
        _route_after_deep_dive,
        {
            "thesis_construction": "thesis_construction",
            "stop": END,
        },
    )

    graph.add_edge("thesis_construction", "risk_stress_test")

    graph.add_conditional_edges(
        "risk_stress_test",
        _route_after_risk_stress,
        {
            "position_monitor": "position_monitor",
            "deep_dive": "deep_dive",  # loop back
            "stop": END,
        },
    )

    graph.add_edge("position_monitor", END)

    return graph.compile(checkpointer=checkpointer)


def get_graph(checkpointer: PostgresSaver):
    """Returns singleton compiled graph."""
    global _COMPILED_GRAPH
    if _COMPILED_GRAPH is None:
        _COMPILED_GRAPH = build_graph(checkpointer)
    return _COMPILED_GRAPH
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/pipeline/graph.py
git commit -m "feat: assemble langgraph pipeline with all 6 phase nodes and conditional routing"
```

---

## Task 9: Pipeline Router and Schemas

**Files:**
- Create: `backend/app/schemas/pipeline.py`
- Modify: `backend/app/routers/pipeline.py`
- Create: `backend/tests/test_pipeline_router.py`

- [ ] **Step 1: Create `backend/app/schemas/pipeline.py`**

```python
import uuid
from pydantic import BaseModel


class StartRunRequest(BaseModel):
    ticker: str
    theme_id: uuid.UUID | None = None


class StartRunResponse(BaseModel):
    run_id: str
    ticker: str
    status: str  # "started"


class ApproveRequest(BaseModel):
    action: str  # "approve" | "watchlist" | "pass" | "stop"
    notes: str = ""


class RunStateResponse(BaseModel):
    run_id: str
    ticker: str
    phase: str
    status: str
    conviction_score: int | None
    thesis_status: str | None
    phase_outputs: dict
    citations: list[dict]
    human_feedback: dict
    loop_context: dict | None
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/test_pipeline_router.py`:

```python
import pytest
import uuid
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import create_app
from app.database import get_db
from app.pipeline.state import empty_state


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def client(mock_db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app)


def test_start_run_creates_research_run(client, mock_db):
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.refresh = MagicMock()

    mock_graph = MagicMock()
    mock_graph.ainvoke = AsyncMock(return_value=empty_state("AAPL", ""))

    with patch("app.routers.pipeline.get_graph", return_value=mock_graph), \
         patch("app.routers.pipeline.get_checkpointer", return_value=MagicMock()):
        resp = client.post("/pipeline/start", json={"ticker": "AAPL"})

    assert resp.status_code == 202
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert "run_id" in data
    mock_db.add.assert_called_once()


def test_get_run_state_not_found(client, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    resp = client.get(f"/pipeline/{uuid.uuid4()}/state")
    assert resp.status_code == 404


def test_approve_run_not_found(client, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    resp = client.post(f"/pipeline/{uuid.uuid4()}/approve", json={"action": "approve"})
    assert resp.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
poetry run pytest tests/test_pipeline_router.py -v
```

Expected: `FAILED` — pipeline router is a stub

- [ ] **Step 4: Replace `backend/app/routers/pipeline.py`**

```python
import uuid
import asyncio
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.research_run import ResearchRun
from app.pipeline.graph import get_graph
from app.pipeline.checkpointer import get_checkpointer
from app.pipeline.state import empty_state
from app.schemas.pipeline import StartRunRequest, StartRunResponse, ApproveRequest, RunStateResponse

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


def _run_id_to_config(run_id: str) -> dict:
    return {"configurable": {"thread_id": run_id}}


@router.post("/start", response_model=StartRunResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_run(
    payload: StartRunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    run_id = str(uuid.uuid4())
    state = empty_state(payload.ticker, str(payload.theme_id) if payload.theme_id else "")

    # Persist run record
    run = ResearchRun(
        id=uuid.UUID(run_id),
        ticker=payload.ticker,
        theme_id=payload.theme_id,
        phase="quick_screen",
        status="in_progress",
        state=state,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    # Start pipeline in background
    checkpointer = get_checkpointer()
    graph = get_graph(checkpointer)
    background_tasks.add_task(_run_pipeline, graph, state, run_id, db)

    return StartRunResponse(run_id=run_id, ticker=payload.ticker, status="started")


async def _run_pipeline(graph, state: dict, run_id: str, db: Session):
    """Runs the graph until the first interrupt or completion."""
    config = _run_id_to_config(run_id)
    try:
        async for chunk in graph.astream(state, config=config):
            # Update run record with latest state on each node completion
            node_name = list(chunk.keys())[0] if chunk else None
            if node_name and node_name in chunk:
                updated_state = chunk[node_name]
                run = db.query(ResearchRun).filter(ResearchRun.id == uuid.UUID(run_id)).first()
                if run:
                    run.phase = updated_state.get("phase", run.phase)
                    run.state = updated_state
                    db.commit()
    except Exception as e:
        run = db.query(ResearchRun).filter(ResearchRun.id == uuid.UUID(run_id)).first()
        if run:
            run.status = "error"
            run.state = {**(run.state or {}), "error": str(e)}
            db.commit()


@router.get("/{run_id}/state", response_model=RunStateResponse)
def get_run_state(run_id: str, db: Session = Depends(get_db)):
    run = db.query(ResearchRun).filter(ResearchRun.id == uuid.UUID(run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Research run not found")
    state = run.state or {}
    return RunStateResponse(
        run_id=run_id,
        ticker=run.ticker,
        phase=run.phase,
        status=run.status,
        conviction_score=state.get("conviction_score"),
        thesis_status=state.get("thesis_status"),
        phase_outputs=state.get("phase_outputs", {}),
        citations=state.get("citations", []),
        human_feedback=state.get("human_feedback", {}),
        loop_context=state.get("loop_context"),
    )


@router.post("/{run_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve_run(
    run_id: str,
    payload: ApproveRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    run = db.query(ResearchRun).filter(ResearchRun.id == uuid.UUID(run_id)).first()
    if not run:
        raise HTTPException(status_code=404, detail="Research run not found")

    checkpointer = get_checkpointer()
    graph = get_graph(checkpointer)
    config = _run_id_to_config(run_id)

    # Resume the interrupted graph with the human decision
    from langgraph.types import Command
    human_decision = {"action": payload.action, "notes": payload.notes}
    background_tasks.add_task(_resume_pipeline, graph, Command(resume=human_decision), config, run_id, db)

    return {"run_id": run_id, "status": "resumed", "action": payload.action}


async def _resume_pipeline(graph, command, config: dict, run_id: str, db: Session):
    try:
        async for chunk in graph.astream(command, config=config):
            node_name = list(chunk.keys())[0] if chunk else None
            if node_name and node_name in chunk:
                updated_state = chunk[node_name]
                run = db.query(ResearchRun).filter(ResearchRun.id == uuid.UUID(run_id)).first()
                if run:
                    run.phase = updated_state.get("phase", run.phase)
                    run.state = updated_state
                    if updated_state.get("phase") in ("complete", "watchlist", "pass", "stop"):
                        run.status = updated_state.get("phase", "complete")
                    db.commit()
    except Exception as e:
        run = db.query(ResearchRun).filter(ResearchRun.id == uuid.UUID(run_id)).first()
        if run:
            run.status = "error"
            run.state = {**(run.state or {}), "error": str(e)}
            db.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_pipeline_router.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Run the full test suite**

```bash
poetry run pytest -v
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/pipeline.py backend/app/routers/pipeline.py backend/tests/test_pipeline_router.py
git commit -m "feat: add pipeline router with start, approve, and state endpoints"
```

---

## Plan 3 Complete

At this point you have:
- `ResearchState` TypedDict with citation accumulation helpers
- PostgreSQL checkpointer for pause/resume across sessions
- All 6 phase nodes: `quick_screen`, `deep_dive`, `thesis_construction`, `risk_stress_test`, `position_monitor`
- Phase 5 → Phase 3 automatic loop when risk/reward < 2:1
- Human interrupt at Phase 1, Phase 3, and Phase 5
- FastAPI endpoints: `POST /pipeline/start`, `POST /pipeline/{id}/approve`, `GET /pipeline/{id}/state`

**Next:** Plan 4 (Frontend) — Next.js 15 App Router, all 5 pages, SSE streaming, citation footnotes.
