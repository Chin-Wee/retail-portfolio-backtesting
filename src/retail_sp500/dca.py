from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .broker import BrokerFeeConfig, execute_buy
from .currency import prior_fx_close
from .data import validate_daily
from .engine import _first_salary_session as first_salary_session

DEFAULT_DEPLOYMENT_MONTHS = (1, 3, 6, 12, 18, 24, 36)


@dataclass(frozen=True)
class DcaConfig:
    capital_sgd: float = 1_000_000.0
    deployment_months: tuple[int, ...] = DEFAULT_DEPLOYMENT_MONTHS
    evaluation_years: int = 5
    buy_day: int = 1
    cash_yield_annual: float = 0.0

    def __post_init__(self) -> None:
        if self.capital_sgd <= 0.0:
            raise ValueError("capital_sgd must be positive")
        if not self.deployment_months:
            raise ValueError("at least one deployment strategy is required")
        if min(self.deployment_months) < 1:
            raise ValueError("deployment months must be positive")
        if len(set(self.deployment_months)) != len(self.deployment_months):
            raise ValueError("deployment strategies must be unique")
        if self.evaluation_years < 1:
            raise ValueError("evaluation_years must be positive")
        if max(self.deployment_months) > self.evaluation_years * 12:
            raise ValueError("deployment period cannot exceed the evaluation horizon")
        if not 1 <= self.buy_day <= 28:
            raise ValueError("buy_day must be between 1 and 28")
        if self.cash_yield_annual <= -1.0:
            raise ValueError("cash_yield_annual must be greater than -100%")


def strategy_label(deployment_months: int) -> str:
    return "Lump sum" if deployment_months == 1 else f"{deployment_months}-month DCA"


def _accrue_cash(cash: float, annual_rate: float, start: pd.Timestamp, end: pd.Timestamp) -> tuple[float, float]:
    days = max((pd.Timestamp(end) - pd.Timestamp(start)).days, 0)
    if cash == 0.0 or days == 0 or annual_rate == 0.0:
        return cash, 0.0
    grown = cash * (1.0 + annual_rate) ** (days / 365.25)
    return grown, grown - cash


def _trade_sessions(
    index: pd.DatetimeIndex,
    *,
    start_month: pd.Period,
    deployment_months: int,
    buy_day: int,
) -> list[pd.Timestamp]:
    sessions: list[pd.Timestamp] = []
    for month in pd.period_range(start_month, periods=deployment_months, freq="M"):
        session = first_salary_session(index, month, buy_day)
        if session is None:
            raise ValueError(f"no trading session is available for {month}")
        sessions.append(pd.Timestamp(session))
    return sessions


def _end_session(
    index: pd.DatetimeIndex,
    *,
    first_session: pd.Timestamp,
    evaluation_years: int,
    evaluation_end: pd.Timestamp | None,
) -> pd.Timestamp:
    if evaluation_end is None:
        target_end = first_session + pd.DateOffset(years=evaluation_years)
        if pd.Timestamp(index[-1]) < target_end:
            raise ValueError("historical window is shorter than the requested evaluation horizon")
    else:
        target_end = pd.Timestamp(evaluation_end)
        if target_end < first_session:
            raise ValueError("evaluation_end cannot precede the first buy session")
        if target_end > pd.Timestamp(index[-1]):
            raise ValueError("evaluation_end is after the available market history")

    eligible = index[(index >= first_session) & (index <= target_end)]
    if len(eligible) == 0:
        raise ValueError("evaluation window contains no sessions")
    return pd.Timestamp(eligible[-1])


def _run_dca_window_validated(
    asset: pd.DataFrame,
    fx_rates: pd.Series,
    *,
    start: pd.Timestamp,
    deployment_months: int,
    config: DcaConfig,
    broker: BrokerFeeConfig,
    evaluation_end: pd.Timestamp | None = None,
    cash_start: pd.Timestamp | None = None,
) -> dict[str, object]:
    if deployment_months not in config.deployment_months:
        raise ValueError("deployment_months is not enabled in the DCA config")
    if not asset.index.equals(fx_rates.index):
        raise ValueError("FX rates must align with the validated asset sessions")

    requested_start = pd.Timestamp(start)
    start_month = requested_start.to_period("M")
    first_session = first_salary_session(asset.index, start_month, config.buy_day)
    if first_session is None:
        raise ValueError("no eligible start session is available")
    first_session = pd.Timestamp(first_session)
    end_session = _end_session(
        asset.index,
        first_session=first_session,
        evaluation_years=config.evaluation_years,
        evaluation_end=evaluation_end,
    )

    trade_sessions = _trade_sessions(
        asset.index,
        start_month=start_month,
        deployment_months=deployment_months,
        buy_day=config.buy_day,
    )
    if trade_sessions[-1] > end_session:
        raise ValueError("deployment period extends beyond the evaluation window")

    effective_cash_start = pd.Timestamp(cash_start) if cash_start is not None else first_session
    if effective_cash_start > trade_sessions[0]:
        raise ValueError("cash_start cannot be after the first buy session")

    base_tranche = config.capital_sgd / deployment_months
    cash = config.capital_sgd
    units = 0.0
    last_cash_date = effective_cash_start
    total_cash_interest = 0.0
    total_commission = 0.0
    total_fx_fees = 0.0
    total_fees = 0.0
    total_trade_notional = 0.0

    for number, session in enumerate(trade_sessions, start=1):
        cash, interest = _accrue_cash(
            cash,
            config.cash_yield_annual,
            last_cash_date,
            session,
        )
        total_cash_interest += interest

        allocation = cash if number == deployment_months else min(base_tranche, cash)
        execution = execute_buy(
            allocation,
            asset_price=float(asset.loc[session, "close"]),
            sgd_per_trade_currency=float(fx_rates.loc[session]),
            config=broker,
        )
        units += execution.units
        cash = max(cash - execution.total_spent_sgd, 0.0)
        total_commission += execution.commission_sgd
        total_fx_fees += execution.fx_fee_sgd
        total_fees += execution.total_fees_sgd
        total_trade_notional += execution.trade_currency_notional * float(fx_rates.loc[session])
        last_cash_date = session

    cash, interest = _accrue_cash(
        cash,
        config.cash_yield_annual,
        last_cash_date,
        end_session,
    )
    total_cash_interest += interest

    ending_portfolio = (
        units
        * float(asset.loc[end_session, "close"])
        * float(fx_rates.loc[end_session])
    )
    ending_wealth = cash + ending_portfolio

    return {
        "start": first_session,
        "comparison_start": effective_cash_start,
        "end": end_session,
        "deployment_months": deployment_months,
        "strategy": strategy_label(deployment_months),
        "capital_sgd": config.capital_sgd,
        "ending_cash_sgd": cash,
        "ending_portfolio_sgd": ending_portfolio,
        "ending_wealth_sgd": ending_wealth,
        "return_pct": ending_wealth / config.capital_sgd - 1.0,
        "total_fees_sgd": total_fees,
        "commission_sgd": total_commission,
        "fx_fees_sgd": total_fx_fees,
        "cash_interest_sgd": total_cash_interest,
        "trade_notional_sgd": total_trade_notional,
        "first_buy": trade_sessions[0],
        "last_buy": trade_sessions[-1],
        "orders": deployment_months,
    }


def run_dca_window(
    asset_daily: pd.DataFrame,
    *,
    start: pd.Timestamp,
    deployment_months: int,
    config: DcaConfig,
    broker: BrokerFeeConfig,
    fx_daily: pd.DataFrame | None = None,
    evaluation_end: pd.Timestamp | None = None,
    cash_start: pd.Timestamp | None = None,
) -> dict[str, object]:
    """Run one capital-deployment strategy over one complete historical window."""

    asset = validate_daily(asset_daily)
    fx_rates = (
        pd.Series(1.0, index=asset.index, name="fx_close", dtype=float)
        if fx_daily is None
        else prior_fx_close(asset.index, fx_daily)
    )
    return _run_dca_window_validated(
        asset,
        fx_rates,
        start=start,
        deployment_months=deployment_months,
        config=config,
        broker=broker,
        evaluation_end=evaluation_end,
        cash_start=cash_start,
    )


def rolling_dca_backtest(
    asset_daily: pd.DataFrame,
    *,
    config: DcaConfig,
    broker: BrokerFeeConfig,
    fx_daily: pd.DataFrame | None = None,
    step_months: int = 1,
) -> pd.DataFrame:
    """Compare every enabled deployment strategy across complete historical windows."""

    if step_months < 1:
        raise ValueError("step_months must be positive")

    asset = validate_daily(asset_daily)
    fx_rates = (
        pd.Series(1.0, index=asset.index, name="fx_close", dtype=float)
        if fx_daily is None
        else prior_fx_close(asset.index, fx_daily)
    )
    months = asset.index.to_period("M").unique()
    records: list[dict[str, object]] = []

    for offset in range(0, len(months), step_months):
        start_month = months[offset]
        start = first_salary_session(asset.index, start_month, config.buy_day)
        if start is None:
            continue

        window_records: list[dict[str, object]] = []
        try:
            for deployment in sorted(config.deployment_months):
                window_records.append(
                    _run_dca_window_validated(
                        asset,
                        fx_rates,
                        start=pd.Timestamp(start),
                        deployment_months=deployment,
                        config=config,
                        broker=broker,
                    )
                )
        except ValueError:
            continue
        records.extend(window_records)

    if not records:
        raise ValueError("no complete historical DCA windows were available")

    result = pd.DataFrame.from_records(records).sort_values(
        ["start", "deployment_months"]
    ).reset_index(drop=True)

    expected = len(config.deployment_months)
    counts = result.groupby("start")["deployment_months"].nunique()
    common_starts = counts[counts == expected].index
    result = result[result["start"].isin(common_starts)].copy()
    if result.empty:
        raise ValueError("no common historical windows cover every DCA strategy")

    baseline = (
        result.loc[result["deployment_months"] == 1, ["start", "ending_wealth_sgd"]]
        .rename(columns={"ending_wealth_sgd": "lump_sum_ending_wealth_sgd"})
    )
    if baseline.empty:
        raise ValueError("lump sum must be included for comparison")
    result = result.merge(baseline, on="start", how="left", validate="many_to_one")
    result["ending_delta_vs_lump_sum_sgd"] = (
        result["ending_wealth_sgd"] - result["lump_sum_ending_wealth_sgd"]
    )
    result["ending_delta_vs_lump_sum_pct"] = (
        result["ending_wealth_sgd"] / result["lump_sum_ending_wealth_sgd"] - 1.0
    )
    return result.sort_values(["start", "deployment_months"]).reset_index(drop=True)


def summarize_dca(results: pd.DataFrame) -> pd.DataFrame:
    required = {
        "deployment_months",
        "strategy",
        "ending_wealth_sgd",
        "ending_delta_vs_lump_sum_sgd",
        "return_pct",
        "total_fees_sgd",
        "commission_sgd",
        "fx_fees_sgd",
    }
    missing = required.difference(results.columns)
    if missing:
        raise ValueError(f"DCA results are missing columns: {', '.join(sorted(missing))}")
    if results.empty:
        raise ValueError("at least one DCA result is required")

    rows: list[dict[str, object]] = []
    for deployment, group in results.groupby("deployment_months", sort=True):
        delta = group["ending_delta_vs_lump_sum_sgd"].astype(float)
        rows.append(
            {
                "deployment_months": int(deployment),
                "strategy": str(group["strategy"].iloc[0]),
                "scenarios": int(len(group)),
                "worst_ending_wealth_sgd": float(group["ending_wealth_sgd"].min()),
                "p10_ending_wealth_sgd": float(group["ending_wealth_sgd"].quantile(0.10)),
                "median_ending_wealth_sgd": float(group["ending_wealth_sgd"].median()),
                "best_ending_wealth_sgd": float(group["ending_wealth_sgd"].max()),
                "median_return_pct": float(group["return_pct"].median()),
                "median_fees_sgd": float(group["total_fees_sgd"].median()),
                "median_commission_sgd": float(group["commission_sgd"].median()),
                "median_fx_fees_sgd": float(group["fx_fees_sgd"].median()),
                "win_rate_vs_lump_sum": (
                    float((delta > 0.0).mean()) if int(deployment) != 1 else float("nan")
                ),
                "median_delta_vs_lump_sum_sgd": float(delta.median()),
                "p10_delta_vs_lump_sum_sgd": float(delta.quantile(0.10)),
            }
        )
    return pd.DataFrame.from_records(rows).sort_values("deployment_months").reset_index(drop=True)
