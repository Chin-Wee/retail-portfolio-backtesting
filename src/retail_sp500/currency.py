from __future__ import annotations

import pandas as pd

from .data import MarketDataError, validate_daily

_PRICE_COLUMNS = ("open", "high", "low", "close")


def prior_fx_close(index: pd.DatetimeIndex, fx: pd.DataFrame) -> pd.Series:
    """Align the most recent prior FX close to each requested asset session."""

    rates = validate_daily(fx)
    requested = pd.DatetimeIndex(index)
    prior = rates["close"].shift(1)
    aligned = prior.reindex(requested, method="ffill")
    if aligned.isna().any():
        first_missing = aligned.index[aligned.isna()][0].date().isoformat()
        raise MarketDataError(f"FX history does not cover asset history from {first_missing}")
    return aligned.astype(float).rename("fx_close")


def convert_daily_prices(daily: pd.DataFrame, fx: pd.DataFrame, *, label: str = "SGD") -> pd.DataFrame:
    """Convert daily OHLC prices using the most recent prior FX close."""

    asset = validate_daily(daily)
    fx_close = prior_fx_close(asset.index, fx)

    converted = asset.copy()
    for column in _PRICE_COLUMNS:
        converted[column] = converted[column] * fx_close
    converted = validate_daily(converted)
    converted.attrs.update(daily.attrs)
    converted.attrs["source"] = (
        f"{daily.attrs.get('source', 'market data')} converted with "
        f"{fx.attrs.get('source', 'FX data')}"
    )
    converted.attrs["currency"] = label
    converted.attrs["fx_symbol"] = fx.attrs.get("symbol") or fx.attrs.get("requested_symbol")
    return converted
