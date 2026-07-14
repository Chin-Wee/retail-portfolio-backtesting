from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

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


@dataclass(frozen=True)
class LaggedAlwaysInvested:
    name: str = "Lagged"
    execution_lag_months: ClassVar[int] = 1
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=market.index)


def test_contribution_contract_with_zero_returns() -> None:
    result = run_backtest(
        _market([0.0, 0.0, 0.0]),
        BuyAndHold(),
        BacktestConfig(initial_cash=100_000, monthly_contribution=1_000),
    )
    assert result.history["portfolio_value"].iloc[-1] == pytest.approx(102_000)
    assert result.metrics["invested_capital"] == pytest.approx(102_000)
    assert result.metrics["profit"] == pytest.approx(0.0)


def test_unconditional_strategy_is_not_delayed() -> None:
    result = run_backtest(
        _market([0.10, 0.10]),
        BuyAndHold(),
        BacktestConfig(initial_cash=100.0, monthly_contribution=0.0),
    )
    assert result.history["target_weight"].tolist() == [1.0, 1.0]
    assert result.history["portfolio_value"].iloc[-1] == pytest.approx(121.0)


def test_signal_strategy_uses_its_declared_lag() -> None:
    result = run_backtest(
        _market([0.10, 0.10, 0.0]),
        LaggedAlwaysInvested(),
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


def test_strategy_data_requirements_are_enforced() -> None:
    market = _market([0.0, 0.0]).drop(columns="price")
    with pytest.raises(KeyError, match="requires market columns: price"):
        run_backtest(market, BuyAndHold())
