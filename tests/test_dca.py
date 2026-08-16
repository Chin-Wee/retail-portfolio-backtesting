from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from retail_sp500.broker import ibkr_pro_preset
from retail_sp500.dca import DcaConfig, rolling_dca_backtest, run_dca_window, summarize_dca


def _asset(start: str = "2005-01-03", end: str = "2025-12-31", *, daily_growth: float = 0.0) -> pd.DataFrame:
    index = pd.date_range(start, end, freq="B")
    t = np.arange(len(index), dtype=float)
    close = 100.0 * np.exp(daily_growth * t)
    return pd.DataFrame(
        {
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": np.full(len(index), 1_000_000.0),
        },
        index=index,
    )


def _fx(start: str = "2004-12-31", end: str = "2025-12-31", rate: float = 1.35) -> pd.DataFrame:
    index = pd.date_range(start, end, freq="B")
    values = np.full(len(index), rate)
    return pd.DataFrame(
        {
            "open": values,
            "high": values,
            "low": values,
            "close": values,
            "volume": np.zeros(len(index)),
        },
        index=index,
    )


def test_flat_market_without_fees_keeps_all_strategies_equal() -> None:
    config = DcaConfig(
        capital_sgd=1_000_000.0,
        deployment_months=(1, 6, 12),
        evaluation_years=5,
        cash_yield_annual=0.0,
    )
    broker = ibkr_pro_preset(market="us", pricing="fixed", fx_method="none")
    custom = broker.__class__(
        market="custom",
        pricing="custom",
        fx_method="none",
    )
    results = rolling_dca_backtest(_asset(), config=config, broker=custom, step_months=12)

    spread = results.groupby("start")["ending_wealth_sgd"].agg(lambda s: s.max() - s.min())
    assert float(spread.max()) == pytest.approx(0.0, abs=1e-6)


def test_rising_market_favors_earlier_deployment_when_costs_are_zero() -> None:
    config = DcaConfig(
        capital_sgd=1_000_000.0,
        deployment_months=(1, 12),
        evaluation_years=5,
    )
    broker = ibkr_pro_preset(market="us", pricing="fixed", fx_method="none")
    custom = broker.__class__(market="custom", pricing="custom", fx_method="none")
    results = rolling_dca_backtest(
        _asset(daily_growth=0.0002),
        config=config,
        broker=custom,
        step_months=12,
    )

    pivot = results.pivot(index="start", columns="deployment_months", values="ending_wealth_sgd")
    assert (pivot[1] > pivot[12]).all()


def test_all_strategies_share_same_terminal_date_for_each_start() -> None:
    config = DcaConfig(
        capital_sgd=1_000_000.0,
        deployment_months=(1, 3, 6, 12, 24, 36),
        evaluation_years=5,
    )
    custom = ibkr_pro_preset(market="us", pricing="fixed", fx_method="none").__class__(
        market="custom",
        pricing="custom",
        fx_method="none",
    )
    results = rolling_dca_backtest(_asset(), config=config, broker=custom, step_months=12)

    assert int(results.groupby("start")["end"].nunique().max()) == 1
    assert int(results.groupby("start")["capital_sgd"].nunique().max()) == 1


def test_repeated_dca_orders_accumulate_more_manual_fx_minimum_fees() -> None:
    config = DcaConfig(
        capital_sgd=12_000.0,
        deployment_months=(1, 12),
        evaluation_years=2,
    )
    broker = ibkr_pro_preset(market="us", pricing="fixed", fx_method="manual_spot")
    results = rolling_dca_backtest(
        _asset("2010-01-04", "2018-12-31"),
        fx_daily=_fx("2009-12-31", "2018-12-31"),
        config=config,
        broker=broker,
        step_months=12,
    )

    fees = results.groupby("deployment_months")["fx_fees_sgd"].median()
    assert fees[12] > fees[1]


def test_cash_yield_is_credited_to_undeployed_cash() -> None:
    asset = _asset("2010-01-04", "2015-12-31")
    broker = ibkr_pro_preset(market="us", pricing="fixed", fx_method="none").__class__(
        market="custom",
        pricing="custom",
        fx_method="none",
    )
    no_yield = DcaConfig(
        capital_sgd=1_000_000.0,
        deployment_months=(12,),
        evaluation_years=3,
        cash_yield_annual=0.0,
    )
    with_yield = DcaConfig(
        capital_sgd=1_000_000.0,
        deployment_months=(12,),
        evaluation_years=3,
        cash_yield_annual=0.04,
    )

    first = run_dca_window(
        asset,
        start=pd.Timestamp("2010-01-04"),
        deployment_months=12,
        config=no_yield,
        broker=broker,
    )
    second = run_dca_window(
        asset,
        start=pd.Timestamp("2010-01-04"),
        deployment_months=12,
        config=with_yield,
        broker=broker,
    )
    assert second["cash_interest_sgd"] > 0.0
    assert second["ending_wealth_sgd"] > first["ending_wealth_sgd"]


def test_summary_reports_relative_results_against_lump_sum() -> None:
    config = DcaConfig(
        capital_sgd=1_000_000.0,
        deployment_months=(1, 6, 12),
        evaluation_years=5,
    )
    broker = ibkr_pro_preset(market="us", pricing="fixed", fx_method="none").__class__(
        market="custom",
        pricing="custom",
        fx_method="none",
    )
    results = rolling_dca_backtest(
        _asset(daily_growth=0.0001),
        config=config,
        broker=broker,
        step_months=12,
    )
    summary = summarize_dca(results)

    assert set(summary["deployment_months"]) == {1, 6, 12}
    assert summary.loc[summary["deployment_months"] == 1, "win_rate_vs_lump_sum"].isna().all()
    assert (summary.loc[summary["deployment_months"] > 1, "median_delta_vs_lump_sum_sgd"] < 0.0).all()
