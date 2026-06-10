#!/usr/bin/env bash
# Launch the full dev stack: FastAPI backend on :8000 + Next.js frontend on :3000.
# Usage: ./scripts/dev.sh   (Ctrl-C stops both)
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x backend/venv/bin/uvicorn ]]; then
  echo "error: backend/venv is missing or has no uvicorn." >&2
  echo "  fix: python3 -m venv backend/venv && backend/venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi
if [[ ! -d frontend/node_modules ]]; then
  echo "error: frontend/node_modules is missing." >&2
  echo "  fix: cd frontend && npm install" >&2
  exit 1
fi
if [[ ! -f .env ]]; then
  echo "error: .env is missing at project root (backend reads secrets from there)." >&2
  exit 1
fi
if command -v pg_isready >/dev/null 2>&1 && ! pg_isready -q -h localhost -p 5432; then
  echo "warning: Postgres is not responding on localhost:5432 (try: brew services start postgresql@17)" >&2
fi

trap 'kill $(jobs -p) 2>/dev/null; wait' INT TERM

# uvicorn must run from project root so backend.app.* absolute imports resolve
backend/venv/bin/uvicorn backend.app.main:app --reload 2>&1 | sed -l 's/^/[backend]  /' &
(cd frontend && exec npm run dev) 2>&1 | sed -l 's/^/[frontend] /' &

wait
