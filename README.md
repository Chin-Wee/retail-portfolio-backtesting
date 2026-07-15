# Retail SPY Limit-Order Research

An auditable research workspace for finding practical SPY buy-limit distances using **real daily OHLCV data**, recurring contribution lots, walk-forward testing, drawdown analysis, and Calmar ratio exploration.

The repository retains the older monthly S&P 500 allocation engine, but every Jupyter notebook uses the real daily path. Monthly averages cannot establish whether a daily limit order filled.

## Calmar ratio

The daily workflow calculates:

```text
Calmar ratio = annualized compounded return / |maximum drawdown|
```

Returns come from a **contribution-neutral daily wealth index**. Deposits are removed from the return calculation before compounding, so a new contribution cannot hide a portfolio drawdown.

A path with no observed drawdown has an undefined Calmar ratio and is reported as `NaN`, not infinity.

The immediate-open baseline is calculated with the same contributions and dates, allowing direct comparisons of:

- annualized compounded return;
- maximum drawdown;
- Calmar ratio;
- terminal excess value;
- fill and forced-execution rates.

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
4. When the waiting horizon expires, buy at that session's close.

The recurring model separately tracks the initial lump sum and subsequent monthly contribution lots. It compares each lot with buying at the first eligible session's open.

Current calculations deliberately exclude dividends, cash yield, spreads, fees, taxes, and SGD/USD effects. These omissions affect both return and Calmar results and must be resolved before treating a candidate as a live policy.

## Setup

```bash
./scripts/setup_jupyter.sh
export TWELVE_DATA_API_KEY="your-key"
```

## Run the daily research and graphs

```bash
./scripts/run_daily_limit_research.sh
```

The runner defaults walk-forward selection to Calmar ratio. Override it with:

```bash
SELECTION_METRIC=ending_excess_value ./scripts/run_daily_limit_research.sh
```

Equivalent direct command:

```bash
source .venv/bin/activate
sp500-limit-orders --selection-metric calmar_ratio
```

Example parameter run:

```bash
sp500-limit-orders \
  --discount-min 0.000 \
  --discount-max 0.030 \
  --discount-step 0.001 \
  --max-wait-sessions 5 \
  --train-years 5 \
  --test-years 1 \
  --selection-metric calmar_ratio
```

## Generated data and graphs

```text
results/daily_limits/one_session_grid.csv
results/daily_limits/strategy_grid.csv
results/daily_limits/strategy_comparison_metrics.csv
results/daily_limits/strategy_comparison_curves.csv
results/daily_limits/walk_forward.csv
results/daily_limits/calmar_candidate_lots.csv
results/daily_limits/calmar_candidate_equity_curve.csv
results/daily_limits/summary.json

results/daily_limits/calmar_by_discount.html
results/daily_limits/return_vs_drawdown.html
results/daily_limits/calmar_candidate_wealth.html
results/daily_limits/calmar_candidate_drawdown.html
results/daily_limits/strategy_calmar_ranking.html
results/daily_limits/strategy_return_vs_drawdown.html
results/daily_limits/strategy_wealth_comparison.html
results/daily_limits/strategy_drawdown_comparison.html
results/daily_limits/walk_forward_selected_discount.html
results/daily_limits/walk_forward_test_calmar.html
```

Open the graphs on macOS:

```bash
open results/daily_limits/calmar_by_discount.html
open results/daily_limits/return_vs_drawdown.html
open results/daily_limits/calmar_candidate_wealth.html
open results/daily_limits/calmar_candidate_drawdown.html
open results/daily_limits/strategy_calmar_ranking.html
open results/daily_limits/strategy_return_vs_drawdown.html
open results/daily_limits/strategy_wealth_comparison.html
open results/daily_limits/strategy_drawdown_comparison.html
results/daily_limits/strategy_calmar_ranking.html
results/daily_limits/strategy_return_vs_drawdown.html
results/daily_limits/strategy_wealth_comparison.html
results/daily_limits/strategy_drawdown_comparison.html
open results/daily_limits/walk_forward_test_calmar.html
```

## Jupyter notebooks

```bash
source .venv/bin/activate
jupyter lab
```

Select the `Retail Portfolio Backtesting` kernel.

1. `01_strategy_comparison.ipynb` — real daily source audit and downside-excursion graphs.
2. `02_parameter_experiments.ipynb` — limit-distance, expiry, Calmar, return, and drawdown graphs.
3. `03_rolling_window_analysis.ipynb` — Calmar-selected walk-forward graphs on unseen years.
4. `04_limit_order_research.ipynb` — final charts comparing immediate investment, fixed pullbacks, terminal-value winners, Calmar winners, and the walk-forward candidate.
5. `05_calmar_ratio_exploration.ipynb` — dedicated Calmar sensitivity and top-strategy chart exploration.


## Final strategy dashboard

The main visual output is `notebooks/04_limit_order_research.ipynb` and the four matching HTML files:

- Calmar ranking across named investment strategies;
- annualized return versus maximum drawdown;
- contribution-neutral wealth paths;
- drawdown paths through time.

The compared strategies include immediate investment, simple fixed pullback rules, the full-sample terminal-value winner, the full-sample Calmar winner, and the median walk-forward candidate. Full-sample winners are labelled as in-sample research results.

## Legacy monthly allocation CLI

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
python -m json.tool notebooks/05_calmar_ratio_exploration.ipynb >/dev/null
bash -n scripts/setup_jupyter.sh
bash -n scripts/run_daily_limit_research.sh
```

No automatic GitHub Actions workflow is included.
