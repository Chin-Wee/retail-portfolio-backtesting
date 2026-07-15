from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np

from .daily_data import (
    DEFAULT_DAILY_START_DATE,
    daily_data_summary,
    load_or_fetch_twelve_data_daily,
)
from .limit_orders import evaluate_limit_discount_grid
from .limit_portfolio import (
    evaluate_recurring_limit_grid,
    walk_forward_recurring_limit_selection,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run real daily SPY limit-order research using Twelve Data OHLCV"
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start-date", default=DEFAULT_DAILY_START_DATE)
    parser.add_argument("--end-date")
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path("data/processed/spy_daily_1day.csv"),
    )
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument(
        "--api-key",
        default=os.getenv("TWELVE_DATA_API_KEY"),
        help="Twelve Data key; defaults to TWELVE_DATA_API_KEY",
    )
    parser.add_argument("--output", type=Path, default=Path("results/daily_limits"))
    parser.add_argument("--discount-min", type=float, default=0.0)
    parser.add_argument("--discount-max", type=float, default=0.05)
    parser.add_argument("--discount-step", type=float, default=0.001)
    parser.add_argument("--max-wait-sessions", type=int, default=5)
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--monthly-contribution", type=float, default=1_000.0)
    parser.add_argument("--train-years", type=int, default=5)
    parser.add_argument("--test-years", type=int, default=1)
    parser.add_argument("--skip-walk-forward", action="store_true")
    return parser


def _discount_grid(minimum: float, maximum: float, step: float) -> np.ndarray:
    if minimum < 0.0 or maximum >= 1.0 or maximum < minimum:
        raise ValueError("discount range must satisfy 0 <= min <= max < 1")
    if step <= 0.0:
        raise ValueError("discount step must be positive")
    count = int(round((maximum - minimum) / step))
    return np.round(minimum + np.arange(count + 1) * step, 10)


def main() -> None:
    parser = _parser()
    args = parser.parse_args()

    try:
        discounts = _discount_grid(
            args.discount_min,
            args.discount_max,
            args.discount_step,
        )
    except ValueError as error:
        parser.error(str(error))

    daily = load_or_fetch_twelve_data_daily(
        args.api_key,
        cache_path=args.cache,
        refresh=args.refresh,
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    summary = daily_data_summary(daily, symbol=args.symbol)

    one_session = evaluate_limit_discount_grid(daily, discounts)
    recurring = evaluate_recurring_limit_grid(
        daily,
        discounts,
        max_wait_sessions=args.max_wait_sessions,
        initial_cash=args.initial_cash,
        monthly_contribution=args.monthly_contribution,
    )
    one_session_best = one_session.loc[
        one_session["mean_one_session_excess_vs_open"].idxmax()
    ].to_dict()
    recurring_best = recurring.loc[recurring["ending_excess_value"].idxmax()].to_dict()

    args.output.mkdir(parents=True, exist_ok=True)
    one_session.to_csv(args.output / "one_session_grid.csv", index=False)
    recurring.to_csv(args.output / "recurring_grid.csv", index=False)

    report: dict[str, object] = {
        "data": summary,
        "assumptions": {
            "limit_reference": "preceding session close",
            "gap_fill": "opening price when open <= limit",
            "touch_fill": "limit price when low <= limit",
            "expiry": f"market-on-close after {args.max_wait_sessions} sessions",
            "dividends_cash_yield_fees": "excluded",
        },
        "best_one_session_candidate": one_session_best,
        "best_recurring_candidate": recurring_best,
    }

    if not args.skip_walk_forward:
        walk_forward = walk_forward_recurring_limit_selection(
            daily,
            discounts,
            train_years=args.train_years,
            test_years=args.test_years,
            max_wait_sessions=args.max_wait_sessions,
            monthly_contribution=args.monthly_contribution,
        )
        walk_forward.to_csv(args.output / "walk_forward.csv", index=False)
        report["walk_forward"] = {
            "folds": int(len(walk_forward)),
            "median_selected_discount": float(walk_forward["selected_discount"].median()),
            "mean_test_excess_value": float(walk_forward["test_ending_excess_value"].mean()),
            "positive_test_fold_rate": float(
                (walk_forward["test_ending_excess_value"] > 0.0).mean()
            ),
        }

    (args.output / "summary.json").write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, default=str))
    print(f"Wrote daily limit-order results to {args.output}")


if __name__ == "__main__":
    main()
