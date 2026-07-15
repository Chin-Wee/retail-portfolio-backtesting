from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

TWELVE_DATA_TIME_SERIES_URL = "https://api.twelvedata.com/time_series"
_DAILY_COLUMNS = ("open", "high", "low", "close", "volume")


class DailyDataError(RuntimeError):
    """Raised when daily market data is missing, truncated, or internally invalid."""


def _validate_daily_ohlc(frame: pd.DataFrame, *, today: date | None = None) -> pd.DataFrame:
    missing = [column for column in _DAILY_COLUMNS if column not in frame.columns]
    if missing:
        raise DailyDataError(f"daily data is missing columns: {', '.join(missing)}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise DailyDataError("daily data must use a DatetimeIndex")

    validated = frame.loc[:, _DAILY_COLUMNS].copy()
    validated.index = pd.DatetimeIndex(validated.index).tz_localize(None).normalize()
    validated = validated.sort_index()
    if validated.index.has_duplicates:
        raise DailyDataError("daily data contains duplicate sessions")

    for column in _DAILY_COLUMNS:
        validated[column] = pd.to_numeric(validated[column], errors="coerce")
    if validated.isna().any().any():
        raise DailyDataError("daily data contains missing or non-numeric OHLCV values")
    if (validated[["open", "high", "low", "close"]] <= 0.0).any().any():
        raise DailyDataError("daily prices must be positive")
    if (validated["volume"] < 0.0).any():
        raise DailyDataError("daily volume cannot be negative")
    if (validated["low"] > validated[["open", "close", "high"]].min(axis=1)).any():
        raise DailyDataError("daily low exceeds another OHLC value")
    if (validated["high"] < validated[["open", "close", "low"]].max(axis=1)).any():
        raise DailyDataError("daily high is below another OHLC value")

    cutoff = pd.Timestamp(today or date.today())
    if not validated.empty and validated.index.max() > cutoff:
        raise DailyDataError("daily data contains future-dated sessions")
    if validated.empty:
        raise DailyDataError("daily data contains no sessions")

    validated.index.name = "date"
    return validated


def parse_twelve_data_daily(
    payload: Mapping[str, object],
    *,
    today: date | None = None,
) -> pd.DataFrame:
    """Parse a Twelve Data ``1day`` response into validated ascending OHLCV data."""

    if payload.get("status") == "error" or "code" in payload:
        message = str(payload.get("message") or "Twelve Data returned an error")
        raise DailyDataError(message)

    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise DailyDataError("Twelve Data response contains no daily values")

    frame = pd.DataFrame.from_records(values)
    if "datetime" not in frame.columns:
        raise DailyDataError("Twelve Data response is missing datetime")
    dates = pd.to_datetime(frame.pop("datetime"), errors="coerce")
    if dates.isna().any():
        raise DailyDataError("Twelve Data response contains an invalid datetime")
    frame.index = pd.DatetimeIndex(dates)
    validated = _validate_daily_ohlc(frame, today=today)

    metadata = payload.get("meta")
    if isinstance(metadata, Mapping):
        validated.attrs.update({str(key): value for key, value in metadata.items()})
    validated.attrs["source"] = "Twelve Data"
    validated.attrs["interval"] = "1day"
    return validated


def fetch_twelve_data_daily(
    api_key: str,
    *,
    symbol: str = "SPY",
    start_date: str = "2007-06-01",
    end_date: str | None = None,
    timeout_seconds: int = 30,
) -> pd.DataFrame:
    """Fetch a real daily OHLCV window from Twelve Data.

    The default starts in mid-2007 so a SPY request remains below Twelve Data's
    5,000-row single-request ceiling while retaining the global financial crisis.
    """

    if not api_key.strip():
        raise ValueError("a Twelve Data API key is required")
    if not symbol.strip():
        raise ValueError("symbol is required")

    effective_end = end_date or date.today().isoformat()
    query = urlencode(
        {
            "symbol": symbol.upper(),
            "interval": "1day",
            "start_date": start_date,
            "end_date": effective_end,
            "order": "asc",
            "timezone": "Exchange",
            "apikey": api_key,
        }
    )
    request = Request(
        f"{TWELVE_DATA_TIME_SERIES_URL}?{query}",
        headers={"User-Agent": "retail-sp500-backtesting/0.4"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise DailyDataError("Twelve Data returned a non-object response")

    frame = parse_twelve_data_daily(payload)
    if len(frame) >= 5_000:
        raise DailyDataError(
            "daily response reached the 5,000-row ceiling; shorten or split the date range"
        )
    frame.attrs.update(
        {
            "requested_symbol": symbol.upper(),
            "requested_start_date": start_date,
            "requested_end_date": effective_end,
        }
    )
    return frame


def load_daily_csv(path: str | Path, *, today: date | None = None) -> pd.DataFrame:
    """Load a cached daily OHLCV CSV written by :func:`save_daily_csv`."""

    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    frame = pd.read_csv(source, parse_dates=["date"]).set_index("date")
    validated = _validate_daily_ohlc(frame, today=today)
    validated.attrs["source"] = f"CSV cache: {source}"
    return validated


def save_daily_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Validate and save daily OHLCV data without notebook outputs or API secrets."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    validated = _validate_daily_ohlc(frame)
    validated.reset_index().to_csv(target, index=False)
    return target


def load_or_fetch_twelve_data_daily(
    api_key: str | None,
    *,
    cache_path: str | Path,
    refresh: bool = False,
    symbol: str = "SPY",
    start_date: str = "2007-06-01",
    end_date: str | None = None,
) -> pd.DataFrame:
    """Use a local real-data cache when present; otherwise fetch and persist it."""

    cache = Path(cache_path)
    if cache.exists() and not refresh:
        return load_daily_csv(cache)
    if api_key is None or not api_key.strip():
        raise ValueError(
            "TWELVE_DATA_API_KEY is required when the daily cache is absent or refresh=True"
        )
    frame = fetch_twelve_data_daily(
        api_key,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    save_daily_csv(frame, cache)
    return frame
