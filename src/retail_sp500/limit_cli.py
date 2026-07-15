from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .daily_data import DEFAULT_DAILY_START_DATE, daily_data_summary, load_or_fetch_twelve_data_daily
from .limit_orders import evaluate_limit_discount_grid
from .limit_plotting import (
    calmar_by_discount_figure,
    drawdown_figure,
    return_drawdown_figure,
    strategy_calmar_ranking_figure,
    strategy_drawdown_figure,
    strategy_return_drawdown_figure,
    strategy_wealth_figure,
    walk_forward_calmar_figure,
    walk_forward_discount_figure,
    wealth_index_figure,
)
from .limit_portfolio import (
    RecurringLimitConfig,
    build_recurring_limit_equity_curve,
    compare_recurring_limit_strategies,
    evaluate_recurring_limit_grid,
    simulate_recurring_limit_strategy,
    walk_forward_recurring_limit_selection,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run real daily SPY limit-order, Calmar, and strategy-chart research"
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start-date", default=DEFAULT_DAILY_START_DATE)
    parser.add_argument("--end-date")
    parser.add_argument("--cache", type=Path, default=Path("data/processed/spy_daily_1day.csv"))
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
    parser.add_argument(
        "--wait-horizons",
        default="1,3,5,10,20",
        help="Comma-separated expiry horizons used in the strategy parameter charts",
    )
    parser.add_argument(
        "--max-wait-sessions",
        type=int,
        default=5,
        help="Expiry horizon used by walk-forward selection",
    )
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--monthly-contribution", type=float, default=1_000.0)
    parser.add_argument("--train-years", type=int, default=5)
    parser.add_argument("--test-years", type=int, default=1)
    parser.add_argument(
        "--selection-metric",
        choices=("ending_excess_value", "calmar_ratio"),
        default="calmar_ratio",
        help="Metric used to select each walk-forward training candidate",
    )
    parser.add_argument("--skip-walk-forward", action="store_true")
    return parser


def _discount_grid(minimum: float, maximum: float, step: float) -> np.ndarray:
    if minimum < 0.0 or maximum >= 1.0 or maximum < minimum:
        raise ValueError("discount range must satisfy 0 <= min <= max < 1")
    if step <= 0.0:
        raise ValueError("discount step must be positive")
    count = int(round((maximum - minimum) / step))
    return np.round(minimum + np.arange(count + 1) * step, 10)


def _parse_wait_horizons(value: str) -> list[int]:
    try:
        horizons = sorted({int(part.strip()) for part in value.split(",") if part.strip()})
    except ValueError as error:
        raise ValueError("wait horizons must be comma-separated positive integers") from error
    if not horizons or horizons[0] < 1:
        raise ValueError("wait horizons must contain at least one positive integer")
    return horizons


def _best_finite(frame: pd.DataFrame, metric: str) -> dict[str, object]:
    usable = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=[metric])
    if usable.empty:
        raise ValueError(f"no finite values available for {metric}")
    return usable.loc[usable[metric].idxmax()].to_dict()


def _named_comparison_strategies(
    *,
    best_ending: dict[str, object],
    best_calmar: dict[str, object],
    walk_forward_discount: float | None,
    walk_forward_wait: int,
    initial_cash: float,
    monthly_contribution: float,
) -> dict[str, RecurringLimitConfig]:
    candidates: list[tuple[str, float, int]] = [
        ("Previous-close limit", 0.0, 1),
        ("0.5% pullback", 0.005, 5),
        ("1.0% pullback", 0.010, 5),
        ("Best terminal value", float(best_ending["discount"]), int(best_ending["max_wait_sessions"])),
        ("Best Calmar", float(best_calmar["discount"]), int(best_calmar["max_wait_sessions"])),
    ]
    if walk_forward_discount is not None:
        candidates.append(("Walk-forward median", walk_forward_discount, walk_forward_wait))

    deduplicated: dict[tuple[float, int], list[str]] = {}
    for label, discount, wait in candidates:
        deduplicated.setdefault((round(discount, 10), wait), []).append(label)

    strategies: dict[str, RecurringLimitConfig] = {}
    for (discount, wait), labels in deduplicated.items():
        combined = " / ".join(labels)
        name = f"{combined}: {discount:.1%} below, {wait} session{'s' if wait != 1 else ''}"
        strategies[name] = RecurringLimitConfig(
            discount=discount,
            max_wait_sessions=wait,
            initial_cash=initial_cash,
            monthly_contribution=monthly_contribution,
        )
    return strategies


def main() -> None:
    parser = _parser()
    args = parser.parse_args()

    try:
        discounts = _discount_grid(args.discount_min, args.discount_max, args.discount_step)
        wait_horizons = _parse_wait_horizons(args.wait_horizons)
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
    data_summary = daily_data_summary(daily, symbol=args.symbol)

    one_session = evaluate_limit_discount_grid(daily, discounts)
    strategy_grid = pd.concat(
        [
            evaluate_recurring_limit_grid(
                daily,
                discounts,
                max_wait_sessions=wait,
                initial_cash=args.initial_cash,
                monthly_contribution=args.monthly_contribution,
            ).assign(wait_horizon=wait)
            for wait in wait_horizons
        ],
        ignore_index=True,
    )
    one_session_best = one_session.loc[one_session["mean_one_session_excess_vs_open"].idxmax()].to_dict()
    best_ending = _best_finite(strategy_grid, "ending_excess_value")
    best_calmar = _best_finite(strategy_grid, "calmar_ratio")

    walk_forward: pd.DataFrame | None = None
    walk_forward_discount: float | None = None
    if not args.skip_walk_forward:
        walk_forward = walk_forward_recurring_limit_selection(
            daily,
            discounts,
            train_years=args.train_years,
            test_years=args.test_years,
            max_wait_sessions=args.max_wait_sessions,
            monthly_contribution=args.monthly_contribution,
            selection_metric=args.selection_metric,
        )
        walk_forward_discount = float(walk_forward["selected_discount"].median())

    comparison_strategies = _named_comparison_strategies(
        best_ending=best_ending,
        best_calmar=best_calmar,
        walk_forward_discount=walk_forward_discount,
        walk_forward_wait=args.max_wait_sessions,
        initial_cash=args.initial_cash,
        monthly_contribution=args.monthly_contribution,
    )
    strategy_metrics, strategy_curves = compare_recurring_limit_strategies(daily, comparison_strategies)

    calmar_config = RecurringLimitConfig(
        discount=float(best_calmar["discount"]),
        max_wait_sessions=int(best_calmar["max_wait_sessions"]),
        initial_cash=args.initial_cash,
        monthly_contribution=args.monthly_contribution,
    )
    calmar_lots = simulate_recurring_limit_strategy(daily, calmar_config)
    calmar_curve = build_recurring_limit_equity_curve(daily, calmar_lots)

    args.output.mkdir(parents=True, exist_ok=True)
    one_session.to_csv(args.output / "one_session_grid.csv", index=False)
    strategy_grid.to_csv(args.output / "strategy_grid.csv", index=False)
    strategy_metrics.to_csv(args.output / "strategy_comparison_metrics.csv", index=False)
    strategy_curves.to_csv(args.output / "strategy_comparison_curves.csv", index=False)
    calmar_lots.to_csv(args.output / "calmar_candidate_lots.csv")
    calmar_curve.to_csv(args.output / "calmar_candidate_equity_curve.csv")

    calmar_by_discount_figure(strategy_grid).write_html(args.output / "calmar_by_discount.html", include_plotlyjs="cdn")
    return_drawdown_figure(strategy_grid).write_html(args.output / "return_vs_drawdown.html", include_plotlyjs="cdn")
    strategy_calmar_ranking_figure(strategy_metrics).write_html(args.output / "strategy_calmar_ranking.html", include_plotlyjs="cdn")
    strategy_return_drawdown_figure(strategy_metrics).write_html(args.output / "strategy_return_vs_drawdown.html", include_plotlyjs="cdn")
    strategy_wealth_figure(strategy_curves).write_html(args.output / "strategy_wealth_comparison.html", include_plotlyjs="cdn")
    strategy_drawdown_figure(strategy_curves).write_html(args.output / "strategy_drawdown_comparison.html", include_plotlyjs="cdn")
    wealth_index_figure(calmar_curve).write_html(args.output / "calmar_candidate_wealth.html", include_plotlyjs="cdn")
    drawdown_figure(calmar_curve).write_html(args.output / "calmar_candidate_drawdown.html", include_plotlyjs="cdn")

    report: dict[str, object] = {
        "data": data_summary,
        "assumptions": {
            "limit_reference": "preceding session close",
            "gap_fill": "opening price when open <= limit",
            "touch_fill": "limit price when low <= limit",
            "expiry": "market-on-close after each strategy's configured wait horizon",
            "calmar": "annualized compounded contribution-neutral return divided by maximum drawdown magnitude",
            "dividends_cash_yield_fees": "excluded",
        },
        "best_one_session_candidate": one_session_best,
        "best_terminal_value_candidate": best_ending,
        "best_calmar_candidate": best_calmar,
        "strategy_comparison": strategy_metrics.to_dict(orient="records"),
    }

    if walk_forward is not None:
        walk_forward.to_csv(args.output / "walk_forward.csv", index=False)
        walk_forward_discount_figure(walk_forward).write_html(args.output / "walk_forward_selected_discount.html", include_plotlyjs="cdn")
        walk_forward_calmar_figure(walk_forward).write_html(args.output / "walk_forward_test_calmar.html", include_plotlyjs="cdn")
        report["walk_forward"] = {
            "selection_metric": args.selection_metric,
            "folds": int(len(walk_forward)),
            "median_selected_discount": walk_forward_discount,
            "mean_test_excess_value": float(walk_forward["test_ending_excess_value"].mean()),
            "positive_test_fold_rate": float((walk_forward["test_ending_excess_value"] > 0.0).mean()),
            "mean_test_calmar_ratio": float(walk_forward["test_calmar_ratio"].mean()),
            "median_test_calmar_ratio": float(walk_forward["test_calmar_ratio"].median()),
            "calmar_beats_baseline_fold_rate": float((walk_forward["test_calmar_ratio"] > walk_forward["test_baseline_calmar_ratio"]).mean()),
        }

    (args.output / "summary.json").write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    print(f"Wrote daily strategy comparison data and graphs to {args.output}")


if __name__ == "__main__":
    main()
