"""Retail S&P 500 backtesting framework."""

from .backtest import BacktestConfig, BacktestResult, run_backtest, run_many
from .daily_data import (
    fetch_twelve_data_daily,
    load_daily_csv,
    load_or_fetch_twelve_data_daily,
    parse_twelve_data_daily,
    save_daily_csv,
)
from .data import enrich_with_risk_free_rate, load_fred_risk_free_rate, load_shiller_data
from .limit_orders import evaluate_limit_discount_grid, one_session_limit_outcomes
from .strategies import default_strategies, select_strategies, strategy_catalog

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "default_strategies",
    "enrich_with_risk_free_rate",
    "evaluate_limit_discount_grid",
    "fetch_twelve_data_daily",
    "load_daily_csv",
    "load_fred_risk_free_rate",
    "load_or_fetch_twelve_data_daily",
    "load_shiller_data",
    "one_session_limit_outcomes",
    "parse_twelve_data_daily",
    "run_backtest",
    "run_many",
    "save_daily_csv",
    "select_strategies",
    "strategy_catalog",
]
