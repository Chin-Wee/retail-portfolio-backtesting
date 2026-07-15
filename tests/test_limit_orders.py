from __future__ import annotations

import pandas as pd
import pytest

from retail_sp500.limit_orders import evaluate_limit_discount_grid, one_session_limit_outcomes


def _daily() -> pd.DataFrame:
    index = pd.date_range("2024-01-02", periods=4, freq="B")
    return pd.DataFrame(
        {
            "open": [100.0, 98.0, 101.0, 100.0],
            "high": [101.0, 101.0, 103.0, 102.0],
            "low": [99.0, 97.0, 98.5, 98.0],
            "close": [100.0, 100.0, 102.0, 101.0],
        },
        index=index,
    )


def test_gap_below_limit_fills_at_open() -> None:
    outcome = one_session_limit_outcomes(_daily(), discount=0.01)
    first = outcome.iloc[0]
    assert first["gap_fill"]
    assert first["fill_price"] == pytest.approx(98.0)
    assert first["limit_price"] == pytest.approx(99.0)


def test_intraday_touch_fills_at_limit() -> None:
    outcome = one_session_limit_outcomes(_daily(), discount=0.01)
    second = outcome.iloc[1]
    assert second["touch_fill"]
    assert second["fill_price"] == pytest.approx(99.0)


def test_unfilled_order_stays_in_cash_for_one_session() -> None:
    outcome = one_session_limit_outcomes(_daily(), discount=0.03)
    second = outcome.iloc[1]
    assert not second["filled"]
    assert second["limit_end_value"] == pytest.approx(1.0)
    assert second["market_end_value"] == pytest.approx(102.0 / 101.0)


def test_grid_reports_fill_tradeoff() -> None:
    summary = evaluate_limit_discount_grid(_daily(), [0.0, 0.01, 0.03])
    assert summary["discount"].tolist() == [0.0, 0.01, 0.03]
    assert summary.loc[0, "fill_rate"] >= summary.loc[2, "fill_rate"]
    assert (summary["sessions"] == 3).all()
