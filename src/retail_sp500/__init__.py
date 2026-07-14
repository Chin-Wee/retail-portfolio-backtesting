"""Retail S&P 500 backtesting framework."""

from .backtest import BacktestConfig, BacktestResult, run_backtest, run_many
from .data import load_shiller_data
from .strategies import default_strategies

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "default_strategies",
    "load_shiller_data",
    "run_backtest",
    "run_many",
]
