from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
import pandas as pd

_REQUIRED = ("open", "high", "low", "close")


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


def summarize_recurring_limit_result(lots: pd.DataFrame) -> dict[str, float | int]:
    contributed = float(lots["amount"].sum())
    ending = float(lots["ending_value"].sum())
    baseline = float(lots["baseline_ending_value"].sum())
    weighted_savings = float(
        np.average(lots["execution_savings_vs_immediate_open"], weights=lots["amount"])
    )
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
        records.append(
            {
                "discount": discount,
                "max_wait_sessions": max_wait_sessions,
                **summarize_recurring_limit_result(lots),
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
) -> pd.DataFrame:
    """Select on trailing years and score the fixed discount on unseen years."""

    if min(train_years, test_years, step_years) < 1:
        raise ValueError("window lengths must be positive")
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
        selected = train_grid.loc[train_grid["ending_excess_value"].idxmax()]
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
                "selected_discount": discount,
                "train_ending_excess_value": float(selected["ending_excess_value"]),
                "test_ending_excess_value": float(tested["ending_excess_value"]),
                "test_ending_excess_pct_of_contributions": float(
                    tested["ending_excess_pct_of_contributions"]
                ),
                "test_limit_fill_rate": float(tested["limit_fill_rate"]),
                "test_forced_fill_rate": float(tested["forced_fill_rate"]),
                "test_average_wait_sessions": float(tested["average_wait_sessions"]),
            }
        )
        train_start += pd.DateOffset(years=step_years)

    if not rows:
        raise ValueError("dataset is too short for the requested walk-forward windows")
    return pd.DataFrame.from_records(rows)
