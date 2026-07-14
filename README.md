# Retail S&P 500 Backtesting

A small, auditable framework for comparing long-only S&P 500 ETF/cash strategies on one graph.

Default portfolio assumptions:

- **$100,000 initial cash**
- **$1,000 contributed at the start of each subsequent month**
- fractional ETF units
- reinvested dividends
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

Fractional Kelly requires an explicit risk-free series. The supported source is FRED `TB3MS`, the monthly average 3-month Treasury-bill secondary-market rate on a discount basis:

```text
https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS
```

The loader converts percentages to annual decimals and does not manufacture observations before the FRED series begins.

### Current quote

A current SPY quote can be read from Twelve Data using its free personal API tier. This quote path is operational input only; it does not replace Shiller as the historical backtest source.

```bash
export TWELVE_DATA_API_KEY=...
sp500-backtest --live-quote --live-symbol SPY
```

## Hotswappable strategies

Use `--strategy` repeatedly to put selected strategies on the same graph.

| Key | Strategy | Data requirement | Execution lag |
|---|---|---|---:|
| `buy-hold` | 100% ETF buy-and-hold | monthly price and total return | 0 months |
| `staged-buy-hold-6m` | Six-month deterministic deployment ramp | monthly price and total return | 0 months |
| `fixed-60-40` | 60% ETF / 40% cash | monthly price and total return | 0 months |
| `trend-10m` | 10-month moving average with 1% hysteresis | monthly price and total return | 1 month |
| `vol-target-12` | 12% annualized volatility target | monthly price and total return | 1 month |
| `trend-vol-12` | Trend gate plus 12% volatility target | monthly price and total return | 1 month |
| `fractional-kelly` | Quarter-Kelly long-only ceiling, 60-month estimate | total return and FRED risk-free rate | 1 month |
| `cape-scaled` | Gradual CAPE-scaled exposure | CAPE, price and total return | 1 month |

Signal strategies are lagged by one month to reduce look-ahead. Unconditional allocation and staged deployment are not artificially delayed.

List the registry:

```bash
sp500-backtest --list-strategies
```

Run a subset:

```bash
sp500-backtest \
  --fetch-risk-free \
  --strategy buy-hold \
  --strategy trend-vol-12 \
  --strategy fractional-kelly \
  --output results
```

When no `--strategy` is supplied, every strategy supported by the loaded columns runs. Unsupported strategies are skipped with an explicit missing-column message. Explicitly selecting an unsupported strategy fails instead of silently substituting data.

## Deliberately excluded

These ideas are not implemented in the shared monthly engine:

- two-day RSI and other short-horizon mean reversion
- Hidden Markov regime switching
- overnight-versus-intraday and calendar/session effects
- shorting, options and leverage

They require daily or intraday adjusted execution data, introduce a materially shorter comparison horizon, and would create a second backtest system with different dividend and fill assumptions. They should only be added with a separately validated daily-data contract.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

## Backtesting

Official Shiller download, with all strategies that do not require FRED:

```bash
sp500-backtest --output results
```

Enable Kelly with official FRED enrichment:

```bash
sp500-backtest --fetch-risk-free --output results
```

Use local source copies:

```bash
sp500-backtest \
  --data /path/to/ie_data.xls \
  --risk-free-data /path/to/TB3MS.csv \
  --output results
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

The Plotly legend controls the shared graph: click a strategy to hide or show it, and double-click one strategy to isolate it.

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
python -m retail_sp500.cli --synthetic --list-strategies
python -m retail_sp500.cli \
  --synthetic \
  --strategy buy-hold \
  --strategy trend-vol-12 \
  --strategy fractional-kelly \
  --output /tmp/retail-portfolio-strategies
```

No automatic GitHub Actions workflow is included.

## Backtest cautions

- Strategy parameters can be overfit to the history used to evaluate them.
- Monthly averages are not guaranteed executable prices.
- Kelly sizing is highly sensitive to expected-return estimates; this implementation uses quarter Kelly and caps exposure at 100%.
- CAPE is a long-horizon valuation measure, not a precise crash timer.
- Expense ratios, spreads, taxes, tracking error and SGD/USD effects are not included.
- Historical results do not establish future profitability.
