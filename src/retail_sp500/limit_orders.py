from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

_REQUIRED_COLUMNS = ("open", "high", "low", "close")


def _validate_daily_prices(daily: pd.DataFrame) -> pd.DataFrame:
    missing = [column for column in _REQUIRED_COLUMNS if column not in daily.columns]
    if missing:
        raise KeyError(f"daily data is missing: {', '.join(missing)}")
    if not isinstance(daily.index, pd.DatetimeIndex):
        raise TypeError("daily data must use a DatetimeIndex")
    if daily.index.has_duplicates or not daily.index.is_monotonic_increasing:
        raise ValueError("daily index must be unique and sorted")
    return daily.copy()


def one_session_limit_outcomes(daily: pd.DataFrame, discount: float) -> pd.DataFrame:
    """Evaluate next-session buy limits set after each preceding close.

    A buy order is placed after session t-1 at ``close * (1 - discount)`` and is
    valid only during session t. A gap below the limit fills at the opening price;
    otherwise a low touching the limit fills at the limit. Unfilled capital stays
    in cash for that one-session experiment.
    """

    if not 0.0 <= discount < 1.0:
        raise ValueError("discount must be in the [0, 1) range")

    frame = _validate_daily_prices(daily)
    previous_close = frame["close"].shift(1)
    limit_price = previous_close * (1.0 - discount)
    eligible = previous_close.notna()
    gap_fill = eligible & (frame["open"] <= limit_price)
    touched_fill = eligible & ~gap_fill & (frame["low"] <= limit_price)
    filled = gap_fill | touched_fill

    fill_price = pd.Series(np.nan, index=frame.index, dtype=float)
    fill_price.loc[gap_fill] = frame.loc[gap_fill, "open"]
    fill_price.loc[touched_fill] = limit_price.loc[touched_fill]

    market_end_value = frame["close"] / frame["open"]
    limit_end_value = pd.Series(1.0, index=frame.index, dtype=float)
    limit_end_value.loc[filled] = frame.loc[filled, "close"] / fill_price.loc[filled]

    outcome = pd.DataFrame(
        {
            "previous_close": previous_close,
            "open": frame["open"],
            "low": frame["low"],
            "close": frame["close"],
            "limit_price": limit_price,
            "filled": filled,
            "gap_fill": gap_fill,
            "touch_fill": touched_fill,
            "fill_price": fill_price,
            "market_end_value": market_end_value,
            "limit_end_value": limit_end_value,
        },
        index=frame.index,
    ).loc[eligible]
    outcome["fill_discount_from_previous_close"] = np.where(
        outcome["filled"],
        1.0 - outcome["fill_price"] / outcome["previous_close"],
        np.nan,
    )
    outcome["one_session_excess_vs_open"] = (
        outcome["limit_end_value"] - outcome["market_end_value"]
    )
    outcome["unfilled_rising_session"] = (~outcome["filled"]) & (
        outcome["close"] > outcome["open"]
    )
    outcome.attrs["discount"] = discount
    return outcome


def evaluate_limit_discount_grid(
    daily: pd.DataFrame,
    discounts: Iterable[float],
) -> pd.DataFrame:
    """Summarize a grid of one-session limit distances without look-ahead."""

    records: list[dict[str, float | int]] = []
    for discount in discounts:
        outcome = one_session_limit_outcomes(daily, float(discount))
        filled = outcome["filled"]
        unfilled = ~filled
        records.append(
            {
                "discount": float(discount),
                "sessions": int(len(outcome)),
                "fills": int(filled.sum()),
                "fill_rate": float(filled.mean()),
                "gap_fill_rate": float(outcome["gap_fill"].mean()),
                "mean_fill_discount": float(
                    outcome.loc[filled, "fill_discount_from_previous_close"].mean()
                )
                if filled.any()
                else float("nan"),
                "median_fill_discount": float(
                    outcome.loc[filled, "fill_discount_from_previous_close"].median()
                )
                if filled.any()
                else float("nan"),
                "mean_limit_end_value": float(outcome["limit_end_value"].mean()),
                "mean_market_end_value": float(outcome["market_end_value"].mean()),
                "mean_one_session_excess_vs_open": float(
                    outcome["one_session_excess_vs_open"].mean()
                ),
                "unfilled_rising_session_rate": float(
                    outcome.loc[unfilled, "unfilled_rising_session"].mean()
                )
                if unfilled.any()
                else 0.0,
            }
        )

    summary = pd.DataFrame.from_records(records).sort_values("discount").reset_index(drop=True)
    if summary.empty:
        raise ValueError("at least one discount is required")
    return summary
