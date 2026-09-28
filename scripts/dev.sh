#!/usr/bin/env bash
# Local development: build the DB from the seed if missing, then run uvicorn with reload on :8000.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export DATABASE_PATH="${DATABASE_PATH:-data/app.db}"

if [[ ! -f "$DATABASE_PATH" ]]; then
  echo "[dev] $DATABASE_PATH not found; importing seed catalogue"
  python -m app.pipeline.importer data/seed/seed_catalogue.csv \
    --source seed --licence "seed; approximate; prototype only" --replace --db "$DATABASE_PATH"
fi

exec uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
