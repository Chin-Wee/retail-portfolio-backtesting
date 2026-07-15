# Notebooks

These notebooks are deliberately thin. Reusable market-data, strategy, portfolio-accounting and plotting logic belongs in `src/retail_sp500/`; notebooks select inputs, run experiments and display results.

## Files

- `01_strategy_comparison.ipynb` — choose registry strategies and compare metrics and portfolio values.
- `02_parameter_experiments.ipynb` — create a small set of custom parameter variants without changing the registry.
- `03_rolling_window_analysis.ipynb` — compare terminal wealth and drawdowns across rolling start dates.
- `04_limit_order_research.ipynb` — define candidate limit-order approaches and the daily OHLC execution contract required before implementation.

## Kernel

All committed notebooks target the kernel:

```text
Retail Portfolio Backtesting
```

Register it with `scripts/setup_jupyter.sh` or the commands in the root README.

## Commit policy

Notebook outputs and execution counts should be cleared before committing. The test suite enforces output-free notebooks to keep diffs reviewable.
