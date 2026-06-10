# backend/scripts

Manual, on-demand scripts. Nothing here runs in CI.

- `backfill_catalysts.py`, `backfill_outcomes.py` — one-shot data backfills against the live DB.
- `smoke_model_state.py` — pure Pydantic schema smoke check (no DB, LLM, or network).
- `smoke_model_baseline.py` — mocks the LLM call but hits the live DB to load a seeding run.
- `smoke_model_e2e.py` — real-DB E2E smoke; makes a real Sonnet API call and fetches real FMP/FRED data.
- `smoke_models_api.py` — spins up the FastAPI app via TestClient with the DB overridden to null results.
- `smoke_earnings_navigator.py`, `smoke_question_log.py`, `smoke_read_through.py` — smoke checks that
  exercise live DB integrations.

The pure-math and parser smoke/verify scripts that used to live here were converted to
CI-run unittest modules in `backend/tests/` (2026-06-10): `test_dcf`, `test_model_balancing`,
`test_reverse_dcf`, `test_model_diff`, `test_parser_*`, `test_status_board_sql`.
