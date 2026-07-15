# Retail S&P 500 Backtesting

An auditable research workspace for two distinct questions:

1. **Monthly ETF/cash allocation strategies** using the long Shiller history.
2. **Daily limit-order execution research** using real SPY OHLCV data.

These paths are intentionally separate. Monthly averages cannot prove that a daily limit order filled.

## Current data paths

### Monthly allocation research

The allocation notebooks and CLI use Robert Shiller's monthly U.S. equity dataset. It includes price, dividends, earnings, CPI, interest rates and CAPE. This path remains useful for slow allocation rules such as buy-and-hold, trend and volatility targeting.

The monthly engine is still undergoing a mathematical audit. Do not use its present strategy ranking as investment advice.

### Daily limit-order research

`notebooks/04_limit_order_research.ipynb` uses Twelve Data's real `1day` SPY OHLCV endpoint.

Default research window:

```text
2007-06-01 through the latest available trading session
```

This keeps the request below the provider's 5,000-row single-request ceiling while retaining the global financial crisis, COVID shock and recent rate cycle.

The first run requires:

```bash
export TWELVE_DATA_API_KEY="your-key"
```

Validated data is cached locally at:

```text
data/processed/spy_daily_1day.csv
```

The cache is ignored by Git. The loader rejects duplicate sessions, invalid OHLC relationships, non-positive prices and future-dated rows.

## Why an earlier graph reached 2040

The notebooks previously defaulted to a deterministic synthetic smoke-test series:

```python
synthetic_market_data(periods=600)
```

That series begins in January 2000 and therefore extends to December 2049. It was not a forecast and was not real market data. The notebooks now default to real data; synthetic data is opt-in only.

## Limit-order experiment currently implemented

For each trading session `t`:

1. Observe the preceding close `close[t-1]`.
2. Set a buy limit:

   ```text
   limit = close[t-1] × (1 - discount)
   ```

3. During session `t`:
   - if `open[t] <= limit`, fill at the opening price;
   - otherwise, if `low[t] <= limit`, fill at the limit;
   - otherwise remain in cash for that one-session experiment.

The notebook evaluates a discount grid and reports:

- fill rate;
- gap-fill rate;
- conditional fill discount;
- unfilled rising-session rate;
- mean one-session value versus buying at the open.

The best row is only a **candidate for this exact one-session objective and sample**. It is not yet a universal portfolio optimum.

## Not yet implemented in the daily execution engine

A portfolio-grade limit-order model still needs:

- persistent monthly contribution lots;
- multi-day order expiry and cancellation;
- market-on-expiry or time-decay rules;
- dividends and ex-dividend order treatment;
- split handling;
- cash yield;
- transaction costs and spread assumptions;
- rolling out-of-sample evaluation.

Those choices materially change the optimal limit distance and must remain explicit.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
python -m ipykernel install \
  --user \
  --name retail-portfolio-backtesting \
  --display-name "Retail Portfolio Backtesting"
```

Or use:

```bash
./scripts/setup_jupyter.sh
```

Start Jupyter:

```bash
source .venv/bin/activate
jupyter lab
```

Select the kernel:

```text
Retail Portfolio Backtesting
```

## Notebooks

- `01_strategy_comparison.ipynb` — real monthly Shiller strategy comparison.
- `02_parameter_experiments.ipynb` — real monthly parameter experiments.
- `03_rolling_window_analysis.ipynb` — provisional monthly rolling analysis.
- `04_limit_order_research.ipynb` — real daily SPY limit-distance research.

## CLI monthly backtesting

```bash
sp500-backtest --list-strategies
sp500-backtest --output results
sp500-backtest --fetch-risk-free --output results
```

Generated monthly outputs:

```text
results/backtests.csv
results/metrics.json
results/comparison.html
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
