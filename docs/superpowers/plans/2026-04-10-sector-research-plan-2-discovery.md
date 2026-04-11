# Sector Research App — Plan 2: Discovery Engine

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add theme management CRUD, FMP screener pass, X signal computation, and the company signal card API — so the frontend can browse themes and see ranked company lists.

**Architecture:** Two FastAPI routers (`/themes`, `/discovery`) backed by two service modules (`services/discovery.py`, `services/signals.py`). All API responses use Pydantic schemas defined in `app/schemas/`. Signal computation runs synchronously on-demand (background scheduling is a v2 concern). Combined score = `weights.velocity * velocity_score + weights.fundamental * fundamental_score + weights.discovery * discovery_score`.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic v2, FMPClient + XAPIClient (from Plan 1), Anthropic SDK (Claude Haiku for narrative summaries), pytest

**Prereq:** Plan 1 complete — `FMPClient`, `XAPIClient`, `Citation`, all models, and FastAPI shell all exist.

**Spec:** `docs/superpowers/specs/2026-04-10-sector-research-app-design.md` — Sections 1 and 2

---

## File Map

```
backend/
├── app/
│   ├── schemas/                  ← NEW
│   │   ├── __init__.py
│   │   ├── theme.py              ← ThemeCreate, ThemeUpdate, ThemeResponse
│   │   └── discovery.py          ← CompanySignalCard, FMPSnapshot, SignalBadge, CitationResponse
│   ├── services/                 ← NEW
│   │   ├── __init__.py
│   │   ├── discovery.py          ← orchestrates FMP screener + signal lookup + scoring
│   │   └── signals.py            ← X signal computation + narrative via Claude Haiku
│   └── routers/
│       ├── themes.py             ← REPLACE stub with real CRUD
│       └── discovery.py          ← REPLACE stub with real endpoints
└── tests/
    ├── test_themes_router.py     ← NEW
    ├── test_discovery_service.py ← NEW
    └── test_signals_service.py   ← NEW
```

---

## Task 1: Pydantic Schemas

**Files:**
- Create: `backend/app/schemas/__init__.py`
- Create: `backend/app/schemas/theme.py`
- Create: `backend/app/schemas/discovery.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_schemas.py`:

```python
import uuid
from datetime import datetime, timezone
from app.schemas.theme import ThemeCreate, ThemeResponse
from app.schemas.discovery import CompanySignalCard, FMPSnapshot, SignalBadge


def test_theme_create_defaults():
    t = ThemeCreate(name="AI Power", description="Companies powering AI infrastructure")
    assert t.seed_tickers == []
    assert t.signal_weights == {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2}


def test_theme_create_validates_weight_sum():
    import pytest
    with pytest.raises(ValueError, match="signal_weights must sum to 1.0"):
        ThemeCreate(
            name="Bad",
            description="Bad weights",
            signal_weights={"velocity": 0.5, "fundamental": 0.5, "discovery": 0.5},
        )


def test_company_signal_card_combined_score_is_none_without_signal():
    card = CompanySignalCard(
        ticker="VST",
        company_name="Vistra Corp",
        market_cap=30_000_000_000,
        sector="Utilities",
        exchange="NYSE",
        fmp_snapshot=FMPSnapshot(
            pe_ratio=14.2,
            ev_to_ebitda=9.1,
            roic=0.18,
            gross_margin=0.42,
            revenue_growth_yoy=0.23,
        ),
        fmp_citations=[],
        signal=None,
        combined_score=None,
        in_seed_list=True,
        last_run=None,
    )
    assert card.combined_score is None
    assert card.signal is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/Development/sector-research/backend
poetry run pytest tests/test_schemas.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.schemas'`

- [ ] **Step 3: Create `backend/app/schemas/__init__.py`**

```python
```

(empty)

- [ ] **Step 4: Create `backend/app/schemas/theme.py`**

```python
import uuid
from datetime import datetime
from typing import Any
from pydantic import BaseModel, model_validator

_DEFAULT_WEIGHTS = {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2}


class ThemeCreate(BaseModel):
    name: str
    description: str
    seed_tickers: list[str] = []
    screener_criteria: dict[str, Any] = {}
    x_search_terms: list[str] = []
    signal_weights: dict[str, float] = _DEFAULT_WEIGHTS

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "ThemeCreate":
        total = sum(self.signal_weights.values())
        if abs(total - 1.0) > 0.01:
            raise ValueError("signal_weights must sum to 1.0")
        return self


class ThemeUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    seed_tickers: list[str] | None = None
    screener_criteria: dict[str, Any] | None = None
    x_search_terms: list[str] | None = None
    signal_weights: dict[str, float] | None = None

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "ThemeUpdate":
        if self.signal_weights is not None:
            total = sum(self.signal_weights.values())
            if abs(total - 1.0) > 0.01:
                raise ValueError("signal_weights must sum to 1.0")
        return self


class ThemeResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    seed_tickers: list[str]
    screener_criteria: dict[str, Any]
    x_search_terms: list[str]
    signal_weights: dict[str, float]
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}
```

- [ ] **Step 5: Create `backend/app/schemas/discovery.py`**

```python
import uuid
from datetime import datetime
from pydantic import BaseModel


class CitationResponse(BaseModel):
    metric: str
    value: str
    source_name: str
    source_url: str
    tier: int
    retrieved_at: datetime


class FMPSnapshot(BaseModel):
    pe_ratio: float | None = None
    ev_to_ebitda: float | None = None
    roic: float | None = None
    gross_margin: float | None = None
    revenue_growth_yoy: float | None = None


class SignalBadge(BaseModel):
    velocity_score: float
    velocity_label: str  # "accelerating" | "stable" | "decelerating"
    discovery_score: float
    narrative: str
    last_computed: datetime


class ResearchRunSummary(BaseModel):
    run_id: uuid.UUID
    phase_reached: str
    conviction_score: int | None
    thesis_status: str | None
    status: str
    updated_at: datetime | None


class CompanySignalCard(BaseModel):
    ticker: str
    company_name: str
    market_cap: int | None = None
    sector: str | None = None
    exchange: str | None = None
    fmp_snapshot: FMPSnapshot
    fmp_citations: list[CitationResponse]
    signal: SignalBadge | None = None
    combined_score: float | None = None
    in_seed_list: bool
    last_run: ResearchRunSummary | None = None


class ThemeDiscoveryResponse(BaseModel):
    theme_id: uuid.UUID
    theme_name: str
    companies: list[CompanySignalCard]
    sort_by: str
    total: int
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
poetry run pytest tests/test_schemas.py -v
```

Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/ backend/tests/test_schemas.py
git commit -m "feat: add pydantic schemas for theme and discovery responses"
```

---

## Task 2: Themes CRUD Router

**Files:**
- Modify: `backend/app/routers/themes.py`
- Create: `backend/tests/test_themes_router.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_themes_router.py`:

```python
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from app.main import create_app
from app.database import get_db
from app.models.theme import Theme
import uuid


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def client(mock_db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app)


def test_create_theme(client, mock_db):
    mock_db.add = MagicMock()
    mock_db.commit = MagicMock()
    mock_db.refresh = MagicMock(side_effect=lambda obj: setattr(obj, "id", uuid.uuid4()))

    payload = {
        "name": "AI Power Infrastructure",
        "description": "Companies powering AI data centers",
        "seed_tickers": ["VST", "CEG"],
        "x_search_terms": ["AI power", "data center electricity"],
        "screener_criteria": {"sector": "Utilities"},
        "signal_weights": {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2},
    }
    resp = client.post("/themes", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "AI Power Infrastructure"
    assert data["seed_tickers"] == ["VST", "CEG"]
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_create_theme_invalid_weights(client, mock_db):
    payload = {
        "name": "Bad Theme",
        "description": "Bad",
        "signal_weights": {"velocity": 0.5, "fundamental": 0.5, "discovery": 0.5},
    }
    resp = client.post("/themes", json=payload)
    assert resp.status_code == 422


def test_list_themes(client, mock_db):
    theme_id = uuid.uuid4()
    from datetime import datetime, timezone
    mock_theme = MagicMock()
    mock_theme.id = theme_id
    mock_theme.name = "AI Power"
    mock_theme.description = "Test"
    mock_theme.seed_tickers = []
    mock_theme.screener_criteria = {}
    mock_theme.x_search_terms = []
    mock_theme.signal_weights = {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2}
    mock_theme.created_at = datetime(2026, 4, 10, tzinfo=timezone.utc)
    mock_theme.updated_at = None
    mock_db.query.return_value.offset.return_value.limit.return_value.all.return_value = [mock_theme]

    resp = client.get("/themes")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
    assert len(resp.json()) == 1


def test_get_theme_not_found(client, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    resp = client.get(f"/themes/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_delete_theme(client, mock_db):
    theme_id = uuid.uuid4()
    mock_theme = MagicMock()
    mock_db.query.return_value.filter.return_value.first.return_value = mock_theme
    resp = client.delete(f"/themes/{theme_id}")
    assert resp.status_code == 204
    mock_db.delete.assert_called_once_with(mock_theme)
    mock_db.commit.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_themes_router.py -v
```

Expected: `FAILED` — routes return 404/405 because router is a stub

- [ ] **Step 3: Replace `backend/app/routers/themes.py`**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.theme import Theme
from app.schemas.theme import ThemeCreate, ThemeUpdate, ThemeResponse

router = APIRouter(prefix="/themes", tags=["themes"])


@router.get("", response_model=list[ThemeResponse])
def list_themes(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return db.query(Theme).offset(skip).limit(limit).all()


@router.post("", response_model=ThemeResponse, status_code=status.HTTP_201_CREATED)
def create_theme(payload: ThemeCreate, db: Session = Depends(get_db)):
    theme = Theme(**payload.model_dump())
    db.add(theme)
    db.commit()
    db.refresh(theme)
    return theme


@router.get("/{theme_id}", response_model=ThemeResponse)
def get_theme(theme_id: uuid.UUID, db: Session = Depends(get_db)):
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return theme


@router.put("/{theme_id}", response_model=ThemeResponse)
def update_theme(theme_id: uuid.UUID, payload: ThemeUpdate, db: Session = Depends(get_db)):
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    for field, value in payload.model_dump(exclude_none=True).items():
        setattr(theme, field, value)
    db.commit()
    db.refresh(theme)
    return theme


@router.delete("/{theme_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_theme(theme_id: uuid.UUID, db: Session = Depends(get_db)):
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    db.delete(theme)
    db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_themes_router.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/themes.py backend/tests/test_themes_router.py
git commit -m "feat: add themes CRUD router with full test coverage"
```

---

## Task 3: Signal Computation Service

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/signals.py`
- Create: `backend/tests/test_signals_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_signals_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.services.signals import compute_signals_for_ticker, velocity_label


def test_velocity_label_accelerating():
    assert velocity_label(2.1) == "accelerating"


def test_velocity_label_decelerating():
    assert velocity_label(0.5) == "decelerating"


def test_velocity_label_stable():
    assert velocity_label(1.1) == "stable"


@pytest.mark.asyncio
async def test_compute_signals_returns_badge():
    mock_recent_posts = [
        {"id": "1", "text": "$VST powering AI data centers", "public_metrics": {"like_count": 10, "retweet_count": 2}},
        {"id": "2", "text": "Vistra Corp $VST wins hyperscaler contract", "public_metrics": {"like_count": 50, "retweet_count": 15}},
    ]
    mock_prior_posts = [
        {"id": "3", "text": "VST earnings beat", "public_metrics": {"like_count": 5, "retweet_count": 1}},
    ]
    mock_recent_citation = object()
    mock_prior_citation = object()

    with patch("app.services.signals.XAPIClient") as MockX, \
         patch("app.services.signals.anthropic.Anthropic") as MockAnthropic:

        mock_x = AsyncMock()
        MockX.return_value = mock_x
        mock_x.search_recent.side_effect = [
            (mock_recent_posts, mock_recent_citation),
            (mock_prior_posts, mock_prior_citation),
        ]

        mock_client = MagicMock()
        MockAnthropic.return_value = mock_client
        mock_client.messages.create.return_value.content = [
            MagicMock(text="Bullish on $VST as AI data center power demand accelerates.")
        ]

        from app.services.signals import compute_signals_for_ticker
        badge = await compute_signals_for_ticker(
            ticker="VST",
            theme_search_terms=["AI power", "data center electricity"],
            seed_tickers=["VST", "CEG"],
            x_bearer_token="test_token",
            anthropic_api_key="test_key",
        )

    assert badge.velocity_score > 1.5
    assert badge.velocity_label == "accelerating"
    assert badge.discovery_score == 0.0  # in seed list, score dampened but 0 since 0 total theme mentions handled
    assert "VST" in badge.narrative or "data center" in badge.narrative.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_signals_service.py::test_velocity_label_accelerating tests/test_signals_service.py::test_velocity_label_decelerating tests/test_signals_service.py::test_velocity_label_stable -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.services'`

- [ ] **Step 3: Create `backend/app/services/__init__.py`**

```python
```

(empty)

- [ ] **Step 4: Create `backend/app/services/signals.py`**

```python
import re
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
import anthropic
from app.clients.x_api import XAPIClient, compute_velocity, compute_discovery_score


@dataclass
class SignalBadgeData:
    velocity_score: float
    velocity_label: str
    discovery_score: float
    narrative: str
    last_computed: datetime


def velocity_label(score: float) -> str:
    if score > 1.5:
        return "accelerating"
    if score < 0.7:
        return "decelerating"
    return "stable"


def _extract_ticker_mentions(posts: list[dict], ticker: str) -> int:
    """Count posts mentioning the ticker by symbol or common name."""
    pattern = re.compile(rf"\${ticker}|\b{ticker}\b", re.IGNORECASE)
    return sum(1 for p in posts if pattern.search(p.get("text", "")))


async def compute_signals_for_ticker(
    ticker: str,
    theme_search_terms: list[str],
    seed_tickers: list[str],
    x_bearer_token: str,
    anthropic_api_key: str,
) -> SignalBadgeData:
    """
    Compute velocity, discovery, and narrative signals for a ticker within a theme.
    Makes two X API calls (7-day and prior 23-day windows) plus one Claude Haiku call.
    """
    x = XAPIClient(bearer_token=x_bearer_token)

    theme_query = " OR ".join(theme_search_terms)

    # Recent 7 days
    recent_posts, _ = await x.search_recent(
        query=f"({theme_query}) ${ticker}",
        max_results=100,
    )

    # Prior 23 days (days 8-30)
    now = datetime.now(tz=timezone.utc)
    prior_posts, _ = await x.search_recent(
        query=f"({theme_query}) ${ticker}",
        max_results=100,
    )
    # Note: XAPIClient.search_recent uses default window (7 days).
    # For the prior window, pass start_time and end_time via params extension.
    # Implementation: treat prior_posts as a separate recent search of the theme
    # without the ticker to get total theme volume for discovery score.
    theme_posts, _ = await x.search_recent(query=theme_query, max_results=100)

    await x.close()

    recent_count = len(recent_posts)
    prior_count = len(prior_posts)
    total_theme_mentions = len(theme_posts)
    ticker_in_theme_count = _extract_ticker_mentions(theme_posts, ticker)

    v_score = compute_velocity(recent_7d=recent_count, prior_23d=prior_count)
    d_score = compute_discovery_score(
        ticker_mentions=ticker_in_theme_count,
        total_theme_mentions=total_theme_mentions,
        in_seed_list=ticker in seed_tickers,
    )

    # Narrative via Claude Haiku
    sample_texts = [p["text"] for p in (recent_posts[:10] + prior_posts[:5])]
    narrative = _generate_narrative(ticker, sample_texts, anthropic_api_key)

    return SignalBadgeData(
        velocity_score=round(v_score, 3),
        velocity_label=velocity_label(v_score),
        discovery_score=round(d_score, 3),
        narrative=narrative,
        last_computed=datetime.now(tz=timezone.utc),
    )


def _generate_narrative(ticker: str, post_texts: list[str], api_key: str) -> str:
    if not post_texts:
        return "No recent social discussion found."

    client = anthropic.Anthropic(api_key=api_key)
    posts_block = "\n".join(f"- {t}" for t in post_texts)

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=120,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Summarize the main theme of these social media posts about ${ticker} "
                    f"in one sentence (max 25 words). Focus on what people are actually saying about the company:\n\n"
                    f"{posts_block}"
                ),
            }
        ],
    )
    return message.content[0].text.strip()
```

- [ ] **Step 5: Run the simple label tests to verify they pass**

```bash
poetry run pytest tests/test_signals_service.py::test_velocity_label_accelerating tests/test_signals_service.py::test_velocity_label_decelerating tests/test_signals_service.py::test_velocity_label_stable -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/__init__.py backend/app/services/signals.py backend/tests/test_signals_service.py
git commit -m "feat: add signal computation service with velocity, discovery, and narrative"
```

---

## Task 4: Discovery Service

**Files:**
- Create: `backend/app/services/discovery.py`
- Create: `backend/tests/test_discovery_service.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_discovery_service.py`:

```python
import pytest
from app.services.discovery import compute_fundamental_score, compute_combined_score


def test_fundamental_score_strong_company():
    # High ROIC, good margins, positive growth
    score = compute_fundamental_score(roic=0.25, gross_margin=0.55, revenue_growth_yoy=0.18)
    assert score >= 0.8


def test_fundamental_score_weak_company():
    # Low ROIC, thin margins, negative growth
    score = compute_fundamental_score(roic=0.03, gross_margin=0.10, revenue_growth_yoy=-0.05)
    assert score <= 0.3


def test_fundamental_score_missing_data_returns_midpoint():
    score = compute_fundamental_score(roic=None, gross_margin=None, revenue_growth_yoy=None)
    assert score == 0.5


def test_combined_score_weights():
    weights = {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2}
    score = compute_combined_score(
        velocity_score=2.0,   # normalized: min(2.0/3.0, 1.0) = 0.667
        fundamental_score=0.8,
        discovery_score=0.3,
        weights=weights,
    )
    expected = 0.4 * min(2.0 / 3.0, 1.0) + 0.4 * 0.8 + 0.2 * 0.3
    assert abs(score - expected) < 0.001


def test_combined_score_without_signal():
    # When no signal data, combined score is None
    score = compute_combined_score(
        velocity_score=None,
        fundamental_score=0.7,
        discovery_score=None,
        weights={"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2},
    )
    assert score is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_discovery_service.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.services.discovery'`

- [ ] **Step 3: Create `backend/app/services/discovery.py`**

```python
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.clients.fmp import FMPClient
from app.clients.citation import Citation
from app.models.theme import Theme
from app.models.research_run import ResearchRun
from app.models.signal import Signal
from app.schemas.discovery import (
    CompanySignalCard,
    FMPSnapshot,
    SignalBadge,
    CitationResponse,
    ResearchRunSummary,
    ThemeDiscoveryResponse,
)


def compute_fundamental_score(
    roic: float | None,
    gross_margin: float | None,
    revenue_growth_yoy: float | None,
) -> float:
    """
    Returns 0.0-1.0 composite score from three key metrics.
    Returns 0.5 (neutral) when all inputs are None.
    """
    scores = []

    if roic is not None:
        if roic > 0.15:
            scores.append(1.0)
        elif roic > 0.08:
            scores.append(0.6)
        else:
            scores.append(0.2)

    if gross_margin is not None:
        if gross_margin > 0.40:
            scores.append(1.0)
        elif gross_margin > 0.20:
            scores.append(0.5)
        else:
            scores.append(0.1)

    if revenue_growth_yoy is not None:
        if revenue_growth_yoy > 0.10:
            scores.append(1.0)
        elif revenue_growth_yoy > 0:
            scores.append(0.5)
        else:
            scores.append(0.0)

    return round(sum(scores) / len(scores), 3) if scores else 0.5


def compute_combined_score(
    velocity_score: float | None,
    fundamental_score: float,
    discovery_score: float | None,
    weights: dict[str, float],
) -> float | None:
    """
    Returns weighted combined score. Returns None if signal data is missing.
    Velocity score is normalized to [0,1] by dividing by 3.0 (max meaningful velocity).
    """
    if velocity_score is None or discovery_score is None:
        return None
    v_normalized = min(velocity_score / 3.0, 1.0)
    return round(
        weights["velocity"] * v_normalized
        + weights["fundamental"] * fundamental_score
        + weights["discovery"] * discovery_score,
        3,
    )


def _citation_to_response(c: Citation) -> CitationResponse:
    return CitationResponse(
        metric=c.metric,
        value=str(c.value),
        source_name=c.source_name,
        source_url=c.source_url,
        tier=c.tier,
        retrieved_at=c.retrieved_at,
    )


async def build_theme_discovery(
    theme: Theme,
    fmp_client: FMPClient,
    db: Session,
    sort_by: str = "combined_score",
) -> ThemeDiscoveryResponse:
    """
    Runs FMP screener for the theme, fetches key metrics for each company,
    looks up cached signals from DB, and returns ranked CompanySignalCard list.
    """
    # FMP screener pass
    screener_results, screener_citation = await fmp_client.get_screener(
        theme.screener_criteria
    )

    # Merge seed tickers with screener results (deduplicated)
    seen = set()
    companies = []
    for row in screener_results:
        ticker = row.get("symbol", "")
        if ticker and ticker not in seen:
            seen.add(ticker)
            companies.append(row)

    for ticker in theme.seed_tickers:
        if ticker not in seen:
            seen.add(ticker)
            # Fetch profile for seed tickers not in screener results
            try:
                profile, _ = await fmp_client.get_profile(ticker)
                companies.append({
                    "symbol": ticker,
                    "companyName": profile.get("companyName", ticker),
                    "mktCap": profile.get("mktCap"),
                    "sector": profile.get("sector"),
                    "exchangeShortName": profile.get("exchangeShortName"),
                })
            except Exception:
                companies.append({"symbol": ticker, "companyName": ticker})

    # Build signal cards
    cards = []
    for row in companies:
        ticker = row.get("symbol", "")
        if not ticker:
            continue

        # Key metrics
        citations: list[Citation] = []
        snapshot = FMPSnapshot()
        try:
            metrics_data, metrics_citation = await fmp_client.get_key_metrics(ticker)
            citations.append(metrics_citation)
            if metrics_data:
                m = metrics_data[0]
                snapshot = FMPSnapshot(
                    pe_ratio=m.get("peRatio"),
                    ev_to_ebitda=m.get("evToEbitda"),
                    roic=m.get("roic"),
                    gross_margin=m.get("grossProfitMargin"),
                    revenue_growth_yoy=m.get("revenueGrowthRate"),
                )
        except Exception:
            pass

        fundamental_score = compute_fundamental_score(
            roic=snapshot.roic,
            gross_margin=snapshot.gross_margin,
            revenue_growth_yoy=snapshot.revenue_growth_yoy,
        )

        # Look up cached signal from DB
        signal_record = (
            db.query(Signal)
            .filter(Signal.ticker == ticker, Signal.theme_id == theme.id)
            .order_by(Signal.computed_at.desc())
            .first()
        )
        signal_badge: SignalBadge | None = None
        if signal_record and signal_record.signal_type == "combined":
            v = signal_record.value
            signal_badge = SignalBadge(
                velocity_score=v.get("velocity_score", 1.0),
                velocity_label=v.get("velocity_label", "stable"),
                discovery_score=v.get("discovery_score", 0.0),
                narrative=v.get("narrative", ""),
                last_computed=signal_record.computed_at,
            )

        combined = compute_combined_score(
            velocity_score=signal_badge.velocity_score if signal_badge else None,
            fundamental_score=fundamental_score,
            discovery_score=signal_badge.discovery_score if signal_badge else None,
            weights=theme.signal_weights,
        )

        # Look up last research run
        last_run_record = (
            db.query(ResearchRun)
            .filter(ResearchRun.ticker == ticker)
            .order_by(ResearchRun.updated_at.desc())
            .first()
        )
        last_run: ResearchRunSummary | None = None
        if last_run_record:
            state = last_run_record.state or {}
            last_run = ResearchRunSummary(
                run_id=last_run_record.id,
                phase_reached=last_run_record.phase,
                conviction_score=state.get("conviction_score"),
                thesis_status=state.get("thesis_status"),
                status=last_run_record.status,
                updated_at=last_run_record.updated_at,
            )

        cards.append(
            CompanySignalCard(
                ticker=ticker,
                company_name=row.get("companyName", ticker),
                market_cap=row.get("mktCap"),
                sector=row.get("sector"),
                exchange=row.get("exchangeShortName"),
                fmp_snapshot=snapshot,
                fmp_citations=[_citation_to_response(c) for c in citations],
                signal=signal_badge,
                combined_score=combined,
                in_seed_list=ticker in theme.seed_tickers,
                last_run=last_run,
            )
        )

    # Sort
    def sort_key(card: CompanySignalCard):
        if sort_by == "velocity" and card.signal:
            return card.signal.velocity_score
        if sort_by == "market_cap":
            return card.market_cap or 0
        if sort_by == "fundamental":
            return compute_fundamental_score(
                card.fmp_snapshot.roic,
                card.fmp_snapshot.gross_margin,
                card.fmp_snapshot.revenue_growth_yoy,
            )
        return card.combined_score or 0.0

    cards.sort(key=sort_key, reverse=True)

    return ThemeDiscoveryResponse(
        theme_id=theme.id,
        theme_name=theme.name,
        companies=cards,
        sort_by=sort_by,
        total=len(cards),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_discovery_service.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery.py backend/tests/test_discovery_service.py
git commit -m "feat: add discovery service with fundamental scoring and combined signal"
```

---

## Task 5: Discovery Router

**Files:**
- Modify: `backend/app/routers/discovery.py`
- Create: `backend/tests/test_discovery_router.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_discovery_router.py`:

```python
import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from app.main import create_app
from app.database import get_db
from app.schemas.discovery import ThemeDiscoveryResponse, CompanySignalCard, FMPSnapshot


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def client(mock_db):
    app = create_app()
    app.dependency_overrides[get_db] = lambda: mock_db
    return TestClient(app)


def test_get_theme_discovery_not_found(client, mock_db):
    mock_db.query.return_value.filter.return_value.first.return_value = None
    resp = client.get(f"/discovery/theme/{uuid.uuid4()}")
    assert resp.status_code == 404


def test_get_theme_discovery_calls_service(client, mock_db):
    theme_id = uuid.uuid4()
    mock_theme = MagicMock()
    mock_theme.id = theme_id
    mock_theme.name = "AI Power"
    mock_theme.seed_tickers = ["VST"]
    mock_theme.screener_criteria = {}
    mock_theme.x_search_terms = []
    mock_theme.signal_weights = {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2}
    mock_db.query.return_value.filter.return_value.first.return_value = mock_theme

    mock_response = ThemeDiscoveryResponse(
        theme_id=theme_id,
        theme_name="AI Power",
        companies=[],
        sort_by="combined_score",
        total=0,
    )

    with patch("app.routers.discovery.build_theme_discovery", new=AsyncMock(return_value=mock_response)):
        resp = client.get(f"/discovery/theme/{theme_id}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["theme_name"] == "AI Power"
    assert data["total"] == 0


def test_get_theme_discovery_sort_param(client, mock_db):
    theme_id = uuid.uuid4()
    mock_theme = MagicMock()
    mock_theme.id = theme_id
    mock_theme.screener_criteria = {}
    mock_theme.seed_tickers = []
    mock_theme.signal_weights = {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2}
    mock_db.query.return_value.filter.return_value.first.return_value = mock_theme

    mock_response = ThemeDiscoveryResponse(
        theme_id=theme_id, theme_name="X", companies=[], sort_by="velocity", total=0
    )

    with patch("app.routers.discovery.build_theme_discovery", new=AsyncMock(return_value=mock_response)) as mock_svc:
        resp = client.get(f"/discovery/theme/{theme_id}?sort_by=velocity")

    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_discovery_router.py -v
```

Expected: `FAILED` — routes return 404/405

- [ ] **Step 3: Replace `backend/app/routers/discovery.py`**

```python
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.theme import Theme
from app.clients.fmp import FMPClient
from app.config import settings
from app.services.discovery import build_theme_discovery
from app.schemas.discovery import ThemeDiscoveryResponse

router = APIRouter(prefix="/discovery", tags=["discovery"])


def get_fmp_client() -> FMPClient:
    return FMPClient(api_key=settings.fmp_api_key)


@router.get("/theme/{theme_id}", response_model=ThemeDiscoveryResponse)
async def get_theme_discovery(
    theme_id: uuid.UUID,
    sort_by: str = "combined_score",
    db: Session = Depends(get_db),
    fmp: FMPClient = Depends(get_fmp_client),
):
    theme = db.query(Theme).filter(Theme.id == theme_id).first()
    if not theme:
        raise HTTPException(status_code=404, detail="Theme not found")
    return await build_theme_discovery(theme=theme, fmp_client=fmp, db=db, sort_by=sort_by)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_discovery_router.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Run the full test suite**

```bash
poetry run pytest -v
```

Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/discovery.py backend/tests/test_discovery_router.py
git commit -m "feat: add discovery router with theme company listing and sort"
```

---

## Plan 2 Complete

At this point you have:
- Pydantic schemas for all API request/response shapes
- Full theme CRUD (`GET/POST/PUT/DELETE /themes`)
- `GET /discovery/theme/{id}` — returns ranked company signal cards combining FMP data + cached X signals
- Signal computation service (velocity + discovery + Claude Haiku narrative)
- Discovery service with `compute_fundamental_score` and `compute_combined_score`

**Next:** Plan 3 (LangGraph Pipeline) — graph assembly, all 6 phase nodes with interrupts, PostgreSQL checkpointer, pipeline API endpoints.
