from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .data import validate_daily

StrategyFamily = Literal["immediate", "fixed", "atr", "empirical"]


@dataclass(frozen=True)
class LabConfig:
    initial_cash: float = 100_000.0
    monthly_contribution: float = 1_000.0
    salary_day: int = 1
    holdout_years: int = 4
    stack_max_components: int = 4
    stack_min_calmar_improvement: float = 0.02
    stack_return_floor_delta: float = -0.0025

    def __post_init__(self) -> None:
        if min(self.initial_cash, self.monthly_contribution) < 0.0:
            raise ValueError("cash flows cannot be negative")
        if self.initial_cash == self.monthly_contribution == 0.0:
            raise ValueError("at least one cash flow must be positive")
        if not 1 <= self.salary_day <= 28:
            raise ValueError("salary_day must be between 1 and 28")
        if self.holdout_years < 1:
            raise ValueError("holdout_years must be positive")
        if self.stack_max_components < 1:
            raise ValueError("stack_max_components must be positive")


@dataclass(frozen=True)
class StrategySpec:
    key: str
    label: str
    family: StrategyFamily
    max_wait_sessions: int = 1
    fixed_discount: float = 0.0
    atr_multiplier: float = 0.0
    target_fill_probability: float = 0.0
    lookback_sessions: int = 756
    minimum_discount: float = 0.0
    maximum_discount: float = 0.05

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.label.strip():
            raise ValueError("strategy key and label are required")
        if self.max_wait_sessions < 1:
            raise ValueError("max_wait_sessions must be positive")
        if not 0.0 <= self.fixed_discount < 1.0:
            raise ValueError("fixed_discount must be in [0, 1)")
        if self.atr_multiplier < 0.0:
            raise ValueError("atr_multiplier cannot be negative")
        if self.family == "empirical" and not 0.0 < self.target_fill_probability < 1.0:
            raise ValueError("empirical strategies require target_fill_probability in (0, 1)")
        if self.lookback_sessions < 50:
            raise ValueError("lookback_sessions must be at least 50")
        if not 0.0 <= self.minimum_discount <= self.maximum_discount < 1.0:
            raise ValueError("discount bounds must satisfy 0 <= minimum <= maximum < 1")


@dataclass
class StrategyRun:
    spec: StrategySpec
    lots: pd.DataFrame
    curve: pd.DataFrame
    metrics: dict[str, float | int | str]


@dataclass
class ComparisonResult:
    daily: pd.DataFrame
    evaluation_start: pd.Timestamp
    holdout_start: pd.Timestamp
    specs: dict[str, StrategySpec]
    runs: dict[str, StrategyRun]
    metrics: pd.DataFrame
    curves: pd.DataFrame


@dataclass
class StackResult:
    weights: pd.Series
    curve: pd.DataFrame
    metrics: dict[str, float | int]
    selection_steps: pd.DataFrame


def default_strategies() -> list[StrategySpec]:
    """Return a compact but broad set of automated monthly execution policies."""

    strategies: list[StrategySpec] = [
        StrategySpec("immediate", "Immediate market", "immediate"),
    ]
    for wait in (5, 10, 20):
        for discount in (0.0025, 0.005, 0.0075, 0.01, 0.015, 0.02):
            strategies.append(
                StrategySpec(
                    key=f"fixed-{discount:.4f}-{wait}",
                    label=f"Fixed {discount:.2%}, {wait} sessions",
                    family="fixed",
                    max_wait_sessions=wait,
                    fixed_discount=discount,
                )
            )
    for wait in (5, 10, 20):
        for multiplier in (0.25, 0.5, 0.75, 1.0):
            strategies.append(
                StrategySpec(
                    key=f"atr-{multiplier:.2f}-{wait}",
                    label=f"ATR × {multiplier:g}, {wait} sessions",
                    family="atr",
                    max_wait_sessions=wait,
                    atr_multiplier=multiplier,
                    minimum_discount=0.001,
                    maximum_discount=0.03,
                )
            )
    for wait in (5, 10, 20):
        for probability in (0.80, 0.90, 0.95):
            strategies.append(
                StrategySpec(
                    key=f"fill-{probability:.2f}-{wait}",
                    label=f"Historical {probability:.0%} fill, {wait} sessions",
                    family="empirical",
                    max_wait_sessions=wait,
                    target_fill_probability=probability,
                    lookback_sessions=756,
                    minimum_discount=0.0,
                    maximum_discount=0.03,
                )
            )
    return strategies


def _true_range(frame: pd.DataFrame) -> pd.Series:
    previous_close = frame["close"].shift(1)
    return pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)


def _forward_minimum(values: pd.Series, horizon: int) -> pd.Series:
    array = values.to_numpy(dtype=float)
    result = np.full(len(array), np.nan, dtype=float)
    for start in range(0, len(array) - horizon + 1):
        result[start] = float(np.min(array[start : start + horizon]))
    return pd.Series(result, index=values.index, dtype=float)


def strategy_discounts(daily: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    """Return the discount known before each session, with no future-data use."""

    frame = validate_daily(daily)
    if spec.family == "immediate":
        return pd.Series(0.0, index=frame.index, name=spec.key)
    if spec.family == "fixed":
        return pd.Series(spec.fixed_discount, index=frame.index, name=spec.key)
    if spec.family == "atr":
        atr = _true_range(frame).rolling(20, min_periods=20).mean()
        discount = (spec.atr_multiplier * atr / frame["close"]).shift(1)
        return discount.clip(spec.minimum_discount, spec.maximum_discount).rename(spec.key)
    if spec.family == "empirical":
        future_low = _forward_minimum(frame["low"], spec.max_wait_sessions)
        previous_close = frame["close"].shift(1)
        realized_depth = (1.0 - future_low / previous_close).clip(lower=0.0)
        available_history = realized_depth.shift(spec.max_wait_sessions)
        minimum_periods = max(100, spec.lookback_sessions // 3)
        discount = available_history.rolling(
            spec.lookback_sessions,
            min_periods=minimum_periods,
        ).quantile(1.0 - spec.target_fill_probability)
        return discount.clip(spec.minimum_discount, spec.maximum_discount).rename(spec.key)
    raise ValueError(f"unsupported strategy family: {spec.family}")
