# Retail S&P 500 Backtesting

A small, auditable framework for comparing long-only S&P 500 ETF/cash strategies through the CLI or thin Jupyter notebooks.

Default portfolio assumptions:

- **$100,000 initial cash**
- **$1,000 contributed at the start of each subsequent month**
- fractional ETF units and reinvested dividends
- ETF exposure constrained to 0%–100%
- no leverage or shorting
- zero cash return by default, configurable per run

## Data architecture

### Canonical long-history backtests

Robert Shiller's monthly `ie_data.xls` dataset is the canonical source:

```text
https://www.econ.yale.edu/~shiller/data/ie_data.xls
```

It combines price, dividends, earnings, CPI, long interest rates and CAPE. The framework derives ordinary P/E, yields, inflation, total-return approximations, real returns, moving averages and realized volatility.

The formally constituted 500-stock S&P 500 began in 1957. Earlier observations represent a reconstructed predecessor U.S. large-cap composite rather than the same investable ETF.

The Shiller dividend series is annualised/interpolated. Monthly reinvestment is approximated as:

```text
monthly total return = (price_t + dividend_t / 12) / price_(t-1) - 1
```

### Risk-free input

Fractional Kelly requires FRED `TB3MS`, a monthly three-month Treasury-bill series:

```text
https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS
```

The loader converts percentages to annual decimals and does not manufacture observations before the FRED series begins.

### Current quote

A current SPY quote can be read from Twelve Data. This operational path does not replace Shiller as the historical backtest source.

```bash
export TWELVE_DATA_API_KEY=...
sp500-backtest --live-quote --live-symbol SPY
```

## Hotswappable strategies

| Key | Strategy | Data requirement | Execution lag |
|---|---|---|---:|
| `buy-hold` | 100% ETF buy-and-hold | monthly price and total return | 0 months |
| `staged-buy-hold-6m` | Six-month deterministic deployment ramp | monthly price and total return | 0 months |
| `fixed-60-40` | 60% ETF / 40% cash | monthly price and total return | 0 months |
| `trend-10m` | 10-month moving average with 1% hysteresis | monthly price and total return | 1 month |
| `vol-target-12` | 12% annualized volatility target | monthly price and total return | 1 month |
| `trend-vol-12` | Trend gate plus 12% volatility target | monthly price and total return | 1 month |
| `fractional-kelly` | Quarter-Kelly ceiling, 60-month estimate | total return and FRED risk-free rate | 1 month |
| `cape-scaled` | Gradual CAPE-scaled exposure | CAPE, price and total return | 1 month |

Signal strategies are lagged by one month to reduce look-ahead. Unconditional allocations are not artificially delayed.

```bash
sp500-backtest --list-strategies
```

## Local setup with Jupyter

The repository includes a setup script that creates `.venv`, installs the editable package and development dependencies, and registers the notebook kernel:

```bash
./scripts/setup_jupyter.sh
source .venv/bin/activate
jupyter lab
```

Select this kernel inside JupyterLab:

```text
Retail Portfolio Backtesting
```

Manual equivalent:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m ipykernel install \
  --user \
  --name retail-portfolio-backtesting \
  --display-name "Retail Portfolio Backtesting"
jupyter lab
```

The editable install means changes under `src/retail_sp500/` are available to notebooks. Each notebook enables IPython autoreload for development.

## Included notebooks

- `notebooks/01_strategy_comparison.ipynb` — select registry strategies and compare metrics and portfolio values.
- `notebooks/02_parameter_experiments.ipynb` — compare a compact set of trend and volatility parameters.
- `notebooks/03_rolling_window_analysis.ipynb` — measure start-date sensitivity over rolling horizons.
- `notebooks/04_limit_order_research.ipynb` — catalogue limit-order approaches and define the daily OHLC execution contract required before implementation.

Reusable logic stays in ordinary Python modules. Notebook outputs and execution counts are intentionally not committed.

## CLI backtesting

Run every strategy supported by Shiller data:

```bash
sp500-backtest --output results
```

Enable fractional Kelly with FRED enrichment:

```bash
sp500-backtest --fetch-risk-free --output results
```

Run selected strategies:

```bash
sp500-backtest \
  --fetch-risk-free \
  --strategy buy-hold \
  --strategy trend-vol-12 \
  --strategy fractional-kelly \
  --output results
```

Use local data files:

```bash
sp500-backtest \
  --data /path/to/ie_data.xls \
  --risk-free-data /path/to/TB3MS.csv \
  --output results
```

Offline deterministic demonstration:

```bash
sp500-backtest --synthetic --output results
```

Generated files:

```text
results/backtests.csv
results/metrics.json
results/comparison.html
```

The Plotly legend can hide, show, or isolate strategies on the shared graph.

## Limit-order boundary

The monthly Shiller dataset cannot establish whether an intramonth limit price was touched or determine price sequencing inside a month. Limit-order testing therefore remains a documented research scaffold until the repository has:

- reliable split-adjusted daily OHLC data;
- explicit order placement, expiry and cancellation rules;
- conservative gap and same-bar ambiguity handling;
- separate dividend, cash-yield and transaction-cost accounting.

Short-horizon RSI, HMM regimes, session effects, shorting, options and leverage remain outside the shared monthly engine.

## Add a strategy

Implement `target_weights()` and register a `StrategyDefinition`:

```python
from dataclasses import dataclass
from typing import ClassVar

import pandas as pd

@dataclass(frozen=True)
class MyStrategy:
    name: str = "My strategy"
    execution_lag_months: ClassVar[int] = 1
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        signal = market["price"] > market["price"].rolling(12).mean()
        return signal.astype(float)
```

## Validation

```bash
python -m pytest -q
python -m compileall -q src
python -m json.tool notebooks/01_strategy_comparison.ipynb >/dev/null
python -m json.tool notebooks/02_parameter_experiments.ipynb >/dev/null
python -m json.tool notebooks/03_rolling_window_analysis.ipynb >/dev/null
python -m json.tool notebooks/04_limit_order_research.ipynb >/dev/null
```

No automatic GitHub Actions workflow is included.

## Backtest cautions

- Strategy parameters can be overfit to the history used to evaluate them.
- Monthly averages are not guaranteed executable prices.
- Kelly sizing is highly sensitive to expected-return estimates.
- CAPE is a long-horizon valuation measure, not a precise crash timer.
- Expense ratios, spreads, taxes, tracking error and SGD/USD effects are not included.
- Historical results do not establish future profitability.
