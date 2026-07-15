from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

TWELVE_DATA_TIME_SERIES_URL = "https://api.twelvedata.com/time_series"
DEFAULT_DAILY_START_DATE = "2007-06-01"
DEFAULT_DAILY_OUTPUT_SIZE = 5_000
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


def _validate_requested_coverage(
    frame: pd.DataFrame,
    *,
    start_date: str,
    end_date: str,
    tolerance_days: int = 10,
) -> None:
    requested_start = pd.Timestamp(start_date).normalize()
    requested_end = pd.Timestamp(end_date).normalize()
    tolerance = pd.Timedelta(days=tolerance_days)

    if frame.index.min() > requested_start + tolerance:
        raise DailyDataError(
            "daily response begins materially after the requested start date; "
            "the provider may have truncated the response"
        )
    if requested_end < pd.Timestamp.today().normalize() - tolerance:
        if frame.index.max() < requested_end - tolerance:
            raise DailyDataError(
                "daily response ends materially before the requested end date; "
                "the provider may have truncated the response"
            )


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
    start_date: str = DEFAULT_DAILY_START_DATE,
    end_date: str | None = None,
    output_size: int = DEFAULT_DAILY_OUTPUT_SIZE,
    timeout_seconds: int = 30,
) -> pd.DataFrame:
    """Fetch a real daily OHLCV window from Twelve Data.

    The default start remains within one 5,000-row response while retaining the
    global financial crisis. Coverage checks reject silently truncated responses.
    """

    if not api_key.strip():
        raise ValueError("a Twelve Data API key is required")
    if not symbol.strip():
        raise ValueError("symbol is required")
    if not 1 <= output_size <= DEFAULT_DAILY_OUTPUT_SIZE:
        raise ValueError("output_size must be between 1 and 5,000")

    effective_end = end_date or date.today().isoformat()
    query = urlencode(
        {
            "symbol": symbol.upper(),
            "interval": "1day",
            "start_date": start_date,
            "end_date": effective_end,
            "outputsize": output_size,
            "order": "asc",
            "timezone": "Exchange",
            "apikey": api_key,
        }
    )
    request = Request(
        f"{TWELVE_DATA_TIME_SERIES_URL}?{query}",
        headers={"User-Agent": "retail-sp500-backtesting/0.5"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise DailyDataError("Twelve Data returned a non-object response")

    frame = parse_twelve_data_daily(payload)
    if len(frame) >= output_size:
        raise DailyDataError(
            f"daily response reached the {output_size:,}-row ceiling; "
            "shorten or split the date range"
        )
    _validate_requested_coverage(
        frame,
        start_date=start_date,
        end_date=effective_end,
    )
    frame.attrs.update(
        {
            "requested_symbol": symbol.upper(),
            "requested_start_date": start_date,
            "requested_end_date": effective_end,
            "output_size": output_size,
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
    validated.attrs["interval"] = "1day"
    return validated


def save_daily_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    """Validate and save daily OHLCV data without API secrets."""

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
    start_date: str = DEFAULT_DAILY_START_DATE,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Use a local real-data cache when present; otherwise fetch and persist it."""

    cache = Path(cache_path)
    if cache.exists() and not refresh:
        frame = load_daily_csv(cache)
        frame.attrs.update(
            {
                "requested_symbol": symbol.upper(),
                "requested_start_date": start_date,
                "requested_end_date": end_date or date.today().isoformat(),
            }
        )
        return frame
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


def daily_data_summary(frame: pd.DataFrame, *, symbol: str = "SPY") -> dict[str, object]:
    """Return explicit source and date metadata for notebooks and scripts."""

    validated = _validate_daily_ohlc(frame)
    return {
        "source": frame.attrs.get("source", "validated daily OHLCV"),
        "symbol": frame.attrs.get("symbol") or frame.attrs.get("requested_symbol") or symbol,
        "interval": frame.attrs.get("interval", "1day"),
        "start": validated.index.min().date().isoformat(),
        "end": validated.index.max().date().isoformat(),
        "sessions": int(len(validated)),
    }
