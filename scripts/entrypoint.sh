#!/usr/bin/env bash
# Container entrypoint: seed the SQLite catalogue on first boot only, then start uvicorn.
# The DB lives on a persistent Azure Files mount (/data) in Azure, so restarts never re-import.
set -euo pipefail

cd "$(dirname "$0")/.."

export DATABASE_PATH="${DATABASE_PATH:-data/app.db}"
export PORT="${PORT:-8000}"

SEED_CSV="${SEED_CSV:-data/seed/seed_catalogue.csv}"
SEED_LICENCE="seed; approximate; prototype only"
KAGGLE_LICENCE="scraped; prototype only; not for commercial use"

perfume_count() {
  # Prints the number of perfumes; a missing file, missing table or unreadable DB counts as 0.
  python - "$1" <<'PY'
import os, sqlite3, sys
path = sys.argv[1]
n = 0
if os.path.exists(path) and os.path.getsize(path) > 0:
    try:
        con = sqlite3.connect(path, timeout=30)
        n = con.execute("SELECT COUNT(*) FROM perfume").fetchone()[0]
        con.close()
    except sqlite3.Error:
        n = 0
print(n)
PY
}

mkdir -p "$(dirname "$DATABASE_PATH")"
[[ -n "${IMAGE_CACHE_DIR:-}" ]] && mkdir -p "$IMAGE_CACHE_DIR" || true

count="$(perfume_count "$DATABASE_PATH")"
if [[ "$count" -eq 0 ]]; then
  # Build on fast container-local disk, then move into place in one step. A restart mid-import leaves the
  # persistent DB untouched (still empty), so the next boot simply re-runs the import.
  BUILD_DIR="$(mktemp -d)"
  BUILD_DB="$BUILD_DIR/app.db"
  echo "[entrypoint] catalogue at $DATABASE_PATH is empty; importing seed"
  python -m app.pipeline.importer "$SEED_CSV" \
    --source seed --licence "$SEED_LICENCE" --replace --db "$BUILD_DB"

  shopt -s nullglob
  raw=(data/raw/*.csv)
  cleaned=(data/raw/*cleaned*.csv)
  shopt -u nullglob
  # The Kaggle zip ships a raw and a cleaned file of the same perfumes; import only the cleaned one when present.
  if [[ ${#cleaned[@]} -gt 0 ]]; then raw=("${cleaned[@]}"); fi
  for csv in ${raw[@]+"${raw[@]}"}; do
    echo "[entrypoint] importing $csv"
    # A bad optional CSV must not stop the app from booting on the seed catalogue.
    python -m app.pipeline.importer "$csv" \
      --source kaggle-fragrantica --licence "$KAGGLE_LICENCE" --db "$BUILD_DB" \
      || echo "[entrypoint] WARNING: import of $csv failed; continuing with what is loaded" >&2
  done

  # Fold the WAL into the main file so one file can be copied, then swap it in.
  python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.execute('PRAGMA journal_mode=DELETE'); c.close()" "$BUILD_DB"
  rm -f "$DATABASE_PATH-wal" "$DATABASE_PATH-shm" "$DATABASE_PATH-journal"
  cp "$BUILD_DB" "$DATABASE_PATH.tmp"
  mv -f "$DATABASE_PATH.tmp" "$DATABASE_PATH"
  rm -rf "$BUILD_DIR"
  echo "[entrypoint] catalogue now has $(perfume_count "$DATABASE_PATH") perfumes"
else
  echo "[entrypoint] catalogue at $DATABASE_PATH already has $count perfumes; skipping import"
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --proxy-headers --forwarded-allow-ips='*'
