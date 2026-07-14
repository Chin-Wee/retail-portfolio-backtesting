from __future__ import annotations

import pandas as pd
import pytest

from retail_sp500.backtest import BacktestConfig, run_many
from retail_sp500.plotting import comparison_figure
from retail_sp500.strategies import BuyAndHold, FixedAllocation


def test_comparison_figure_contains_selected_lines_and_contributions() -> None:
    index = pd.date_range("2020-01-01", periods=4, freq="MS")
    market = pd.DataFrame(
        {"price": [100, 101, 99, 105], "total_return": [0.0, 0.01, -0.02, 0.06]},
        index=index,
    )
    results = run_many(market, [BuyAndHold(), FixedAllocation()], BacktestConfig())
    figure = comparison_figure(results, selected=["Buy and hold"])
    assert [trace.name for trace in figure.data] == ["Buy and hold", "Capital contributed"]


def test_comparison_figure_rejects_unknown_strategy() -> None:
    with pytest.raises(KeyError):
        comparison_figure({}, selected=["unknown"])
