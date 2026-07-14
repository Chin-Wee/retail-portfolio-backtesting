from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .backtest import BacktestConfig, run_many
from .data import load_shiller_data, synthetic_market_data
from .plotting import comparison_figure
from .strategies import default_strategies


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run monthly S&P 500 strategy backtests")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--data", type=Path, help="Local Shiller XLS/XLSX/CSV file")
    source.add_argument("--synthetic", action="store_true", help="Use deterministic demo data")
    parser.add_argument("--output", type=Path, default=Path("results"))
    parser.add_argument("--initial-cash", type=float, default=100_000.0)
    parser.add_argument("--monthly-contribution", type=float, default=1_000.0)
    parser.add_argument("--cash-annual-return", type=float, default=0.0)
    return parser


def main() -> None:
    args = _parser().parse_args()
    market = synthetic_market_data() if args.synthetic else load_shiller_data(args.data)
    config = BacktestConfig(
        initial_cash=args.initial_cash,
        monthly_contribution=args.monthly_contribution,
        cash_annual_return=args.cash_annual_return,
    )
    results = run_many(market, default_strategies(), config)

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
