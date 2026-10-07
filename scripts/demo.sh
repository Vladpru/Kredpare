#!/usr/bin/env bash
# Seed a separate demo database and run the API and web. Run via `make demo` (after `make up`).
# The dev database named in .env is never touched: DATABASE_URL is overridden for this script only.
set -euo pipefail
cd "$(dirname "$0")/.."

DEMO_DB="${DEMO_DB:-kredpare_demo}"
DATA_DIR="data/demo"
AS_OF="2026-09-08"

# Same server and credentials as .env, different database name. The URL is never printed.
DATABASE_URL="$(DEMO_DB="$DEMO_DB" uv run --directory backend python -c '
import os
from sqlalchemy import create_engine, make_url, text
from kredpare.core.settings import get_settings
base = make_url(get_settings().database_url)
name = os.environ["DEMO_DB"]
admin = create_engine(base, isolation_level="AUTOCOMMIT")
with admin.connect() as conn:
    if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name}):
        conn.execute(text(f"CREATE DATABASE \"{name}\""))
print(base.set(database=name).render_as_string(hide_password=False))
')"
export DATABASE_URL

uv run --directory backend alembic upgrade head
# Seed 42 is deterministic, so an existing dataset is reused; re-ingest is idempotent.
if [ ! -f "$DATA_DIR/manifest.jsonl" ]; then
  uv run kredpare-datagen --seed 42 --days 30 --out "$DATA_DIR"
fi
uv run kredpare ingest "$DATA_DIR"
uv run kredpare match --as-of "$AS_OF"
if [ -n "${GEMINI_API_KEY:-}" ] || grep -qE '^GEMINI_API_KEY=.+' .env 2>/dev/null; then
  uv run kredpare explain
else
  echo "GEMINI_API_KEY not set: skipping the workflow level"
  uv run kredpare explain --no-workflow
fi

trap 'kill 0' EXIT INT TERM
(cd backend && uv run uvicorn kredpare.api_main:app --port 8000) &
(cd web && NEXT_PUBLIC_API_URL="http://localhost:8000" pnpm dev) &
echo
echo "Demo database: $DEMO_DB"
echo "Web: http://localhost:3000   API docs: http://localhost:8000/docs   (Ctrl-C to stop)"
wait
