from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _clean_returns(returns: pd.Series) -> pd.Series:
    clean = pd.to_numeric(returns, errors="coerce").dropna().astype(float)
    if clean.empty:
        raise ValueError("at least one valid return is required")
    if (clean <= -1.0).any():
        raise ValueError("returns must exceed -100%")
    return clean


def wealth_index_from_returns(returns: pd.Series) -> pd.Series:
    """Compound a return series into a contribution-neutral wealth index."""

    clean = _clean_returns(returns)
    return (1.0 + clean).cumprod().rename("wealth_index")


def drawdown_series(wealth_index: pd.Series) -> pd.Series:
    """Return percentage drawdown from the running wealth-index peak."""

    wealth = pd.to_numeric(wealth_index, errors="coerce").dropna().astype(float)
    if wealth.empty:
        raise ValueError("wealth index must contain at least one valid value")
    if (wealth <= 0.0).any():
        raise ValueError("wealth index values must be positive")
    running_peak = wealth.cummax().clip(lower=1.0)
    return (wealth / running_peak - 1.0).rename("drawdown")


def annualized_compound_return(
    returns: pd.Series,
    *,
    periods_per_year: int = 252,
) -> float:
    """Annualize compounded periodic returns using the observed return count."""

    if periods_per_year < 1:
        raise ValueError("periods_per_year must be positive")
    clean = _clean_returns(returns)
    growth = float((1.0 + clean).prod())
    return growth ** (periods_per_year / len(clean)) - 1.0


def maximum_drawdown(returns: pd.Series) -> float:
    """Calculate maximum drawdown from a periodic return series."""

    wealth = wealth_index_from_returns(returns)
    return float(drawdown_series(wealth).min())


def calmar_ratio(
    returns: pd.Series,
    *,
    periods_per_year: int = 252,
) -> float:
    """Calculate annualized compounded return divided by drawdown magnitude.

    A series with no drawdown has an undefined ratio and returns NaN rather than
    infinity so it cannot dominate parameter rankings accidentally.
    """

    annualized = annualized_compound_return(returns, periods_per_year=periods_per_year)
    drawdown = maximum_drawdown(returns)
    if not math.isfinite(drawdown) or abs(drawdown) <= np.finfo(float).eps:
        return float("nan")
    return annualized / abs(drawdown)


def summarize_return_series(
    returns: pd.Series,
    *,
    periods_per_year: int = 252,
) -> dict[str, float | int]:
    clean = _clean_returns(returns)
    annualized = annualized_compound_return(clean, periods_per_year=periods_per_year)
    drawdown = maximum_drawdown(clean)
    ratio = (
        annualized / abs(drawdown)
        if math.isfinite(drawdown) and abs(drawdown) > np.finfo(float).eps
        else float("nan")
    )
    return {
        "return_periods": int(len(clean)),
        "annualized_return": annualized,
        "max_drawdown": drawdown,
        "calmar_ratio": ratio,
    }
