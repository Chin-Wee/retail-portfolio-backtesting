"""Unified strategy comparison and stacking API."""

from .engine import build_curve, compare_strategies, return_metrics, simulate_strategy
from .models import (
    ComparisonResult,
    LabConfig,
    StackResult,
    StrategyRun,
    StrategySpec,
    default_strategies,
    strategy_discounts,
)
from .stacking import build_stack, comparison_figures, export_results

__all__ = [
    "ComparisonResult",
    "LabConfig",
    "StackResult",
    "StrategyRun",
    "StrategySpec",
    "build_curve",
    "build_stack",
    "compare_strategies",
    "comparison_figures",
    "default_strategies",
    "export_results",
    "return_metrics",
    "simulate_strategy",
    "strategy_discounts",
]
