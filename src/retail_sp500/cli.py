from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .data import DEFAULT_START_DATE, load_market, market_summary
from .research import LabConfig, build_stack, compare_strategies, export_results


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare automated monthly SPY purchase strategies and build a robust stack"
    )
    parser.add_argument("--symbol", default="SPY")
    parser.add_argument("--start-date", default=DEFAULT_START_DATE)
    parser.add_argument("--end-date")
    parser.add_argument("--cache", type=Path, default=Path("data/spy_daily.csv"))
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--api-key", default=os.getenv("TWELVE_DATA_API_KEY"))
    parser.add_argument("--output", type=Path, default=Path("results/portfolio"))
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--monthly-contribution", type=float, default=1_000.0)
    parser.add_argument("--salary-day", type=int, default=1)
    parser.add_argument("--holdout-years", type=int, default=4)
    parser.add_argument("--max-stack-components", type=int, default=4)
    parser.add_argument(
        "--approve",
        action="append",
        dest="approved",
        metavar="STRATEGY_KEY",
        help="Restrict stacking to an approved strategy key; repeat as needed",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    config = LabConfig(
        initial_cash=args.initial_cash,
        monthly_contribution=args.monthly_contribution,
        salary_day=args.salary_day,
        holdout_years=args.holdout_years,
        stack_max_components=args.max_stack_components,
    )
    daily = load_market(
        args.api_key,
        cache_path=args.cache,
        refresh=args.refresh,
        symbol=args.symbol,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    comparison = compare_strategies(daily, config=config)
    stack = build_stack(
        comparison,
        config=config,
        approved_strategies=args.approved,
    )
    output = export_results(comparison, stack, output_dir=args.output)

    ranking_columns = [
        "key",
        "strategy",
        "selection_calmar_ratio",
        "holdout_calmar_ratio",
        "holdout_annualized_return",
        "holdout_max_drawdown",
        "worth_testing",
    ]
    print(json.dumps(market_summary(daily, symbol=args.symbol), indent=2))
    print(comparison.metrics[ranking_columns].head(15).to_string(index=False))
    print("\nStack weights:")
    print(stack.weights.to_string())
    print("\nStack metrics:")
    print(json.dumps(stack.metrics, indent=2, default=float))
    print(f"\nWrote results and charts to {output}")


if __name__ == "__main__":
    main()
