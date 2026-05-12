# Findings: global-shell

- **BUG [med]** — Console error: Failed to load resource: the server responded with a status of 404 (Not Found)
  - URL: `http://localhost:3000/this-route-does-not-exist`
- **POLISH [med]** — Backend CORS allow-list excludes `http://127.0.0.1:3000`
  - URL: `http://127.0.0.1:3000/*`
  - `backend/app/config.py:37` defines `cors_origins: list[str] = ["http://localhost:3000"]`. Browsers treat `127.0.0.1` and `localhost` as different origins, so visiting the frontend at `127.0.0.1:3000` silently breaks every API call (Failed to fetch). Suggest adding `http://127.0.0.1:3000` to the allow-list so both work. NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 (per Docker-IPv6 memory note) is unaffected — the issue is the *frontend* page origin, not the API.
