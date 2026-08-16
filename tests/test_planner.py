from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retail_sp500.currency import convert_daily_prices
from retail_sp500.planner import (
    PlanConfig,
    cpf_2026_rates,
    monthly_budget,
    rolling_plan_backtest,
    run_plan_window,
    scenario_summary,
)


def _daily(start: str = "2000-01-03", end: str = "2025-12-31", *, scale: float = 1.0) -> pd.DataFrame:
    index = pd.date_range(start, end, freq="B")
    t = np.arange(len(index), dtype=float)
    close = scale * 100.0 * np.exp(0.0002 * t + 0.02 * np.sin(t / 45.0))
    open_ = close * (1.0 + 0.001 * np.sin(t / 9.0))
    high = np.maximum(open_, close) * 1.005
    low = np.minimum(open_, close) * 0.995
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


def test_2026_cpf_rates_and_ordinary_wage_ceiling() -> None:
    assert cpf_2026_rates(25) == pytest.approx((0.17, 0.20))
    assert cpf_2026_rates(58) == pytest.approx((0.16, 0.18))

    budget = monthly_budget(10_000.0, 3_000.0, age=25)
    assert budget["employee_cpf"] == pytest.approx(1_600.0)
    assert budget["employer_cpf"] == pytest.approx(1_360.0)
    assert budget["take_home"] == pytest.approx(8_400.0)
    assert budget["monthly_surplus"] == pytest.approx(5_400.0)


def test_low_wage_cpf_scope_is_explicit() -> None:
    with pytest.raises(ValueError, match="above S\$750"):
        monthly_budget(700.0, 300.0, age=20)

    budget = monthly_budget(700.0, 300.0, age=20, cpf_enabled=False)
    assert budget["monthly_surplus"] == pytest.approx(400.0)


def test_currency_conversion_uses_fx_close() -> None:
    asset = _daily("2020-01-02", "2020-01-10")
    fx = _daily("2020-01-01", "2020-01-10", scale=0.013)
    fx.loc[:, ["open", "high", "low", "close"]] = 1.35
    converted = convert_daily_prices(asset, fx)

    assert converted.loc[asset.index[0], "close"] == pytest.approx(
        asset.loc[asset.index[0], "close"] * 1.35
    )
    assert converted.attrs["currency"] == "SGD"


def test_plan_builds_reserve_then_invests_surplus() -> None:
    daily = _daily("2010-01-01", "2012-12-31")
    config = PlanConfig(
        start_age=25,
        gross_monthly_salary=5_000.0,
        monthly_expenses=2_000.0,
        current_cash=0.0,
        current_investments=0.0,
        annual_salary_growth=0.0,
        annual_expense_inflation=0.0,
        emergency_months=1.0,
        horizon_years=1,
    )
    path = run_plan_window(daily, start=pd.Timestamp("2010-01-04"), config=config)

    assert path.iloc[0]["cash"] == pytest.approx(2_000.0)
    assert path.iloc[0]["invested_this_month"] == pytest.approx(0.0)
    assert path["invested_this_month"].iloc[1:].sum() > 0.0
    assert path.iloc[-1]["cash"] == pytest.approx(2_000.0)


def test_forced_sale_is_reported_as_liquidity_stress() -> None:
    daily = _daily("2010-01-01", "2012-12-31")
    config = PlanConfig(
        start_age=25,
        gross_monthly_salary=1_000.0,
        monthly_expenses=2_000.0,
        current_cash=0.0,
        current_investments=10_000.0,
        annual_salary_growth=0.0,
        annual_expense_inflation=0.0,
        emergency_months=0.0,
        horizon_years=1,
        cpf_enabled=False,
    )
    path = run_plan_window(daily, start=pd.Timestamp("2010-01-04"), config=config)

    assert path["cash_shortfall"].any()
    assert path["sold_this_month"].sum() > 0.0


def test_rolling_backtest_returns_comparable_historical_windows() -> None:
    config = PlanConfig(
        start_age=25,
        gross_monthly_salary=5_000.0,
        monthly_expenses=2_000.0,
        current_cash=6_000.0,
        current_investments=5_000.0,
        annual_salary_growth=0.02,
        annual_expense_inflation=0.02,
        emergency_months=3.0,
        horizon_years=5,
    )
    scenarios = rolling_plan_backtest(_daily(), config=config, step_months=12)
    summary = scenario_summary(scenarios)

    assert len(scenarios) >= 10
    assert scenarios["start"].is_monotonic_increasing
    assert (scenarios["ending_liquid_net_worth"] > 0.0).all()
    assert summary["worst_real_ending"] <= summary["median_real_ending"] <= summary["best_real_ending"]
