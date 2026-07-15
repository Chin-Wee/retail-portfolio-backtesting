#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d .venv ]]; then
  echo "Missing .venv. Run ./scripts/setup_jupyter.sh first." >&2
  exit 1
fi

source .venv/bin/activate

CACHE_PATH="${CACHE_PATH:-data/processed/spy_daily_1day.csv}"
if [[ ! -f "$CACHE_PATH" && -z "${TWELVE_DATA_API_KEY:-}" ]]; then
  echo "Set TWELVE_DATA_API_KEY for the first daily-data fetch." >&2
  exit 1
fi

exec sp500-limit-orders --cache "$CACHE_PATH" "$@"
