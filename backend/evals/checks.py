"""Deterministic checks on a thesis (ThesisOutput-shaped dict) against the
prompt it was written from. Pure functions — no model calls, no database.

- grounding: share of the numbers in the thesis narrative that appear in a
  source text (within display precision), measured two ways. Against the
  prompt, which is mostly model-written deep-dive analysis, it checks the
  thesis agrees with the earlier steps. Against the raw data (the FMP/FRED
  numbers stored as curated_financials), it checks numbers trace to data —
  a lower bound, since transcript and filing figures aren't in that store.
  Numbers the thesis derives itself (an upside %, a new threshold) count as
  ungrounded either way; the trend and the ungrounded list are what matter.
- citations: every "[Source: …]" tag must name a source family the pipeline
  actually feeds the thesis step; evidence with no tag is counted separately.
- consistency: rules a coherent call satisfies (stance vs targets vs price,
  falsifiable kill criteria present, …), returned as violation codes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_NUMBER = re.compile(
    r"(?<![\w.])(?P<sign>[-−+])?(?P<dollar>\$)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<unit>%|x\b|bn\b|billion\b|B\b|mn\b|million\b|M\b|K\b|thousand\b|T\b|trillion\b)?",
    re.IGNORECASE,
)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6,
          "b": 1e9, "bn": 1e9, "billion": 1e9, "t": 1e12, "trillion": 1e12}


@dataclass(frozen=True)
class Number:
    text: str
    value: float
    tolerance: float
    unit: str  # "%", "x", "$" or "" (plain / scaled count)


def extract_numbers(text: str) -> list[Number]:
    """Numbers worth checking: skips bare years, bare small integers (counts,
    'Q3', '3 catalysts') and anything without a digit of substance."""
    out: list[Number] = []
    for m in _NUMBER.finditer(text):
        raw, unit = m.group("num"), (m.group("unit") or "")
        value = float(raw.replace(",", ""))
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        u = unit.lower()
        if not unit and not m.group("dollar"):
            if value.is_integer() and (value <= 10 or 1900 <= value <= 2100):
                continue
        scale = _SCALE.get(u, 1.0)
        kind = "%" if u == "%" else "x" if u == "x" else "$" if m.group("dollar") else ""
        if m.group("sign") in ("-", "−"):
            value = -value
        # Half a unit of the last displayed digit, or 1% — whichever is looser.
        tol = max(abs(value) * 0.01, 0.5 * 10 ** -decimals) * scale
        out.append(Number(text=m.group(0).strip(), value=value * scale, tolerance=tol, unit=kind))
    return out


def _matches(n: Number, source: list[Number]) -> bool:
    for s in source:
        for candidate in (s.value, -s.value):
            if abs(candidate - n.value) <= max(n.tolerance, s.tolerance):
                return True
        if n.unit == "%" and abs(s.value * 100 - n.value) <= n.tolerance:  # fraction in the source
            return True
    return False


@dataclass
class Grounding:
    total: int = 0
    grounded: int = 0
    ungrounded: list[str] = field(default_factory=list)

    @property
    def share(self) -> float | None:
        return self.grounded / self.total if self.total else None


def narrative_text(thesis: dict) -> str:
    """The claims-bearing prose of a thesis. Catalysts and kill criteria are
    left out: their numbers are forward thresholds, not facts from the input."""
    parts = [thesis.get("core_thesis") or "", thesis.get("variant_perception") or ""]
    for side in ("bull_case", "bear_case"):
        for p in thesis.get(side) or []:
            parts += [p.get("title") or "", p.get("evidence") or ""]
    return "\n".join(parts)


def raw_data_text(curated_financials: dict | None) -> str:
    """The stored FMP/FRED data as text. The daily price series is left out:
    250 days of OHLC would match almost any price-like number by chance."""
    import json
    data = {k: v for k, v in (curated_financials or {}).items() if k != "daily_prices"}
    return json.dumps(data, default=str)


def grounding(thesis: dict, prompt: str) -> Grounding:
    source = extract_numbers(prompt)
    g = Grounding()
    for n in extract_numbers(narrative_text(thesis)):
        g.total += 1
        if _matches(n, source):
            g.grounded += 1
        else:
            g.ungrounded.append(n.text)
    return g


_CITATION = re.compile(r"\[Source:\s*([^\]]+)\]", re.IGNORECASE)
SOURCE_FAMILIES = (
    "fmp", "sec", "edgar", "10-k", "10-q", "8-k", "def 14a", "13f", "form 4", "transcript", "earnings call",
    "fred", "x signal", "deep dive", "quick screen", "business quality", "financial health",
    "growth & earnings", "management & governance", "technical & market structure", "macro & regime",
    "sentiment & narrative", "risk assessment", "future durability",
)


@dataclass
class Citations:
    tags: int = 0
    invalid: list[str] = field(default_factory=list)
    uncited_evidence: int = 0
    evidence_items: int = 0


def citations(thesis: dict) -> Citations:
    c = Citations()
    for tag in _CITATION.findall(narrative_text(thesis)):
        c.tags += 1
        if not any(f in tag.lower() for f in SOURCE_FAMILIES):
            c.invalid.append(tag.strip())
    for side in ("bull_case", "bear_case"):
        for p in thesis.get(side) or []:
            c.evidence_items += 1
            if not _CITATION.search(p.get("evidence") or ""):
                c.uncited_evidence += 1
    return c


# Avoid calls may carry some upside in the base case, but not a compelling one.
AVOID_MAX_BASE_UPSIDE = 0.10


def consistency(thesis: dict, price: float | None) -> list[str]:
    """Violation codes; an empty list is a coherent call."""
    issues: list[str] = []
    stance = thesis.get("stance")
    targets = thesis.get("price_targets") or {}
    base = targets.get("base")
    if stance is None:
        issues.append("no_stance")
    if not targets:
        issues.append("no_price_targets")
    if not thesis.get("time_horizon"):
        issues.append("no_time_horizon")
    if price and base:
        if stance == "long" and base <= price:
            issues.append("long_without_upside")
        if stance == "short" and base >= price:
            issues.append("short_without_downside")
        if stance == "avoid" and base > price * (1 + AVOID_MAX_BASE_UPSIDE):
            issues.append("avoid_with_compelling_upside")
    if not thesis.get("kill_criteria"):
        issues.append("no_kill_criteria")
    if not thesis.get("pre_mortem"):
        issues.append("no_pre_mortem")
    return issues
