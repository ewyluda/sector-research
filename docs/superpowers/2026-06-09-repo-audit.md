# Repository Audit — sector-research

**Audited:** 2026-06-09 · analysis only, no code modified.
**Method:** full recon of manifests/configs/structure, four parallel deep-read passes (backend architecture, security, frontend, testing/DevEx), with every Critical/High claim re-verified by hand against the cited lines. Lighter review: `services/prospectus_*`, `services/earnings_*`, `services/read_through.py`, deep-dive chart components.
**Status of open questions:** all five resolved with the owner on 2026-06-09 — resolutions are folded into the strategy and task plan below (see "Resolved Questions" at the end).

---

## Executive Summary

**Overall health: B−.** This is a well-documented, thoughtfully designed personal tool whose deterministic core is flying without instruments. The architecture is coherent (citations-first data layer, clean service seams, intact 24-migration chain), documentation is genuinely excellent, and the ~6,900 lines of existing tests are high quality — but nothing runs automatically (no CI, no pre-commit, no backend linter), and the modules where a silent bug costs real money — `model_balancing.py`, `dcf.py`, `reverse_dcf.py`, `discovery.py` scoring, the entire `graph/nodes.py` pipeline — have **zero automated test coverage** (verified: no test file imports any of them).

**Top 3 risks:**
1. A live FMP API key is committed in a tracked file pushed to GitHub.
2. Financial-math regressions are undetectable — a balance-sheet plug or bisection bug would surface only as a quietly wrong valuation.
3. Background pipeline tasks borrow request-scoped DB sessions and work by timing coincidence.

**Top 3 opportunities:**
1. A half-day CI setup instantly activates the existing 57 test files (323 tests, green as of 2026-06-09) plus 5 ready-made smoke suites for the untested math core.
2. Splitting the two god files (`nodes.py` 1,631 lines, `api.ts` 2,113 lines) pays compounding dividends in an LLM-assisted workflow.
3. The SSE layer's known reliability gaps are individually small, well-understood (already documented in `hunches.md`), and cheap to fix.

---

## Phase 1 — Repo Map

**Purpose:** Personal stock-research app (single user, local-only, no auth by design — confirmed: the investor-portal roadmap is also personal-use; the app will not be shared or exposed). Discovery (FMP fundamentals + X social signal), a 6-phase LangGraph due-diligence pipeline with citations on every datum, SEC EDGAR filing/relationship extraction, an editable 5-year financial model with reverse-DCF, and a fleet-management status board. Maturity: **serious long-lived internal tool** — 474 tracked files, 24 migrations, active PR-based workflow on GitHub.

**Stack:** FastAPI + async SQLAlchemy 2.0 + LangGraph + PostgreSQL (Python, venv) · Next.js 16 App Router + React 19 + Tailwind v4 (strict TypeScript) · Anthropic Sonnet/Haiku · APScheduler cron jobs · single root `.env`.

**Architecture sketch:**

```
frontend (Next 16, all data via lib/api.ts ──► FastAPI :8000)
                                                │
   api/ (19 routers) ──► services/ (45 modules) ──► clients/ (fmp, x, fred, edgar)
                              │                          │
        graph/ (LangGraph pipeline: quick_screen ──► deep_dive ──► thesis ──► risk ⟲)
                              │
        PostgreSQL (JSONB state checkpoints, citations, signals, models)
   + in-process: SSE queues (pipeline/workspace), APScheduler (signals 02:00, earnings 21:00, outcomes 03:00 UTC)
```

| Area | One-liner |
|---|---|
| `backend/app/graph/` | LangGraph nodes, prompts, state dataclass, LLM wrapper, output parser (~23K lines backend total) |
| `backend/app/services/` | 45 modules: pipeline/workspace orchestrators, EDGAR 5-phase extraction, model math, scoring |
| `backend/app/api/` | 19 routers, ~104 endpoints |
| `backend/app/clients/` | FMP, X, FRED, EDGAR — every method returns `(data, Citation)` |
| `backend/tests/` | 57 unittest files, 6,946 lines, 323 tests |
| `backend/scripts/` | 20 manual smoke/verify/backfill scripts |
| `frontend/lib/api.ts` | The single typed API client — 2,113 lines, 195 exports |
| `frontend/components/` | 110 components in 8 domain subdirectories |
| `docs/` | ADRs, CONTEXT.md domain glossary, specs, e2e findings |
| `design/architecture.html` | Interactive architecture diagram — **kept by owner decision**, to be refreshed as living onboarding documentation |

**Surprises:** (1) A live FMP API key in a tracked markdown file (below). (2) The repo's self-knowledge is unusually good — `hunches.md` and `CONTEXT.md` already document several of the bugs this audit found; the gap is execution, not awareness. (3) `CLAUDE.md` says "seven top-level workspaces" but the app has grown four more surfaces (`/prospectus`, `/performance`, `/compare`, `/company`). (4) Smoke scripts for the untested math core already exist with real assertions — they're just never run automatically.

---

## Phase 2 — Audit Report

### Security

**[CRITICAL] Live FMP API key committed and pushed to GitHub** — FACT, verified.
`docs/claude_hunches/hunches.md:70` contains a real `apikey=…` value (redacted here) inside a pasted httpx log line. The file is git-tracked and the repo pushes to `github.com:ewyluda/sector-research`. Even in a private repo, the key is in remote history permanently — redacting the file is not enough. **Consequence:** anyone with repo access (or a future accidental visibility flip) gets the paid FMP quota. **Fix:** rotate the key at FMP, then redact the file.

**[MEDIUM] FMP key logged in every request URL** — FACT.
`clients/fmp.py` passes `apikey` in `params`, and httpx logs full URLs at INFO. Already self-documented with the fix sketched (`hunches.md`, "P2 — FMP API key is logged in every request URL"). It's how the key ended up in finding #1. A `logging.Filter` on the `httpx` logger closes both the cause and the recurrence path.

**Clean (facts, one line each):** CORS locked to localhost origins (`main.py:160-166`, `config.py:37-40`); uvicorn binds 127.0.0.1 by default (`scripts/dev.sh`); `.env` files untracked with no `.env` in git history; ILIKE input properly escaped (`api/pipeline.py:150-151`); no raw SQL/eval/pickle; SSRF via prospectus URL ingestion is neutralized by CIK/accession regex re-construction (`prospectus_ingest.py:146-150`); dependencies current with no known CVEs; prompt-injection exposure from filings/X text is real but low-impact here (structured-output parsing + no tool-use on untrusted text). No-auth is appropriate and **stays** — the owner confirmed nothing here will be shared or exposed (the "investor portal" roadmap is personal-use tooling, not a deployment).

### Testing

**[HIGH] The deterministic money-math core has zero automated coverage** — FACT, verified by grep: no file in `backend/tests/` imports `services.model_balancing`, `services.dcf`, `services.reverse_dcf`, `services.discovery`, `services.pipeline`, or `graph.nodes`. `clients/fmp.py` has one test covering one of ~12 methods. This is the inverted-priority problem: the well-tested code (workspace steps, peer comp, outcome tracker — genuinely good tests) is mostly LLM-adjacent glue, while the pure-function code whose errors are silent and financially consequential (balance-sheet plug, bisection solvers, 40/40/20 score weighting, `_extract_score` fallback-to-50 behavior in `nodes.py`) is unguarded. **Mitigating fact:** `backend/scripts/smoke_dcf.py`, `smoke_model_balancing.py`, `smoke_reverse_dcf.py`, `smoke_model_diff.py`, `smoke_models_api.py` already exist with real assertions — manual-only.

**[MEDIUM] Frontend: 3 logic test files, no runner** — FACT. `frontend/lib/{cellPath,questions-ui,pipeline-progress}.test.mts` exist, but `package.json` has no test script and no jest/vitest/playwright config — nothing executes them. Component coverage is zero (acceptable for this tool; the orphaned logic tests are not).

**Strength:** test quality where tests exist is high — behavior assertions, parameterized failure injection (`test_peer_comp.py::make_fake_fmp(fail=...)`), FastAPI `dependency_overrides` at the HTTP boundary, no real network/DB/clock anywhere (no flaky patterns found).

### Architecture & design

**[HIGH] Background tasks borrow request-scoped DB sessions** — FACT, verified.
`api/pipeline.py:122` and `services/pipeline.py:175` do `asyncio.create_task(pipeline._run_phase(run_id, state, db))` where `db` comes from `Depends(get_db)`, whose `async with` closes the session at response teardown (`db.py:22-25`). It works today only because SQLAlchemy sessions can re-acquire a connection after `close()` and the first LLM phase takes seconds — but there's a real race if teardown's `close()` lands during an in-flight `db.begin()`, and any session-lifecycle change breaks it (CLAUDE.md itself carries a warning about this). Rated High, not Critical: fragile-by-coincidence, not broken today. Fix is small: open `async_session()` inside `_run_phase`.

**[HIGH] Phase routing has two sources of truth** — FACT. `graph/pipeline.py` conditional edges vs `services/pipeline.py::_next_phase` (lines 178–190) encode the same sequence independently; CLAUDE.md documents the footgun rather than fixing it. A new phase added to one but not the other mis-routes `/advance` silently.

**[HIGH] `graph/nodes.py` is a 1,631-line monolith** — FACT + JUDGMENT. Mixes phase nodes, a 272-line/13-parameter `_fmt_fundamentals` (lines 97–372), question-lifecycle DB writes, and transcript analysis. Matters more than usual here because LLM-assisted editing of a file this size invites collateral changes, and it's the most-edited file in the repo.

**[MEDIUM] SSE delivery is single-subscriber, drop-prone** — FACT, verified, and already documented in `hunches.md`. `services/pipeline.py:520` replaces any existing queue per run_id (second tab steals the stream; first tab's disconnect then unsubscribes the second's queue via the `finally` at line 539); events emitted before the client connects are dropped (`_emit` checks `if run_id in self._streams`, line 511). The frontend's REST-then-SSE hydration masks most of it. Note: an earlier "unbounded queue growth" claim is **wrong** — cleanup exists in the `finally`; the real defects are replacement and pre-subscribe drops.

**[MEDIUM] Swallowed exceptions in discovery** — FACT. `services/discovery.py:198,210,224` `except Exception: return None` with no logging — empty discovery cards become undiagnosable. Similar silent-fallback in `outcome_tracker.py:155-178` (missing state fields → empty snapshot, no warning).

**[LOW–MEDIUM] Assorted, verified:** FIFO (not LRU) eviction can drop a still-running fanout's status (`fanout.py:132-140`); `run_transcript_analysis` returns dict|string|error-string|None per pass (`nodes.py:1433-1502`), pushing union-handling onto every consumer; `WorkspaceContext` fields all typed `Any` (`workspace_context.py:20-25`); `output_parser.py:29`'s greedy `\{.*\}` can't recover when the LLM emits multiple JSON objects or a bare array — though `json.loads` at line 65 means it degrades to a captured error rather than corrupting (the never-raises + persist-error contract here is actually a strength).

### Code quality (frontend)

**[MEDIUM-HIGH] `any` at the workspace SSE boundary** — FACT. `lib/api.ts:1548,1596,1606` (`read_throughs: any[]`, `citations: any[]`, `step_complete.output: any`) feed directly into `WorkspaceReport.tsx` setState. Combined with all backend types being hand-mirrored in `api.ts`, schema drift lands at runtime, not compile time. (`Theme.seed_tickers: string[]` vs backend `Mapped[dict]` JSONB at `models/theme.py:27-29` is a live example of mirror-by-convention.)

**[MEDIUM] `lib/api.ts` is a 2,113-line, 195-export god file** — FACT. Every domain's types and fetchers in one module; the same navigation/merge-conflict tax as `nodes.py`.

**Healthy in one line each:** strict TS enabled; SSE `EventSource.close()` cleanup correct in both streaming consumers; cancelled-flag fetch guards consistent; SSR-safe localStorage hook; recharts confined to deep-dive routes; eslint flat config present (baseline rules only).

### Performance

No N+1s or blocking-in-async found in reviewed paths; FMP fetches are batched (10 at a time) and gathered with `return_exceptions=True`; fanout polling self-terminates (`TickerFilingsCard.tsx:115-130`); in-memory status maps are bounded (fanout, 128 entries). Performance is healthy for the scale, and the May "perf quick-wins pack" plan already covers the rest.

### Dependencies

Healthy: all current, no known CVEs, lockfile present, nothing unmaintained. `psycopg2-binary` + `asyncpg` + `aiosqlite` triple-driver is mildly redundant but justified (Alembic sync / runtime async / test fixtures).

### DevEx & operations

**[HIGH] Zero automation** — FACT. No `.github/workflows`, no pre-commit, no Makefile; backend has no ruff/black/mypy config anywhere (verified: no `pyproject.toml` at either level); `npm` has no `test` or `tsc --noEmit` script; the 20 smoke/verify scripts are memory-dependent. Every regression gate in this project is "the developer remembers." `scripts/dev.sh` itself is good (fail-fast checks, clean signal trapping).

### Documentation

Excellent overall — README accurate with a 30-entry key-files table, CONTEXT.md domain glossary matches code, ADRs exist, TODO.md current. Confirmed drift items (both now scheduled in M3.5):

- CLAUDE.md's "seven workspaces" omits `/prospectus`, `/performance`, `/compare`, `/company` (FACT — directories exist in `frontend/app/`; also independently flagged in the 2026-06-09 investor-portal handoff doc).
- **CONTEXT.md still lists the `compute_delta` race as a known limitation, but it was fixed** (commit `18e601f`, savepoint-guarded INSERT) — owner confirmed the fix landed and the doc was simply never updated. This is now purely a documentation task.

### Strengths to preserve

1. **Citations as a first-class primitive** — every client returns `(data, Citation)`; this discipline held across all five EDGAR phases.
2. **The output-parser contract** (`output_parser.py`): never raises, persists raw response + error for debugging, regex fallback — runs complete despite LLM misbehavior, failures stay visible.
3. **Graceful-degradation fetch pattern** — dedicated sessions per auxiliary fetch, `gather(return_exceptions=True)`, phases proceed with partial context.
4. **Documentation culture** — CLAUDE.md/CONTEXT.md/ADRs/hunches.md mean the system's sharp edges are written down (rare anywhere).
5. **Migration hygiene** — 24 versions, clean single-head chain.

---

## Phase 3 — Improvement Strategy

**Theme 1: There is no safety net — everything is manual.**
Explains: no CI, orphaned smoke scripts, orphaned frontend tests, no linter, regressions found by use. *Target:* every push runs backend unittest + the smoke suites (converted) + `tsc --noEmit` + eslint + ruff, and fails red. *Principle:* an LLM-heavy solo workflow needs mechanical gates more than a team does — there's no reviewer to catch what you don't re-run.

**Theme 2: Test investment is inverted relative to risk.**
Explains: 6,946 well-written test lines guarding glue while pure financial math is unguarded. *Target:* `model_balancing`, `dcf`, `reverse_dcf`, discovery scoring, and `nodes.py` parsing helpers under unittest — these are pure functions; this is the cheapest high-value testing in the repo. *Principle:* test where bugs are silent and consequential, not where code is easiest to mock.

**Theme 3: The long-running async layer works by coincidence.**
Explains: request-scoped sessions in background tasks, single-subscriber SSE with pre-connect drops, dual routing tables. *Target:* background tasks own their sessions; one queue-list per run with cross-tab safety; one routing table imported by both graph and service, pinned by a test. *Principle:* make lifecycle ownership explicit instead of documented-as-fragile.

**Theme 4: Two god files tax every change at the system's busiest seams.**
Explains: `nodes.py` (1,631) and `api.ts` (2,113), hand-mirrored types, `any` at the SSE boundary. *Target:* `nodes.py` split into nodes / formatters / question-lifecycle / transcript-analysis; `api.ts` split by domain; the three `any`s replaced with per-step unions. *Principle:* file size is a real cost when your collaborators are LLMs with context windows.

**Explicitly not fixing (trade-offs, updated with owner decisions):**

- **Authentication** — confirmed permanently out of scope: the app is personal-use only, the investor-portal roadmap does not involve sharing or deployment. Localhost binding + locked CORS is the security boundary, and it's adequate.
- **Full mypy adoption** — decided against (owner deferred to recommendation). A 23K-line backend with `Any`-typed seams makes blanket mypy a multi-day slog with low marginal value next to ruff + tests. **Narrow alternative adopted instead:** if appetite ever materializes, run mypy in strict mode *only* on the pure-math modules (`model_balancing.py`, `dcf.py`, `reverse_dcf.py`, `models/cell_path.py`) where type errors are most costly — that's an S-effort, high-precision slice. Not scheduled in any milestone; strict TypeScript remains the type boundary.
- **Frontend component/E2E tests** — low payoff, high maintenance for one user. The 3 existing `lib/*.test.mts` logic tests get wired into CI; nothing more.
- **AbortController plumbing and memoization sweeps** — the cancelled-flag pattern is correct; React 19 mitigates re-render cost.
- **Postgres-backed test fixtures** — the mock-based suite is fast and adequate.
- **Structured JSON logging** — terminal logs suffice for a local tool.
- **FIFO→LRU fanout eviction beyond a one-line guard** — the 128-entry cap is generous for one user.

**"Done" signals:** FMP key rotated + file redacted; CI required-green on every push including the converted smoke suites; `grep -rn "create_task.*db)" backend/app` returns nothing; a unittest fails if graph edges and `_next_phase` diverge; zero Critical and zero High-correctness findings open; the three `api.ts` `any`s gone; CONTEXT.md/CLAUDE.md drift items closed; `design/architecture.html` reflects the current system.

---

## Phase 4 — Task Plan

> **Execution status (2026-06-10, campaign session A1, PR #41 merged `58a11a4`):** QW2–QW5, M0.1, M0.2, M0.3, and the filter half of M1.1 are DONE. **QW1 / M1.1 rotation half remains open — the user deferred FMP key rotation; the key is redacted from the tree but still live and in git history.** M0.2 outcome: all 6 `verify_*` scripts were fixture-driven and converted (none left as manual); 4 math smoke scripts converted with shared fixtures in `backend/tests/model_fixtures.py`; remaining manual scripts documented in `backend/scripts/README.md`. The redaction filter exceeded the M1.1 sketch: installed on the httpx logger AND root handlers (the FMP retry-warning path leaks the key via `HTTPStatusError` messages). M1.2–M1.4 → session A2; M2 → C2; M3 → C3.

### Quick wins (do immediately, all S)

| # | Task | Impact |
|---|---|---|
| QW1 | Rotate FMP key; redact `hunches.md:70` | Closes the only Critical |
| QW2 | httpx `logging.Filter` redacting `apikey=` (`clients/fmp.py`) | Stops recurrence at the source |
| QW3 | Minimal GitHub Actions: backend unittest (explicit module enumeration — see M0.1 gotcha) + `tsc --noEmit` + `next lint` | Activates 6,946 existing test lines |
| QW4 | Add `ruff` with default config; fix/ignore baseline | First backend lint gate ever |
| QW5 | Log tracebacks in `discovery.py:198,210,224` instead of bare `return None` | Ends undiagnosable empty cards |

### Milestone 0 — Safety net

| ID | Task | Files | Acceptance | Effort | Risk | Deps |
|---|---|---|---|---|---|---|
| M0.1 | CI pipeline (QW3 formalized: backend tests, ruff, tsc, eslint, plus `node --test` for the 3 orphaned `lib/*.test.mts`) | `.github/workflows/ci.yml`, `package.json` | Push triggers run; failure blocks; all current suites green | M | Low | — |
| M0.2 | Convert `smoke_dcf` / `smoke_model_balancing` / `smoke_reverse_dcf` / `smoke_model_diff` into `backend/tests/test_*` unittest modules. **For the `verify_*_parser.py` scripts (owner deferred to recommendation): triage each during this task — convert any that run on recorded/static fixtures; leave inherently-manual ones (those needing live LLM output) as scripts and note that in a README line in `backend/scripts/`** | `backend/scripts/smoke_*.py`, `verify_*.py` → `backend/tests/` | Math core covered in CI; each verify script either converted or explicitly marked manual | M | Low | M0.1 |
| M0.3 | Characterization tests for `nodes.py` parsing helpers (`_extract_score` incl. silent-50 fallback, `_extract_key_findings`) and `output_parser` edges (multiple objects, bare array, fenced) | new `backend/tests/test_output_parsing.py` | Documented behavior pinned before any refactor | S | Low | — |

### Milestone 1 — Critical & correctness fixes

| ID | Task | Files | Acceptance | Effort | Risk | Deps |
|---|---|---|---|---|---|---|
| M1.1 | Key rotation + redaction (QW1) + redaction filter (QW2) | FMP dashboard, `hunches.md`, `clients/fmp.py` or `main.py` | Old key dead; `grep apikey` on logs/repo clean | S | None | — |
| M1.2 | Background tasks own their sessions: `_run_phase` opens `async_session()` internally; drop `db` param at `api/pipeline.py:122` and `services/pipeline.py:175` | `services/pipeline.py`, `api/pipeline.py` | No request session crosses into a task; full run E2E-verified | M | **Medium** — touches every run | M0.2/M0.3 |
| M1.3 | Single-source phase routing: one table in `graph/pipeline.py`, imported by `_next_phase`; divergence test | `graph/pipeline.py`, `services/pipeline.py`, new test | Test fails if either side drifts | S | Low | M0.1 |
| M1.4 | SSE: `dict[run_id, list[Queue]]`, unsubscribe removes only own queue; optional small pre-subscribe replay buffer | `services/pipeline.py:511-539`, mirror in `workspace.py` | Two tabs stream independently; first-disconnect doesn't kill second | M | Medium | — |

### Milestone 2 — High-leverage improvements

| ID | Task | Files | Acceptance | Effort | Risk | Deps |
|---|---|---|---|---|---|---|
| M2.1 | Tests: discovery scoring (40/40/20, stale collapse, all-missing) + top-5 FMPClient parsers against canned malformed payloads | new tests | Weighting + degradation pinned | M | Low | M0.1 |
| M2.2 | Split `nodes.py` → `graph/formatters.py`, `services/question_lifecycle.py`, `services/transcript_analysis.py`; nodes-only remainder | `graph/nodes.py` + new | Pure moves; M0.3 tests green unchanged; nodes.py < ~700 lines | L | Medium-High | M0.2, M0.3 |
| M2.3 | Split `lib/api.ts` into `lib/api/{core,themes,pipeline,filings,workspace,model,peers,…}.ts` with barrel re-export | `frontend/lib/` | Zero callsite changes; tsc green | M | Low | M0.1 |
| M2.4 | Kill the three `any`s: per-step output union, `Citation[]`, typed `read_throughs` | `api.ts:1548,1596,1606`, `WorkspaceReport.tsx` | tsc green, no `no-explicit-any` suppressions in api.ts | S | Low | M2.3 helps |

### Milestone 3 — Quality & polish

| ID | Task | Effort |
|---|---|---|
| M3.1 | Typed result container for `run_transcript_analysis` (status + value/error) | M |
| M3.2 | Real types on `WorkspaceContext` (drop `Any`, `TYPE_CHECKING` if needed) | S |
| M3.3 | Fanout eviction: skip `running` entries (or LRU) at `fanout.py:132-140` | S |
| M3.4 | Warn-log on missing state fields in `outcome_tracker.py:155-178`; mark snapshots incomplete | S |
| M3.5 | Doc reconciliation: CLAUDE.md workspace list (+`/prospectus`, `/performance`, `/compare`, `/company`), add unittest how-to, **update CONTEXT.md to remove the `compute_delta` race from known limitations (fixed in `18e601f` — confirmed by owner)** | S |
| M3.6 | Break up `_fmt_fundamentals` into per-section formatters (fold into M2.2 if convenient) | M |
| M3.7 | **`design/` cleanup (owner decision):** keep `design/architecture.html` and refresh it to the current architecture so it serves as interactive onboarding/reference documentation (include the post-May surfaces: company workspace, prospectus, performance/outcomes, peer comparison; verify whether `architecture.json` is its data source and update or inline accordingly). Delete `design/style-explorer.html` and `design/citation-styles.html`. | M |
| M3.8 | Type seed_tickers/JSONB mirroring note in `api.ts`; consider runtime validation on the workspace SSE payload only | S |

### Implementation sketches — top 3

**M1.1 — Key rotation.** Generate a new key in the FMP dashboard first, update `.env`, verify with one live request, *then* kill the old key (no downtime window). Redact `hunches.md`. Don't bother rewriting git history — rotation makes the leaked key worthless, and a filtered force-push would fight every PR ref. Then the filter: a `logging.Filter` on the `"httpx"` logger whose `filter()` rewrites `record.args`/`record.msg` with `re.sub(r"apikey=[^&\s\"]+", "apikey=REDACTED", ...)`, installed in `main.py` at startup. Gotcha: httpx logs URLs via lazy `%`-args — mutate `record.args`, not just `msg`.

**M1.2 — Session ownership.** Change `_run_phase(self, run_id, state, db)` → `_run_phase(self, run_id, state)`; first line: `async with async_session() as db:` wrapping the existing loop body (the `db.begin()` blocks inside work unchanged). Update both `create_task` callsites and the `advance` path. Gotcha 1: `_run_deep_dive_with_streaming(state, run_id, db)` receives the same session — pass the new one through. Gotcha 2: keep the session open across the whole multi-phase loop (one long-lived session per run is fine at pool_size=5 for one user) rather than per-phase, to minimize behavior change. Verify: run a full pipeline E2E and confirm phase-by-phase rows update in `research_runs`.

**M0.1 — CI.** One workflow, two jobs. Backend: Python 3.12 + `pip install -r backend/requirements.txt` + ruff + unittest. **Gotcha (confirmed, cost a session previously):** `backend/tests` has no `__init__.py`, so `unittest discover -t .` fails. Use the proven explicit-enumeration form from repo root:
```bash
python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')
```
(or add `backend/tests/__init__.py` once and use `discover` — either is fine; enumeration is the known-green path, 323 tests as of 2026-06-09). Gotcha 2: `config.py` requires `fmp_api_key`/`x_bearer_token`/`anthropic_api_key` at import — set dummy env vars in the workflow. Gotcha 3: confirm no test touches Postgres (the suite is mock-based; if a straggler needs it, add a `services: postgres` block later, not now). Frontend job: `npm ci` + `npx tsc --noEmit` + `npm run lint` + `node --test lib/*.test.mts`.

---

## Resolved Questions (formerly "Open Questions")

1. **Investor portal / future exposure — RESOLVED:** the portal roadmap and its handoff doc are for personal use across sessions, not for sharing the app with another person. No-auth posture is permanent and correct; no pre-deployment security revisit is needed. Removed from the plan.
2. **`verify_*` scripts — RESOLVED (owner deferred to recommendation):** triage case-by-case inside M0.2 — convert fixture-driven ones to unittest, leave live-LLM-dependent ones as documented manual scripts.
3. **`compute_delta` race — RESOLVED:** fixed in commit `18e601f`; CONTEXT.md was never updated. Reclassified from correctness concern to documentation task (M3.5).
4. **`design/` folder — RESOLVED:** keep and refresh `design/architecture.html` as living interactive onboarding documentation (new task M3.7); delete `style-explorer.html` and `citation-styles.html`. `docs/e2e-findings-2026-05-12/` and root PNGs were not ruled on and remain untouched.
5. **mypy — RESOLVED (owner deferred to recommendation):** skip blanket mypy. Optional future slice: strict mypy on the four pure-math modules only. Not scheduled; ruff (M0.1/QW4) is the backend gate, strict TypeScript is the frontend gate.
