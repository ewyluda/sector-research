# Session A1 — Quick Wins + CI + Test Conversion Implementation Plan

> **STATUS: COMPLETE (2026-06-10).** All 10 tasks executed and merged to main as PR #41 (`58a11a4`); CI green 3× on branch + on main. Exit criteria met except QW1 key rotation, which the user explicitly deferred (ledger note in the campaign doc). Notable deviations from plan, all review-driven: filter also installed on root handlers + dict-args branch (FMP retry-warning leak); `_extract_gross_margin` gained an empty-income guard; `test_theme_id_parameterization` rewritten to pin the bind-param contract; 3 extra characterization pins (space-before-slash, negative score, digit-bullet mangling); CI actions bumped to v6 majors (Node-24 deprecation). Final suite: 641 backend tests.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a CI safety net under the repo: httpx key-redaction filter, discovery traceback logging, smoke/verify-script → unittest conversion, characterization tests for parsing helpers, ruff baseline, and a GitHub Actions workflow that runs it all on every push.

**Architecture:** Pure additive work plus mechanical script→test conversions. No behavior changes outside (a) a logging filter installed in `main.py`, (b) `logger.exception` calls in three `discovery.py` helpers, (c) ruff lint fixes, (d) `tsconfig.json` gaining `allowImportingTsExtensions`. CI = one workflow, two jobs (backend / frontend).

**Tech Stack:** Python 3.12 + stdlib `unittest` (no pytest), ruff 0.15.x, GitHub Actions, Node 24 + `node --test` for `.mts` logic tests, `tsc --noEmit`, eslint flat config.

**Branch:** `chore/a1-safety-net` (created in Task 0, from up-to-date `main`).

**Conventions (apply to every task):**
- Run backend tests from repo root with the venv: `backend/venv/bin/python -m unittest backend.tests.<module> -v`
- `backend/tests/` has NO `__init__.py` — it works as a PEP 420 namespace package; `python -m unittest backend.tests.test_x` is the proven invocation. Do not add `__init__.py`.
- Test style in this repo: plain `unittest.TestCase` classes, descriptive method names, no pytest idioms.
- Commit after each task with the message given in the task.

**Pre-verified facts (don't re-litigate, but trust-but-verify is fine):**
- All 6 `verify_*` scripts are fixture-only (no LLM/DB/network) — confirmed by full read on 2026-06-10.
- `npx tsc --noEmit` currently fails with exactly 4 × TS5097 (`.ts` import extensions in the 4 `lib/*.test.mts` files). `tsconfig.json` has `"noEmit": true`, so `allowImportingTsExtensions` is legal.
- `node --test lib/*.test.mts` passes locally (17 tests) on Node 25; CI uses Node 24 (type stripping is default from Node 23).
- Ruff baseline (default rules, `backend/app backend/tests backend/scripts`): 89 errors — 34 F401, 31 E402, 12 F841, 8 F541, 2 E702, 1 E741, 1 F821. The F821 (`nodes.py:571` `"CuratedFinancials"` return annotation) is a forward ref whose import is function-local at line 573 — benign, fix via `TYPE_CHECKING` import.
- `config.py` requires only `fmp_api_key`, `x_bearer_token`, `anthropic_api_key` (others default).

---

### Task 0: Branch setup

**Files:** none

- [ ] **Step 1: Create the branch**

```bash
git checkout main && git pull && git checkout -b chore/a1-safety-net
```

Expected: on `chore/a1-safety-net`, clean tree (untracked `docs/superpowers/*` files are gitignored-adjacent local docs — leave them).

---

### Task 1: httpx apikey log-redaction filter (QW2)

**Files:**
- Create: `backend/app/logging_filters.py`
- Create: `backend/tests/test_logging_filters.py`
- Modify: `backend/app/main.py` (install filter near top, after imports)

**Context:** httpx logs request URLs at INFO via lazy %-formatting: `logger.info('HTTP Request: %s %s "%s %d %s"', request.method, request.url, ...)`. The key lives in `record.args` (an `httpx.URL` arg), NOT in `record.msg` — the filter must rewrite `record.args`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_logging_filters.py
"""Tests for the httpx apikey redaction logging filter."""
import logging
import unittest

from backend.app.logging_filters import ApiKeyRedactionFilter


def _record(msg: str, args: tuple | None) -> logging.LogRecord:
    return logging.LogRecord(
        name="httpx", level=logging.INFO, pathname=__file__, lineno=1,
        msg=msg, args=args, exc_info=None,
    )


class TestApiKeyRedactionFilter(unittest.TestCase):
    def setUp(self):
        self.filter = ApiKeyRedactionFilter()

    def test_redacts_apikey_in_lazy_args(self):
        # Mirrors httpx's actual log call shape: URL arrives as an arg.
        rec = _record(
            'HTTP Request: %s %s "%s %d %s"',
            ("GET",
             "https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=SECRET123abc",
             "HTTP/1.1", 200, "OK"),
        )
        self.assertTrue(self.filter.filter(rec))
        rendered = rec.getMessage()
        self.assertNotIn("SECRET123abc", rendered)
        self.assertIn("apikey=REDACTED", rendered)
        self.assertIn("symbol=NVDA", rendered)  # only the key is redacted

    def test_redacts_apikey_embedded_in_msg(self):
        rec = _record("retrying https://x.test/q?apikey=SECRET123abc now", None)
        self.filter.filter(rec)
        self.assertNotIn("SECRET123abc", rec.getMessage())

    def test_leaves_clean_records_untouched(self):
        rec = _record('HTTP Request: %s %s', ("GET", "https://api.example.com/health"))
        self.filter.filter(rec)
        self.assertEqual(
            rec.getMessage(), "HTTP Request: GET https://api.example.com/health"
        )

    def test_non_string_args_survive(self):
        rec = _record("status %d for %s?apikey=k123", (200, "https://a.b/c"))
        self.filter.filter(rec)
        self.assertIn("apikey=REDACTED", rec.getMessage())
        self.assertIn("200", rec.getMessage())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `backend/venv/bin/python -m unittest backend.tests.test_logging_filters -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'backend.app.logging_filters'`

- [ ] **Step 3: Write the filter**

```python
# backend/app/logging_filters.py
"""Logging filters shared by the app. Currently: FMP apikey redaction.

httpx logs request URLs at INFO via lazy %-args, so the key value lives in
record.args, not record.msg — the filter rewrites both.
"""
import logging
import re

_APIKEY_RE = re.compile(r"apikey=[^&\s\"']+")


class ApiKeyRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str) and "apikey=" in record.msg:
            record.msg = _APIKEY_RE.sub("apikey=REDACTED", record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(
                _APIKEY_RE.sub("apikey=REDACTED", str(a))
                if "apikey=" in str(a) else a
                for a in record.args
            )
        return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m unittest backend.tests.test_logging_filters -v`
Expected: 4 tests PASS

- [ ] **Step 5: Install the filter in `main.py`**

In `backend/app/main.py`, after the existing import block (it already does `import logging` at line 3), add — alongside the other `backend.app` imports:

```python
from backend.app.logging_filters import ApiKeyRedactionFilter
```

and at module level immediately after the import block (before `lifespan` is defined):

```python
logging.getLogger("httpx").addFilter(ApiKeyRedactionFilter())
```

- [ ] **Step 6: Verify app still imports**

Run: `backend/venv/bin/python -c "from backend.app.main import app; print('ok')"`
Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/app/logging_filters.py backend/tests/test_logging_filters.py backend/app/main.py
git commit -m "feat(logging): redact FMP apikey from httpx log records (QW2)"
```

---

### Task 2: Traceback logging in discovery extractors (QW5)

**Files:**
- Modify: `backend/app/services/discovery.py:229-270` (the three `_extract_*` helpers)
- Create: `backend/tests/test_discovery_extractors.py`

**Context:** `_extract_roic`, `_extract_gross_margin`, `_extract_revenue_growth` end with bare `except Exception: return None` (lines 243, 255, 269) — failures are undiagnosable. `discovery.py` already has `logger = logging.getLogger(__name__)` at line 31. Behavior contract (return `None` on failure) must NOT change.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_discovery_extractors.py
"""The _extract_* FMP helpers: happy path, None on bad data, and (new) logged tracebacks."""
import unittest

from backend.app.services.discovery import (
    _extract_gross_margin,
    _extract_revenue_growth,
    _extract_roic,
)


class TestExtractHelpersHappyPath(unittest.TestCase):
    def test_gross_margin(self):
        income = [{"revenue": 200.0, "grossProfit": 120.0}]
        self.assertEqual(_extract_gross_margin(income), 0.6)

    def test_revenue_growth(self):
        income = [{"revenue": 110.0}, {"revenue": 100.0}]
        self.assertEqual(_extract_revenue_growth(income), 0.1)

    def test_roic(self):
        balance = [{"totalEquity": 800.0, "longTermDebt": 200.0}]
        cashflow = [{"operatingCashFlow": 100.0}]
        self.assertEqual(_extract_roic(balance, cashflow), 0.1)


class TestExtractHelpersFailuresAreLogged(unittest.TestCase):
    def test_gross_margin_bad_data_returns_none_and_logs(self):
        # revenue is a truthy string -> division raises TypeError
        income = [{"revenue": "N/A", "grossProfit": 5.0}]
        with self.assertLogs("backend.app.services.discovery", level="WARNING"):
            self.assertIsNone(_extract_gross_margin(income))

    def test_revenue_growth_bad_data_returns_none_and_logs(self):
        income = [{"revenue": "N/A"}, {"revenue": "N/A"}]
        with self.assertLogs("backend.app.services.discovery", level="WARNING"):
            self.assertIsNone(_extract_revenue_growth(income))

    def test_roic_bad_data_returns_none_and_logs(self):
        balance = [{"totalEquity": "N/A", "longTermDebt": 1.0}]
        cashflow = [{"operatingCashFlow": 1.0}]
        with self.assertLogs("backend.app.services.discovery", level="WARNING"):
            self.assertIsNone(_extract_roic(balance, cashflow))

    def test_empty_input_still_returns_none_without_exception_noise(self):
        # The guarded early-return paths (no data) are NOT exceptions -> no log requirement.
        self.assertIsNone(_extract_gross_margin([]))
        self.assertIsNone(_extract_revenue_growth([{"revenue": 1.0}]))
        self.assertIsNone(_extract_roic([], []))


if __name__ == "__main__":
    unittest.main()
```

Note: `_extract_gross_margin([])` currently raises-and-swallows IndexError (its `try` covers `income[0]`) — after the change it will log. That's fine: the last test only asserts the return value.

- [ ] **Step 2: Run test to verify the logging assertions fail**

Run: `backend/venv/bin/python -m unittest backend.tests.test_discovery_extractors -v`
Expected: happy-path tests PASS; the three `assertLogs` tests FAIL with `AssertionError: no logs of level WARNING or higher triggered`

- [ ] **Step 3: Add `logger.exception` to the three sites**

In `backend/app/services/discovery.py`, change each of the three helpers' `except` clause from:

```python
    except Exception:
        return None
```

to (with the matching helper name in the message):

```python
    except Exception:
        logger.exception("_extract_roic failed on malformed FMP data")
        return None
```

(`_extract_gross_margin` / `_extract_revenue_growth` messages name themselves.) `logger.exception` logs at ERROR with traceback — satisfies `assertLogs(level="WARNING")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `backend/venv/bin/python -m unittest backend.tests.test_discovery_extractors -v`
Expected: 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/discovery.py backend/tests/test_discovery_extractors.py
git commit -m "fix(discovery): log tracebacks in _extract_* helpers instead of silent None (QW5)"
```

---

### Task 3: Convert the 4 math smoke scripts → unittest (M0.2 part 1)

**Files:**
- Create: `backend/tests/model_fixtures.py` (shared fixture builders)
- Create: `backend/tests/test_dcf.py`
- Create: `backend/tests/test_model_balancing.py`
- Create: `backend/tests/test_reverse_dcf.py`
- Create: `backend/tests/test_model_diff.py`
- Delete: `backend/scripts/smoke_dcf.py`, `backend/scripts/smoke_model_balancing.py`, `backend/scripts/smoke_reverse_dcf.py`, `backend/scripts/smoke_model_diff.py`

**Context — cross-script fixture imports that must be untangled:**
- `smoke_reverse_dcf.py` imports `make_flat_fixture` from `smoke_dcf`
- `smoke_model_diff.py` imports `make_minimal_state` from `smoke_model_balancing`

Resolution: move `make_flat_fixture` (from `smoke_dcf.py:10-37`) and `make_minimal_state` (from `smoke_model_balancing.py:7-57`) **verbatim** into `backend/tests/model_fixtures.py` (keep their docstrings and the imports they need from `backend.app.models.model_state`). All four test modules import fixtures from `backend.tests.model_fixtures`.

**Conversion recipe (identical for all four):** read the source script in full first. Each top-level `test_*` function becomes a method on a single `unittest.TestCase` class; the bare `assert x, msg` statements are kept as-is (they fail tests correctly); the `print(...)` success lines and the `if __name__ == "__main__"` block are dropped (add the standard `if __name__ == "__main__": unittest.main()` instead). Module-private helpers (e.g. `_make_recompute_state` in `smoke_reverse_dcf.py:9-29`) move with their module as module-level functions. Do not "improve" assertions or tolerances — this is a pure move.

Worked example — `backend/tests/test_dcf.py` in full (the other three follow the same shape):

```python
# backend/tests/test_dcf.py
"""Pure DCF engine tests (converted from backend/scripts/smoke_dcf.py)."""
import unittest

from backend.app.services.dcf import dcf
from backend.tests.model_fixtures import make_flat_fixture


class TestDcf(unittest.TestCase):
    def test_flat_dcf_exit_multiple(self):
        state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
        result = dcf(state)
        # PV of 5 yearly FCFs of 100 @ 10% = 100 * (1 - 1.10^-5) / 0.10 = 379.0787
        # Terminal = EBITDA(year 5) * 12 = 1800; PV @ 10% / (1.10^5) = 1117.69
        # Total intrinsic = 379.08 + 1117.69 = 1496.77
        expected = 1496.77
        actual = result.intrinsic_value
        assert abs(actual - expected) < 1.0, f"intrinsic_value mismatch: got {actual}, expected ≈ {expected}"
        expected_per_share = expected / 100.0
        assert abs(result.intrinsic_per_share - expected_per_share) < 0.01, f"per_share mismatch: got {result.intrinsic_per_share}"

    def test_flat_dcf_perpetuity(self):
        state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
        result = dcf(state, terminal_method="perpetuity")
        # PV of 5 FCFs = 379.08; TV = 100 * 1.025 / (0.10 - 0.025) = 1366.67
        # PV terminal = 1366.67 / 1.10^5 = 848.42; Intrinsic = 1227.50
        expected = 1227.50
        assert abs(result.intrinsic_value - expected) < 1.0, f"perpetuity DCF mismatch: got {result.intrinsic_value}"

    def test_dcf_discount_override(self):
        state = make_flat_fixture(fcf_per_year=100.0, share_count=100.0, discount=0.10, exit_mult=12.0, ebitda=150.0)
        base = dcf(state).intrinsic_value
        higher = dcf(state, discount_rate=0.15).intrinsic_value
        assert higher < base, f"higher discount must reduce intrinsic; got {higher} >= {base}"


if __name__ == "__main__":
    unittest.main()
```

Class names for the other modules: `TestModelBalancing` (4 methods from `smoke_model_balancing.py:59-146`), `TestReverseDcf` (6 methods from `smoke_reverse_dcf.py:31-120`, plus module-level `_make_recompute_state`), `TestModelDiff` (1 method from `smoke_model_diff.py:8-17`).

- [ ] **Step 1: Create `backend/tests/model_fixtures.py`** with the two builders moved verbatim (docstring the module: `"""Shared ModelState fixtures for the math-core tests (moved from backend/scripts/smoke_*)."""`).

- [ ] **Step 2: Create the four test modules** per the recipe above.

- [ ] **Step 3: Run them**

Run: `backend/venv/bin/python -m unittest backend.tests.test_dcf backend.tests.test_model_balancing backend.tests.test_reverse_dcf backend.tests.test_model_diff -v`
Expected: 14 tests PASS (3 + 4 + 6 + 1)

- [ ] **Step 4: Delete the four smoke scripts**

```bash
git rm backend/scripts/smoke_dcf.py backend/scripts/smoke_model_balancing.py backend/scripts/smoke_reverse_dcf.py backend/scripts/smoke_model_diff.py
```

Then confirm nothing else imports them: `git grep -n "smoke_dcf\|smoke_model_balancing\|smoke_reverse_dcf\|smoke_model_diff" -- ':!docs'`
Expected: no hits in code (docs mentions are fine).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/model_fixtures.py backend/tests/test_dcf.py backend/tests/test_model_balancing.py backend/tests/test_reverse_dcf.py backend/tests/test_model_diff.py
git commit -m "test(model): convert math-core smoke scripts to unittest modules (M0.2)"
```

---

### Task 4: Convert the 6 verify scripts → unittest (M0.2 part 2) + scripts README

**Files:**
- Create: `backend/tests/test_parser_quick_screen.py`, `test_parser_deep_dive.py`, `test_parser_thesis.py`, `test_parser_risk.py`, `test_parser_position.py`, `test_status_board_sql.py`
- Create: `backend/scripts/README.md`
- Delete: the 6 `backend/scripts/verify_*.py` scripts

**Context:** All six were triaged on 2026-06-10 and are pure-fixture (embedded JSON builders, no LLM/DB/network) — every one converts. The five parser scripts share a shape: a `_make_good_json(**overrides)` builder + ~10 `test_N_*` functions asserting `parse_structured_output(...)` results against a `phase_schemas` schema, counting failures in `main()`. `verify_status_board_regressions.py` is one `main()` with ~10 inline asserts over `services/run_timestamps.py` and `status_board._build_latest_runs_sql`.

**Conversion recipe:** read each source script in full first. Keep `_make_good_json` (and any constants) as module-level helpers verbatim; each `test_N_*` function becomes a `TestCase` method (drop the numeric prefix if present, keep the descriptive name); keep bare asserts; drop `main()`/failure-counting/`sys.exit`; add `if __name__ == "__main__": unittest.main()`. For `verify_status_board_regressions.py`, split `main()`'s assert clusters into separate methods on `TestStatusBoardSql` — one method per behavior being pinned (timestamp idempotence, SQL CTE structure, archived-filter toggling, theme_id parameterization), following the script's own section comments.

- [ ] **Step 1: Convert the five parser scripts** to `backend/tests/test_parser_<phase>.py` (class names `TestQuickScreenParser`, `TestDeepDiveParser`, `TestThesisParser`, `TestRiskParser`, `TestPositionParser`).

- [ ] **Step 2: Convert `verify_status_board_regressions.py`** to `backend/tests/test_status_board_sql.py` (class `TestStatusBoardSql`).

- [ ] **Step 3: Run all six**

Run: `backend/venv/bin/python -m unittest backend.tests.test_parser_quick_screen backend.tests.test_parser_deep_dive backend.tests.test_parser_thesis backend.tests.test_parser_risk backend.tests.test_parser_position backend.tests.test_status_board_sql -v`
Expected: ~53 tests PASS (10+11+10+11+11 parser tests + the status-board methods), zero failures.

- [ ] **Step 4: Delete the verify scripts and write the scripts README**

```bash
git rm backend/scripts/verify_deep_dive_parser.py backend/scripts/verify_position_parser.py backend/scripts/verify_quick_screen_parser.py backend/scripts/verify_risk_parser.py backend/scripts/verify_thesis_parser.py backend/scripts/verify_status_board_regressions.py
```

```markdown
# backend/scripts/README.md

Manual, on-demand scripts. Nothing here runs in CI.

- `backfill_catalysts.py`, `backfill_outcomes.py` — one-shot data backfills against the live DB.
- `smoke_*.py` — manual smoke checks that need a live app, DB, or LLM key
  (`smoke_model_baseline.py`, `smoke_model_e2e.py` hit Anthropic; `smoke_models_api.py`
  spins up the FastAPI app; the rest exercise live integrations).

The pure-math and parser smoke/verify scripts that used to live here were converted to
CI-run unittest modules in `backend/tests/` (2026-06-10): `test_dcf`, `test_model_balancing`,
`test_reverse_dcf`, `test_model_diff`, `test_parser_*`, `test_status_board_sql`.
```

(Verify the per-script claims by skimming each remaining script's imports before committing the README — adjust wording if one is actually pure.)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_parser_*.py backend/tests/test_status_board_sql.py backend/scripts/README.md
git commit -m "test(parsers): convert verify_* scripts to unittest; document remaining manual scripts (M0.2)"
```

---

### Task 5: Characterization tests for nodes.py helpers + output_parser edges (M0.3)

**Files:**
- Create: `backend/tests/test_output_parsing.py`

**Context:** Pin current behavior before the C2 god-file split. `_extract_score` (`nodes.py:69-75`): regex `SCORE|CONVICTION: N/100` then bare `N/100`, clamps to [0,100], **silently returns 50 when nothing matches**. `_extract_key_findings` (`nodes.py:78-95`): collects bullet lines after a line containing "key finding", strips `•-*123456789. ` prefixes, skips lines ≤10 chars, caps at 5, stops at first blank line after at least one finding. `parse_structured_output` (`graph/output_parser.py`): never raises; happy-path direct parse, then greedy `\{.*\}` regex (DOTALL) — multiple JSON objects produce one first-`{`-to-last-`}` blob → JSONDecodeError string; bare arrays → "no JSON object found"; empty → "empty response".

- [ ] **Step 1: Write the tests (these pin existing behavior, so they should pass immediately — a failure means the characterization is wrong; investigate, don't "fix" the code)**

```python
# backend/tests/test_output_parsing.py
"""Characterization tests pinning nodes.py parsing helpers and output_parser edges (M0.3).

These document CURRENT behavior (including the _extract_score silent-50 fallback)
ahead of the planned nodes.py split. If one fails, the helper changed — that's the signal.
"""
import unittest

from pydantic import BaseModel

from backend.app.graph.nodes import _extract_key_findings, _extract_score
from backend.app.graph.output_parser import parse_structured_output


class _ToySchema(BaseModel):
    name: str
    score: int


class TestExtractScore(unittest.TestCase):
    def test_score_label(self):
        self.assertEqual(_extract_score("blah\nSCORE: 85/100\nblah"), 85)

    def test_conviction_label(self):
        self.assertEqual(_extract_score("CONVICTION: 42/100"), 42)

    def test_case_insensitive(self):
        self.assertEqual(_extract_score("score: 61/100"), 61)

    def test_bare_fraction_fallback(self):
        self.assertEqual(_extract_score("I rate this 73/100 overall."), 73)

    def test_labeled_wins_over_bare(self):
        # First pattern (labeled) is tried before the bare fallback.
        self.assertEqual(_extract_score("3/100 chance... SCORE: 90/100"), 90)

    def test_clamps_above_100(self):
        self.assertEqual(_extract_score("SCORE: 150/100"), 100)

    def test_silent_50_fallback_when_absent(self):
        # CHARACTERIZATION: no score anywhere -> silently 50, not an error.
        self.assertEqual(_extract_score("no numeric verdict here"), 50)

    def test_silent_50_on_empty(self):
        self.assertEqual(_extract_score(""), 50)


class TestExtractKeyFindings(unittest.TestCase):
    def test_collects_bullets_after_heading(self):
        text = (
            "Analysis...\n"
            "Key findings:\n"
            "- Revenue acceleration is broad-based\n"
            "* Margins expanded for the 4th quarter\n"
            "3. Management guided above consensus\n"
        )
        self.assertEqual(_extract_key_findings(text), [
            "Revenue acceleration is broad-based",
            "Margins expanded for the 4th quarter",
            "Management guided above consensus",
        ])

    def test_caps_at_five(self):
        bullets = "\n".join(f"- finding number {i} is long enough" for i in range(8))
        text = f"Key findings:\n{bullets}"
        self.assertEqual(len(_extract_key_findings(text)), 5)

    def test_stops_at_blank_line_after_findings(self):
        text = (
            "Key findings:\n"
            "- the only finding worth keeping\n"
            "\n"
            "- this is after the blank line section break\n"
        )
        self.assertEqual(_extract_key_findings(text), ["the only finding worth keeping"])

    def test_skips_short_lines(self):
        text = "Key findings:\n- tiny\n- a genuinely substantive finding\n"
        self.assertEqual(_extract_key_findings(text), ["a genuinely substantive finding"])

    def test_no_heading_returns_empty(self):
        self.assertEqual(_extract_key_findings("- bullet without a heading above it"), [])


class TestParseStructuredOutputEdges(unittest.TestCase):
    def test_clean_json(self):
        parsed, err = parse_structured_output('{"name": "NVDA", "score": 9}', _ToySchema)
        self.assertIsNone(err)
        self.assertEqual(parsed.name, "NVDA")

    def test_markdown_fenced_json(self):
        raw = '```json\n{"name": "NVDA", "score": 9}\n```'
        parsed, err = parse_structured_output(raw, _ToySchema)
        self.assertIsNone(err)
        self.assertEqual(parsed.score, 9)

    def test_prose_preamble(self):
        raw = 'Here is the result you asked for:\n{"name": "NVDA", "score": 9}'
        parsed, err = parse_structured_output(raw, _ToySchema)
        self.assertIsNone(err)

    def test_empty_response(self):
        parsed, err = parse_structured_output("", _ToySchema)
        self.assertIsNone(parsed)
        self.assertEqual(err, "empty response")

    def test_bare_array_is_not_recovered(self):
        # CHARACTERIZATION: the regex only matches {...}; a bare top-level array fails.
        parsed, err = parse_structured_output('[{"name": "NVDA", "score": 9}]', _ToySchema)
        self.assertIsNone(parsed)
        # The greedy {...} inside the array IS found and parses as a lone object,
        # so this actually recovers the inner object — pin whichever happens:
        # run once and keep the accurate assertion (see Step 2 note).

    def test_two_json_objects_fail_with_decode_error(self):
        # CHARACTERIZATION: greedy regex spans first { to last } -> invalid JSON.
        raw = '{"name": "A", "score": 1}\n{"name": "B", "score": 2}'
        parsed, err = parse_structured_output(raw, _ToySchema)
        self.assertIsNone(parsed)
        self.assertIn("JSONDecodeError", err or "")

    def test_validation_error_is_returned_not_raised(self):
        parsed, err = parse_structured_output('{"name": "NVDA"}', _ToySchema)
        self.assertIsNone(parsed)
        self.assertIn("ValidationError", err or "")

    def test_never_raises_on_garbage(self):
        parsed, err = parse_structured_output("}{ not json at all }{", _ToySchema)
        self.assertIsNone(parsed)
        self.assertIsNotNone(err)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and true-up the two open characterizations**

Run: `backend/venv/bin/python -m unittest backend.tests.test_output_parsing -v`

`test_bare_array_is_not_recovered` is deliberately written loose: run it, observe what actually happens (the `{...}` regex will find the inner object of the array, so it may parse successfully), and **replace the comment block with the precise assertion** of observed behavior (either `assertIsNone(err)` + parsed inner object, or the error string). Same diligence for `test_two_json_objects_fail_with_decode_error` — if the combined blob somehow parses, pin reality instead. Re-run until all green with exact assertions.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_output_parsing.py
git commit -m "test(parsing): characterization tests for _extract_score/_extract_key_findings/output_parser (M0.3)"
```

---

### Task 6: Ruff baseline (QW4)

**Files:**
- Create: `ruff.toml` (repo root)
- Create: `backend/requirements-dev.txt`
- Modify: assorted `backend/**` files (lint fixes)

**Context:** ruff 0.15.16 is already installed in the venv (done during planning). Baseline with default rules: 89 errors (34 F401 unused-import, 31 E402 import-not-at-top, 12 F841 unused-variable, 8 F541 f-string-no-placeholder, 2 E702, 1 E741, 1 F821). 42 are `--fix`-able.

- [ ] **Step 1: Create `ruff.toml`**

```toml
# ruff.toml — backend lint gate (frontend is eslint's job)
target-version = "py312"
extend-exclude = ["backend/venv", "frontend", "design"]

[lint]
# Default rule set (E4/E7/E9 + F). Widen deliberately, not by default.
```

- [ ] **Step 2: Create `backend/requirements-dev.txt`**

```
ruff==0.15.16
```

- [ ] **Step 3: Auto-fix the safe 42**

```bash
backend/venv/bin/ruff check backend --fix
```

Then `git diff --stat` and skim: fixes should be unused-import removals and `f""`→`""` only. Run the full backend suite to prove nothing broke (see Task 8 Step 1 command).

- [ ] **Step 4: Fix the rest by hand**

- **F821 `nodes.py:571`** — at the top of `nodes.py`, in the typing imports area, add a `TYPE_CHECKING` guard import: `if TYPE_CHECKING: from backend.app.graph.state import CuratedFinancials` (add `TYPE_CHECKING` to the existing `typing` import). Keep the function-local import at line 573 (it's the runtime path).
- **E741 `read_through.py:391`** — rename the lambda/loop variable `l` to something meaningful in its one scope (read the line first).
- **E702 `reverse_dcf.py:118,120`** — split the two `x; y` lines onto separate lines.
- **F841 (12 sites)** — case-by-case: `health.py:20` becomes `await db.execute(text("SELECT 1"))` (no assignment — the execute is the point); genuinely dead assignments get deleted; if a variable is kept deliberately for readability in test files, prefix it `_` or delete. Do NOT delete any expression with side effects.
- **E402 (31 sites — concentrated in `services/pipeline.py` (16), `tests/test_outcome_tracker.py` (14), plus `nodes.py` stragglers)** — these are deliberate late imports (sys.path/bootstrap ordering). Inspect each file: if the late imports are load-bearing (they are in `pipeline.py`-style files), add `[lint.per-file-ignores]` entries to `ruff.toml` rather than reordering code:

```toml
[lint.per-file-ignores]
"backend/app/services/pipeline.py" = ["E402"]
"backend/tests/test_outcome_tracker.py" = ["E402"]
# + any other file where the late import is deliberate
```

Surgical-changes rule applies: prefer the explicit ignore over restructuring working import order in this session.

- [ ] **Step 5: Verify clean and suite green**

Run: `backend/venv/bin/ruff check backend`
Expected: `All checks passed!`
Run the full backend suite (Task 8 Step 1 command). Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add ruff.toml backend/requirements-dev.txt backend
git commit -m "chore(lint): add ruff with default rules; fix/ignore the 89-error baseline (QW4)"
```

---

### Task 7: Frontend typecheck + test wiring

**Files:**
- Modify: `frontend/tsconfig.json` (add `allowImportingTsExtensions`)
- Modify: `frontend/package.json` (add `typecheck` and `test` scripts)

**Context:** `npx tsc --noEmit` currently fails with exactly 4 × TS5097 because the `.test.mts` files import `./cellPath.ts`-style explicit extensions (required by `node --test`). `tsconfig.json` already has `"noEmit": true` (line 8), which makes `allowImportingTsExtensions` legal.

- [ ] **Step 1: Add the compiler option**

In `frontend/tsconfig.json` `compilerOptions`, next to `"noEmit": true`, add:

```json
"allowImportingTsExtensions": true,
```

- [ ] **Step 2: Add npm scripts**

In `frontend/package.json` `scripts`:

```json
"typecheck": "tsc --noEmit",
"test": "node --test lib/*.test.mts"
```

- [ ] **Step 3: Verify all four frontend gates locally**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm test && npm run build
```

Expected: tsc silent/0 errors; lint clean; 17 node tests pass; build succeeds.

- [ ] **Step 4: Commit**

```bash
git add frontend/tsconfig.json frontend/package.json
git commit -m "chore(frontend): wire tsc --noEmit and node --test as npm scripts"
```

---

### Task 8: GitHub Actions CI (QW3 / M0.1)

**Files:**
- Create: `.github/workflows/ci.yml`

**Context gotchas (from the audit, confirmed):** `backend/tests` has no `__init__.py` → `unittest discover` fails; use explicit enumeration. `config.py` requires `FMP_API_KEY`/`X_BEARER_TOKEN`/`ANTHROPIC_API_KEY` env vars at import (no `.env` in CI). The suite is mock-based — no Postgres service needed. Node 24 for default TS type-stripping (`.mts` tests).

- [ ] **Step 1: Verify the enumeration command locally first**

```bash
cd /Users/ericwyluda/Development/projects/sector-research
backend/venv/bin/python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```

Expected: all tests green (323 baseline + ~78 new from Tasks 1–5). Record the count.

- [ ] **Step 2: Write the workflow**

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
  pull_request:
    branches: [main]

jobs:
  backend:
    runs-on: ubuntu-latest
    env:
      FMP_API_KEY: dummy
      X_BEARER_TOKEN: dummy
      ANTHROPIC_API_KEY: dummy
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@localhost:5432/ci_dummy
      DATABASE_URL_SYNC: postgresql://postgres:postgres@localhost:5432/ci_dummy
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip
          cache-dependency-path: |
            backend/requirements.txt
            backend/requirements-dev.txt
      - run: pip install -r backend/requirements.txt -r backend/requirements-dev.txt
      - name: Ruff
        run: ruff check backend
      - name: Backend unittest suite
        # backend/tests has no __init__.py — discover fails; enumerate explicitly.
        run: python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: frontend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "24"
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: npm ci
      - name: Typecheck
        run: npx tsc --noEmit
      - name: Lint
        run: npm run lint
      - name: Logic tests
        run: npm test
```

Note: avoid duplicate runs (push + PR both firing) is accepted — `on: push` with no branch filter is what the campaign exit criteria asks for ("a push to a branch triggers CI").

- [ ] **Step 3: Commit and push**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: GitHub Actions — ruff + backend unittest + tsc/eslint/node-test (QW3/M0.1)"
git push -u origin chore/a1-safety-net
```

- [ ] **Step 4: Watch the run to green**

```bash
gh run watch --exit-status || gh run view --log-failed
```

Expected: both jobs green. If a job fails, fix on the branch, push, re-watch. (Likely first-run issues: pip cache path, Node type-stripping of `.mts` — if `node --test` fails on Node 24 in CI, bump to `"25"` to match local, or add `--experimental-strip-types`.)

---

### Task 9: Redact the leaked key + key rotation handoff (QW1)

**Files:**
- Modify: `docs/claude_hunches/hunches.md` (~line 68–70: the pasted httpx log line containing the real `apikey=` value)

**IMPORTANT — user in the loop:** rotation needs the FMP dashboard, which only the user can access. The safe order overall is: new key generated → `.env` updated → one live request verified → old key killed. The working-tree redaction below is independent and safe to do now (the key stays in git history either way; rotation is what kills it).

- [ ] **Step 1: Redact the value in the working tree**

In `docs/claude_hunches/hunches.md`, replace the real key in the pasted log line with `REDACTED`, keeping the line illustrative:

```
INFO:httpx:HTTP Request: GET https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=REDACTED "HTTP/1.1 200 OK"
```

- [ ] **Step 2: Verify no live key anywhere in the tree**

```bash
git grep -in "apikey=" -- ':!*.lock'
```

Expected: only code references (`fmp.py` param assignment, the `***` citation builder, the new filter/test with fake values) and the redacted doc line. No 20+-char real key values.

- [ ] **Step 3: Commit**

```bash
git add docs/claude_hunches/hunches.md
git commit -m "docs: redact leaked FMP apikey from hunches.md (QW1 — rotation tracked separately)"
git push
```

- [ ] **Step 4: Ask the user to rotate** (main session does this, not a subagent): generate new key in the FMP dashboard → paste into `.env` (`FMP_API_KEY=`) → main session verifies with one live request (`curl "https://financialmodelingprep.com/stable/profile?symbol=AAPL&apikey=$NEW"` or via the app) → user kills the old key. If the user is unavailable, record "QW1 rotation deferred — key still live, redaction landed" in the campaign ledger and proceed.

---

### Task 10: Merge + ledger/TODO updates

- [ ] **Step 1: Confirm CI green on the branch head** (`gh run list --branch chore/a1-safety-net --limit 1`)

- [ ] **Step 2: PR and merge**

```bash
gh pr create --title "chore: A1 safety net — CI, ruff, key redaction, math-core test conversion" --body "$(cat <<'EOF'
Session A1 of the 2026-06-10 improvement campaign: httpx apikey log redaction (QW2), discovery traceback logging (QW5), smoke/verify script → unittest conversion (M0.2), parsing characterization tests (M0.3), ruff baseline (QW4), GitHub Actions CI (QW3/M0.1), hunches.md key redaction (QW1 — rotation handled with user).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Known footgun (memory): `gh` API may 401 on the **merge** call — if `gh pr merge` fails, merge via git: `git checkout main && git pull && git merge --no-ff chore/a1-safety-net && git push`.

- [ ] **Step 3: Update the campaign ledger** — in `docs/superpowers/2026-06-10-improvement-campaign.md`, check the A1 box and append a one-line note (CI workflow name, test-count delta, whether QW1 rotation completed or deferred).

- [ ] **Step 4: TODO.md** — add a "Done (recent)" entry: `A1 safety net: GitHub Actions CI (backend ruff+unittest, frontend tsc/lint/node-test), httpx apikey redaction, smoke/verify→unittest conversion (+~78 tests), hunches.md key redacted`.

- [ ] **Step 5: Commit the TODO.md update to main** (ledger doc is untracked/local — no commit needed for it).

---

## Verification summary (A1 exit criteria → where proven)

| Exit criterion | Proven by |
|---|---|
| Push triggers CI, green incl. converted math tests | Task 8 Step 4 |
| Ruff passes | Task 6 Step 5 + CI |
| No live key in working tree | Task 9 Step 2 |
| Key rotation confirmed or explicitly deferred | Task 9 Step 4 / ledger note |
