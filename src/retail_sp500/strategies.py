from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd


class Strategy(Protocol):
    name: str

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        """Return unlagged monthly ETF target weights in the inclusive [0, 1] range."""


def _bounded(weights: pd.Series) -> pd.Series:
    return weights.astype(float).clip(lower=0.0, upper=1.0).fillna(0.0)


@dataclass(frozen=True)
class BuyAndHold:
    name: str = "Buy and hold"

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=market.index, name=self.name)


@dataclass(frozen=True)
class FixedAllocation:
    allocation: float = 0.60
    name: str = "60% ETF / 40% cash"

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        return _bounded(pd.Series(self.allocation, index=market.index, name=self.name))


@dataclass(frozen=True)
class MovingAverageTrend:
    months: int = 10
    name: str = "10-month trend"

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        average = market["price"].rolling(self.months, min_periods=self.months).mean()
        return _bounded((market["price"] > average).astype(float).rename(self.name))


@dataclass(frozen=True)
class VolatilityTarget:
    target_volatility: float = 0.12
    lookback_months: int = 12
    name: str = "12% volatility target"

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        volatility = market["total_return"].rolling(
            self.lookback_months, min_periods=self.lookback_months
        ).std(ddof=1) * np.sqrt(12.0)
        weights = self.target_volatility / volatility.replace(0.0, np.nan)
        return _bounded(weights.rename(self.name))


@dataclass(frozen=True)
class TrendVolatilityTarget:
    trend_months: int = 10
    target_volatility: float = 0.12
    volatility_lookback_months: int = 12
    name: str = "Trend + 12% volatility target"

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        trend = MovingAverageTrend(months=self.trend_months).target_weights(market)
        volatility = VolatilityTarget(
            target_volatility=self.target_volatility,
            lookback_months=self.volatility_lookback_months,
        ).target_weights(market)
        return _bounded((trend * volatility).rename(self.name))


@dataclass(frozen=True)
class CapeScaledAllocation:
    low_cape: float = 15.0
    high_cape: float = 35.0
    minimum_weight: float = 0.25
    name: str = "CAPE-scaled allocation"

    def target_weights(self, market: pd.DataFrame) -> pd.Series:
        if "cape" not in market:
            raise KeyError("CAPE-scaled allocation requires a 'cape' column")
        span = self.high_cape - self.low_cape
        if span <= 0:
            raise ValueError("high_cape must exceed low_cape")
        scaled = 1.0 - (market["cape"] - self.low_cape) / span
        weights = self.minimum_weight + (1.0 - self.minimum_weight) * scaled
        return _bounded(weights.rename(self.name))


def default_strategies() -> list[Strategy]:
    return [
        BuyAndHold(),
        FixedAllocation(),
        MovingAverageTrend(),
        VolatilityTarget(),
        TrendVolatilityTarget(),
        CapeScaledAllocation(),
    ]
