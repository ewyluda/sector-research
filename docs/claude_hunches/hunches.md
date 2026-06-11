# Claude Hunches & TODOs

A running log of things Claude has noticed while debugging/building in this repo but hasn't fixed yet, plus stuff flagged as "worth knowing about" and deferred items from fixes that were scoped smaller than ideal. Date-stamped; append-only.

Convention:
- **P0** = blocks core flow · **P1** = degrades feature · **P2** = nice to have · **P3** = tech debt / future direction
- `[ ]` = open · `[~]` = partial fix in place · `[x]` = resolved in a later session
- Each entry has **why it matters** and a concrete **next action** so future-Claude (or future-you) can jump in cold.

---

## 2026-04-11 · Session 1 (initial bring-up)

### P1 — CSS-variable audit across the rest of the frontend

- [ ] Audit every `.tsx` file under `frontend/app/` and `frontend/components/` for references to `var(--color-*)` — the design-token scheme that was baked into early scaffolding but **does not exist** in `globals.css`. The real palette uses `--bg`, `--surface`, `--border`, `--text`, `--text-muted`, `--text-faint`, `--primary`, `--primary-dk`, `--accent-bg`, etc.
- **Why:** found this bug twice already (`pipeline/new/page.tsx` then `pipeline/[runId]/page.tsx`) — both had wholesale `--color-*` refs that silently fell back to browser defaults. Every other page in the app probably has the same issue and just hasn't been visually inspected yet.
- **Known suspects** (not yet opened): `app/report/[runId]/page.tsx`, `app/library/page.tsx`, `app/theme/[id]/ThemeDetailClient.tsx`, the score/badge components under `components/`.
- **Canonical mapping** (for future find-and-replace): `--color-bg → --bg`, `--color-surface → --surface`, `--color-border → --border`, `--color-text-primary → --text`, `--color-text-secondary → --text-muted`, `--color-text-muted → --text-faint`, `--color-accent → --primary`, `hover:bg-[var(--color-accent)]/90 → hover:bg-[var(--primary-dk)]`.
- **Next action:** `grep -rn "var(--color-" frontend/app frontend/components` and either fix in place or flag files where the mapping isn't obvious (e.g. custom accent usage).

### P1 — Frontend `PHASE_RAIL` lists a phase that doesn't exist in the backend

- [ ] `frontend/app/pipeline/[runId]/page.tsx:10-17` hardcodes a 6-step rail including `{ key: "transcript_analysis", label: "Transcript Analysis", num: 2 }`.
- **Why it matters:** there is NO `transcript_analysis` phase in the backend graph. `backend/app/graph/pipeline.py` goes `quick_screen → deep_dive → thesis_construction → risk_stress_test → position_monitor`. `backend/app/services/pipeline.py::PHASE_META` also has no `transcript_analysis`. The rail step will never activate and `PHASE_RAIL.findIndex((p) => p.key === currentPhase)` is fragile — if currentPhase is `"deep_dive"`, the index-compare logic for the "done" checkmarks might mark Transcript Analysis as "done" purely because its index (1) is lower than deep_dive's index (2). Looks accidentally correct but is coincidence, not design.
- **Next action:** pick one of:
  1. Remove `transcript_analysis` from the rail entirely (fastest). Rail becomes 5 steps.
  2. Actually implement a `transcript_analysis` phase in the backend graph (the skills/due-diligence methodology references it — it's a 6-pass earnings forensics routine that was in `pipeline/new/page.tsx`'s old phase preview).
- If going with #2, the current `get_earnings_transcript` FMP method is already wired up but has never been exercised through the graph.

### P2 — PE ratio is always `None` on company cards

- [ ] `/stable/profile` and `/stable/quote` don't include `pe` on FMP's new API. I wired up `FMPClient.get_key_metrics_ttm()` (that endpoint DOES expose PE) but `services/discovery.py` doesn't call it — `FMPSnapshot.pe_ratio` is hardcoded to `None`.
- **Why:** cosmetic for now. `compute_fundamental_quality_score` never actually used `pe_ratio` (it's in the signature but the body only uses roic/gross_margin/revenue_growth), so scoring is unaffected. But the UI displays `—` for PE on every card.
- **Next action:** either (a) in `_fetch_company_fundamentals`, add a 5th parallel fetch for `get_key_metrics_ttm(ticker)` and pull `peRatioTTM` from the result; or (b) drop PE from the card UI entirely.

### P1 — Options flow is stubbed (`get_options_flow` returns `[]`)

- [x] Stubbed in this session — `backend/app/clients/fmp.py::get_options_flow` logs a warning and returns an empty list with a Tier-2 "unavailable" citation.
- **Why still on the list:** when the Deep Dive phase runs Phase 3 Category 5 (`05-technical-market-structure`), the `options-flow` subcategory will have no data and its score will collapse to whatever the prompt does when facts are missing. The user hasn't exercised Deep Dive end-to-end yet, so we don't know how degraded it looks in practice.
- **Next action:** when/if the user gets to Deep Dive and sees degradation, pick one:
  1. Upgrade FMP subscription tier (check if `/stable/` ever exposes options).
  2. Swap in an alternative provider: Unusual Whales, Cheddar Flow, Market Chameleon, Tradytics. Any would need new client methods + API key wiring.
  3. Remove options-flow from the `05-technical-market-structure` category entirely and rely on volume/trend/support-resistance signals only.

### P2 — Non-streaming phases (`risk_stress_test`, `position_monitor`) haven't been tested end-to-end

- [ ] The Quick Screen fix I applied to `pipeline/[runId]/page.tsx` (seed `tokens` from persisted `phase_outputs` + from `interrupt` event's `output.content`) should cover all three non-streaming phases, but only Quick Screen has been run so far.
- **Why:** same bug class — if the frontend fix doesn't correctly match the content shape for those phases, the user will see "Waiting for output…" again.
- **Next action:** when testing, drive a run through to risk_stress_test and position_monitor and confirm content renders.

### P1 — Theme creation form is missing `parent_theme_id` and `signal_weights` fields

- [ ] `frontend/app/theme/new/page.tsx` only collects name, description, seed_tickers, x_search_terms, screener_criteria. The backend `ThemeCreate` schema supports `parent_theme_id` (sub-themes) and `signal_weights` (40/40/20 default), but there's no UI to set them.
- **Why it matters:** the dashboard has a "Sub-themes" section that will remain empty forever unless we add sub-theme support. Signal weights are more niche but the point of having them as theme-level config is that users can tune them per theme.
- **Next action:** add a `parent_theme_id` dropdown (populated from `themes.list()`) and 3 numeric inputs for signal weights with a validator that enforces `sum === 1.0`. Or keep it as a "defaults only" v1 and add later.

### P1 — LLM-powered theme → screener translation (proper fix for Bug 2)

- [~] This session patched the "empty criteria returns garbage" bug by skipping the FMP screener when no filter keys are set. But that means users with no criteria get *only* their seed tickers — no expansion of the universe at all. That's acceptable short-term but not ideal.
- **Proper fix:** at theme-create time, call Claude Haiku with the theme name + description and ask it to emit a `screener_criteria` JSON object (sector, industry, market cap bounds). This bridges the semantic → structured gap that FMP's screener alone can't handle.
- **Even better:** after fetching candidate tickers (seeds + screener), run them through a quick Haiku relevance filter that scores each ticker vs. the theme name and drops the bottom quartile. This catches issues where the sector filter is too broad (e.g. "Industrials" pulls in 1000 unrelated companies).
- **Next action:** prototype in `services/discovery.py`. Start with the create-time criteria generator — it's a 1-shot Haiku call and the output is structured JSON.
- **Caveats:** may blur multi-sector themes (Power & Energy Bottleneck spans Industrials + Utilities + Technology — no single sector filter covers it). Relevance-filter approach is more robust for cross-sector themes.

### P2 — FMP API key is logged in every request URL

- [ ] `backend/app/clients/fmp.py::_request` passes `apikey` as part of the `params` dict, and httpx logs the full URL at INFO level:
  ```
  INFO:httpx:HTTP Request: GET https://financialmodelingprep.com/stable/profile?symbol=NVDA&apikey=REDACTED "HTTP/1.1 200 OK"
  ```
- **Why it matters:** the key ends up in terminal output, log files, and potentially crash reports. Anyone with log access gets the key. Already happened in this session's transcript multiple times.
- **Next action:** wire httpx with an `event_hooks={"request": [redact_apikey_in_logs]}` handler, OR pass `apikey` via an `X-API-KEY` header if FMP supports it, OR lower the httpx logger to WARN globally. Cleanest: install a `logging.Filter` on the `httpx` logger that regex-redacts `apikey=[^&\s]+`.

### P2 — SSE stream reliability is fragile (in-memory single-subscriber)

- [ ] `services/pipeline.py::PipelineService._streams` is a `dict[run_id, asyncio.Queue]`. Only the most recent subscriber wins (later `subscribe` calls silently replace earlier ones). Events emitted between when `POST /api/runs` returns and when the client's `EventSource` connects are **dropped** — the `_emit` method checks `if run_id in self._streams` and discards otherwise.
- **Why it matters:** this is WHY the Quick Screen render bug manifested — the Quick Screen phase ran and emitted an `interrupt` event in 8 seconds, but the user's browser might not have connected SSE that fast. The event got dropped. My fix (seed tokens from persisted phase_outputs on initial load) works around this, but the underlying SSE reliability issue remains for real-time event delivery.
- **Follow-on risks:**
  - Multiple browser tabs of the same run collide and cross-replace each other's streams.
  - Server restart mid-run → in-memory queue lost → client never sees events (only state persisted to PG is recoverable).
  - Long-running phases (deep_dive, 90s/category × 9 categories) emit many token events; a momentarily-disconnected client loses all of them.
- **Next action:** either (a) persist SSE events to Postgres (event log table) and replay on subscribe, (b) switch to polling with `ETag`/`If-Modified-Since` + long-poll, or (c) accept the fragility and rely on state persistence + page-refresh to recover. Option (c) is basically what I did; (a) is the most robust.

### P2 — Every Theme Detail page load triggers a full FMP fan-out

- [ ] `GET /theme/[id]` is `dynamic = "force-dynamic"` and calls `discovery.run(id)` server-side on every request. For a theme with 50 tickers, that's 50 × 4 FMP calls per page view (income, balance, cashflow, profile). The in-memory FMP client cache (24h TTL) mitigates repeat calls within the process lifetime, but:
  - Any backend restart blows the cache.
  - Multiple browser tab reloads within the TTL are cheap, but the cold first render is ~8 seconds for 50 tickers.
- **Why it matters:** FMP rate limits exist even on ultimate tier; slow first render is user-visible.
- **Next action:** cache the DiscoveryResult to Postgres with a short TTL (e.g. 15 min), keyed by theme_id. On request, serve from cache and async-refresh in the background (stale-while-revalidate). Or move discovery.run to a client-side fetch with React Suspense so the page shell renders instantly.

### P3 — No test framework configured

- [ ] No pytest setup in backend, no jest/vitest in frontend, no smoke tests anywhere. Every bug in this session was caught by manually hitting a URL.
- **Next action:** install pytest + `pytest-asyncio`. Start with API-level smoke tests: `POST /api/themes`, `GET /api/themes/{id}/discover`, `POST /api/runs` + poll for `awaiting_approval`. Frontend can wait.

### P3 — Python 3.12+ floor is not enforced

- [ ] Fresh setup creates a venv with whatever `python3` is on PATH. System Python (3.9) hits PEP 604 union-type syntax errors (`str | None`). Already caused a 5-minute detour this session.
- **Next action:** add `.python-version` pointing at `3.12`, or add `python_requires=">=3.10"` to `requirements.txt` via a pyproject.toml, or document the minimum in CLAUDE.md's "Common commands" section.

### P3 — Alembic/uvicorn require running from project root (absolute-import quirk)

- [ ] Backend uses absolute imports (`from backend.app.config import ...`), so:
  - `uvicorn` must be launched from project root (documented in CLAUDE.md).
  - `alembic` command needs `PYTHONPATH=..` or `cd backend && PYTHONPATH=.. alembic upgrade head`.
- Neither is self-evident to a fresh developer (or fresh Claude).
- **Next action:** either add a `Makefile` / `justfile` / shell script that wraps both commands with the right cwd + PYTHONPATH, or `pip install -e .` with a minimal `pyproject.toml` so the package resolves via installed path instead of filesystem layout.

### P3 — Dead `backend/.env` file and stale comment in project-root `.env`

- [ ] `backend/.env` is a duplicate env file with different DB credentials (`postgres:postgres`) from project-root `.env` (`ericwyluda:postgres`). Only project-root is read (after my `config.py` fix). The backend file is dead weight.
- [ ] Project-root `.env` has a stale comment: `# In sector-research/app/backend/.env, change both DB lines to:` — references the pre-restructure layout.
- **Why it matters:** confusing for anyone else (or future Claude) who sees two .env files and tries to reconcile. Not blocking.
- **Next action:** delete `backend/.env`, delete the stale comment from root `.env`.

### P3 — Turbopack persistent-cache gets re-poisoned if project moves again

- [ ] Turbopack writes absolute paths into `.next/dev/cache/turbopack/*.sst`. If the project ever moves again, those SST files will have stale paths baked in → HMR panic loop (exactly what happened this session). The fix is `rm -rf .next`, but the trap is silent until you open a browser.
- **Next action:** either (a) document in CLAUDE.md the "if you moved the project, rm -rf frontend/.next" rule, or (b) add a `predev` npm script that stats a pinned file and removes `.next` if it's from a different location. Cheaper to just document.

### P3 — APScheduler daily job unverified (runs at 2 AM, never exercised)

- [ ] `backend/app/main.py::lifespan` registers `run_daily_refresh` to fire daily at 2 AM local time. For each theme it loops over `seed_tickers + known_tickers` and calls X API for velocity, narrative, discovery signals — 3 signals per ticker × 25 tickers × 5 themes = ~375 X API calls per run. With a 2-second inter-call sleep that's ~12 minutes. Rate limits not yet validated.
- **Why it matters:** X API v2 basic tier has strict limits. Unverified job could blow the rate budget in one run.
- **Next action:** trigger the job manually once via the `/api/themes/{id}/signals/refresh` endpoint (which exists per `api/discovery.py`) and validate: (a) does it complete without 429s, (b) are the signals actually populated in the `signals` table, (c) does the `SurpriseAlert` detection fire correctly.

### P3 — LangGraph's interrupt mechanism is hand-rolled, not real

- [ ] The "human-in-the-loop interrupt" at each phase boundary is NOT `interrupt()` from LangGraph — it's a status-flag pattern. Each node sets `state.status = "awaiting_approval"`, the conditional edge returns `END`, and `services/pipeline.py::_next_phase` computes the next phase when the user hits `/advance`. Routing logic is duplicated between `graph/pipeline.py` (the compiled edges) and `services/pipeline.py` (the advance logic).
- **Why it matters:** adding a new phase means editing routing in TWO places; they can drift. Also, real LangGraph `interrupt()` integrates with checkpointing so resumption is automatic — here it's manual.
- **Next action:** consider refactoring to LangGraph's native `interrupt()` + `Command(resume=...)` once the core flow is stable. Non-urgent.

### P3 — Stale plan / spec files deleted from working tree but still referenced by README

- [ ] `git status` shows ~70 files deleted under `docs/superpowers/plans/`, `docs/superpowers/specs/`, and `skills/due-diligence/*`. The README still links to `docs/superpowers/specs/2026-04-10-sector-research-app-design.md` etc. The files are recoverable via `git show HEAD:path`.
- **Next action:** either commit the deletions and update README links, or `git restore` them. Currently in "limbo" where the working tree says deleted but they're still in HEAD.

---

## Ideas parked for later (no action yet)

- **Auto-generated screener criteria from theme intent** — see "LLM-powered theme → screener translation" above. The meta-idea: lean on LLMs to bridge the semantic→structured gap that FMP's structured API can't.
- **LLM-powered company relevance filter** — second-pass scoring of FMP screener results against theme prompt before they enter the Discovery card list.
- **Citation verification** — currently the `Citation.source_url` string is constructed client-side by the FMP client; there's no verification that the URL actually resolves. A Claude pass that "clicks" a random subset of citations would catch drift if FMP ever re-renames paths again.
- **Theme sub-themes** — the DB schema supports `parent_theme_id` FK and the dashboard UI has a "Sub-themes" grid, but there's no UI path to create one. When enabled, discovery for the parent should union seed tickers across parent + all sub-themes.
- **Obsidian export** — pipeline API has an `/api/runs/{id}/report` endpoint that returns an `obsidian` block in the response, but no UI "Export to Obsidian" button or downloader. Exists in backend, orphaned in frontend.
- **Research Library page** — `app/library/page.tsx` exists but hasn't been opened yet this session. May be stubbed or may have the same CSS-var issue.
