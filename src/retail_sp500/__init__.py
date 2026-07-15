"""Retail SPY limit-order and S&P 500 allocation research framework."""

from .backtest import BacktestConfig, BacktestResult, run_backtest, run_many
from .data import enrich_with_risk_free_rate, load_fred_risk_free_rate, load_shiller_data
from .daily_data import (
    DEFAULT_DAILY_START_DATE,
    DailyDataError,
    daily_data_summary,
    fetch_twelve_data_daily,
    load_daily_csv,
    load_or_fetch_twelve_data_daily,
    parse_twelve_data_daily,
    save_daily_csv,
)
from .limit_orders import evaluate_limit_discount_grid, one_session_limit_outcomes
from .limit_portfolio import (
    RecurringLimitConfig,
    evaluate_recurring_limit_grid,
    simulate_recurring_limit_strategy,
    summarize_recurring_limit_result,
    walk_forward_recurring_limit_selection,
)
from .strategies import default_strategies, select_strategies, strategy_catalog

__all__ = [
    "BacktestConfig",
    "BacktestResult",
    "DEFAULT_DAILY_START_DATE",
    "DailyDataError",
    "RecurringLimitConfig",
    "daily_data_summary",
    "default_strategies",
    "enrich_with_risk_free_rate",
    "evaluate_limit_discount_grid",
    "evaluate_recurring_limit_grid",
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
    "simulate_recurring_limit_strategy",
    "strategy_catalog",
    "summarize_recurring_limit_result",
    "walk_forward_recurring_limit_selection",
]
