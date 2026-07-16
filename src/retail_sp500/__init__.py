"""One-notebook retail portfolio research lab."""

from .data import (
    DEFAULT_START_DATE,
    MarketDataError,
    fetch_daily,
    load_market,
    market_summary,
    parse_twelve_data,
    save_csv,
    validate_daily,
)
from .research import (
    ComparisonResult,
    LabConfig,
    StackResult,
    StrategySpec,
    build_stack,
    compare_strategies,
    comparison_figures,
    default_strategies,
    export_results,
    return_metrics,
    strategy_discounts,
)

__all__ = [
    "ComparisonResult",
    "DEFAULT_START_DATE",
    "LabConfig",
    "MarketDataError",
    "StackResult",
    "StrategySpec",
    "build_stack",
    "compare_strategies",
    "comparison_figures",
    "default_strategies",
    "export_results",
    "fetch_daily",
    "load_market",
    "market_summary",
    "parse_twelve_data",
    "return_metrics",
    "save_csv",
    "strategy_discounts",
    "validate_daily",
]
