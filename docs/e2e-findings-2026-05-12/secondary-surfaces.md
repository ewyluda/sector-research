# Findings: secondary-surfaces

- **NOTE** — No read-through CTA found on status board (may be expected if none queued)
  - URL: `http://localhost:3000/status`
- **BUG [high]** — GET /api/outcomes → 500: Pydantic response validation fails on `narrative` field
  - URL: `http://localhost:3000/performance`
  - Root cause: response model declares `signal_snapshot.signals_row.narrative` as `float`, but the actual DB row is a dict `{summary, post_count, post_texts, ...}` (X-signal post snapshot). The frontend Performance page calls `outcomesApi.list()` which hits this endpoint — every visit to /performance fails. `outcomes/summary` works fine; only `/api/outcomes` (the list) is broken. Check the `SignalsRow` / outcomes response schema for the narrative typing.
