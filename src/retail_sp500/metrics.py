from __future__ import annotations

import math

import numpy as np
import pandas as pd


def max_drawdown(values: pd.Series) -> float:
    running_peak = values.cummax()
    drawdown = values / running_peak - 1.0
    return float(drawdown.min())


def annualized_volatility(returns: pd.Series, periods_per_year: int = 12) -> float:
    clean = returns.dropna()
    if len(clean) < 2:
        return float("nan")
    return float(clean.std(ddof=1) * math.sqrt(periods_per_year))


def time_weighted_cagr(returns: pd.Series, periods_per_year: int = 12) -> float:
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    years = len(clean) / periods_per_year
    growth = float((1.0 + clean).prod())
    return growth ** (1.0 / years) - 1.0


def summarize(history: pd.DataFrame, periods_per_year: int = 12) -> dict[str, float]:
    ending_value = float(history["portfolio_value"].iloc[-1])
    invested_capital = float(history["cumulative_contributions"].iloc[-1])
    strategy_returns = history["strategy_return"]
    volatility = annualized_volatility(strategy_returns, periods_per_year)
    cagr = time_weighted_cagr(strategy_returns, periods_per_year)
    mean_return = float(strategy_returns.dropna().mean() * periods_per_year)
    sharpe = mean_return / volatility if volatility and np.isfinite(volatility) else float("nan")

    wealth_index = (1.0 + strategy_returns.fillna(0.0)).cumprod()

    return {
        "ending_value": ending_value,
        "invested_capital": invested_capital,
        "profit": ending_value - invested_capital,
        "time_weighted_cagr": cagr,
        "annualized_volatility": volatility,
        "max_drawdown": max_drawdown(wealth_index),
        "sharpe_zero_cash": sharpe,
        "average_etf_weight": float(history["target_weight"].mean()),
    }
