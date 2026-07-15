from __future__ import annotations

import math

import pandas as pd
import pytest

from retail_sp500.risk_metrics import (
    annualized_compound_return,
    calmar_ratio,
    drawdown_series,
    maximum_drawdown,
    wealth_index_from_returns,
)


def test_calmar_uses_compounded_return_and_drawdown_magnitude() -> None:
    returns = pd.Series([0.10, -0.20, 0.25])
    assert annualized_compound_return(returns, periods_per_year=3) == pytest.approx(0.10)
    assert maximum_drawdown(returns) == pytest.approx(-0.20)
    assert calmar_ratio(returns, periods_per_year=3) == pytest.approx(0.50)


def test_drawdown_tracks_running_wealth_peak() -> None:
    wealth = wealth_index_from_returns(pd.Series([0.10, -0.20, 0.25]))
    drawdown = drawdown_series(wealth)
    assert wealth.tolist() == pytest.approx([1.10, 0.88, 1.10])
    assert drawdown.tolist() == pytest.approx([0.0, -0.20, 0.0])


def test_first_period_loss_is_measured_from_initial_wealth() -> None:
    assert maximum_drawdown(pd.Series([-0.10])) == pytest.approx(-0.10)


def test_calmar_is_undefined_without_drawdown() -> None:
    assert math.isnan(calmar_ratio(pd.Series([0.01, 0.01]), periods_per_year=2))
