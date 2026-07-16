from __future__ import annotations

from collections.abc import Sequence
import math

import numpy as np
import pandas as pd

from .data import validate_daily
from .models import (
    ComparisonResult,
    LabConfig,
    StrategyRun,
    StrategySpec,
    default_strategies,
    strategy_discounts,
)

def _first_salary_session(index: pd.DatetimeIndex, month: pd.Period, salary_day: int) -> pd.Timestamp | None:
    sessions = index[index.to_period("M") == month]
    eligible = sessions[sessions.day >= salary_day]
    return pd.Timestamp(eligible[0]) if len(eligible) else None


def _contribution_events(
    index: pd.DatetimeIndex,
    *,
    evaluation_start: pd.Timestamp,
    config: LabConfig,
) -> list[tuple[pd.Timestamp, float]]:
    eligible = index[index >= evaluation_start]
    if len(eligible) == 0:
        raise ValueError("evaluation_start is after the available data")

    initial_session = pd.Timestamp(eligible[0])
    events: list[tuple[pd.Timestamp, float]] = []
    if config.initial_cash > 0.0:
        events.append((initial_session, config.initial_cash))

    if config.monthly_contribution > 0.0:
        months = pd.period_range(initial_session.to_period("M"), index[-1].to_period("M"), freq="M")
        for month in months[1:]:
            session = _first_salary_session(index, month, config.salary_day)
            if session is not None:
                events.append((session, config.monthly_contribution))
    return events


def _month_end_position(index: pd.DatetimeIndex, position: int) -> int:
    month = index[position].to_period("M")
    positions = np.flatnonzero(index.to_period("M") == month)
    return int(positions[-1])


def simulate_strategy(
    daily: pd.DataFrame,
    spec: StrategySpec,
    discount: pd.Series,
    *,
    evaluation_start: pd.Timestamp,
    config: LabConfig,
) -> pd.DataFrame:
    frame = validate_daily(daily)
    discount = discount.reindex(frame.index)
    rows: list[dict[str, object]] = []

    for contribution_date, amount in _contribution_events(
        frame.index,
        evaluation_start=evaluation_start,
        config=config,
    ):
        start = int(frame.index.get_loc(contribution_date))
        immediate_price = float(frame["open"].iloc[start])

        if spec.family == "immediate":
            fill_position = start
            fill_price = immediate_price
            fill_type = "immediate"
            applied_discount = 0.0
            limit_price = immediate_price
        else:
            month_end = _month_end_position(frame.index, start)
            expiry = min(start + spec.max_wait_sessions - 1, month_end)
            fill_position = expiry
            fill_price = float(frame["close"].iloc[expiry])
            fill_type = "expiry_close"
            applied_discount = float(discount.iloc[expiry])
            limit_price = float("nan")

            for position in range(start, expiry + 1):
                applied_discount = float(discount.iloc[position])
                if not math.isfinite(applied_discount):
                    raise ValueError(f"strategy {spec.key!r} has unavailable data at {frame.index[position]}")
                reference_close = float(frame["close"].iloc[position - 1])
                limit_price = reference_close * (1.0 - applied_discount)
                row = frame.iloc[position]
                if float(row["open"]) <= limit_price:
                    fill_position = position
                    fill_price = float(row["open"])
                    fill_type = "gap"
                    break
                if float(row["low"]) <= limit_price:
                    fill_position = position
                    fill_price = limit_price
                    fill_type = "touch"
                    break

        rows.append(
            {
                "contribution_date": contribution_date,
                "amount": amount,
                "fill_date": frame.index[fill_position],
                "fill_type": fill_type,
                "wait_sessions": fill_position - start + 1,
                "discount": applied_discount,
                "limit_price": limit_price,
                "fill_price": fill_price,
                "immediate_open_price": immediate_price,
                "execution_savings_vs_immediate": 1.0 - fill_price / immediate_price,
                "units": amount / fill_price,
            }
        )

    if not rows:
        raise ValueError("no contribution events were generated")
    result = pd.DataFrame.from_records(rows).set_index("contribution_date")
    result.index = pd.DatetimeIndex(result.index)
    return result


def _returns_to_wealth(returns: pd.Series) -> pd.Series:
    clean = pd.to_numeric(returns, errors="coerce").fillna(0.0)
    if (clean <= -1.0).any():
        raise ValueError("returns must exceed -100%")
    return (1.0 + clean).cumprod()


def _drawdown(wealth: pd.Series) -> pd.Series:
    running_peak = wealth.cummax().clip(lower=1.0)
    return wealth / running_peak - 1.0


def build_curve(daily: pd.DataFrame, lots: pd.DataFrame) -> pd.DataFrame:
    frame = validate_daily(daily)
    size = len(frame)
    contributions = np.zeros(size, dtype=float)
    cash_changes = np.zeros(size + 1, dtype=float)
    unit_changes = np.zeros(size + 1, dtype=float)

    for contribution_date, lot in lots.iterrows():
        start = int(frame.index.get_loc(pd.Timestamp(contribution_date)))
        fill = int(frame.index.get_loc(pd.Timestamp(lot["fill_date"])))
        amount = float(lot["amount"])
        contributions[start] += amount
        if fill > start:
            cash_changes[start] += amount
            cash_changes[fill] -= amount
        unit_changes[fill] += float(lot["units"])

    cash = np.cumsum(cash_changes[:-1])
    units = np.cumsum(unit_changes[:-1])
    value = cash + units * frame["close"].to_numpy(dtype=float)
    curve = pd.DataFrame(
        {
            "contribution": contributions,
            "cash": cash,
            "units": units,
            "portfolio_value": value,
        },
        index=frame.index,
    )
    curve = curve.loc[curve["contribution"].cumsum() > 0.0].copy()
    capital = curve["portfolio_value"].shift(1).fillna(0.0) + curve["contribution"]
    curve["daily_return"] = curve["portfolio_value"] / capital - 1.0
    curve["wealth_index"] = _returns_to_wealth(curve["daily_return"])
    curve["drawdown"] = _drawdown(curve["wealth_index"])
    curve.index.name = "date"
    return curve


def return_metrics(returns: pd.Series, *, periods_per_year: int = 252) -> dict[str, float | int]:
    clean = pd.to_numeric(returns, errors="coerce").dropna().astype(float)
    if clean.empty:
        raise ValueError("at least one return is required")
    growth = float((1.0 + clean).prod())
    annualized = growth ** (periods_per_year / len(clean)) - 1.0
    wealth = _returns_to_wealth(clean)
    max_drawdown = float(_drawdown(wealth).min())
    calmar = annualized / abs(max_drawdown) if abs(max_drawdown) > np.finfo(float).eps else float("nan")
    volatility = float(clean.std(ddof=1) * math.sqrt(periods_per_year)) if len(clean) > 1 else float("nan")
    return {
        "return_periods": int(len(clean)),
        "annualized_return": annualized,
        "annualized_volatility": volatility,
        "max_drawdown": max_drawdown,
        "calmar_ratio": calmar,
    }


def _run_metrics(spec: StrategySpec, lots: pd.DataFrame, curve: pd.DataFrame) -> dict[str, float | int | str]:
    contributed = float(lots["amount"].sum())
    ending_value = float(curve["portfolio_value"].iloc[-1])
    natural_fill = lots["fill_type"].isin(["gap", "touch", "immediate"])
    weighted_savings = float(
        np.average(lots["execution_savings_vs_immediate"], weights=lots["amount"])
    )
    return {
        "strategy": spec.label,
        "key": spec.key,
        "family": spec.family,
        "max_wait_sessions": spec.max_wait_sessions,
        "total_contributed": contributed,
        "ending_value": ending_value,
        "natural_fill_rate": float(natural_fill.mean()),
        "forced_fill_rate": float((lots["fill_type"] == "expiry_close").mean()),
        "average_wait_sessions": float(lots["wait_sessions"].mean()),
        "weighted_execution_savings": weighted_savings,
        **return_metrics(curve["daily_return"]),
    }


def _period_metrics(curve: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp | None) -> dict[str, float | int]:
    selected = curve
    if start is not None:
        selected = selected.loc[selected.index >= start]
    if end is not None:
        selected = selected.loc[selected.index < end]
    if selected.empty:
        raise ValueError("selected metric period contains no returns")
    return return_metrics(selected["daily_return"])


def compare_strategies(
    daily: pd.DataFrame,
    strategies: Sequence[StrategySpec] | None = None,
    *,
    config: LabConfig = LabConfig(),
) -> ComparisonResult:
    frame = validate_daily(daily)
    strategy_list = list(strategies or default_strategies())
    keys = [spec.key for spec in strategy_list]
    if len(keys) != len(set(keys)):
        raise ValueError("strategy keys must be unique")
    if "immediate" not in keys:
        raise ValueError("the immediate strategy is required as the benchmark")

    discounts = {spec.key: strategy_discounts(frame, spec) for spec in strategy_list}
    available_starts = []
    for spec in strategy_list:
        first = discounts[spec.key].first_valid_index()
        if first is None:
            raise ValueError(f"strategy {spec.key!r} never becomes available")
        available_starts.append(pd.Timestamp(first))
    evaluation_start = max(max(available_starts), frame.index[1])

    runs: dict[str, StrategyRun] = {}
    records: list[dict[str, object]] = []
    curve_frames: list[pd.DataFrame] = []
    for spec in strategy_list:
        lots = simulate_strategy(
            frame,
            spec,
            discounts[spec.key],
            evaluation_start=evaluation_start,
            config=config,
        )
        curve = build_curve(frame, lots)
        metrics = _run_metrics(spec, lots, curve)
        runs[spec.key] = StrategyRun(spec, lots, curve, metrics)
        records.append(metrics)
        selected = curve[["portfolio_value", "contribution", "daily_return", "wealth_index", "drawdown"]].copy()
        selected["key"] = spec.key
        selected["strategy"] = spec.label
        curve_frames.append(selected.reset_index())

    metrics = pd.DataFrame.from_records(records)
    baseline_ending = float(metrics.loc[metrics["key"] == "immediate", "ending_value"].iloc[0])
    metrics["ending_excess_value"] = metrics["ending_value"] - baseline_ending
    metrics["ending_excess_pct_of_contributions"] = (
        metrics["ending_excess_value"] / metrics["total_contributed"]
    )

    holdout_start = max(
        evaluation_start + pd.DateOffset(years=1),
        frame.index[-1] - pd.DateOffset(years=config.holdout_years),
    )
    period_records = []
    for key, run in runs.items():
        selection = _period_metrics(run.curve, None, holdout_start)
        holdout = _period_metrics(run.curve, holdout_start, None)
        period_records.append(
            {
                "key": key,
                **{f"selection_{name}": value for name, value in selection.items()},
                **{f"holdout_{name}": value for name, value in holdout.items()},
            }
        )
    metrics = metrics.merge(pd.DataFrame.from_records(period_records), on="key", how="left")
    baseline = metrics.loc[metrics["key"] == "immediate"].iloc[0]
    metrics["selection_calmar_delta"] = metrics["selection_calmar_ratio"] - baseline["selection_calmar_ratio"]
    metrics["holdout_calmar_delta"] = metrics["holdout_calmar_ratio"] - baseline["holdout_calmar_ratio"]
    metrics["worth_testing"] = (
        (metrics["selection_calmar_delta"] > 0.0)
        & (metrics["selection_annualized_return"] >= baseline["selection_annualized_return"] - 0.0025)
    )
    metrics = metrics.sort_values(
        ["worth_testing", "selection_calmar_ratio", "selection_annualized_return"],
        ascending=[False, False, False],
    ).reset_index(drop=True)

    curves = pd.concat(curve_frames, ignore_index=True).sort_values(["date", "key"])
    return ComparisonResult(
        daily=frame,
        evaluation_start=evaluation_start,
        holdout_start=pd.Timestamp(holdout_start),
        specs={spec.key: spec for spec in strategy_list},
        runs=runs,
        metrics=metrics,
        curves=curves,
    )
