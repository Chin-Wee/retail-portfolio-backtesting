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
  --name retail-portfolio-backtesting \
  --display-name "Retail Portfolio Backtesting"

mkdir -p data/processed results/daily_limits

cat <<'EOF'

Setup complete.

Real daily research requires a Twelve Data API key on the first fetch:
  export TWELVE_DATA_API_KEY="your-key"

Run the reproducible command-line research with Calmar walk-forward selection:
  source .venv/bin/activate
  ./scripts/run_daily_limit_research.sh  # runs sp500-limit-orders

Open the graph notebooks:
  source .venv/bin/activate
  jupyter lab

Dedicated Calmar notebook:
  notebooks/05_calmar_ratio_exploration.ipynb
EOF
