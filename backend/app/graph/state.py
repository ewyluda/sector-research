"""ResearchState — the single source of truth flowing through the LangGraph pipeline.

Persisted to PostgreSQL at every interrupt via research_runs.state (JSONB).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


# ── Category error / result types ────────────────────────────────────────────

@dataclass
class CategoryError:
    category: str
    reason: str
    traceback: str | None = None

    def to_dict(self) -> dict:
        return {"__type__": "CategoryError", "category": self.category,
                "reason": self.reason, "traceback": self.traceback}

    @classmethod
    def from_dict(cls, d: dict) -> "CategoryError":
        return cls(category=d["category"], reason=d["reason"], traceback=d.get("traceback"))


@dataclass
class CategoryResult:
    category: str
    content: str          # Markdown analysis output
    score: int            # 0–100 composite score for this category
    key_findings: list[str] = field(default_factory=list)
    structured: dict | None = None  # Parsed DeepDiveCategoryOutput.model_dump()

    def to_dict(self) -> dict:
        d = {"__type__": "CategoryResult", "category": self.category,
             "content": self.content, "score": self.score,
             "key_findings": self.key_findings}
        if self.structured is not None:
            d["structured"] = self.structured
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CategoryResult":
        return cls(category=d["category"], content=d["content"],
                   score=d["score"], key_findings=d.get("key_findings", []),
                   structured=d.get("structured"))


# ── Citation (portable version for state) ─────────────────────────────────────

@dataclass
class StateCitation:
    value: str
    metric: str
    source_name: str
    source_url: str
    tier: int
    retrieved_at: str  # ISO string for JSON serialisation

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_citation(cls, c: Any) -> "StateCitation":
        """Convert a models.citation.Citation to a state-safe version."""
        return cls(
            value=str(c.value),
            metric=c.metric,
            source_name=c.source_name,
            source_url=c.source_url,
            tier=c.tier,
            retrieved_at=c.retrieved_at.isoformat(),
        )


# ── Curated financials for frontend dashboard ────────────────────────────────

@dataclass
class QuarterlyMetric:
    period: str          # "Q3 2025"
    value: float
    yoy_growth: float | None = None

    def to_dict(self) -> dict:
        return {"period": self.period, "value": self.value, "yoy_growth": self.yoy_growth}

    @classmethod
    def from_dict(cls, d: dict) -> "QuarterlyMetric":
        return cls(period=d["period"], value=d["value"], yoy_growth=d.get("yoy_growth"))


@dataclass
class EstimateMetric:
    period: str          # "Q1 2026"
    estimate: float
    actual: float | None = None

    def to_dict(self) -> dict:
        return {"period": self.period, "estimate": self.estimate, "actual": self.actual}

    @classmethod
    def from_dict(cls, d: dict) -> "EstimateMetric":
        return cls(period=d["period"], estimate=d["estimate"], actual=d.get("actual"))


@dataclass
class CuratedFinancials:
    """Curated subset of FMP data for frontend charts. Built once per deep-dive run."""
    # Identity
    ticker: str
    company_name: str
    sector: str
    industry: str
    market_cap: float
    current_price: float

    # Income Statement (4 quarters, newest first)
    quarterly_revenue: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_eps: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_gross_margin: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_operating_margin: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_net_margin: list[QuarterlyMetric] = field(default_factory=list)

    # Balance Sheet (4 periods)
    quarterly_cash: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_total_debt: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_shareholders_equity: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_current_ratio: list[QuarterlyMetric] = field(default_factory=list)
    debt_to_equity: float = 0.0

    # Cash Flow (4 periods)
    quarterly_operating_cf: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_free_cf: list[QuarterlyMetric] = field(default_factory=list)
    quarterly_capex: list[QuarterlyMetric] = field(default_factory=list)

    # Valuation
    dcf_intrinsic_value: float | None = None
    dcf_gap_percent: float | None = None

    # Analyst Estimates (4 quarters forward)
    forward_revenue_estimates: list[EstimateMetric] = field(default_factory=list)
    forward_eps_estimates: list[EstimateMetric] = field(default_factory=list)

    # Technical
    beta: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    volume_avg: float | None = None
    # Technical — 1 year daily OHLCV + computed indicators (SMA, RSI)
    daily_prices: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "sector": self.sector,
            "industry": self.industry,
            "market_cap": self.market_cap,
            "current_price": self.current_price,
            "quarterly_revenue": [m.to_dict() for m in self.quarterly_revenue],
            "quarterly_eps": [m.to_dict() for m in self.quarterly_eps],
            "quarterly_gross_margin": [m.to_dict() for m in self.quarterly_gross_margin],
            "quarterly_operating_margin": [m.to_dict() for m in self.quarterly_operating_margin],
            "quarterly_net_margin": [m.to_dict() for m in self.quarterly_net_margin],
            "quarterly_cash": [m.to_dict() for m in self.quarterly_cash],
            "quarterly_total_debt": [m.to_dict() for m in self.quarterly_total_debt],
            "quarterly_shareholders_equity": [m.to_dict() for m in self.quarterly_shareholders_equity],
            "quarterly_current_ratio": [m.to_dict() for m in self.quarterly_current_ratio],
            "debt_to_equity": self.debt_to_equity,
            "quarterly_operating_cf": [m.to_dict() for m in self.quarterly_operating_cf],
            "quarterly_free_cf": [m.to_dict() for m in self.quarterly_free_cf],
            "quarterly_capex": [m.to_dict() for m in self.quarterly_capex],
            "dcf_intrinsic_value": self.dcf_intrinsic_value,
            "dcf_gap_percent": self.dcf_gap_percent,
            "forward_revenue_estimates": [m.to_dict() for m in self.forward_revenue_estimates],
            "forward_eps_estimates": [m.to_dict() for m in self.forward_eps_estimates],
            "beta": self.beta,
            "fifty_two_week_high": self.fifty_two_week_high,
            "fifty_two_week_low": self.fifty_two_week_low,
            "volume_avg": self.volume_avg,
            "daily_prices": self.daily_prices,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "CuratedFinancials":
        return cls(
            ticker=d["ticker"],
            company_name=d["company_name"],
            sector=d.get("sector", ""),
            industry=d.get("industry", ""),
            market_cap=d.get("market_cap", 0),
            current_price=d.get("current_price", 0),
            quarterly_revenue=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_revenue", [])],
            quarterly_eps=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_eps", [])],
            quarterly_gross_margin=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_gross_margin", [])],
            quarterly_operating_margin=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_operating_margin", [])],
            quarterly_net_margin=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_net_margin", [])],
            quarterly_cash=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_cash", [])],
            quarterly_total_debt=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_total_debt", [])],
            quarterly_shareholders_equity=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_shareholders_equity", [])],
            quarterly_current_ratio=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_current_ratio", [])],
            debt_to_equity=d.get("debt_to_equity", 0.0),
            quarterly_operating_cf=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_operating_cf", [])],
            quarterly_free_cf=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_free_cf", [])],
            quarterly_capex=[QuarterlyMetric.from_dict(m) for m in d.get("quarterly_capex", [])],
            dcf_intrinsic_value=d.get("dcf_intrinsic_value"),
            dcf_gap_percent=d.get("dcf_gap_percent"),
            forward_revenue_estimates=[EstimateMetric.from_dict(m) for m in d.get("forward_revenue_estimates", [])],
            forward_eps_estimates=[EstimateMetric.from_dict(m) for m in d.get("forward_eps_estimates", [])],
            beta=d.get("beta"),
            fifty_two_week_high=d.get("fifty_two_week_high"),
            fifty_two_week_low=d.get("fifty_two_week_low"),
            volume_avg=d.get("volume_avg"),
            daily_prices=d.get("daily_prices", []),
        )


# ── Main state ────────────────────────────────────────────────────────────────

@dataclass
class ResearchState:
    # Identity
    ticker: str
    theme_id: str
    run_id: str

    # Pipeline position
    phase: str = "quick_screen"
    status: str = "in_progress"  # in_progress | awaiting_approval | completed | watchlist | pass

    # Accumulated outputs keyed by phase/category name
    # Values are dicts (CategoryResult.to_dict() or CategoryError.to_dict())
    phase_outputs: dict[str, Any] = field(default_factory=dict)

    # Scores per category (0–100)
    scores: dict[str, int] = field(default_factory=dict)

    # Overall conviction (0–100), computed after Phase 4
    conviction_score: int = 0

    # Thesis status
    thesis_status: str = "PENDING"  # PENDING | ON TRACK | DRIFTING | BROKEN

    # Human feedback at each interrupt
    human_feedback: dict[str, str] = field(default_factory=dict)

    # Flags set by human at interrupts (travel with state)
    flags: list[str] = field(default_factory=list)

    # Loop tracking (Phase 5 → Phase 3 loop-back, max 2)
    loop_count: int = 0
    loop_context: dict | None = None  # {"categories": [...], "reason": "..."}

    # All citations accumulated (as dicts for JSON serialisation)
    citations: list[dict] = field(default_factory=list)

    # Streaming buffer — current phase text being generated
    # Flushed to phase_outputs on completion
    stream_buffer: str = ""

    # Curated financial data for frontend dashboard charts
    curated_financials: dict | None = None

    # Earnings transcript analysis (6-pass LLM output, stored as dict for JSON)
    transcript_analysis: dict | None = None

    # Metadata
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchState":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def add_citation(self, citation: Any) -> None:
        """Add a citation (models.citation.Citation or StateCitation) to state."""
        if hasattr(citation, "to_dict"):
            self.citations.append(citation.to_dict())
        elif isinstance(citation, dict):
            self.citations.append(citation)

    def set_category_result(self, result: CategoryResult | CategoryError) -> None:
        self.phase_outputs[result.category] = result.to_dict()
        if isinstance(result, CategoryResult):
            self.scores[result.category] = result.score

    def get_deep_dive_results(self) -> dict[str, CategoryResult | CategoryError]:
        """Return all Phase 3 category results, deserialised."""
        out = {}
        for key, val in self.phase_outputs.items():
            if not isinstance(val, dict):
                continue
            t = val.get("__type__")
            if t == "CategoryResult":
                out[key] = CategoryResult.from_dict(val)
            elif t == "CategoryError":
                out[key] = CategoryError.from_dict(val)
        return out

    def failed_categories(self) -> list[str]:
        return [k for k, v in self.phase_outputs.items()
                if isinstance(v, dict) and v.get("__type__") == "CategoryError"]

    def compute_conviction_score(self) -> int:
        """Average of all available category scores, rounded."""
        if not self.scores:
            return 0
        return round(sum(self.scores.values()) / len(self.scores))
