from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"
DEFAULT_START_DATE = "2007-06-01"
MAX_OUTPUT_SIZE = 5_000
_REQUIRED = ("open", "high", "low", "close", "volume")


class MarketDataError(RuntimeError):
    """Raised when live or cached market data is incomplete or invalid."""


def validate_daily(frame: pd.DataFrame, *, today: date | None = None) -> pd.DataFrame:
    missing = [column for column in _REQUIRED if column not in frame.columns]
    if missing:
        raise MarketDataError(f"daily data is missing columns: {', '.join(missing)}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise MarketDataError("daily data must use a DatetimeIndex")

    validated = frame.loc[:, _REQUIRED].copy()
    validated.index = pd.DatetimeIndex(validated.index).tz_localize(None).normalize()
    validated = validated.sort_index()
    if validated.index.has_duplicates:
        raise MarketDataError("daily data contains duplicate sessions")

    for column in _REQUIRED:
        validated[column] = pd.to_numeric(validated[column], errors="coerce")
    if validated.isna().any().any():
        raise MarketDataError("daily data contains missing or non-numeric OHLCV values")
    if (validated[["open", "high", "low", "close"]] <= 0.0).any().any():
        raise MarketDataError("daily prices must be positive")
    if (validated["volume"] < 0.0).any():
        raise MarketDataError("daily volume cannot be negative")
    if (validated["low"] > validated[["open", "close", "high"]].min(axis=1)).any():
        raise MarketDataError("daily low exceeds another OHLC value")
    if (validated["high"] < validated[["open", "close", "low"]].max(axis=1)).any():
        raise MarketDataError("daily high is below another OHLC value")
    if validated.empty:
        raise MarketDataError("daily data contains no sessions")

    cutoff = pd.Timestamp(today or date.today())
    if validated.index.max() > cutoff:
        raise MarketDataError("daily data contains future-dated sessions")
    validated.index.name = "date"
    return validated


def parse_twelve_data(payload: Mapping[str, object], *, today: date | None = None) -> pd.DataFrame:
    if payload.get("status") == "error" or "code" in payload:
        raise MarketDataError(str(payload.get("message") or "Twelve Data returned an error"))

    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise MarketDataError("Twelve Data response contains no daily values")

    frame = pd.DataFrame.from_records(values)
    if "datetime" not in frame.columns:
        raise MarketDataError("Twelve Data response is missing datetime")
    index = pd.to_datetime(frame.pop("datetime"), errors="coerce")
    if index.isna().any():
        raise MarketDataError("Twelve Data response contains an invalid datetime")
    frame.index = pd.DatetimeIndex(index)
    validated = validate_daily(frame, today=today)

    metadata = payload.get("meta")
    if isinstance(metadata, Mapping):
        validated.attrs.update({str(key): value for key, value in metadata.items()})
    validated.attrs.update({"source": "Twelve Data", "interval": "1day"})
    return validated


def fetch_daily(
    api_key: str,
    *,
    symbol: str = "SPY",
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
    timeout_seconds: int = 30,
) -> pd.DataFrame:
    if not api_key.strip():
        raise ValueError("a Twelve Data API key is required")
    effective_end = end_date or date.today().isoformat()
    query = urlencode(
        {
            "symbol": symbol.upper(),
            "interval": "1day",
            "start_date": start_date,
            "end_date": effective_end,
            "outputsize": MAX_OUTPUT_SIZE,
            "order": "asc",
            "timezone": "Exchange",
            "apikey": api_key,
        }
    )
    request = Request(
        f"{TWELVE_DATA_URL}?{query}",
        headers={"User-Agent": "retail-portfolio-lab/1.0"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise MarketDataError("Twelve Data returned a non-object response")

    frame = parse_twelve_data(payload)
    if len(frame) >= MAX_OUTPUT_SIZE:
        raise MarketDataError(
            "daily response reached the 5,000-row ceiling; shorten or split the requested range"
        )
    frame.attrs.update(
        {
            "requested_symbol": symbol.upper(),
            "requested_start_date": start_date,
            "requested_end_date": effective_end,
        }
    )
    return frame


def load_csv(path: str | Path, *, today: date | None = None) -> pd.DataFrame:
    source = Path(path)
    if not source.exists():
        raise FileNotFoundError(source)
    frame = pd.read_csv(source, parse_dates=["date"]).set_index("date")
    validated = validate_daily(frame, today=today)
    validated.attrs.update({"source": f"CSV cache: {source}", "interval": "1day"})
    return validated


def save_csv(frame: pd.DataFrame, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    validate_daily(frame).reset_index().to_csv(target, index=False)
    return target


def load_market(
    api_key: str | None,
    *,
    cache_path: str | Path = "data/spy_daily.csv",
    refresh: bool = False,
    symbol: str = "SPY",
    start_date: str = DEFAULT_START_DATE,
    end_date: str | None = None,
) -> pd.DataFrame:
    cache = Path(cache_path)
    if cache.exists() and not refresh:
        frame = load_csv(cache)
        frame.attrs.update(
            {
                "requested_symbol": symbol.upper(),
                "requested_start_date": start_date,
                "requested_end_date": end_date or date.today().isoformat(),
            }
        )
        return frame
    if api_key is None or not api_key.strip():
        raise ValueError("TWELVE_DATA_API_KEY is required when the cache is absent or refresh=True")
    frame = fetch_daily(
        api_key,
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
    )
    save_csv(frame, cache)
    return frame


def market_summary(frame: pd.DataFrame, *, symbol: str = "SPY") -> dict[str, object]:
    validated = validate_daily(frame)
    return {
        "source": frame.attrs.get("source", "validated daily OHLCV"),
        "symbol": frame.attrs.get("symbol") or frame.attrs.get("requested_symbol") or symbol,
        "interval": frame.attrs.get("interval", "1day"),
        "start": validated.index.min().date().isoformat(),
        "end": validated.index.max().date().isoformat(),
        "sessions": int(len(validated)),
    }
