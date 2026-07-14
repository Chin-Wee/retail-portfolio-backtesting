from __future__ import annotations

import pandas as pd
import pytest

from retail_sp500.data import synthetic_market_data
from retail_sp500.strategies import (
    BuyAndHold,
    CapeScaledAllocation,
    FractionalKelly,
    MovingAverageTrend,
    StagedDeployment,
    TrendVolatilityTarget,
    VolatilityTarget,
    select_strategies,
    strategy_catalog,
)


def test_all_strategy_weights_are_bounded() -> None:
    market = synthetic_market_data(periods=84)
    strategies = [
        BuyAndHold(),
        StagedDeployment(BuyAndHold(), months=6),
        MovingAverageTrend(),
        VolatilityTarget(),
        TrendVolatilityTarget(),
        FractionalKelly(),
        CapeScaledAllocation(),
    ]
    for strategy in strategies:
        weights = strategy.target_weights(market)
        assert weights.between(0.0, 1.0).all()
        assert weights.index.equals(market.index)


def test_cape_scaled_weight_decreases_as_cape_rises() -> None:
    market = synthetic_market_data(periods=24)
    market["cape"] = pd.Series([15.0, 35.0] + [25.0] * 22, index=market.index)
    weights = CapeScaledAllocation().target_weights(market)
    assert weights.iloc[0] == pytest.approx(1.0)
    assert weights.iloc[1] == pytest.approx(0.25)


def test_staged_deployment_ramps_to_full_exposure() -> None:
    market = synthetic_market_data(periods=24)
    weights = StagedDeployment(BuyAndHold(), months=6).target_weights(market)
    assert weights.iloc[:7].tolist() == pytest.approx(
        [1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6, 1.0, 1.0]
    )


def test_trend_buffer_uses_hysteresis() -> None:
    index = pd.date_range("2020-01-01", periods=5, freq="MS")
    market = pd.DataFrame(
        {
            "price": [100.0, 100.0, 103.0, 102.0, 98.0],
            "total_return": [0.0] * 5,
        },
        index=index,
    )
    weights = MovingAverageTrend(months=2, buffer=0.01).target_weights(market)
    assert weights.tolist() == [0.0, 0.0, 1.0, 1.0, 0.0]


def test_fractional_kelly_stays_in_cash_for_negative_expected_excess_return() -> None:
    index = pd.date_range("2000-01-01", periods=24, freq="MS")
    market = pd.DataFrame(
        {
            "price": range(100, 124),
            "total_return": [-0.01] * 24,
            "risk_free_rate": [0.03] * 24,
        },
        index=index,
    )
    weights = FractionalKelly(lookback_months=12).target_weights(market)
    assert weights.iloc[-1] == pytest.approx(0.0)


def test_registry_filters_only_missing_data() -> None:
    market = synthetic_market_data(periods=84).drop(columns="risk_free_rate")
    strategies, skipped = select_strategies(None, market, skip_unavailable=True)
    assert "fractional-kelly" in skipped
    assert skipped["fractional-kelly"] == ("risk_free_rate",)
    assert all(strategy.name != FractionalKelly().name for strategy in strategies)
    assert "trend-vol-12" in strategy_catalog()


def test_explicit_unavailable_strategy_fails() -> None:
    market = synthetic_market_data(periods=84).drop(columns="risk_free_rate")
    with pytest.raises(KeyError, match="risk_free_rate"):
        select_strategies(["fractional-kelly"], market, skip_unavailable=False)
