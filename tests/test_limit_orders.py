from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retail_sp500.limit_orders import evaluate_limit_discount_grid, one_session_limit_outcomes
from retail_sp500.limit_portfolio import (
    RecurringLimitConfig,
    evaluate_recurring_limit_grid,
    simulate_recurring_limit_strategy,
    walk_forward_recurring_limit_selection,
)


def _daily() -> pd.DataFrame:
    index = pd.date_range("2024-01-02", periods=8, freq="B")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0],
            "high": [101.0, 102.0, 103.0, 103.0, 104.0, 105.0, 106.0, 108.0],
            "low": [99.0, 98.0, 100.0, 101.0, 102.0, 103.0, 104.0, 105.0],
            "close": [100.0, 100.0, 102.0, 102.0, 103.0, 104.0, 105.0, 107.0],
        },
        index=index,
    )


def test_gap_below_limit_fills_at_open() -> None:
    daily = _daily().copy()
    daily.iloc[1, daily.columns.get_loc("open")] = 98.0
    outcome = one_session_limit_outcomes(daily, discount=0.01)
    first = outcome.iloc[0]
    assert first["gap_fill"]
    assert first["fill_price"] == pytest.approx(98.0)
    assert first["limit_price"] == pytest.approx(99.0)


def test_intraday_touch_fills_at_limit() -> None:
    outcome = one_session_limit_outcomes(_daily(), discount=0.01)
    first = outcome.iloc[0]
    assert first["touch_fill"]
    assert first["fill_price"] == pytest.approx(99.0)


def test_unfilled_order_stays_in_cash_for_one_session() -> None:
    outcome = one_session_limit_outcomes(_daily(), discount=0.10)
    first = outcome.iloc[0]
    assert not first["filled"]
    assert first["limit_end_value"] == pytest.approx(1.0)


def test_grid_reports_fill_tradeoff() -> None:
    summary = evaluate_limit_discount_grid(_daily(), [0.0, 0.01, 0.10])
    assert summary["discount"].tolist() == [0.0, 0.01, 0.10]
    assert summary.loc[0, "fill_rate"] >= summary.loc[2, "fill_rate"]


def test_recurring_limit_tracks_lump_sum_separately() -> None:
    lots = simulate_recurring_limit_strategy(
        _daily(),
        RecurringLimitConfig(
            discount=0.01,
            max_wait_sessions=2,
            initial_cash=100.0,
            monthly_contribution=0.0,
        ),
    )
    assert len(lots) == 1
    assert lots.iloc[0]["fill_type"] == "touch"
    assert lots.iloc[0]["fill_price"] == pytest.approx(99.0)
    assert lots.iloc[0]["baseline_open_price"] == pytest.approx(101.0)
    assert lots.iloc[0]["ending_excess_value"] > 0.0


def test_recurring_grid_reports_forced_execution() -> None:
    summary = evaluate_recurring_limit_grid(
        _daily(),
        [0.01, 0.20],
        max_wait_sessions=2,
        initial_cash=100.0,
        monthly_contribution=0.0,
    )
    deep = summary.loc[summary["discount"] == 0.20].iloc[0]
    assert deep["forced_fill_rate"] == pytest.approx(1.0)
    assert deep["average_wait_sessions"] == pytest.approx(2.0)


def test_walk_forward_uses_unseen_test_windows() -> None:
    index = pd.date_range("2010-01-01", "2020-12-31", freq="B")
    base = 100.0 * np.exp(np.linspace(0.0, 1.0, len(index)))
    wave = 1.0 + 0.01 * np.sin(np.arange(len(index)) / 5.0)
    close = base * wave
    daily = pd.DataFrame(
        {
            "open": close * 1.001,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
        },
        index=index,
    )
    result = walk_forward_recurring_limit_selection(
        daily,
        [0.0, 0.005, 0.01],
        train_years=5,
        test_years=1,
        max_wait_sessions=3,
        monthly_contribution=100.0,
    )
    assert not result.empty
    assert (result["test_start"] > result["train_end"]).all()
    assert result["selected_discount"].isin([0.0, 0.005, 0.01]).all()
