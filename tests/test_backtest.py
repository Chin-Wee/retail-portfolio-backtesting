from __future__ import annotations

import pandas as pd
import pytest

from retail_sp500.backtest import BacktestConfig, run_backtest, run_many
from retail_sp500.strategies import BuyAndHold, FixedAllocation


def _market(returns: list[float]) -> pd.DataFrame:
    index = pd.date_range("2020-01-01", periods=len(returns), freq="MS")
    return pd.DataFrame(
        {
            "price": 100.0,
            "total_return": returns,
            "cape": 20.0,
        },
        index=index,
    )


def test_contribution_contract_with_zero_returns() -> None:
    result = run_backtest(
        _market([0.0, 0.0, 0.0]),
        BuyAndHold(),
        BacktestConfig(initial_cash=100_000, monthly_contribution=1_000),
    )
    assert result.history["portfolio_value"].iloc[-1] == pytest.approx(102_000)
    assert result.metrics["invested_capital"] == pytest.approx(102_000)
    assert result.metrics["profit"] == pytest.approx(0.0)


def test_signal_is_lagged_one_month() -> None:
    result = run_backtest(
        _market([0.10, 0.10, 0.0]),
        BuyAndHold(),
        BacktestConfig(initial_cash=100.0, monthly_contribution=0.0),
    )
    assert result.history["target_weight"].tolist() == [0.0, 1.0, 1.0]
    assert result.history["portfolio_value"].iloc[-1] == pytest.approx(110.0)


def test_run_many_rejects_duplicate_strategy_names() -> None:
    with pytest.raises(ValueError, match="duplicate strategy"):
        run_many(_market([0.0, 0.0]), [FixedAllocation(), FixedAllocation()])


def test_drawdown_is_not_masked_by_contributions() -> None:
    result = run_backtest(
        _market([0.0, 0.0, -0.50]),
        BuyAndHold(),
        BacktestConfig(initial_cash=100.0, monthly_contribution=1_000.0),
    )
    assert result.metrics["max_drawdown"] == pytest.approx(-0.50)
