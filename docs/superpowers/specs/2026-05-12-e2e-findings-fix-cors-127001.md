# Fix: CORS allow-list omits `http://127.0.0.1:3000`

**Source:** e2e finding 2026-05-12 (global-shell, POLISH [med]).
**Status:** Validated. Reproduces whenever the user opens the frontend at `http://127.0.0.1:3000` instead of `http://localhost:3000`.

## Problem

`backend/app/config.py:37` declares:

```python
cors_origins: list[str] = ["http://localhost:3000"]
```

The browser treats `127.0.0.1` and `localhost` as different origins. When the frontend page is served from `http://127.0.0.1:3000` (Playwright defaults to it; the dev server prints both URLs at startup; users who pin to it for IPv4 lookup speed land here), every `fetch()` to the backend gets blocked with "Failed to fetch" and the page falls back to its empty state with no useful console message beyond the CORS preflight rejection.

This has already been logged twice as a separate incident (2026-05-10 and 2026-05-12). Time to fix the config rather than the workaround.

## Root cause

Single-origin allow-list in `cors_origins`. The browser sends `Origin: http://127.0.0.1:3000`; `CORSMiddleware` (configured via `app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, ...)`) rejects.

Note: this is independent of `NEXT_PUBLIC_API_URL`. The user already pins `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` (per the Docker IPv6 collision memory) so the *backend* hostname matches; the issue is the *frontend page origin* that the browser stamps onto every CORS preflight.

## Fix

Add `http://127.0.0.1:3000` to the default list in `backend/app/config.py:37`:

```python
cors_origins: list[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
```

Two origins is enough for this personal-tool use case — no need to wildcard or read from `.env`. If the user ever serves the frontend on another port or host, they can override `cors_origins` via the env file (pydantic-settings will parse a JSON list out of `CORS_ORIGINS=...`).

## Verification

1. Restart uvicorn.
2. `curl -i -X OPTIONS http://127.0.0.1:8000/api/themes -H "Origin: http://127.0.0.1:3000" -H "Access-Control-Request-Method: GET"` returns `Access-Control-Allow-Origin: http://127.0.0.1:3000`.
3. Same for `http://localhost:3000` (regression — must still work).
4. Browser: load `http://127.0.0.1:3000/`, network tab shows `/api/themes` succeeds with the matching `Access-Control-Allow-Origin` header.

## Out of scope

- Whether to expand to `http://localhost:*` / `http://127.0.0.1:*` wildcards. Not needed today; two explicit origins keeps the surface small.
- The Next.js dev server behavior of binding to both `localhost` and `127.0.0.1` is upstream and not worth fighting — fix the backend.
