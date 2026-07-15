# Daily research notebooks

The notebooks are thin orchestration layers over `src/retail_sp500/`. Reusable fetching, validation, fill simulation, recurring-cash accounting, and walk-forward logic belongs in Python modules.

All four notebooks use real Twelve Data `1day` SPY OHLCV data. They contain no synthetic default and do not import the monthly Shiller strategy engine.

## Files

- `01_strategy_comparison.ipynb` — audit source dates and describe how far daily lows trade below the preceding close.
- `02_parameter_experiments.ipynb` — compare discount grids and 1/3/5/10/20-session expiry horizons.
- `03_rolling_window_analysis.ipynb` — train on trailing windows and score the selected discount on unseen years.
- `04_limit_order_research.ipynb` — derive a candidate from walk-forward selections and inspect contribution-lot execution.

## First run

```bash
export TWELVE_DATA_API_KEY="your-key"
source .venv/bin/activate
jupyter lab
```

The validated cache is stored at `data/processed/spy_daily_1day.csv` and ignored by Git.

## Commit policy

Notebook outputs and execution counts must remain cleared. The test suite also rejects monthly and synthetic imports inside the notebook suite.
