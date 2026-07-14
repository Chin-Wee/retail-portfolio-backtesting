from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from .metrics import summarize
from .strategies import Strategy


@dataclass(frozen=True)
class BacktestConfig:
    initial_cash: float = 100_000.0
    monthly_contribution: float = 1_000.0
    cash_annual_return: float = 0.0
    signal_lag_months: int = 1

    def __post_init__(self) -> None:
        if self.initial_cash < 0 or self.monthly_contribution < 0:
            raise ValueError("cash and contributions cannot be negative")
        if self.cash_annual_return <= -1:
            raise ValueError("cash_annual_return must exceed -100%")
        if self.signal_lag_months < 0:
            raise ValueError("signal_lag_months cannot be negative")


@dataclass(frozen=True)
class BacktestResult:
    name: str
    history: pd.DataFrame
    metrics: dict[str, float]


def _validate_market(market: pd.DataFrame, strategy: Strategy) -> pd.DataFrame:
    required = set(strategy.required_columns)
    missing = sorted(required.difference(market.columns))
    if missing:
        raise KeyError(f"{strategy.name} requires market columns: {', '.join(missing)}")
    if not isinstance(market.index, pd.DatetimeIndex):
        raise TypeError("market data must use a DatetimeIndex")
    if market.index.has_duplicates or not market.index.is_monotonic_increasing:
        raise ValueError("market index must be unique and sorted")
    return market.copy()


def run_backtest(
    market: pd.DataFrame,
    strategy: Strategy,
    config: BacktestConfig | None = None,
) -> BacktestResult:
    """Run a monthly ETF/cash backtest with start-of-period contributions.

    Signal strategies declare their own execution lag. Third-party strategies
    without that attribute use ``BacktestConfig.signal_lag_months``.
    """

    config = config or BacktestConfig()
    frame = _validate_market(market, strategy)
    raw_weights = strategy.target_weights(frame).reindex(frame.index)
    lag_months = getattr(strategy, "execution_lag_months", config.signal_lag_months)
    if lag_months < 0:
        raise ValueError("strategy execution lag cannot be negative")
    target_weights = raw_weights.shift(lag_months).fillna(0.0).clip(0.0, 1.0)

    cash_monthly_return = (1.0 + config.cash_annual_return) ** (1.0 / 12.0) - 1.0
    portfolio_value = config.initial_cash
    cumulative_contributions = config.initial_cash
    records: list[dict[str, float | pd.Timestamp]] = []

    for period_index, (month, row) in enumerate(frame.iterrows()):
        contribution = config.monthly_contribution if period_index > 0 else 0.0
        portfolio_value += contribution
        cumulative_contributions += contribution

        weight = float(target_weights.loc[month])
        market_return = float(row["total_return"]) if pd.notna(row["total_return"]) else 0.0
        strategy_return = weight * market_return + (1.0 - weight) * cash_monthly_return
        portfolio_value *= 1.0 + strategy_return

        records.append(
            {
                "month": month,
                "portfolio_value": portfolio_value,
                "contribution": contribution,
                "cumulative_contributions": cumulative_contributions,
                "target_weight": weight,
                "market_return": market_return,
                "strategy_return": strategy_return,
            }
        )

    history = pd.DataFrame.from_records(records).set_index("month")
    return BacktestResult(strategy.name, history, summarize(history))


def run_many(
    market: pd.DataFrame,
    strategies: Iterable[Strategy],
    config: BacktestConfig | None = None,
) -> dict[str, BacktestResult]:
    results: dict[str, BacktestResult] = {}
    for strategy in strategies:
        result = run_backtest(market, strategy, config)
        if result.name in results:
            raise ValueError(f"duplicate strategy name: {result.name}")
        results[result.name] = result
    return results
