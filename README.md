# Retail SPY Limit-Order Research

An auditable research workspace for finding practical buy-limit distances below the preceding SPY close using **real daily OHLCV data**.

The repository retains the older monthly S&P 500 allocation engine, but every Jupyter notebook now uses the real daily path. Monthly Shiller averages cannot establish whether a daily limit order filled.

## Data source

The daily workflow uses Twelve Data's official `1day` SPY OHLCV endpoint.

Default window:

```text
2007-06-01 through the latest available trading session
```

The request explicitly asks for 5,000 rows, validates OHLC relationships, rejects duplicate and future-dated sessions, checks for likely truncation, and caches the result at:

```text
data/processed/spy_daily_1day.csv
```

The first fetch requires:

```bash
export TWELVE_DATA_API_KEY="your-key"
```

Later runs use the ignored local cache unless refresh is requested.

## Limit-order assumptions

For each eligible session `t`:

```text
limit[t] = close[t-1] × (1 - discount)
```

Execution rules:

1. If `open[t] <= limit[t]`, fill at the opening price.
2. Otherwise, if `low[t] <= limit[t]`, fill at the limit.
3. Otherwise, keep the cash lot pending and reprice from the next preceding close.
4. When the configured waiting horizon expires, buy at that session's close.

The recurring model separately tracks the initial lump sum and subsequent monthly contribution lots. It compares each lot with buying at the first eligible session's open.

Current calculations deliberately exclude dividends, cash yield, spreads, fees, taxes, and SGD/USD effects. These omissions must be resolved before using a candidate as a live policy.

## Setup

```bash
./scripts/setup_jupyter.sh
export TWELVE_DATA_API_KEY="your-key"
```

## Run all daily research from the terminal

```bash
./scripts/run_daily_limit_research.sh
```

Equivalent direct command:

```bash
source .venv/bin/activate
sp500-limit-orders
```

Refresh the cached market data:

```bash
sp500-limit-orders --refresh
```

Example parameter run:

```bash
sp500-limit-orders \
  --discount-min 0.000 \
  --discount-max 0.030 \
  --discount-step 0.001 \
  --max-wait-sessions 5 \
  --train-years 5 \
  --test-years 1
```

Outputs:

```text
results/daily_limits/one_session_grid.csv
results/daily_limits/recurring_grid.csv
results/daily_limits/walk_forward.csv
results/daily_limits/summary.json
```

## Jupyter notebooks

Start JupyterLab:

```bash
source .venv/bin/activate
jupyter lab
```

Select the `Retail Portfolio Backtesting` kernel.

All notebooks now use real daily SPY data:

1. `01_strategy_comparison.ipynb` — source audit and daily dip distribution.
2. `02_parameter_experiments.ipynb` — limit-distance and expiry grids.
3. `03_rolling_window_analysis.ipynb` — walk-forward out-of-sample selection.
4. `04_limit_order_research.ipynb` — candidate sensitivity and contribution-lot trace.

Notebook names are retained to avoid breaking existing links, but their contents are now daily-limit research.

## Legacy monthly allocation CLI

The older monthly research remains available as a separate path:

```bash
sp500-backtest --output results/monthly
```

It is not used by the notebooks and is not suitable for testing daily limit fills. Its strategy-comparison mathematics remains under audit.

## Validation

```bash
python -m pytest -q
python -m compileall -q src
python -m json.tool notebooks/01_strategy_comparison.ipynb >/dev/null
python -m json.tool notebooks/02_parameter_experiments.ipynb >/dev/null
python -m json.tool notebooks/03_rolling_window_analysis.ipynb >/dev/null
python -m json.tool notebooks/04_limit_order_research.ipynb >/dev/null
bash -n scripts/setup_jupyter.sh
bash -n scripts/run_daily_limit_research.sh
```

No automatic GitHub Actions workflow is included.
