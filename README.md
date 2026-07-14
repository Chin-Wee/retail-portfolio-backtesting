# Retail S&P 500 Backtesting

A small, auditable framework for comparing monthly S&P 500 allocation strategies on one graph.

Default portfolio assumptions:

- **$100,000 initial cash**
- **$1,000 contributed at the start of each subsequent month**
- fractional ETF units
- reinvested dividends
- ETF/cash allocations from 0% to 100%
- no leverage or shorting
- one-month signal lag to reduce look-ahead bias
- zero cash return by default, configurable per run

## Data choice

The primary source is Robert Shiller's `ie_data.xls` dataset:

```text
https://www.econ.yale.edu/~shiller/data/ie_data.xls
```

It is monthly and combines the fields needed by the initial models: price, dividends, earnings, CPI, long interest rates and CAPE. Ordinary P/E, dividend yield, earnings yield, inflation, total-return approximations, real returns and rolling volatility are derived locally.

### Historical interpretation

The formally constituted 500-stock S&P 500 began in 1957. The source's earlier history is a reconstructed predecessor U.S. large-cap composite. The application labels that distinction instead of presenting the entire 1871-present span as one unchanged investable ETF.

### Dividend convention

The Shiller dividend series is an annualised/interpolated amount. The framework approximates each month's reinvested dividend as `D / 12` and calculates:

```text
monthly total return = (price_t + dividend_t / 12) / price_(t-1) - 1
```

This is suitable for broad long-horizon comparisons, but it is not an exact ETF execution record. Expense ratios, bid/ask spreads, taxes and tracking error are not included yet.

## Included strategies

- Buy and hold
- 60% ETF / 40% cash
- 10-month moving-average trend
- 12% annualised volatility target
- Trend plus 12% volatility target
- CAPE-scaled allocation

These are examples built on the same `Strategy.target_weights()` contract. New strategies only need to return a monthly series of ETF weights between zero and one.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Interactive graph

Run a backtest and open the generated HTML report:

```bash
sp500-backtest --output results
open results/comparison.html  # macOS
```

The Plotly legend controls the shared graph: click a strategy to hide or show it, and double-click one strategy to isolate it. The chart remains a single comparable portfolio-value graph rather than separate reports.

## Command line

Official download:

```bash
sp500-backtest --output results
```

Local spreadsheet copy:

```bash
sp500-backtest --data /path/to/ie_data.xls --output results
```

Offline deterministic demonstration:

```bash
python -m retail_sp500.cli --synthetic --output results
```

Generated files:

```text
results/backtests.csv
results/metrics.json
results/comparison.html
```

## Add a strategy

```python
from dataclasses import dataclass
import pandas as pd

@dataclass(frozen=True)
class MyStrategy:
    name: str = "My strategy"

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        signal = market["price"] > market["price"].rolling(12).mean()
        return signal.astype(float)
```

Pass an instance into `run_backtest()` or include it in the list supplied to `run_many()`.

## Validation

```bash
python -m pytest -q
python -m compileall src
python -m retail_sp500.cli --synthetic --output results
```

No automatic GitHub Actions workflow is included. Validation is local by default.

## Backtest cautions

- Strategy parameters can be overfit to the same history used to evaluate them.
- Monthly averages are not guaranteed executable prices.
- CAPE is mainly a long-horizon valuation measure, not a precise crash timer.
- Results with recurring contributions should be compared using both terminal wealth and time-weighted statistics.
- Historical results do not establish future profitability.
