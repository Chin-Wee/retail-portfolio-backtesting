# Retail Portfolio Lab

One research notebook for one question:

> Given monthly investable cash, real daily market data, and automation, which purchase policies are robust enough to use together?

The repository compares every strategy on the same SPY history and cash-flow schedule, reserves the latest years as an untouched holdout, then builds a small strategy stack using only the earlier selection period.

It does **not** claim to discover a permanently perfect portfolio. It creates an auditable candidate that can be rerun as new live data arrives.

## What remains

```text
notebooks/retail_portfolio.ipynb   single research interface
src/retail_sp500/data.py           live Twelve Data loader and cache
src/retail_sp500/models.py         strategy definitions and adaptive limit signals
src/retail_sp500/engine.py         common backtest and contribution accounting
src/retail_sp500/stacking.py       selection, stacking, charts, and exports
src/retail_sp500/research.py       small public facade imported by the notebook
src/retail_sp500/cli.py            automated terminal runner
```

The older monthly Shiller engine, duplicate limit-order modules, five separate notebooks, and committed market-data snapshot have been removed.

## Strategies compared

- immediate purchase at the first eligible open;
- fixed pullback limits from 0.25% to 2.00%;
- volatility-scaled limits based on trailing ATR;
- leak-free historical fill-probability limits targeting 80%, 90%, or 95% execution;
- 5-, 10-, and 20-session maximum waits, always capped at the final trading session of the contribution month;
- market-on-close fallback at expiry so missed orders are not ignored.

Every strategy receives the same initial cash and monthly contributions.

## Selection and stacking

1. All strategies are run over the common history where every strategy has valid inputs.
2. The most recent four years are reserved as an untouched holdout by default.
3. The earlier period marks strategies worth further testing when they improve Calmar without materially sacrificing annualized return.
4. A greedy stack begins with immediate investment and adds only strategies that improve selection-period Calmar.
5. The notebook then shows the untouched holdout results for the final stack.

The final stack represents separate automated subaccounts: each monthly contribution is divided by the selected weights. It is not leverage and does not short the market.

## Setup

```bash
./scripts/setup.sh
export TWELVE_DATA_API_KEY="your-key"
source .venv/bin/activate
jupyter lab
```

Open:

```text
notebooks/retail_portfolio.ipynb
```

Select the `Retail Portfolio Lab` kernel.

The first run downloads validated SPY daily OHLCV data to:

```text
data/spy_daily.csv
```

Later runs use the cache unless `REFRESH = True` is set in the notebook.

## Notebook workflow

Run the notebook through the selection-period comparison, then stop at the approval cell. The holdout is not displayed until after you choose one of two stacking modes:

```python
APPROVED_STRATEGIES = None
```

Uses the automatic pre-holdout filter.

```python
APPROVED_STRATEGIES = [
    "fixed-0.0050-10",
    "fill-0.90-20",
]
```

Restricts the stack to strategies you explicitly approve after reviewing the charts.

## Terminal automation

```bash
./scripts/run.sh
```

Restrict the stack from the command line:

```bash
./scripts/run.sh \
  --approve fixed-0.0050-10 \
  --approve fill-0.90-20
```

Outputs:

```text
results/portfolio/strategy_metrics.csv
results/portfolio/strategy_curves.csv
results/portfolio/stack_weights.csv
results/portfolio/stack_curve.csv
results/portfolio/stack_metrics.json
results/portfolio/*.html
```

## Main charts

- selection versus holdout Calmar ranking;
- holdout return versus drawdown;
- fill reliability versus execution savings;
- contribution-neutral wealth paths;
- drawdown paths;
- final stack weights.

## Current omissions

The model excludes dividends, idle-cash yield, spreads, fees, taxes, FX costs, and partial fills. These can matter more than small differences between execution strategies and must be added before live deployment.

## Validation

```bash
python -m pytest -q
python -m compileall -q src
python -m json.tool notebooks/retail_portfolio.ipynb >/dev/null
bash -n scripts/setup.sh
bash -n scripts/run.sh
```
