from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, ClassVar, Protocol

import numpy as np
import pandas as pd


class Strategy(Protocol):
    name: str
    execution_lag_months: int
    required_columns: tuple[str, ...]

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        """Return monthly ETF target weights in the inclusive [0, 1] range."""


def _bounded(weights: pd.Series) -> pd.Series:
    return weights.astype(float).clip(lower=0.0, upper=1.0).fillna(0.0)


@dataclass(frozen=True)
class BuyAndHold:
    name: str = "Buy and hold"

    execution_lag_months: ClassVar[int] = 0
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=market.index, name=self.name)


@dataclass(frozen=True)
class FixedAllocation:
    allocation: float = 0.60
    name: str = "60% ETF / 40% cash"

    execution_lag_months: ClassVar[int] = 0
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return")

    def __post_init__(self) -> None:
        if not 0.0 <= self.allocation <= 1.0:
            raise ValueError("allocation must be between zero and one")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        return pd.Series(self.allocation, index=market.index, name=self.name)


@dataclass(frozen=True)
class StagedDeployment:
    """Ramp a base strategy from cash to its full target over several months."""

    base: Strategy
    months: int = 6

    @property
    def name(self) -> str:
        return f"{self.base.name} ({self.months}-month staged deployment)"

    @property
    def execution_lag_months(self) -> int:
        return self.base.execution_lag_months

    @property
    def required_columns(self) -> tuple[str, ...]:
        return self.base.required_columns

    def __post_init__(self) -> None:
        if self.months < 1:
            raise ValueError("months must be at least one")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        base_weights = self.base.target_weights(market)
        ramp = pd.Series(
            np.minimum((np.arange(len(market), dtype=float) + 1.0) / self.months, 1.0),
            index=market.index,
        )
        return _bounded((base_weights * ramp).rename(self.name))


@dataclass(frozen=True)
class MovingAverageTrend:
    months: int = 10
    buffer: float = 0.01
    name: str = "10-month trend (1% buffer)"

    execution_lag_months: ClassVar[int] = 1
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return")

    def __post_init__(self) -> None:
        if self.months < 2:
            raise ValueError("months must be at least two")
        if not 0.0 <= self.buffer < 1.0:
            raise ValueError("buffer must be in the [0, 1) range")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        average = market["price"].rolling(self.months, min_periods=self.months).mean()
        invested = False
        weights: list[float] = []

        for price, moving_average in zip(market["price"], average, strict=True):
            if pd.isna(price) or pd.isna(moving_average):
                invested = False
            elif invested:
                if price < moving_average * (1.0 - self.buffer):
                    invested = False
            elif price > moving_average * (1.0 + self.buffer):
                invested = True
            weights.append(float(invested))

        return pd.Series(weights, index=market.index, name=self.name)


@dataclass(frozen=True)
class VolatilityTarget:
    target_volatility: float = 0.12
    lookback_months: int = 12
    minimum_volatility: float = 0.01
    name: str = "12% volatility target"

    execution_lag_months: ClassVar[int] = 1
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return")

    def __post_init__(self) -> None:
        if self.target_volatility <= 0.0:
            raise ValueError("target_volatility must be positive")
        if self.lookback_months < 2:
            raise ValueError("lookback_months must be at least two")
        if self.minimum_volatility <= 0.0:
            raise ValueError("minimum_volatility must be positive")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        volatility = market["total_return"].rolling(
            self.lookback_months, min_periods=self.lookback_months
        ).std(ddof=1) * np.sqrt(12.0)
        weights = self.target_volatility / volatility.clip(lower=self.minimum_volatility)
        return _bounded(weights.rename(self.name))


@dataclass(frozen=True)
class TrendVolatilityTarget:
    trend_months: int = 10
    trend_buffer: float = 0.01
    target_volatility: float = 0.12
    volatility_lookback_months: int = 12
    name: str = "Trend + 12% volatility target"

    execution_lag_months: ClassVar[int] = 1
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        trend = MovingAverageTrend(
            months=self.trend_months,
            buffer=self.trend_buffer,
        ).target_weights(market)
        volatility = VolatilityTarget(
            target_volatility=self.target_volatility,
            lookback_months=self.volatility_lookback_months,
        ).target_weights(market)
        return _bounded((trend * volatility).rename(self.name))


@dataclass(frozen=True)
class FractionalKelly:
    fraction: float = 0.25
    lookback_months: int = 60
    minimum_annual_variance: float = 1e-6
    name: str = "Quarter-Kelly ceiling (60-month)"

    execution_lag_months: ClassVar[int] = 1
    required_columns: ClassVar[tuple[str, ...]] = (
        "price",
        "total_return",
        "risk_free_rate",
    )

    def __post_init__(self) -> None:
        if not 0.0 < self.fraction <= 1.0:
            raise ValueError("fraction must be in the (0, 1] range")
        if self.lookback_months < 12:
            raise ValueError("lookback_months must be at least twelve")
        if self.minimum_annual_variance <= 0.0:
            raise ValueError("minimum_annual_variance must be positive")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        monthly_returns = market["total_return"].astype(float)
        expected_annual_return = monthly_returns.rolling(
            self.lookback_months, min_periods=self.lookback_months
        ).mean() * 12.0
        annual_variance = monthly_returns.rolling(
            self.lookback_months, min_periods=self.lookback_months
        ).var(ddof=1) * 12.0
        excess_return = expected_annual_return - market["risk_free_rate"].astype(float)
        full_kelly = excess_return / annual_variance.clip(lower=self.minimum_annual_variance)
        return _bounded((self.fraction * full_kelly).rename(self.name))


@dataclass(frozen=True)
class CapeScaledAllocation:
    low_cape: float = 15.0
    high_cape: float = 35.0
    minimum_weight: float = 0.25
    name: str = "CAPE-scaled allocation"

    execution_lag_months: ClassVar[int] = 1
    required_columns: ClassVar[tuple[str, ...]] = ("price", "total_return", "cape")

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        span = self.high_cape - self.low_cape
        if span <= 0:
            raise ValueError("high_cape must exceed low_cape")
        if not 0.0 <= self.minimum_weight <= 1.0:
            raise ValueError("minimum_weight must be between zero and one")
        scaled = 1.0 - (market["cape"] - self.low_cape) / span
        weights = self.minimum_weight + (1.0 - self.minimum_weight) * scaled
        return _bounded(weights.rename(self.name))


@dataclass(frozen=True)
class StrategyDefinition:
    key: str
    description: str
    factory: Callable[[], Strategy]
    required_columns: tuple[str, ...]

    def is_available(self, market: pd.DataFrame) -> bool:
        return not set(self.required_columns).difference(market.columns)

    def missing_columns(self, market: pd.DataFrame) -> tuple[str, ...]:
        return tuple(sorted(set(self.required_columns).difference(market.columns)))


_STRATEGY_DEFINITIONS: tuple[StrategyDefinition, ...] = (
    StrategyDefinition(
        "buy-hold",
        "Immediate 100% ETF allocation with dividends and contributions reinvested.",
        BuyAndHold,
        BuyAndHold.required_columns,
    ),
    StrategyDefinition(
        "staged-buy-hold-6m",
        "Ramp buy-and-hold exposure from one-sixth to 100% over six months.",
        lambda: StagedDeployment(BuyAndHold(), months=6),
        BuyAndHold.required_columns,
    ),
    StrategyDefinition(
        "fixed-60-40",
        "Maintain 60% ETF and 40% cash.",
        FixedAllocation,
        FixedAllocation.required_columns,
    ),
    StrategyDefinition(
        "trend-10m",
        "Long above a 10-month average with a 1% enter/exit hysteresis buffer.",
        MovingAverageTrend,
        MovingAverageTrend.required_columns,
    ),
    StrategyDefinition(
        "vol-target-12",
        "Scale ETF exposure to a 12% annualized volatility target.",
        VolatilityTarget,
        VolatilityTarget.required_columns,
    ),
    StrategyDefinition(
        "trend-vol-12",
        "Allow risk only in the trend regime, then apply the 12% volatility target.",
        TrendVolatilityTarget,
        TrendVolatilityTarget.required_columns,
    ),
    StrategyDefinition(
        "fractional-kelly",
        "Apply a quarter-Kelly long-only exposure ceiling using a 60-month estimate.",
        FractionalKelly,
        FractionalKelly.required_columns,
    ),
    StrategyDefinition(
        "cape-scaled",
        "Scale exposure gradually between CAPE 15 and 35; never below 25% ETF.",
        CapeScaledAllocation,
        CapeScaledAllocation.required_columns,
    ),
)


def strategy_catalog() -> dict[str, StrategyDefinition]:
    return {definition.key: definition for definition in _STRATEGY_DEFINITIONS}


def select_strategies(
    keys: list[str] | tuple[str, ...] | None,
    market: pd.DataFrame,
    *,
    skip_unavailable: bool,
) -> tuple[list[Strategy], dict[str, tuple[str, ...]]]:
    catalog = strategy_catalog()
    selected_keys = list(keys) if keys else list(catalog)
    unknown = sorted(set(selected_keys).difference(catalog))
    if unknown:
        raise KeyError(f"unknown strategies: {', '.join(unknown)}")

    strategies: list[Strategy] = []
    skipped: dict[str, tuple[str, ...]] = {}
    for key in selected_keys:
        definition = catalog[key]
        missing = definition.missing_columns(market)
        if missing:
            if skip_unavailable:
                skipped[key] = missing
                continue
            raise KeyError(f"strategy {key!r} requires: {', '.join(missing)}")
        strategies.append(definition.factory())
    return strategies, skipped


def default_strategies(market: pd.DataFrame | None = None) -> list[Strategy]:
    catalog = strategy_catalog()
    if market is None:
        return [definition.factory() for definition in catalog.values()]
    strategies, _ = select_strategies(None, market, skip_unavailable=True)
    return strategies
