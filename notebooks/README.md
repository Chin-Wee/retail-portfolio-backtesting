# Notebooks

These notebooks are deliberately thin. Reusable market-data, strategy, portfolio-accounting and plotting logic belongs in `src/retail_sp500/`; notebooks select inputs, run experiments and display results.

## Files

- `01_strategy_comparison.ipynb` — real monthly Shiller strategy comparison; synthetic data is opt-in only.
- `02_parameter_experiments.ipynb` — real monthly parameter experiments.
- `03_rolling_window_analysis.ipynb` — real monthly rolling analysis, explicitly marked provisional until warm-up semantics are repaired.
- `04_limit_order_research.ipynb` — real SPY daily OHLCV and fixed-discount next-session limit-order experiments.

## Real daily data

The limit-order notebook reads `TWELVE_DATA_API_KEY` and caches validated data at:

```text
data/processed/spy_daily_1day.csv
```

The cache is ignored by Git. The notebook reports the source, first session, last session and row count, and rejects future-dated data.

## Kernel

All committed notebooks target the kernel:

```text
Retail Portfolio Backtesting
```

Register it with `scripts/setup_jupyter.sh` or the commands in the root README.

## Commit policy

Notebook outputs and execution counts should be cleared before committing. The test suite enforces output-free notebooks to keep diffs reviewable.
