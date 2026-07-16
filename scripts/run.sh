#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d .venv ]]; then
  echo "Missing .venv. Run ./scripts/setup.sh first." >&2
  exit 1
fi
source .venv/bin/activate

if [[ ! -f data/spy_daily.csv && -z "${TWELVE_DATA_API_KEY:-}" ]]; then
  echo "Set TWELVE_DATA_API_KEY for the first live-data fetch." >&2
  exit 1
fi

exec retail-portfolio "$@"
