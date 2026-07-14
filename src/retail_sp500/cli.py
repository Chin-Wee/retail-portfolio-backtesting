from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

import pandas as pd

from .backtest import BacktestConfig, run_many
from .data import enrich_with_risk_free_rate, load_shiller_data, synthetic_market_data
from .live import fetch_twelve_data_quote
from .plotting import comparison_figure
from .strategies import select_strategies, strategy_catalog


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run monthly S&P 500 strategy backtests")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--data", type=Path, help="Local Shiller XLS/XLSX/CSV file")
    source.add_argument("--synthetic", action="store_true", help="Use deterministic demo data")
    parser.add_argument("--risk-free-data", type=Path, help="Local FRED TB3MS CSV file")
    parser.add_argument(
        "--fetch-risk-free",
        action="store_true",
        help="Download FRED TB3MS and enable risk-free-dependent strategies",
    )
    parser.add_argument(
        "--strategy",
        action="append",
        dest="strategies",
        metavar="KEY",
        help="Run one strategy key; repeat to compare several. Defaults to all available.",
    )
    parser.add_argument("--list-strategies", action="store_true")
    parser.add_argument("--live-quote", action="store_true", help="Print a current Twelve Data quote and exit")
    parser.add_argument("--live-symbol", default="SPY")
    parser.add_argument("--twelve-data-api-key", default=os.getenv("TWELVE_DATA_API_KEY"))
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--monthly-contribution", type=float, default=1_000.0)
    parser.add_argument("--cash-annual-return", type=float, default=0.0)
    return parser


def _print_strategy_catalog() -> None:
    for definition in strategy_catalog().values():
        requirements = ", ".join(definition.required_columns)
        print(f"{definition.key:22} requires [{requirements}]  {definition.description}")


def main() -> None:
    parser = _parser()
    args = parser.parse_args()

    if args.list_strategies:
        _print_strategy_catalog()
        return

    if args.live_quote:
        if not args.twelve_data_api_key:
            parser.error("--live-quote requires --twelve-data-api-key or TWELVE_DATA_API_KEY")
        quote = fetch_twelve_data_quote(args.twelve_data_api_key, args.live_symbol)
        print(json.dumps(quote.to_dict(), indent=2))
        return

    market = synthetic_market_data() if args.synthetic else load_shiller_data(args.data)
    if args.risk_free_data is not None:
        market = enrich_with_risk_free_rate(market, args.risk_free_data)
    elif args.fetch_risk_free:
        market = enrich_with_risk_free_rate(market)

    explicit_selection = args.strategies is not None
    try:
        strategies, skipped = select_strategies(
            args.strategies,
            market,
            skip_unavailable=not explicit_selection,
        )
    except KeyError as error:
        parser.error(str(error))

    if not strategies:
        parser.error("no selected strategy is supported by the loaded dataset")
    for key, missing in skipped.items():
        print(
            f"Skipping {key}: missing {', '.join(missing)}. Add the required data source to enable it.",
            file=sys.stderr,
        )

    config = BacktestConfig(
        initial_cash=args.initial_cash,
        monthly_contribution=args.monthly_contribution,
        cash_annual_return=args.cash_annual_return,
    )
    results = run_many(market, strategies, config)

    args.output.mkdir(parents=True, exist_ok=True)
    histories = []
    for name, result in results.items():
        history = result.history.copy()
        history.insert(0, "strategy", name)
        histories.append(history.reset_index())
    pd.concat(histories, ignore_index=True).to_csv(args.output / "backtests.csv", index=False)

    metrics = {name: result.metrics for name, result in results.items()}
    (args.output / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    comparison_figure(results).write_html(args.output / "comparison.html", include_plotlyjs="cdn")

    print(f"Wrote {len(results)} strategies to {args.output}")


if __name__ == "__main__":
    main()
