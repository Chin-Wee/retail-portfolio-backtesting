from __future__ import annotations

import pandas as pd

from retail_sp500.limit_plotting import (
    calmar_by_discount_figure,
    drawdown_figure,
    return_drawdown_figure,
    strategy_calmar_ranking_figure,
    strategy_drawdown_figure,
    strategy_return_drawdown_figure,
    strategy_wealth_figure,
    walk_forward_calmar_figure,
    wealth_index_figure,
)


def test_calmar_parameter_figures_render_expected_traces() -> None:
    grid = pd.DataFrame(
        {
            "discount": [0.0, 0.01],
            "calmar_ratio": [0.7, 0.8],
            "baseline_calmar_ratio": [0.6, 0.6],
            "annualized_return": [0.08, 0.09],
            "max_drawdown": [-0.12, -0.11],
            "max_wait_sessions": [5, 5],
        }
    )
    assert len(calmar_by_discount_figure(grid).data) == 2
    assert len(return_drawdown_figure(grid).data) == 1


def test_multi_horizon_calmar_figure_renders_each_strategy_family() -> None:
    grid = pd.DataFrame(
        {
            "discount": [0.0, 0.01, 0.0, 0.01],
            "calmar_ratio": [0.7, 0.8, 0.6, 0.75],
            "baseline_calmar_ratio": [0.6] * 4,
            "annualized_return": [0.08, 0.09, 0.075, 0.085],
            "max_drawdown": [-0.12, -0.11, -0.13, -0.12],
            "wait_horizon": [1, 1, 5, 5],
        }
    )
    assert len(calmar_by_discount_figure(grid).data) == 3
    assert len(return_drawdown_figure(grid).data) == 2


def test_equity_walk_forward_and_strategy_figures_render() -> None:
    index = pd.date_range("2024-01-02", periods=3, freq="B")
    curve = pd.DataFrame(
        {
            "wealth_index": [1.0, 0.9, 1.1],
            "baseline_wealth_index": [1.0, 0.95, 1.05],
            "drawdown": [0.0, -0.1, 0.0],
            "baseline_drawdown": [0.0, -0.05, 0.0],
        },
        index=index,
    )
    walk_forward = pd.DataFrame(
        {
            "test_start": index[:2],
            "test_calmar_ratio": [0.5, 0.8],
            "test_baseline_calmar_ratio": [0.4, 0.6],
        }
    )
    metrics = pd.DataFrame(
        {
            "strategy": ["Immediate open", "Limit"],
            "annualized_return": [0.08, 0.09],
            "max_drawdown": [-0.12, -0.10],
            "calmar_ratio": [0.67, 0.90],
            "ending_excess_value": [0.0, 100.0],
        }
    )
    curves = pd.DataFrame(
        {
            "date": list(index) * 2,
            "strategy": ["Immediate open"] * 3 + ["Limit"] * 3,
            "wealth_index": [1.0, 0.95, 1.05, 1.0, 0.97, 1.08],
            "drawdown": [0.0, -0.05, 0.0, 0.0, -0.03, 0.0],
        }
    )
    assert len(wealth_index_figure(curve).data) == 2
    assert len(drawdown_figure(curve).data) == 2
    assert len(walk_forward_calmar_figure(walk_forward).data) == 2
    assert len(strategy_calmar_ranking_figure(metrics).data) == 1
    assert len(strategy_return_drawdown_figure(metrics).data) == 1
    assert len(strategy_wealth_figure(curves).data) == 2
    assert len(strategy_drawdown_figure(curves).data) == 2
