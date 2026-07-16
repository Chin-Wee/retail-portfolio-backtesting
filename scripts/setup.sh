#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3.11}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  PYTHON_BIN=python3
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit("Python 3.11 or newer is required")
PY

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m ipykernel install \
  --user \
  --name retail-portfolio \
  --display-name "Retail Portfolio Lab"
mkdir -p data results/portfolio

cat <<'EOF'
Setup complete.

First live-data run:
  export TWELVE_DATA_API_KEY="your-key"
  source .venv/bin/activate
  jupyter lab

Terminal equivalent:
  ./scripts/run.sh
EOF
