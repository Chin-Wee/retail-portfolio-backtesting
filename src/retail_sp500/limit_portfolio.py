from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .risk_metrics import drawdown_series, summarize_return_series, wealth_index_from_returns

_REQUIRED = ("open", "high", "low", "close")
_SELECTION_METRICS = ("ending_excess_value", "calmar_ratio")


def _validate(daily: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in _REQUIRED if column not in daily]
    if missing:
        raise KeyError(f"daily data is missing: {', '.join(missing)}")
    if not isinstance(daily.index, pd.DatetimeIndex):
        raise TypeError("daily data must use a DatetimeIndex")
    if daily.index.has_duplicates or not daily.index.is_monotonic_increasing:
        raise ValueError("daily index must be unique and sorted")
    if len(daily) < 2:
        raise ValueError("at least two sessions are required")
    return daily.copy()


def _discounts(values: Iterable[float]) -> list[float]:
    result = sorted({float(value) for value in values})
    if not result:
        raise ValueError("at least one discount is required")
    if result[0] < 0.0 or result[-1] >= 1.0:
        raise ValueError("discounts must be in the [0, 1) range")
    return result


@dataclass(frozen=True)
class RecurringLimitConfig:
    discount: float
    max_wait_sessions: int = 5
    initial_cash: float = 100_000.0
    monthly_contribution: float = 1_000.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.discount < 1.0:
            raise ValueError("discount must be in the [0, 1) range")
        if self.max_wait_sessions < 1:
            raise ValueError("max_wait_sessions must be positive")
        if min(self.initial_cash, self.monthly_contribution) < 0.0:
            raise ValueError("cash flows cannot be negative")
        if self.initial_cash == self.monthly_contribution == 0.0:
            raise ValueError("at least one cash flow must be positive")


def _events(frame: pd.DataFrame, config: RecurringLimitConfig) -> list[tuple[pd.Timestamp, float]]:
    eligible = frame.index[1:]
    events: list[tuple[pd.Timestamp, float]] = []
    if config.initial_cash > 0.0:
        events.append((eligible[0], config.initial_cash))
    if config.monthly_contribution > 0.0:
        first_sessions = pd.Series(eligible, index=eligible).groupby(eligible.to_period("M")).first()
        initial_month = eligible[0].to_period("M")
        events.extend(
            (pd.Timestamp(session), config.monthly_contribution)
            for session in first_sessions
            if pd.Timestamp(session).to_period("M") != initial_month
        )
    return sorted(events)


def simulate_recurring_limit_strategy(
    daily: pd.DataFrame,
    config: RecurringLimitConfig,
) -> pd.DataFrame:
    """Track lump-sum and monthly cash lots using daily-repriced limits.

    A lot's limit is reset each session from the preceding close. Gap fills receive
    the open, touches receive the limit, and expiry buys at that session's close.
    Dividends, cash yield, spreads, fees, and taxes are excluded.
    """

    frame = _validate(daily)
    final_close = float(frame["close"].iloc[-1])
    rows: list[dict[str, object]] = []

    for contribution_date, amount in _events(frame, config):
        start = int(frame.index.get_loc(contribution_date))
        if start + config.max_wait_sessions - 1 >= len(frame):
            continue

        baseline_price = float(frame["open"].iloc[start])
        fill_date: pd.Timestamp | None = None
        fill_price = float("nan")
        fill_type = "unfilled"
        wait = config.max_wait_sessions
        reference_close = float("nan")
        limit_price = float("nan")

        for offset in range(config.max_wait_sessions):
            position = start + offset
            row = frame.iloc[position]
            reference_close = float(frame["close"].iloc[position - 1])
            limit_price = reference_close * (1.0 - config.discount)
            wait = offset + 1
            if float(row["open"]) <= limit_price:
                fill_date, fill_price, fill_type = frame.index[position], float(row["open"]), "gap"
                break
            if float(row["low"]) <= limit_price:
                fill_date, fill_price, fill_type = frame.index[position], limit_price, "touch"
                break
            if wait == config.max_wait_sessions:
                fill_date, fill_price, fill_type = frame.index[position], float(row["close"]), "expiry_close"

        units = amount / fill_price
        baseline_units = amount / baseline_price
        ending_value = units * final_close
        baseline_ending_value = baseline_units * final_close
        rows.append(
            {
                "contribution_date": contribution_date,
                "amount": amount,
                "discount": config.discount,
                "max_wait_sessions": config.max_wait_sessions,
                "fill_date": fill_date,
                "fill_type": fill_type,
                "wait_sessions": wait,
                "reference_close": reference_close,
                "limit_price": limit_price,
                "fill_price": fill_price,
                "baseline_open_price": baseline_price,
                "execution_savings_vs_immediate_open": 1.0 - fill_price / baseline_price,
                "units": units,
                "baseline_units": baseline_units,
                "ending_value": ending_value,
                "baseline_ending_value": baseline_ending_value,
                "ending_excess_value": ending_value - baseline_ending_value,
            }
        )

    if not rows:
        raise ValueError("dataset is too short for the contribution and expiry rules")
    result = pd.DataFrame.from_records(rows).set_index("contribution_date")
    result.attrs.update({"final_date": frame.index[-1], "final_close": final_close})
    return result


def build_recurring_limit_equity_curve(
    daily: pd.DataFrame,
    lots: pd.DataFrame,
) -> pd.DataFrame:
    """Build contribution-neutral daily returns, wealth, and drawdown from lot fills."""

    frame = _validate(daily)
    required = {"amount", "fill_date", "units", "baseline_units"}
    missing = sorted(required.difference(lots.columns))
    if missing:
        raise KeyError(f"lot data is missing: {', '.join(missing)}")
    if not isinstance(lots.index, pd.DatetimeIndex):
        raise TypeError("lot data must use contribution dates as a DatetimeIndex")

    size = len(frame)
    contributions = np.zeros(size, dtype=float)
    cash_changes = np.zeros(size + 1, dtype=float)
    unit_changes = np.zeros(size + 1, dtype=float)
    baseline_unit_changes = np.zeros(size + 1, dtype=float)

    for contribution_date, lot in lots.iterrows():
        start = int(frame.index.get_loc(pd.Timestamp(contribution_date)))
        fill = int(frame.index.get_loc(pd.Timestamp(lot["fill_date"])))
        amount = float(lot["amount"])
        contributions[start] += amount
        if fill > start:
            cash_changes[start] += amount
            cash_changes[fill] -= amount
        unit_changes[fill] += float(lot["units"])
        baseline_unit_changes[start] += float(lot["baseline_units"])

    cash_balance = np.cumsum(cash_changes[:-1])
    invested_units = np.cumsum(unit_changes[:-1])
    baseline_units = np.cumsum(baseline_unit_changes[:-1])
    close = frame["close"].to_numpy(dtype=float)
    portfolio_value = cash_balance + invested_units * close
    baseline_value = baseline_units * close

    curve = pd.DataFrame(
        {
            "close": close,
            "contribution": contributions,
            "cash_balance": cash_balance,
            "invested_units": invested_units,
            "portfolio_value": portfolio_value,
            "baseline_portfolio_value": baseline_value,
        },
        index=frame.index,
    )
    active = curve["contribution"].cumsum() > 0.0
    curve = curve.loc[active].copy()

    strategy_capital = curve["portfolio_value"].shift(1).fillna(0.0) + curve["contribution"]
    baseline_capital = curve["baseline_portfolio_value"].shift(1).fillna(0.0) + curve["contribution"]
    curve["strategy_return"] = curve["portfolio_value"] / strategy_capital - 1.0
    curve["baseline_return"] = curve["baseline_portfolio_value"] / baseline_capital - 1.0
    curve["wealth_index"] = wealth_index_from_returns(curve["strategy_return"])
    curve["baseline_wealth_index"] = wealth_index_from_returns(curve["baseline_return"])
    curve["drawdown"] = drawdown_series(curve["wealth_index"])
    curve["baseline_drawdown"] = drawdown_series(curve["baseline_wealth_index"])
    curve.index.name = "date"
    return curve


def summarize_recurring_limit_result(lots: pd.DataFrame) -> dict[str, float | int]:
    contributed = float(lots["amount"].sum())
    ending = float(lots["ending_value"].sum())
    baseline = float(lots["baseline_ending_value"].sum())
    weighted_savings = float(np.average(lots["execution_savings_vs_immediate_open"], weights=lots["amount"]))
    return {
        "lots": int(len(lots)),
        "total_contributed": contributed,
        "ending_value": ending,
        "baseline_ending_value": baseline,
        "ending_excess_value": ending - baseline,
        "ending_excess_pct_of_contributions": (ending - baseline) / contributed,
        "limit_fill_rate": float(lots["fill_type"].isin(["gap", "touch"]).mean()),
        "gap_fill_rate": float((lots["fill_type"] == "gap").mean()),
        "touch_fill_rate": float((lots["fill_type"] == "touch").mean()),
        "forced_fill_rate": float((lots["fill_type"] == "expiry_close").mean()),
        "average_wait_sessions": float(lots["wait_sessions"].mean()),
        "weighted_execution_savings_vs_immediate_open": weighted_savings,
    }


def summarize_recurring_limit_risk(curve: pd.DataFrame) -> dict[str, float | int]:
    strategy = summarize_return_series(curve["strategy_return"])
    baseline = summarize_return_series(curve["baseline_return"])
    return {
        **strategy,
        "baseline_annualized_return": float(baseline["annualized_return"]),
        "baseline_max_drawdown": float(baseline["max_drawdown"]),
        "baseline_calmar_ratio": float(baseline["calmar_ratio"]),
        "calmar_ratio_delta": float(strategy["calmar_ratio"]) - float(baseline["calmar_ratio"]),
    }


def compare_recurring_limit_strategies(
    daily: pd.DataFrame,
    strategies: Mapping[str, RecurringLimitConfig],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compare named recurring strategies on one contribution-neutral basis."""

    if not strategies:
        raise ValueError("at least one named strategy is required")

    expected_cash_flows: tuple[float, float] | None = None
    records: list[dict[str, object]] = []
    curve_frames: list[pd.DataFrame] = []
    baseline_curve: pd.DataFrame | None = None
    baseline_metrics: dict[str, float | int] | None = None
    baseline_ending_value: float | None = None
    total_contributed: float | None = None

    for name, config in strategies.items():
        if not str(name).strip():
            raise ValueError("strategy names cannot be empty")
        cash_flows = (config.initial_cash, config.monthly_contribution)
        if expected_cash_flows is None:
            expected_cash_flows = cash_flows
        elif cash_flows != expected_cash_flows:
            raise ValueError("compared strategies must use identical cash-flow assumptions")

        lots = simulate_recurring_limit_strategy(daily, config)
        curve = build_recurring_limit_equity_curve(daily, lots)
        lot_summary = summarize_recurring_limit_result(lots)
        risk_summary = summarize_recurring_limit_risk(curve)
        records.append(
            {
                "strategy": str(name),
                "discount": config.discount,
                "max_wait_sessions": config.max_wait_sessions,
                **lot_summary,
                "annualized_return": risk_summary["annualized_return"],
                "max_drawdown": risk_summary["max_drawdown"],
                "calmar_ratio": risk_summary["calmar_ratio"],
            }
        )

        selected_curve = curve[["wealth_index", "drawdown"]].copy()
        selected_curve["strategy"] = str(name)
        curve_frames.append(selected_curve.reset_index())

        if baseline_curve is None:
            baseline_curve = curve[["baseline_wealth_index", "baseline_drawdown"]].rename(
                columns={"baseline_wealth_index": "wealth_index", "baseline_drawdown": "drawdown"}
            )
            baseline_metrics = summarize_return_series(curve["baseline_return"])
            baseline_ending_value = float(lot_summary["baseline_ending_value"])
            total_contributed = float(lot_summary["total_contributed"])

    assert baseline_curve is not None
    assert baseline_metrics is not None
    assert baseline_ending_value is not None
    assert total_contributed is not None

    baseline_curve = baseline_curve.copy()
    baseline_curve["strategy"] = "Immediate open"
    curve_frames.insert(0, baseline_curve.reset_index())
    records.insert(
        0,
        {
            "strategy": "Immediate open",
            "discount": float("nan"),
            "max_wait_sessions": 0,
            "lots": float("nan"),
            "total_contributed": total_contributed,
            "ending_value": baseline_ending_value,
            "baseline_ending_value": baseline_ending_value,
            "ending_excess_value": 0.0,
            "ending_excess_pct_of_contributions": 0.0,
            "limit_fill_rate": float("nan"),
            "gap_fill_rate": float("nan"),
            "touch_fill_rate": float("nan"),
            "forced_fill_rate": float("nan"),
            "average_wait_sessions": 0.0,
            "weighted_execution_savings_vs_immediate_open": 0.0,
            "annualized_return": baseline_metrics["annualized_return"],
            "max_drawdown": baseline_metrics["max_drawdown"],
            "calmar_ratio": baseline_metrics["calmar_ratio"],
        },
    )

    metrics = pd.DataFrame.from_records(records)
    curves = pd.concat(curve_frames, ignore_index=True).sort_values(["date", "strategy"])
    return metrics, curves


def evaluate_recurring_limit_grid(
    daily: pd.DataFrame,
    discounts: Iterable[float],
    *,
    max_wait_sessions: int = 5,
    initial_cash: float = 100_000.0,
    monthly_contribution: float = 1_000.0,
) -> pd.DataFrame:
    records = []
    for discount in _discounts(discounts):
        lots = simulate_recurring_limit_strategy(
            daily,
            RecurringLimitConfig(discount, max_wait_sessions, initial_cash, monthly_contribution),
        )
        curve = build_recurring_limit_equity_curve(daily, lots)
        records.append(
            {
                "discount": discount,
                "max_wait_sessions": max_wait_sessions,
                **summarize_recurring_limit_result(lots),
                **summarize_recurring_limit_risk(curve),
            }
        )
    return pd.DataFrame.from_records(records).sort_values("discount").reset_index(drop=True)


def _window(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    first = int(frame.index.searchsorted(start, side="left"))
    last = int(frame.index.searchsorted(end, side="right"))
    return frame.iloc[max(0, first - 1) : last]


def walk_forward_recurring_limit_selection(
    daily: pd.DataFrame,
    discounts: Iterable[float],
    *,
    train_years: int = 5,
    test_years: int = 1,
    step_years: int = 1,
    max_wait_sessions: int = 5,
    monthly_contribution: float = 1_000.0,
    selection_metric: str = "ending_excess_value",
) -> pd.DataFrame:
    """Select on trailing years and score the fixed discount on unseen years."""

    if min(train_years, test_years, step_years) < 1:
        raise ValueError("window lengths must be positive")
    if selection_metric not in _SELECTION_METRICS:
        raise ValueError(f"selection_metric must be one of: {', '.join(_SELECTION_METRICS)}")
    frame = _validate(daily)
    candidates = _discounts(discounts)
    train_start, final_date = frame.index[1], frame.index[-1]
    rows: list[dict[str, object]] = []

    while True:
        train_end = train_start + pd.DateOffset(years=train_years) - pd.Timedelta(days=1)
        test_start = train_end + pd.Timedelta(days=1)
        test_end = test_start + pd.DateOffset(years=test_years) - pd.Timedelta(days=1)
        if test_end > final_date:
            break
        train, test = _window(frame, train_start, train_end), _window(frame, test_start, test_end)
        if len(train) < 50 or len(test) < 20:
            train_start += pd.DateOffset(years=step_years)
            continue

        train_grid = evaluate_recurring_limit_grid(
            train,
            candidates,
            max_wait_sessions=max_wait_sessions,
            initial_cash=monthly_contribution,
            monthly_contribution=monthly_contribution,
        )
        usable = train_grid.dropna(subset=[selection_metric])
        if usable.empty:
            raise ValueError(f"no finite training values for selection metric {selection_metric!r}")
        selected = usable.loc[usable[selection_metric].idxmax()]
        discount = float(selected["discount"])
        tested = evaluate_recurring_limit_grid(
            test,
            [discount],
            max_wait_sessions=max_wait_sessions,
            initial_cash=monthly_contribution,
            monthly_contribution=monthly_contribution,
        ).iloc[0]
        rows.append(
            {
                "train_start": train_start,
                "train_end": train_end,
                "test_start": test_start,
                "test_end": test_end,
                "selection_metric": selection_metric,
                "selected_discount": discount,
                "train_selected_metric": float(selected[selection_metric]),
                "train_ending_excess_value": float(selected["ending_excess_value"]),
                "train_calmar_ratio": float(selected["calmar_ratio"]),
                "test_ending_excess_value": float(tested["ending_excess_value"]),
                "test_ending_excess_pct_of_contributions": float(tested["ending_excess_pct_of_contributions"]),
                "test_annualized_return": float(tested["annualized_return"]),
                "test_max_drawdown": float(tested["max_drawdown"]),
                "test_calmar_ratio": float(tested["calmar_ratio"]),
                "test_baseline_calmar_ratio": float(tested["baseline_calmar_ratio"]),
                "test_limit_fill_rate": float(tested["limit_fill_rate"]),
                "test_forced_fill_rate": float(tested["forced_fill_rate"]),
                "test_average_wait_sessions": float(tested["average_wait_sessions"]),
            }
        )
        train_start += pd.DateOffset(years=step_years)

    if not rows:
        raise ValueError("dataset is too short for the requested walk-forward windows")
    return pd.DataFrame.from_records(rows)
