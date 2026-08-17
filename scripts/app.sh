#!/usr/bin/env bash
set -euo pipefail

if [[ ! -d .venv ]]; then
  echo "Missing .venv. Run ./scripts/setup.sh first." >&2
  exit 1
fi

source .venv/bin/activate
exec python -m streamlit run app.py
