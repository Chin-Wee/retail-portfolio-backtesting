"""Retail S&P 500 backtesting framework."""

from .backtest import BacktestConfig, BacktestResult, run_backtest, run_many
from .data import enrich_with_risk_free_rate, load_fred_risk_free_rate, load_shiller_data
from .strategies import default_strategies, select_strategies, strategy_catalog

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "default_strategies",
    "enrich_with_risk_free_rate",
    "load_fred_risk_free_rate",
    "load_shiller_data",
    "run_backtest",
    "run_many",
    "select_strategies",
    "strategy_catalog",
]
