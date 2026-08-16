from __future__ import annotations

import pandas as pd

from .data import MarketDataError, validate_daily

_PRICE_COLUMNS = ("open", "high", "low", "close")


def convert_daily_prices(daily: pd.DataFrame, fx: pd.DataFrame, *, label: str = "SGD") -> pd.DataFrame:
    """Convert daily OHLC prices using the most recent prior FX close."""

    asset = validate_daily(daily)
    rates = validate_daily(fx)
    prior_fx_close = rates["close"].shift(1)
    fx_close = prior_fx_close.reindex(asset.index, method="ffill")
    if fx_close.isna().any():
        first_missing = fx_close.index[fx_close.isna()][0].date().isoformat()
        raise MarketDataError(f"FX history does not cover asset history from {first_missing}")

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
