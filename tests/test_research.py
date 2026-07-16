from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retail_sp500.research import (
    LabConfig,
    StrategySpec,
    build_stack,
    compare_strategies,
    simulate_strategy,
    strategy_discounts,
)


def _daily(start: str = "2012-01-02", end: str = "2024-12-31") -> pd.DataFrame:
    index = pd.date_range(start, end, freq="B")
    t = np.arange(len(index), dtype=float)
    close = 100.0 * np.exp(0.00025 * t + 0.025 * np.sin(t / 31.0))
    open_ = close * (1.0 + 0.002 * np.sin(t / 7.0))
    high = np.maximum(open_, close) * 1.008
    low = np.minimum(open_, close) * 0.992
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.full(len(index), 1_000_000.0),
        },
        index=index,
    )


def _strategies() -> list[StrategySpec]:
    return [
        StrategySpec("immediate", "Immediate market", "immediate"),
        StrategySpec(
            "fixed",
            "Fixed 0.5%, 5 sessions",
            "fixed",
            max_wait_sessions=5,
            fixed_discount=0.005,
        ),
        StrategySpec(
            "atr",
            "ATR 0.5, 10 sessions",
            "atr",
            max_wait_sessions=10,
            atr_multiplier=0.5,
            minimum_discount=0.001,
            maximum_discount=0.03,
        ),
        StrategySpec(
            "fill",
            "Historical 90% fill",
            "empirical",
            max_wait_sessions=10,
            target_fill_probability=0.9,
            lookback_sessions=252,
            maximum_discount=0.03,
        ),
    ]


def test_empirical_discount_uses_only_completed_history() -> None:
    daily = _daily("2018-01-01", "2022-12-30")
    spec = _strategies()[-1]
    original = strategy_discounts(daily, spec)

    changed = daily.copy()
    cutoff = pd.Timestamp("2022-01-03")
    changed.loc[changed.index >= cutoff, "low"] *= 0.5
    modified = strategy_discounts(changed, spec)

    pd.testing.assert_series_equal(
        original.loc[original.index < cutoff],
        modified.loc[modified.index < cutoff],
    )


def test_expiry_never_crosses_calendar_month() -> None:
    daily = _daily("2020-01-01", "2021-12-31")
    spec = StrategySpec(
        "deep",
        "Deep limit",
        "fixed",
        max_wait_sessions=20,
        fixed_discount=0.50,
    )
    discount = strategy_discounts(daily, spec)
    lots = simulate_strategy(
        daily,
        spec,
        discount,
        evaluation_start=pd.Timestamp("2020-02-03"),
        config=LabConfig(initial_cash=100.0, monthly_contribution=10.0, holdout_years=1),
    )
    assert all(
        contribution.to_period("M") == pd.Timestamp(fill).to_period("M")
        for contribution, fill in zip(lots.index, lots["fill_date"], strict=True)
    )
    assert (lots["fill_type"] == "expiry_close").all()


def test_comparison_and_stack_use_common_cashflows() -> None:
    comparison = compare_strategies(
        _daily(),
        _strategies(),
        config=LabConfig(
            initial_cash=1_000.0,
            monthly_contribution=100.0,
            holdout_years=2,
            stack_max_components=3,
            stack_min_calmar_improvement=0.0,
        ),
    )
    assert set(comparison.metrics["key"]) == {"immediate", "fixed", "atr", "fill"}
    assert comparison.metrics["total_contributed"].nunique() == 1

    stack = build_stack(
        comparison,
        config=LabConfig(
            initial_cash=1_000.0,
            monthly_contribution=100.0,
            holdout_years=2,
            stack_max_components=3,
            stack_min_calmar_improvement=0.0,
        ),
        approved_strategies=["fixed", "atr", "fill"],
    )
    assert stack.weights.sum() == pytest.approx(1.0)
    assert "immediate" in stack.weights
    assert stack.curve["portfolio_value"].iloc[-1] > 0.0


def test_holdout_changes_do_not_change_selection_metrics_for_fixed_rules() -> None:
    config = LabConfig(initial_cash=1_000.0, monthly_contribution=100.0, holdout_years=2)
    strategies = _strategies()[:3]
    first = compare_strategies(_daily(), strategies, config=config)

    changed = _daily()
    holdout = changed.index >= first.holdout_start
    changed.loc[holdout, ["open", "high", "low", "close"]] *= np.linspace(
        1.0, 0.5, int(holdout.sum())
    )[:, None]
    second = compare_strategies(changed, strategies, config=config)

    columns = ["key", "selection_annualized_return", "selection_max_drawdown", "selection_calmar_ratio"]
    pd.testing.assert_frame_equal(
        first.metrics[columns].sort_values("key").reset_index(drop=True),
        second.metrics[columns].sort_values("key").reset_index(drop=True),
    )
