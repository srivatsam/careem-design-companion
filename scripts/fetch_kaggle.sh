#!/usr/bin/env bash
# Downloads the Fragrantica dataset from Kaggle into data/raw/ and unzips it.
# Optional auth: export KAGGLE_USERNAME=... KAGGLE_KEY=... (from kaggle.json).
# Licence: scraped data, prototype use only, not for commercial use.
set -euo pipefail

cd "$(dirname "$0")/.."

URL="https://www.kaggle.com/api/v1/datasets/download/olgagmiufana1/fragrantica-com-fragrance-dataset"
OUT_DIR="data/raw"
ZIP="$OUT_DIR/fragrantica.zip"

mkdir -p "$OUT_DIR"

auth=()
if [[ -n "${KAGGLE_USERNAME:-}" && -n "${KAGGLE_KEY:-}" ]]; then
  auth=(-u "${KAGGLE_USERNAME}:${KAGGLE_KEY}")
fi

echo "Downloading $URL -> $ZIP"
curl -fL --retry 3 ${auth[@]+"${auth[@]}"} -o "$ZIP" "$URL"

echo "Unzipping into $OUT_DIR/"
if command -v unzip >/dev/null 2>&1; then
  unzip -o "$ZIP" -d "$OUT_DIR"
else
  python3 -m zipfile -e "$ZIP" "$OUT_DIR"
fi

# Flatten: the entrypoint only imports data/raw/*.csv.
find "$OUT_DIR" -mindepth 2 -type f -name '*.csv' -exec mv -f {} "$OUT_DIR"/ \;

echo
echo "CSV files in $OUT_DIR:"
ls -1 "$OUT_DIR"/*.csv 2>/dev/null || echo "  (none found; check the archive contents)"
echo
echo "Import with (repeat per CSV):"
echo "  python -m app.pipeline.importer $OUT_DIR/<file>.csv --source kaggle-fragrantica \\"
echo "    --licence \"scraped; prototype only; not for commercial use\" --db \${DATABASE_PATH:-data/app.db}"
echo "Add --replace to wipe the existing catalogue first."
