from __future__ import annotations

import pandas as pd
import pytest

from retail_sp500.data import synthetic_market_data
from retail_sp500.strategies import (
    BuyAndHold,
    CapeScaledAllocation,
    MovingAverageTrend,
    TrendVolatilityTarget,
    VolatilityTarget,
)


def test_all_strategy_weights_are_bounded() -> None:
    market = synthetic_market_data(periods=60)
    strategies = [
        BuyAndHold(),
        MovingAverageTrend(),
        VolatilityTarget(),
        TrendVolatilityTarget(),
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
