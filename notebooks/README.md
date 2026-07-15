# Daily research notebooks

The notebooks are thin orchestration layers over `src/retail_sp500/`. Reusable fetching, validation, fill simulation, recurring-cash accounting, risk metrics, and graph construction belong in Python modules.

All notebooks use real Twelve Data `1day` SPY OHLCV data. They contain no synthetic default and do not import the monthly Shiller strategy engine.

## Files

- `01_strategy_comparison.ipynb` — audit source dates and daily downside excursions from the preceding close.
- `02_parameter_experiments.ipynb` — compare discount grids, expiry horizons, Calmar ratios, returns, and drawdowns.
- `03_rolling_window_analysis.ipynb` — compare terminal-value and Calmar selection on trailing windows and score unseen years.
- `04_limit_order_research.ipynb` — final strategy dashboard: Calmar ranking, return/drawdown scatter, wealth paths, and drawdown paths.
- `05_calmar_ratio_exploration.ipynb` — Calmar sensitivity across discounts and expiry horizons, plus top-strategy charts.

## First run

```bash
export TWELVE_DATA_API_KEY="your-key"
source .venv/bin/activate
jupyter lab
```

The validated cache is stored at `data/processed/spy_daily_1day.csv` and ignored by Git.

## Commit policy

Notebook outputs and execution counts must remain cleared. The test suite rejects monthly and synthetic imports inside the notebook suite.
