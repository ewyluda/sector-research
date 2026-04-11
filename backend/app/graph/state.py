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

    def to_dict(self) -> dict:
        return {"__type__": "CategoryResult", "category": self.category,
                "content": self.content, "score": self.score,
                "key_findings": self.key_findings}

    @classmethod
    def from_dict(cls, d: dict) -> "CategoryResult":
        return cls(category=d["category"], content=d["content"],
                   score=d["score"], key_findings=d.get("key_findings", []))


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
