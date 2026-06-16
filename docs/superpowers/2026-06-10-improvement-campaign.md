# Improvement Campaign — sector-research

Written 2026-06-10. A multi-session campaign to (A) put a safety net under the codebase and fix known correctness risks, (B) audit and redesign the UX/navigation, and (C) land perf wins and split the god files. Architecture work executes the existing audit plan; UX work starts with discovery because no UX audit exists yet.

## How to use this doc (pointer prompt)

Paste this into a fresh session:

> Read `docs/superpowers/2026-06-10-improvement-campaign.md`. Find the first unchecked session block in the status ledger, verify its entry criteria against the actual repo state (git log, files on disk — do not trust the ledger blindly), and execute that block using the workflow named in it. When done: check the box, add a TODO.md "Done (recent)" entry, and update this doc if anything you learned changes a later block.

Rules for executing sessions:

- One session block per session. Don't start the next block if the current one isn't fully verified.
- Every block ends with its exit criteria demonstrably met — run the commands, paste the output, no "should work."
- If a block's premise turns out stale (code moved, problem already fixed), record that in the ledger with a one-line note and move on — don't force the work.
- Branch per block (`chore/...`, `fix/...`, `refactor/...`, `feat/ux-...`), PR to `main`, merge before the next block.

## Status ledger

- [x] **A1** — Quick wins + CI + test conversion *(done 2026-06-10, PR #41 merged `58a11a4`. CI live — `.github/workflows/ci.yml`, backend ruff+unittest / frontend tsc+eslint+node-test, green 3× on branch + on main; ruff baseline clean; apikey redaction filter at httpx-logger + root-handler level; 4 smoke + 6 verify scripts → unittest, backend suite now 641 tests; 24 M0.3 characterization tests; hunches.md key REDACTED. ⚠️ QW1 rotation DEFERRED — user must rotate the FMP key at the dashboard; it's still live and still in git history. Plan: `docs/superpowers/plans/2026-06-10-a1-safety-net.md`.)*
- [x] **A2** — Correctness fixes (sessions, routing, SSE) *(done 2026-06-11, PR #42 merged `c9630c1`. M1.2: `_run_phase` opens its own `async_session()`, 3 create_task call sites dropped the request `db`. M1.3: `PHASE_SEQUENCE` + `next_phase()` in `graph/pipeline.py` single-source the routing; `after_*` edges lifted to module level; divergence pinned by `test_phase_routing.py` (28 tests); behavior verified byte-identical by exhaustive differential check. M1.4: pipeline SSE `dict[run_id, list[Queue]]` fan-out (pre-subscribe drops intentional — REST hydration recovers); workspace mirror with per-run replay buffer (pre-subscribe buffering is load-bearing there); 11 SSE tests incl. cancellation cleanup. Suite 641→680; live E2E run (ERIC, test DB) completed through a deep-dive loop-back; two-tab SSE verified live (45s disconnect of one tab didn't affect the other). Note: the exit-criteria grep `create_task.*db)` retains one pre-existing hit at `discovery.py:306` — immediately awaited via `gather` in the same request, not the M1.2 pattern. Note 2: `prospectus_service.py` still uses the legacy single-shared-queue SSE pattern — third pattern in the codebase now; candidate for C3 polish.)*
- [x] **C1** — Perf quick-wins pack *(done 2026-06-11, PR #43 merged `bd270bb`. All 6 plan premises re-verified live before work — all still valid (17 section files now, not 13; 4 status-page pollers, not 3). (1) React.memo on 14 deep-dive sections + `lib/categoryWrappers.ts` reference-stable wrapper cache — the wrap alone did NOT short-circuit (pipeline page minted fresh wrapper objects per render; caught in spec review), now pinned by 6 node tests; (2) 30s visibility-refetch debounce on all 4 status pollers; (3) 30s TTL quote cache behind reverse-DCF (live-verified: 2 opens → 1 FMP call); (4) `archived_at` on StatusBoardEntry, double-fetch removed (live archive/unarchive round-trip verified); (5) SurpriseAlert N+1 → one IN() (exactly-one-query test); (6) partial index `(ticker, theme_id, created_at DESC) WHERE status IN ('completed','watchlist') AND theme_id IS NOT NULL` — the plan's expression index is impossible (cast STABLE not IMMUTABLE, verified vs live PG); predicate exactly matches `_build_latest_runs_sql`, EXPLAIN shows index → Incremental Sort. Backend 691 tests / frontend 23 green. Jank exit criterion satisfied via wrapper reference-stability tests + independent render-path trace rather than a second paid live-run profile. Note: migration `77bcb5d1bfbd` is a byte-identical copy from the in-flight `feat/ux-phase1-unblocks` branch (B3 session) to keep the alembic chain — merges cleanly either order.)*
- [x] **B1** — UX discovery audit *(done 2026-06-10, out of order at user direction — A1 not yet executed; B1 is read-only so the missing CI gate only matters for B3. Audit: `docs/superpowers/2026-06-10-ux-audit.md`, screenshots in `docs/superpowers/ux-audit-2026-06-10/`. Top findings for B2: earnings-day journey blocked by hidden `no_ticker_model` preflight; curation queue has no dismiss for private counterparties; app is split between CSS-variable light theme (workspace report, model forecast tab, company peers tab) and hardcoded dark everywhere else.)*
- [x] **B2** — UX/IA design spec *(done 2026-06-10, spec at `docs/superpowers/specs/2026-06-10-ux-overhaul-design.md`, user-approved. Decisions: dark theme everywhere via token-first sweep; 6-entry top nav (Catalysts→Today tab, Prospectus/Workspace/Questions demoted); global ⌘K full scope; earnings unblock = relax `no_ticker_model` to warning; all four optional M items pulled in incl. the FMP ratio scaling fix.)*
- [x] **B3** — UX implementation plan + execution *(COMPLETE 2026-06-11, four phases across PRs #44, #50, #51, #53. Phase 1 (PR #44, `433adf5`): earnings unblock (`no_ticker_model` → warning + model-skip), curation tombstones, metric guards (audit's "scaling bug" premise disproven — upstream FMP corruption + cumulative-vs-CAGR mislabel), performance data-first defaults. Phase 2 (PR #50, `e0423cc`): `GET /api/tickers`, global ⌘K `GlobalCommandPalette` (report-local palette retired), 6-entry nav, Today absorbs Catalysts (`/catalysts` redirects; Next 16 Suspense footgun handled), attention severity tiers + undated-catalyst compaction + archived-thesis chips (catalyst-rows-only — earnings rows can't distinguish archived from never-thesis), prospectus-on-filings + workspace Retry, status row menu + KillCriteriaDrawer. Phase 3 (PR #51, `d599df7`): questions `snoozed_until` + bulk endpoint + filter-chips/bulk-bar UI, 8-K near-duplicate grouping (pure helper, both consumers, ×N badges), run abandon + Library grouped-by-ticker rebuild (gate-era chips retired; backfills: 6 zombies + 14 awaiting_approval rows on both DBs), filings polish (chore chip, depth-2 default). Phase 4 (PR #53, `ec39ccf`): 9-fix bundle (incl. Researched chip — `last_run_id` was a never-populated dead field; signals-refresh banner; reverse-DCF footnotes), Task 25 theme diagnosis (light mechanism GONE — removal no-op), 93-hit token sweep in 5 per-surface commits with screenshot parity + 12 justified survivors + AGENTS.md guard, CLAUDE.md phases-2-4 reconciliation. Acceptance walk (spec §14): all four B1 journeys re-walked live — morning check 2 actions (B1 ~3-5), new idea 3 (B1 ~5), earnings day 3 with visible blocked-reasons (B1 6-step hidden detour), filings chores 2 with full restore (B1 dead end); 7/8 spot-checks pass, the 1 failure is pre-existing (earnings board drops yesterday-prints with null actuals → `expand_earnings` no-ops; filed as issue #52, not a B3 regression). Suite 836 backend / 28 node; every phase two-stage-reviewed with fixes.)*
- [x] **C2** — God-file splits (`nodes.py`, `api.ts`, kill the `any`s) *(done 2026-06-11 in two halves. Backend (M2.2), PR #45 merged `6922e43`: `nodes.py` 1,669→888 lines via pure moves into `graph/formatters.py` / `services/transcript_analysis.py` / `services/question_lifecycle.py`, all moved symbols re-exported as a documented transitional shim, AST-level body diff verified. Frontend (M2.3+M2.4), PR #48 merged `b7ea0e7`, executed in the window right after B3 phase 1 merged (no UX branch in flight — phase 2+ inherits the split): `lib/api.ts` 2,451 lines → 12 domain modules + barrel, all 244 exports preserved (compiler-API verified), `BASE`/`apiFetch` kept package-private; workspace SSE boundary typed (`WorkspaceStepOutput` union / `Citation[]` / `ReadThroughItem[]`, casts proven sound) — typing exposed and removed a dead `rt.summary` render in DifferentiationCard. Known notes: M2.4's lib changes physically sit in the M2.3 commit (bisection-only concern); 2 pre-existing `any` suppressions remain in `ValidationCard.tsx` adapters (out of audit scope — follow-up candidate). M3.6 fold-in done separately in PR #46.)*
- [x] **C3** — Polish + doc reconciliation + architecture.html refresh *(done 2026-06-11 across three PRs. PR #46 `46ace4b`: M3.1 `TranscriptAnalysisResult` container (persisted shape unchanged), M3.2 WorkspaceContext real types, M3.4 snapshot warn-logs + `"incomplete": true` markers, M3.6 `_fmt_fundamentals` → 12 per-section helpers with frozen-legacy identity test, prospectus SSE replay mirror (all three SSE services now consistent), M3.7 delete-half. PR #47 `3dda8d1`: CONTEXT.md compute_delta drift fix + audit-orphan M2.1 (56 characterization tests — discovery 40/40/20 + stale collapse, FMP parser degradation; suite 766). PR #49 `2c7adba`: M3.5 full CLAUDE.md/CONTEXT.md sweep vs PRs #42-48 (11 drift items fixed, ~12 suspects verified already-accurate), M3.8 seed_tickers JSONB-mirroring JSDoc (read path serves rows as-is — verified; SSE runtime-validation half closed as redundant post-M2.4), M3.7 refresh-half — architecture.json updated to main `b7ea0e7` (new invariants: single-source routing, SSE replay semantics, task-owned sessions, preflight warning, margin guards) + 6 stale hardcoded spots in architecture.html fixed. M3.3 was already shipped pre-campaign (FanoutService eviction). ⚠️ B3 phases 2-4 will mint NEW drift in the surfaces they change — that reconciliation belongs to the Track B sessions per the campaign's own rules, not retroactively to this block.)*

Recommended order as listed: A1 → A2 → C1 → B1 → B2 → B3 → C2 → C3. Rationale: CI first so everything after has a regression gate; perf pack before the UX redesign so the deep-dive jank fix lands under it; god-file splits last because they're mechanical once tests exist and they'd churn against the UX work if done concurrently.

## Current state (as of 2026-06-10)

- Investor-portal sub-projects 1–4 are merged: peer comparison (PR #34), quick-fixes pack (#35), unified calendar (#36), Today dashboard (#37), 8-K/Form 4 material events (#38). Remaining feature work (quant layer, trade journal) is **out of scope here** — it lives in `docs/superpowers/2026-06-09-investor-portal-handoff.md`.
- The full repo audit is at `docs/superpowers/2026-06-09-repo-audit.md` — read its Phase 4 task plan before Track A or C work. **A1 executed its Quick Wins + Milestone 0 + the M1.1 filter half (2026-06-10, PR #41)**: CI at `.github/workflows/ci.yml`, `ruff.toml` + `backend/requirements-dev.txt`, redaction filter, scripts→unittest conversion, M0.3 characterization tests. Still open from the audit: **FMP key rotation (user deferred — key still live)**, all of M1.2–M1.4 (→ A2), M2 (→ C2), M3 (→ C3).
- The perf quick-wins plan is at `docs/superpowers/plans/2026-05-27-perf-quick-wins-pack.md` — written before PRs #36–#38 merged, so premises need re-verification (see C1).
- Backend tests: 323+ green as of 2026-06-09, manual-only. Frontend: 3 orphaned `lib/*.test.mts` files with no runner wired up.

---

## Track A — Safety net & correctness

Executes the audit's Quick Wins + Milestones 0–1. The audit doc is the source of truth for task details and implementation sketches; this doc only sequences them.

### Session A1 — Quick wins + CI + test conversion

**Entry criteria:** none (this is the campaign's first block).

**Work** (audit refs in parens):

1. **FMP key rotation (QW1) — USER IN THE LOOP.** Requires the FMP dashboard. Order matters: generate new key → update `.env` → verify with one live request → kill old key → redact `docs/claude_hunches/hunches.md:70`. Don't rewrite git history. If the user isn't available this session, do everything else and leave this unchecked in a note.
2. httpx `logging.Filter` redacting `apikey=` (QW2) — see audit's M1.1 sketch; mutate `record.args`, not just `msg`.
3. GitHub Actions CI (QW3/M0.1): backend job = ruff + unittest via explicit module enumeration (no `__init__.py` in `backend/tests/`, so `discover -t .` fails — use the enumeration command in the audit's M0.1 sketch); set dummy `FMP_API_KEY`/`X_BEARER_TOKEN`/`ANTHROPIC_API_KEY`/`DATABASE_URL`/`DATABASE_URL_SYNC` env vars (`config.py` requires them at import). Frontend job = `npm ci` + `npx tsc --noEmit` + `npm run lint` + `node --test lib/*.test.mts`.
4. Add ruff with default config; fix or explicitly ignore the baseline (QW4).
5. Log tracebacks in `services/discovery.py` bare `except Exception: return None` sites (QW5).
6. Convert `smoke_dcf` / `smoke_model_balancing` / `smoke_reverse_dcf` / `smoke_model_diff` to `backend/tests/test_*` modules (M0.2). Triage `verify_*` scripts case-by-case: fixture-driven → convert; live-LLM-dependent → leave as scripts with a README note in `backend/scripts/`.
7. Characterization tests for `nodes.py` parsing helpers (`_extract_score` incl. silent-50 fallback, `_extract_key_findings`) and `output_parser` edge cases (M0.3).

**Exit criteria:** a push to a branch triggers CI and it's green, including the converted math-core tests; ruff passes; no live key value remains anywhere in the working tree (`git grep -i apikey` shows only redacted/code references); key rotation confirmed by the user (or explicitly deferred in the ledger).

### Session A2 — Correctness fixes

**Entry criteria:** A1 merged; CI green on `main`.

**Work:**

1. Background tasks own their DB sessions (M1.2): `_run_phase` opens `async_session()` internally; drop the `db` param at both `create_task` call sites. Follow the audit's M1.2 sketch — gotchas around `_run_deep_dive_with_streaming` and keeping one session across the multi-phase loop. **Verify with a full live pipeline run end-to-end**, not just tests.
2. Single-source phase routing (M1.3): one table in `graph/pipeline.py` imported by `services/pipeline.py::_next_phase`, plus a divergence unittest. Update the CLAUDE.md footgun note afterward — it documents the dual-source problem this removes.
3. SSE multi-subscriber (M1.4): `dict[run_id, list[Queue]]`, unsubscribe removes only own queue, optionally a small pre-subscribe replay buffer. Mirror in `services/workspace.py`. Verify: two tabs stream the same run independently; closing one doesn't kill the other.

**Exit criteria:** `grep -rn "create_task.*db)" backend/app` returns nothing; the routing divergence test exists and fails if either side drifts; two-tab SSE verified live; full backend suite + a real pipeline run green.

---

## Track C — Perf + architecture deepening

### Session C1 — Perf quick-wins pack

**Entry criteria:** A1 merged (CI exists). Can run before or after A2.

**Work:** execute `docs/superpowers/plans/2026-05-27-perf-quick-wins-pack.md` (6 tasks: React.memo on deep-dive sections, visibility-gated polling, reverse-DCF quote round-trip, status-board archived flag, discovery `_merge_results` N+1, composite index migration). **The plan predates PRs #36–#38** — before each task, re-verify its premise against current `main` (file paths, line numbers, whether the problem still exists). The Today dashboard already does visibility-gated polling; check whether that task is partially done. Skip stale tasks with a ledger note.

**Exit criteria:** each of the 6 tasks either implemented + verified per the plan's own checks, or skipped with a written reason; backend suite + frontend lint/build green; deep-dive live-stream jank measurably reduced (eyeball a live run before/after).

### Session C2 — God-file splits

**Entry criteria:** A1 + A2 merged (M0.2/M0.3 tests exist — they're the regression net for this); B3 substantially done or not yet started (don't split `api.ts` mid-UX-implementation).

**Work:**

1. Split `graph/nodes.py` (1,631 lines) → `graph/formatters.py`, `services/question_lifecycle.py`, `services/transcript_analysis.py`; nodes-only remainder < ~700 lines (M2.2). Pure moves — M0.3 characterization tests must pass unchanged. Fold in the `_fmt_fundamentals` per-section breakup (M3.6) if it stays mechanical.
2. Split `frontend/lib/api.ts` (2,113 lines) into `lib/api/{core,themes,pipeline,filings,workspace,model,peers,...}.ts` with a barrel re-export — zero call-site changes, tsc green (M2.3).
3. Kill the three `any`s at the workspace SSE boundary: per-step output union, `Citation[]`, typed `read_throughs` (M2.4).

**Exit criteria:** audit's M2 acceptance rows; CLAUDE.md references to moved code updated.

### Session C3 — Polish + docs

**Entry criteria:** C2 merged.

**Work:** audit M3.1–M3.5 + M3.7–M3.8 (typed transcript-analysis result, `WorkspaceContext` types, fanout eviction guard, outcome-tracker warn-logs, CLAUDE.md/CONTEXT.md drift closure incl. the fixed `compute_delta` race, `design/architecture.html` refresh + delete the two stale design HTML files, seed_tickers JSONB mirroring note). Re-check the doc-drift list first — Track B will have changed the workspace list again.

**Exit criteria:** all M3 rows closed or consciously dropped; zero known doc-drift items; `design/architecture.html` reflects the post-campaign system.

---

## Track B — UX/navigation overhaul

No UX audit exists; this track is discovery → design → implement. The app has ~12 user-facing surfaces: 8 nav entries (Today, Themes, Filings, Catalysts, Status, Workspace, Questions, Library) plus hidden routes (`/company/[ticker]`, `/compare`, `/performance`, `/prospectus`, `/model/[ticker]`, `/pipeline/*`). Enumerate live from `frontend/app/**/page.tsx` — PR #38 may have added surfaces this doc doesn't know about.

### Session B1 — UX discovery audit

**Entry criteria:** A1 merged (so frontend changes later have a CI gate). User availability not required.

**Work:**

1. Launch both servers (backend: `uvicorn backend.app.main:app --reload` from repo root with venv active; frontend: `npm run dev`; `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` — Docker steals IPv6 `localhost:8000` on this machine).
2. Walk **every** surface with Playwright MCP, screenshotting each. Use real data in the DB — exercise interactive states (drawers, modals, kick-off buttons, editors), not just page loads.
3. Map the core journeys end-to-end and time/step-count them:
   - **Morning check:** open app → triage Today banner/attention list → act on an item (workspace kick-off, question, drawer).
   - **New idea:** discovery/theme → company card → start pipeline run → watch live → read report → create model.
   - **Earnings day:** calendar/status → earnings drawer → workspace refresh → updated verdict.
   - **Filings chores:** ingest → extract → curation queue → graph exploration.
4. Produce `docs/superpowers/<session-date>-ux-audit.md` (fill in the actual date): per-surface friction log (dead ends, redundant clicks, inconsistent patterns, orphaned pages), IA critique (what deserves nav placement vs. contextual entry; the handoff doc notes nav was already "full" at 10 entries), navigation-graph map (which pages link where, which are reachable only by URL), visual-consistency notes (the model pages were migrated to light-theme CSS variables — check the rest), and a ranked recommendation list sized S/M/L.

**Exit criteria:** audit doc exists with screenshots referenced, every surface covered, journeys mapped, recommendations ranked. No code changes in this session.

### Session B2 — UX/IA design spec (user must be present)

**Entry criteria:** B1 audit doc exists; user available to answer questions.

**Work:** brainstorm with the user (superpowers:brainstorming — one question at a time; offer the visual companion, this is exactly its use case) from the B1 findings. Settle: navigation/IA structure, layout system, per-surface changes, what gets cut or merged. Write the spec to `docs/superpowers/specs/<session-date>-ux-overhaul-design.md`.

Constraints to honor in the design:

- **Next.js 16:** read `node_modules/next/dist/docs/` before assuming any App Router API — per `frontend/AGENTS.md`.
- Light theme via CSS variables (`var(--surface)`, `var(--text)`, etc.) — no hardcoded palette classes.
- Existing registries stay single-source: `sections.ts` (SectionNav + CommandPalette), `scoreColors.ts`, `usePersistedCollapse`, `data-print-hide` on new sticky UI.
- This is an information-dense professional research tool for one expert user — optimize for speed-to-signal and keyboard flow, not onboarding or whitespace.
- No auth, local-only — permanent (audit Resolved Question 1).

**Exit criteria:** spec written, self-reviewed, and approved by the user.

### Session B3 — UX implementation (spans sessions)

**Entry criteria:** B2 spec approved.

**Work:** superpowers:writing-plans → plan in `docs/superpowers/plans/` → subagent-driven execution, the same workflow as the investor-portal sub-projects. Slice vertically (one nav/IA change or one surface per slice), each slice ends lint + `tsc` + build green and is verified live with Playwright before the next.

**Exit criteria:** spec fully implemented; every journey from B1 re-walked and measurably better (fewer steps/dead ends); CI green; CLAUDE.md workspace/layout sections updated.

---

## Conventions for every session (carry-over knowledge)

- Backend tests from repo root, venv active: `python -m unittest backend.tests.<module>`; full suite needs explicit enumeration (`python -m unittest $(ls backend/tests/test_*.py | sed 's|/|.|g; s|\.py$||' | tr '\n' ' ')`).
- Frontend: `npm run lint` + `npm run build` from `frontend/`; after A1, also `npx tsc --noEmit` and `node --test lib/*.test.mts`.
- FMP /stable/ gotcha: dump live keys before mapping any endpoint (see handoff doc §"FMP gotcha"); valuation multiples live on `ratios-ttm`, returns on `key-metrics-ttm`.
- Services consumed by routes are commit-free — callers own the session (peer_sets pattern). Background writers use `unit_of_work()` or explicit commits.
- Workflow per block: brainstorm/spec only where this doc says so; otherwise the work is already specced — go straight to plan/execute. Subagent-driven execution with per-task review is the house style.
- Update after every block: this ledger, TODO.md "Done (recent)", and auto-memory if a roadmap status changed.

## Out of scope (don't pull into this campaign)

- Investor-portal feature work: quant layer (sub-project 5), trade journal (6) — `docs/superpowers/2026-06-09-investor-portal-handoff.md`.
- Authentication, blanket mypy, frontend component/E2E test suites, structured logging — all explicitly rejected in the audit's trade-offs section with reasons; don't re-litigate.
- TODO.md "Backlog / v3" items (D3 graph viewer, Sankey, options data, 13F, etc.) unless the B2 design pulls one in deliberately.
