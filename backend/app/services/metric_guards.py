"""Two-tier sanity guard for FMP-derived margin metrics.

Shared by company_snapshot.py (Overview stats) and peer_comp.py (_fetch_one) —
one helper so both builders apply identical policy.

Scaling convention: the backend emits fraction-form margins (0.69 = 69%); the
frontend multiplies by 100 exactly once. Pinned by
backend/tests/test_metric_scaling.py.

Tiers:

1. **Impossible → nulled.** ``gross_margin > 1.0`` is arithmetically impossible
   (it would require negative cost of revenue) and only occurs as upstream FMP
   data corruption (live example: ORCL grossProfitMarginTTM=1.1815 on
   2026-06-10). Emit None — the UI renders its existing em-dash instead of a
   trust-destroying 118.1%.

2. **Suspicious → log-only.** Other margin-type metrics outside [-5.0, 1.5] are
   logged but passed through UNCHANGED — deep-loss companies are real (CORZ's
   genuine netProfitMarginTTM of -3.43 must not be nulled).
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Tier-1 trigger: only gross margin has a hard arithmetic ceiling at 1.0.
GROSS_MARGIN_KEY = "grossProfitMarginTTM"

# Tier-2 sanity window for fraction-form margins (warn-only outside it).
MARGIN_SANE_RANGE = (-5.0, 1.5)


def guard_margin(value: Optional[float], *, metric: str, ticker: str) -> Optional[float]:
    """Apply the two-tier margin guard described in the module docstring.

    `metric` is the FMP wire key (e.g. "grossProfitMarginTTM",
    "netProfitMarginTTM") or the derived-field name ("fcf_margin"); tier 1
    fires only for GROSS_MARGIN_KEY.
    """
    if value is None:
        return None
    if metric == GROSS_MARGIN_KEY and value > 1.0:
        logger.warning(
            "impossible grossProfitMarginTTM=%s for %s — upstream FMP data corruption; nulled",
            value,
            ticker,
        )
        return None
    lo, hi = MARGIN_SANE_RANGE
    if not (lo <= value <= hi):
        logger.warning(
            "suspicious %s=%s for %s — outside sane margin range [%s, %s]; passed through unchanged",
            metric,
            value,
            ticker,
            lo,
            hi,
        )
    return value
