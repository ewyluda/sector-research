# Sector Research App — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a new repo with PostgreSQL schema, FMP client, X API client, and a running FastAPI server — all tested. This is the prerequisite for Plans 2–4.

**Architecture:** Monorepo with `backend/` (Python/FastAPI) and `frontend/` (Next.js) directories sharing a `docker-compose.yml`. Backend is structured as `app/clients/`, `app/models/`, `app/routers/`, `app/services/`, and `app/pipeline/`. Every data client method returns `(data, Citation)` — this is the citation contract all later plans depend on.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, httpx, cachetools, pydantic-settings, pytest, respx, Docker Compose, PostgreSQL 16

**Spec:** `docs/superpowers/specs/2026-04-10-sector-research-app-design.md`

---

## File Map

```
sector-research/                  ← new repo, create outside this vault
├── docker-compose.yml
├── .env.example
├── .env                          ← gitignored, copy from .env.example
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py               ← FastAPI app factory
│   │   ├── config.py             ← pydantic-settings Settings
│   │   ├── database.py           ← SQLAlchemy engine + get_db()
│   │   ├── clients/
│   │   │   ├── __init__.py
│   │   │   ├── citation.py       ← Citation dataclass
│   │   │   ├── fmp.py            ← FMP API client
│   │   │   └── x_api.py          ← X API client + signal computation
│   │   ├── models/
│   │   │   ├── __init__.py       ← imports all models (required by Alembic)
│   │   │   ├── theme.py
│   │   │   ├── research_run.py
│   │   │   ├── citation_record.py
│   │   │   ├── signal.py
│   │   │   └── watchlist.py
│   │   └── routers/
│   │       ├── __init__.py
│   │       ├── health.py         ← GET /health
│   │       ├── themes.py         ← stub, wired in Plan 2
│   │       ├── discovery.py      ← stub, wired in Plan 2
│   │       └── pipeline.py       ← stub, wired in Plan 3
│   └── tests/
│       ├── conftest.py
│       ├── test_citation.py
│       ├── test_fmp_client.py
│       └── test_x_client.py
└── frontend/
    └── (scaffolded in Plan 4)
```

---

## Task 1: Create Repo and Docker Compose

**Files:**
- Create: `sector-research/docker-compose.yml`
- Create: `sector-research/.env.example`
- Create: `sector-research/.gitignore`

- [ ] **Step 1: Create the repo directory and initialize git**

```bash
mkdir ~/Development/sector-research
cd ~/Development/sector-research
git init
```

- [ ] **Step 2: Create `.gitignore`**

```
.env
__pycache__/
*.pyc
.pytest_cache/
.venv/
dist/
.next/
node_modules/
*.egg-info/
```

- [ ] **Step 3: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: sector
      POSTGRES_PASSWORD: sector
      POSTGRES_DB: sector_research
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

- [ ] **Step 4: Create `.env.example`**

```
FMP_API_KEY=your_fmp_key_here
X_BEARER_TOKEN=your_x_bearer_token_here
ANTHROPIC_API_KEY=your_anthropic_key_here
DATABASE_URL=postgresql://sector:sector@localhost:5432/sector_research
```

- [ ] **Step 5: Copy `.env.example` to `.env` and fill in real keys**

```bash
cp .env.example .env
# Edit .env with your actual API keys
```

- [ ] **Step 6: Start the database**

```bash
docker compose up -d db
```

Expected: container `sector-research-db-1` running, port 5432 accessible.

- [ ] **Step 7: Verify database is reachable**

```bash
docker compose exec db psql -U sector -d sector_research -c "SELECT 1;"
```

Expected output: `?column? / ---------- / 1`

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml .env.example .gitignore
git commit -m "chore: add repo structure and docker compose for postgres"
```

---

## Task 2: Python Backend Setup

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Initialize Poetry project**

```bash
cd ~/Development/sector-research
mkdir backend && cd backend
poetry init --name sector-research-backend --python "^3.12" --no-interaction
```

- [ ] **Step 2: Add production dependencies**

```bash
poetry add fastapi "uvicorn[standard]" sqlalchemy alembic psycopg2-binary \
  httpx cachetools "pydantic-settings" anthropic langgraph langchain-anthropic
```

- [ ] **Step 3: Add development dependencies**

```bash
poetry add --group dev pytest pytest-asyncio respx httpx
```

- [ ] **Step 4: Create `backend/app/__init__.py`**

```python
```

(empty file — marks `app` as a package)

- [ ] **Step 5: Create `backend/tests/conftest.py`**

```python
# Fixtures are added in Task 9 once app.main exists.
# This file must exist for pytest to recognize the tests/ directory.
```

- [ ] **Step 6: Create `backend/pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 7: Commit**

```bash
cd ~/Development/sector-research
git add backend/
git commit -m "chore: python backend project setup with poetry"
```

---

## Task 3: Config and Database

**Files:**
- Create: `backend/app/config.py`
- Create: `backend/app/database.py`

- [ ] **Step 1: Create `backend/app/config.py`**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    fmp_api_key: str
    x_bearer_token: str
    anthropic_api_key: str
    database_url: str

    class Config:
        env_file = ".env"


settings = Settings()
```

- [ ] **Step 2: Create `backend/app/database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


engine = create_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py backend/app/database.py
git commit -m "feat: add config and database session setup"
```

---

## Task 4: Database Models

**Files:**
- Create: `backend/app/models/theme.py`
- Create: `backend/app/models/research_run.py`
- Create: `backend/app/models/citation_record.py`
- Create: `backend/app/models/signal.py`
- Create: `backend/app/models/watchlist.py`
- Create: `backend/app/models/__init__.py`

- [ ] **Step 1: Create `backend/app/models/theme.py`**

```python
import uuid
from sqlalchemy import Column, String, JSON, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Theme(Base):
    __tablename__ = "themes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    description = Column(String, nullable=False)
    seed_tickers = Column(JSON, nullable=False, default=list)
    screener_criteria = Column(JSON, nullable=False, default=dict)
    x_search_terms = Column(JSON, nullable=False, default=list)
    signal_weights = Column(
        JSON,
        nullable=False,
        default=lambda: {"velocity": 0.4, "fundamental": 0.4, "discovery": 0.2},
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

- [ ] **Step 2: Create `backend/app/models/research_run.py`**

```python
import uuid
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class ResearchRun(Base):
    __tablename__ = "research_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String, nullable=False, index=True)
    theme_id = Column(UUID(as_uuid=True), ForeignKey("themes.id"), nullable=True)
    phase = Column(String, nullable=False, default="quick_screen")
    # status: in_progress | complete | watchlist | pass
    status = Column(String, nullable=False, default="in_progress")
    state = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

- [ ] **Step 3: Create `backend/app/models/citation_record.py`**

```python
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class CitationRecord(Base):
    __tablename__ = "citations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id"), nullable=False, index=True)
    metric = Column(String, nullable=False)
    value = Column(String, nullable=False)
    source_name = Column(String, nullable=False)
    source_url = Column(String, nullable=False)
    tier = Column(Integer, nullable=False)
    retrieved_at = Column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Create `backend/app/models/signal.py`**

```python
import uuid
from sqlalchemy import Column, String, JSON, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Signal(Base):
    __tablename__ = "signals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String, nullable=False, index=True)
    theme_id = Column(UUID(as_uuid=True), ForeignKey("themes.id"), nullable=False)
    # signal_type: velocity | discovery | narrative
    signal_type = Column(String, nullable=False)
    value = Column(JSON, nullable=False)
    computed_at = Column(DateTime(timezone=True), server_default=func.now())
```

- [ ] **Step 5: Create `backend/app/models/watchlist.py`**

```python
import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker = Column(String, nullable=False)
    theme_id = Column(UUID(as_uuid=True), ForeignKey("themes.id"), nullable=False)
    trigger_condition = Column(String, nullable=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())
    run_id = Column(UUID(as_uuid=True), ForeignKey("research_runs.id"), nullable=True)
```

- [ ] **Step 6: Create `backend/app/models/__init__.py`**

```python
# Import all models so Alembic can detect them via Base.metadata
from app.models.theme import Theme
from app.models.research_run import ResearchRun
from app.models.citation_record import CitationRecord
from app.models.signal import Signal
from app.models.watchlist import Watchlist

__all__ = ["Theme", "ResearchRun", "CitationRecord", "Signal", "Watchlist"]
```

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/
git commit -m "feat: add sqlalchemy models for all five tables"
```

---

## Task 5: Alembic Migration

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0001_initial_schema.py`

- [ ] **Step 1: Initialize Alembic inside `backend/`**

```bash
cd ~/Development/sector-research/backend
poetry run alembic init alembic
```

- [ ] **Step 2: Edit `backend/alembic/env.py`** — replace the `target_metadata` section

Find the line `target_metadata = None` and replace it with:

```python
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.database import Base
from app.config import settings
import app.models  # noqa: F401 — registers all models with Base.metadata

target_metadata = Base.metadata

# Also update the sqlalchemy.url to use settings:
# In the run_migrations_online() function, replace engine creation with:
# connectable = create_engine(settings.database_url)
```

Full `run_migrations_online` block to use (replace existing):

```python
def run_migrations_online() -> None:
    from sqlalchemy import create_engine
    connectable = create_engine(settings.database_url)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
```

- [ ] **Step 3: Generate the initial migration**

```bash
cd ~/Development/sector-research/backend
poetry run alembic revision --autogenerate -m "initial_schema"
```

Expected: a new file created at `alembic/versions/<hash>_initial_schema.py` containing `CreateTable` for all five tables.

- [ ] **Step 4: Apply the migration**

```bash
poetry run alembic upgrade head
```

Expected output ends with: `Running upgrade  -> <hash>, initial_schema`

- [ ] **Step 5: Verify tables exist**

```bash
docker compose exec db psql -U sector -d sector_research -c "\dt"
```

Expected: `themes`, `research_runs`, `citations`, `signals`, `watchlist` all listed.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic.ini backend/alembic/
git commit -m "feat: add alembic migration for initial schema"
```

---

## Task 6: Citation Dataclass

**Files:**
- Create: `backend/app/clients/citation.py`
- Create: `backend/app/clients/__init__.py`
- Create: `backend/tests/test_citation.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_citation.py`:

```python
from datetime import datetime, timezone
from app.clients.citation import Citation


def test_citation_to_dict_serializes_datetime():
    c = Citation(
        value=15.3,
        metric="P/E Ratio",
        source_name="FMP /key-metrics/AAPL",
        source_url="https://financialmodelingprep.com/api/v3/key-metrics/AAPL",
        tier=1,
        retrieved_at=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
    )
    d = c.to_dict()
    assert d["value"] == 15.3
    assert d["metric"] == "P/E Ratio"
    assert d["tier"] == 1
    assert d["retrieved_at"] == "2026-04-10T12:00:00+00:00"


def test_citation_tier2_label():
    c = Citation(
        value="Bullish",
        metric="X Narrative",
        source_name="X API search",
        source_url="https://api.twitter.com/2/tweets/search/recent?query=%24AAPL",
        tier=2,
        retrieved_at=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert c.tier == 2
    assert c.is_qualitative() is True


def test_citation_tier1_is_not_qualitative():
    c = Citation(
        value=100.0,
        metric="Revenue",
        source_name="FMP /income-statement/AAPL",
        source_url="https://financialmodelingprep.com/api/v3/income-statement/AAPL",
        tier=1,
        retrieved_at=datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc),
    )
    assert c.is_qualitative() is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/Development/sector-research/backend
poetry run pytest tests/test_citation.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.clients.citation'`

- [ ] **Step 3: Create `backend/app/clients/__init__.py`**

```python
```

(empty)

- [ ] **Step 4: Create `backend/app/clients/citation.py`**

```python
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class Citation:
    value: str | float
    metric: str
    source_name: str
    source_url: str
    tier: int  # 1 = Tier 1 authoritative, 2 = Tier 2 qualitative signal
    retrieved_at: datetime

    def to_dict(self) -> dict:
        d = asdict(self)
        d["retrieved_at"] = self.retrieved_at.isoformat()
        return d

    def is_qualitative(self) -> bool:
        return self.tier == 2
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
poetry run pytest tests/test_citation.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/app/clients/ backend/tests/test_citation.py
git commit -m "feat: add Citation dataclass with tier and serialization"
```

---

## Task 7: FMP Client

**Files:**
- Create: `backend/app/clients/fmp.py`
- Create: `backend/tests/test_fmp_client.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_fmp_client.py`:

```python
import pytest
import respx
import httpx
from datetime import datetime, timezone
from app.clients.fmp import FMPClient
from app.clients.citation import Citation

BASE = "https://financialmodelingprep.com/api"


@pytest.fixture
def client():
    return FMPClient(api_key="test_key")


@pytest.mark.asyncio
async def test_get_profile_returns_data_and_citation(client):
    with respx.mock:
        respx.get(f"{BASE}/v3/profile/AAPL").mock(
            return_value=httpx.Response(200, json=[{
                "symbol": "AAPL",
                "companyName": "Apple Inc.",
                "mktCap": 3_000_000_000_000,
                "sector": "Technology",
                "industry": "Consumer Electronics",
                "exchange": "NASDAQ",
            }])
        )
        data, citation = await client.get_profile("AAPL")

    assert data["symbol"] == "AAPL"
    assert data["companyName"] == "Apple Inc."
    assert isinstance(citation, Citation)
    assert citation.tier == 1
    assert citation.metric == "Company Profile"
    assert "AAPL" in citation.source_url


@pytest.mark.asyncio
async def test_get_key_metrics_returns_data_and_citation(client):
    with respx.mock:
        respx.get(f"{BASE}/v3/key-metrics/AAPL").mock(
            return_value=httpx.Response(200, json=[{
                "symbol": "AAPL",
                "date": "2024-09-28",
                "peRatio": 34.5,
                "evToEbitda": 25.1,
                "priceToSalesRatio": 8.2,
                "roic": 0.58,
                "debtToEquity": 1.87,
            }])
        )
        data, citation = await client.get_key_metrics("AAPL")

    assert data[0]["peRatio"] == 34.5
    assert citation.tier == 1
    assert citation.metric == "Key Metrics"


@pytest.mark.asyncio
async def test_get_income_statement_returns_list(client):
    with respx.mock:
        respx.get(f"{BASE}/v3/income-statement/AAPL").mock(
            return_value=httpx.Response(200, json=[
                {"date": "2024-09-28", "revenue": 391_035_000_000, "grossProfit": 180_683_000_000},
                {"date": "2023-09-30", "revenue": 383_285_000_000, "grossProfit": 169_148_000_000},
            ])
        )
        data, citation = await client.get_income_statement("AAPL", years=2)

    assert len(data) == 2
    assert data[0]["revenue"] == 391_035_000_000
    assert citation.metric == "Income Statement"


@pytest.mark.asyncio
async def test_get_screener_returns_list(client):
    with respx.mock:
        respx.get(f"{BASE}/v3/stock-screener").mock(
            return_value=httpx.Response(200, json=[
                {"symbol": "VST", "companyName": "Vistra Corp", "marketCap": 30_000_000_000, "sector": "Utilities"},
                {"symbol": "CEG", "companyName": "Constellation Energy", "marketCap": 60_000_000_000, "sector": "Utilities"},
            ])
        )
        data, citation = await client.get_screener({"sector": "Utilities", "marketCapMoreThan": 1_000_000_000})

    assert len(data) == 2
    assert data[0]["symbol"] == "VST"
    assert citation.metric == "Stock Screener"
    assert citation.tier == 1


@pytest.mark.asyncio
async def test_fmp_client_raises_on_api_error(client):
    with respx.mock:
        respx.get(f"{BASE}/v3/profile/INVALID").mock(
            return_value=httpx.Response(401, json={"Error Message": "Invalid API KEY."})
        )
        with pytest.raises(ValueError, match="FMP API error"):
            await client.get_profile("INVALID")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_fmp_client.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.clients.fmp'`

- [ ] **Step 3: Create `backend/app/clients/fmp.py`**

```python
import httpx
from datetime import datetime, timezone
from typing import Any
from cachetools import TTLCache
from app.clients.citation import Citation

BASE_URL = "https://financialmodelingprep.com/api"

# TTL caches keyed by (method_name, ticker)
_profile_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)      # 24hr
_metrics_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)      # 24hr
_income_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)       # 24hr
_balance_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)      # 24hr
_cashflow_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)     # 24hr
_dcf_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)          # 24hr
_screener_cache: TTLCache = TTLCache(maxsize=100, ttl=300)       # 5min
_options_cache: TTLCache = TTLCache(maxsize=500, ttl=900)        # 15min
_transcript_cache: TTLCache = TTLCache(maxsize=200, ttl=604800)  # 7 days
_estimates_cache: TTLCache = TTLCache(maxsize=500, ttl=86400)    # 24hr


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _cite(metric: str, path: str, tier: int = 1, value: str = "") -> Citation:
    return Citation(
        value=value,
        metric=metric,
        source_name=f"FMP {path}",
        source_url=f"{BASE_URL}{path}",
        tier=tier,
        retrieved_at=_now(),
    )


class FMPClient:
    def __init__(self, api_key: str):
        self._key = api_key
        self._http = httpx.AsyncClient(base_url=BASE_URL, timeout=30.0)

    async def _get(self, path: str, params: dict | None = None) -> Any:
        p = {"apikey": self._key, **(params or {})}
        resp = await self._http.get(path, params=p)
        if resp.status_code != 200:
            raise ValueError(f"FMP API error {resp.status_code}: {resp.text}")
        return resp.json()

    async def get_profile(self, ticker: str) -> tuple[dict, Citation]:
        if ticker not in _profile_cache:
            path = f"/v3/profile/{ticker}"
            data = await self._get(path)
            _profile_cache[ticker] = data[0] if data else {}
        return _profile_cache[ticker], _cite("Company Profile", f"/v3/profile/{ticker}")

    async def get_key_metrics(self, ticker: str) -> tuple[list, Citation]:
        if ticker not in _metrics_cache:
            path = f"/v3/key-metrics/{ticker}"
            data = await self._get(path, {"period": "annual"})
            _metrics_cache[ticker] = data
        return _metrics_cache[ticker], _cite("Key Metrics", f"/v3/key-metrics/{ticker}")

    async def get_income_statement(self, ticker: str, years: int = 3) -> tuple[list, Citation]:
        key = (ticker, years)
        if key not in _income_cache:
            path = f"/v3/income-statement/{ticker}"
            data = await self._get(path, {"limit": years * 4, "period": "annual"})
            _income_cache[key] = data
        return _income_cache[key], _cite("Income Statement", f"/v3/income-statement/{ticker}")

    async def get_balance_sheet(self, ticker: str, years: int = 3) -> tuple[list, Citation]:
        key = (ticker, years)
        if key not in _balance_cache:
            path = f"/v3/balance-sheet-statement/{ticker}"
            data = await self._get(path, {"limit": years * 4, "period": "annual"})
            _balance_cache[key] = data
        return _balance_cache[key], _cite("Balance Sheet", f"/v3/balance-sheet-statement/{ticker}")

    async def get_cash_flow(self, ticker: str, years: int = 3) -> tuple[list, Citation]:
        key = (ticker, years)
        if key not in _cashflow_cache:
            path = f"/v3/cash-flow-statement/{ticker}"
            data = await self._get(path, {"limit": years * 4, "period": "annual"})
            _cashflow_cache[key] = data
        return _cashflow_cache[key], _cite("Cash Flow Statement", f"/v3/cash-flow-statement/{ticker}")

    async def get_dcf(self, ticker: str) -> tuple[dict, Citation]:
        if ticker not in _dcf_cache:
            path = f"/v3/discounted-cash-flow/{ticker}"
            data = await self._get(path)
            _dcf_cache[ticker] = data[0] if isinstance(data, list) and data else data
        return _dcf_cache[ticker], _cite("DCF Valuation", f"/v3/discounted-cash-flow/{ticker}")

    async def get_screener(self, criteria: dict) -> tuple[list, Citation]:
        cache_key = str(sorted(criteria.items()))
        if cache_key not in _screener_cache:
            path = "/v3/stock-screener"
            data = await self._get(path, criteria)
            _screener_cache[cache_key] = data
        return _screener_cache[cache_key], _cite("Stock Screener", "/v3/stock-screener")

    async def get_options_flow(self, ticker: str) -> tuple[list, Citation]:
        if ticker not in _options_cache:
            path = f"/v4/unusual-activity/{ticker}"
            data = await self._get(path)
            _options_cache[ticker] = data
        return _options_cache[ticker], _cite("Options Flow", f"/v4/unusual-activity/{ticker}")

    async def get_earnings_transcript(
        self, ticker: str, year: int, quarter: int
    ) -> tuple[list, Citation]:
        key = (ticker, year, quarter)
        if key not in _transcript_cache:
            path = f"/v3/earning_call_transcript/{ticker}"
            data = await self._get(path, {"year": year, "quarter": quarter})
            _transcript_cache[key] = data
        return (
            _transcript_cache[key],
            _cite("Earnings Transcript", f"/v3/earning_call_transcript/{ticker}"),
        )

    async def get_analyst_estimates(self, ticker: str) -> tuple[list, Citation]:
        if ticker not in _estimates_cache:
            path = f"/v3/analyst-estimates/{ticker}"
            data = await self._get(path)
            _estimates_cache[ticker] = data
        return _estimates_cache[ticker], _cite("Analyst Estimates", f"/v3/analyst-estimates/{ticker}")

    async def close(self):
        await self._http.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_fmp_client.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/fmp.py backend/tests/test_fmp_client.py
git commit -m "feat: add FMP client with TTL caching and citation on every method"
```

---

## Task 8: X API Client

**Files:**
- Create: `backend/app/clients/x_api.py`
- Create: `backend/tests/test_x_client.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_x_client.py`:

```python
import pytest
import respx
import httpx
from app.clients.x_api import XAPIClient, compute_velocity, compute_discovery_score

BASE = "https://api.twitter.com/2"


@pytest.fixture
def client():
    return XAPIClient(bearer_token="test_token")


@pytest.mark.asyncio
async def test_search_recent_returns_posts(client):
    with respx.mock:
        respx.get(f"{BASE}/tweets/search/recent").mock(
            return_value=httpx.Response(200, json={
                "data": [
                    {"id": "1", "text": "$VST Vistra crushing it on data center demand", "created_at": "2026-04-10T10:00:00Z", "public_metrics": {"like_count": 42, "retweet_count": 12}},
                    {"id": "2", "text": "Vistra Corp $VST is the AI power play nobody talks about", "created_at": "2026-04-10T09:00:00Z", "public_metrics": {"like_count": 18, "retweet_count": 4}},
                ],
                "meta": {"newest_id": "2", "oldest_id": "1", "result_count": 2}
            })
        )
        posts, citation = await client.search_recent("$VST Vistra", max_results=10)

    assert len(posts) == 2
    assert posts[0]["id"] == "1"
    assert citation.tier == 2
    assert citation.metric == "X Search Results"
    assert "$VST Vistra" in citation.source_url


def test_compute_velocity_accelerating():
    # 50 mentions in last 7 days vs 10 in prior 23 days (normalized to 7-day rate: 10/23*7 ≈ 3.0)
    score = compute_velocity(recent_7d=50, prior_23d=10)
    assert score > 1.5  # accelerating threshold


def test_compute_velocity_decelerating():
    score = compute_velocity(recent_7d=5, prior_23d=100)
    assert score < 0.7  # decelerating threshold


def test_compute_velocity_stable():
    score = compute_velocity(recent_7d=30, prior_23d=90)  # 30 vs 30 normalized
    assert 0.7 <= score <= 1.5


def test_compute_discovery_score_boosts_unknown_tickers():
    # ticker mentioned 20 times in theme search of 100 total, not in seed list
    score = compute_discovery_score(ticker_mentions=20, total_theme_mentions=100, in_seed_list=False)
    assert score == pytest.approx(0.20 * 1.5, rel=1e-3)


def test_compute_discovery_score_no_boost_for_known_tickers():
    score = compute_discovery_score(ticker_mentions=20, total_theme_mentions=100, in_seed_list=True)
    assert score == pytest.approx(0.20 * 1.0, rel=1e-3)


def test_compute_discovery_score_zero_total_returns_zero():
    score = compute_discovery_score(ticker_mentions=0, total_theme_mentions=0, in_seed_list=False)
    assert score == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
poetry run pytest tests/test_x_client.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.clients.x_api'`

- [ ] **Step 3: Create `backend/app/clients/x_api.py`**

```python
import httpx
import time
from datetime import datetime, timezone
from app.clients.citation import Citation

BASE_URL = "https://api.twitter.com/2"


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def compute_velocity(recent_7d: int, prior_23d: int) -> float:
    """
    Returns ratio of recent mention rate to prior mention rate.
    recent_7d: mentions in last 7 days
    prior_23d: mentions in days 8-30 (23-day window)
    > 1.5 = accelerating, < 0.7 = decelerating, else stable
    """
    if prior_23d == 0:
        return 2.0 if recent_7d > 0 else 1.0
    prior_7d_normalized = (prior_23d / 23) * 7
    if prior_7d_normalized == 0:
        return 2.0
    return recent_7d / prior_7d_normalized


def compute_discovery_score(
    ticker_mentions: int,
    total_theme_mentions: int,
    in_seed_list: bool,
) -> float:
    """
    Returns a score reflecting how prominent a ticker is in theme discussion
    relative to how known it already is to the user.
    Higher = more prominent in theme discussion AND less known to user.
    """
    if total_theme_mentions == 0:
        return 0.0
    base = ticker_mentions / total_theme_mentions
    multiplier = 1.0 if in_seed_list else 1.5
    return base * multiplier


class _TokenBucket:
    """Simple token bucket for rate limiting."""

    def __init__(self, rate: float, capacity: float):
        self._rate = rate  # tokens per second
        self._capacity = capacity
        self._tokens = capacity
        self._last = time.monotonic()

    def consume(self, tokens: float = 1.0) -> float:
        """Returns seconds to wait before consuming, 0 if immediately available."""
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last = now
        if self._tokens >= tokens:
            self._tokens -= tokens
            return 0.0
        wait = (tokens - self._tokens) / self._rate
        return wait


class XAPIClient:
    # X API v2: ~500 requests per 15 min window = ~0.55 req/sec
    _bucket = _TokenBucket(rate=0.5, capacity=10)

    def __init__(self, bearer_token: str):
        self._http = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={"Authorization": f"Bearer {bearer_token}"},
            timeout=30.0,
        )

    async def search_recent(
        self, query: str, max_results: int = 100
    ) -> tuple[list[dict], Citation]:
        """Search recent tweets. Returns (posts, Citation)."""
        import asyncio

        wait = self._bucket.consume()
        if wait > 0:
            await asyncio.sleep(wait)

        params = {
            "query": f"{query} -is:retweet lang:en",
            "max_results": min(max_results, 100),
            "tweet.fields": "created_at,public_metrics",
        }
        resp = await self._http.get("/tweets/search/recent", params=params)
        if resp.status_code != 200:
            raise ValueError(f"X API error {resp.status_code}: {resp.text}")

        body = resp.json()
        posts = body.get("data", [])
        encoded_query = query.replace(" ", "%20")
        citation = Citation(
            value=f"{len(posts)} posts",
            metric="X Search Results",
            source_name="X API v2 /tweets/search/recent",
            source_url=f"{BASE_URL}/tweets/search/recent?query={encoded_query}",
            tier=2,
            retrieved_at=_now(),
        )
        return posts, citation

    async def close(self):
        await self._http.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
poetry run pytest tests/test_x_client.py -v
```

Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/clients/x_api.py backend/tests/test_x_client.py
git commit -m "feat: add X API client with velocity and discovery score computation"
```

---

## Task 9: FastAPI App + Health Check

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/health.py`
- Create: `backend/app/routers/themes.py` (stub)
- Create: `backend/app/routers/discovery.py` (stub)
- Create: `backend/app/routers/pipeline.py` (stub)

- [ ] **Step 1: Write the failing test**

Replace `backend/tests/conftest.py` with real content:

```python
import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)
```

Create `backend/tests/test_health.py`:

```python
def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_cors_header_present(client):
    resp = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:3000"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
poetry run pytest tests/test_health.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.main'`

- [ ] **Step 3: Create `backend/app/routers/__init__.py`**

```python
```

(empty)

- [ ] **Step 4: Create `backend/app/routers/health.py`**

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: Create stub routers**

`backend/app/routers/themes.py`:
```python
from fastapi import APIRouter
router = APIRouter(prefix="/themes", tags=["themes"])
```

`backend/app/routers/discovery.py`:
```python
from fastapi import APIRouter
router = APIRouter(prefix="/discovery", tags=["discovery"])
```

`backend/app/routers/pipeline.py`:
```python
from fastapi import APIRouter
router = APIRouter(prefix="/pipeline", tags=["pipeline"])
```

- [ ] **Step 6: Create `backend/app/main.py`**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers.health import router as health_router
from app.routers.themes import router as themes_router
from app.routers.discovery import router as discovery_router
from app.routers.pipeline import router as pipeline_router


def create_app() -> FastAPI:
    app = FastAPI(title="Sector Research API", version="0.1.0")

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

- [ ] **Step 7: Run tests to verify they pass**

```bash
poetry run pytest tests/test_health.py -v
```

Expected: `2 passed`

- [ ] **Step 8: Run the full test suite to verify nothing broke**

```bash
poetry run pytest -v
```

Expected: all tests pass (citation + fmp + x + health)

- [ ] **Step 9: Start the server and verify it runs**

```bash
poetry run uvicorn app.main:create_app --factory --reload --port 8000
```

Open `http://localhost:8000/health` in browser.
Expected: `{"status":"ok"}`

Open `http://localhost:8000/docs` — FastAPI auto-docs should show all routers.

- [ ] **Step 10: Commit**

```bash
git add backend/app/main.py backend/app/routers/ backend/tests/test_health.py
git commit -m "feat: add fastapi app factory with health check and stub routers"
```

---

## Plan 1 Complete

At this point you have:
- PostgreSQL running with all 5 tables migrated
- `Citation` dataclass — the core contract for all data provenance
- `FMPClient` — all 9 data methods, TTL caching, every method returns `(data, Citation)`
- `XAPIClient` — search recent, velocity + discovery score computation, rate limiting
- FastAPI server running with CORS, health check, and stub routers for Plans 2–4
- Full test coverage on all clients

**Next:** Plan 2 (Discovery Engine) — theme CRUD endpoints, FMP screener pass, X signal computation and scheduling, combined signal scoring, company signal card API response shape.
