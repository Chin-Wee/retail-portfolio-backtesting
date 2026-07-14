from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Final
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

SHILLER_DATA_URL: Final[str] = "https://www.econ.yale.edu/~shiller/data/ie_data.xls"
FRED_TB3MS_CSV_URL: Final[str] = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=TB3MS"
_REQUIRED_COLUMNS: Final[tuple[str, ...]] = ("date", "price", "dividend", "earnings", "cpi")


class DataSchemaError(ValueError):
    """Raised when a source cannot be mapped to the expected market-data schema."""


def _download(url: str, timeout_seconds: int = 30) -> bytes:
    request = Request(url, headers={"User-Agent": "retail-sp500-backtesting/0.2"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _normalise_name(value: object) -> str:
    text = str(value).strip().lower()
    return "".join(character for character in text if character.isalnum())


def _find_header_row(raw: pd.DataFrame) -> int:
    for index, row in raw.iterrows():
        names = {_normalise_name(value) for value in row.iloc[:12] if pd.notna(value)}
        if {"date", "p", "d", "e", "cpi"}.issubset(names):
            return int(index)
    raise DataSchemaError("Could not locate the Shiller Date/P/D/E/CPI header row")


def _map_columns(columns: list[object]) -> dict[object, str]:
    mapped: dict[object, str] = {}
    seen: set[str] = set()

    aliases = {
        "date": "date",
        "p": "price",
        "price": "price",
        "d": "dividend",
        "dividend": "dividend",
        "e": "earnings",
        "earnings": "earnings",
        "cpi": "cpi",
        "fraction": "date_fraction",
        "rategs10": "long_rate",
        "gs10": "long_rate",
        "cape": "cape",
        "trcape": "total_return_cape",
    }

    for column in columns:
        normalised = _normalise_name(column)
        target = aliases.get(normalised)
        if target is None or target in seen:
            continue
        mapped[column] = target
        seen.add(target)
    return mapped


def _parse_shiller_date(value: object) -> pd.Timestamp:
    number = float(value)
    year = int(number)
    month = int(round((number - year) * 100))
    if month == 0:
        month = 1
    if not 1 <= month <= 12:
        raise DataSchemaError(f"Invalid Shiller month encoded by {value!r}")
    return pd.Timestamp(year=year, month=month, day=1)


def _read_source(source: str | Path | bytes | None) -> pd.DataFrame:
    if source is None:
        payload = _download(SHILLER_DATA_URL)
        return pd.read_excel(BytesIO(payload), sheet_name=0, header=None)
    if isinstance(source, bytes):
        return pd.read_excel(BytesIO(source), sheet_name=0, header=None)

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path, header=None)
    return pd.read_excel(path, sheet_name=0, header=None)


def _derive_fields(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_index().copy()
    for column in (
        "price",
        "dividend",
        "earnings",
        "cpi",
        "long_rate",
        "cape",
        "total_return_cape",
    ):
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["price", "dividend", "cpi"])
    frame = frame[(frame["price"] > 0) & (frame["cpi"] > 0)]

    frame["pe"] = frame["price"] / frame["earnings"].replace(0, np.nan)
    frame["dividend_yield"] = frame["dividend"] / frame["price"]
    frame["earnings_yield"] = frame["earnings"] / frame["price"]
    frame["inflation"] = frame["cpi"].pct_change()
    frame["price_return"] = frame["price"].pct_change()

    # Shiller's D series is an annualised/interpolated dividend amount. Dividing
    # by 12 provides the monthly cash-flow approximation used for reinvestment.
    monthly_dividend = frame["dividend"] / 12.0
    frame["total_return"] = (frame["price"] + monthly_dividend) / frame["price"].shift(1) - 1.0
    frame["real_total_return"] = (1.0 + frame["total_return"]) / (1.0 + frame["inflation"]) - 1.0
    frame["realized_vol_12m"] = frame["total_return"].rolling(12).std(ddof=1) * np.sqrt(12.0)
    frame["moving_average_10m"] = frame["price"].rolling(10).mean()

    return frame.replace([np.inf, -np.inf], np.nan)


def load_shiller_data(source: str | Path | bytes | None = None) -> pd.DataFrame:
    """Load and normalise Robert Shiller's monthly U.S. equity dataset.

    ``source`` may be omitted to download the official spreadsheet, or it may
    point to a local XLS/XLSX/CSV copy. The returned frame is indexed by the
    first day of each encoded month and includes total-return approximations,
    valuation ratios, inflation and rolling volatility.
    """

    raw = _read_source(source)
    header_row = _find_header_row(raw)
    header = list(raw.iloc[header_row])
    body = raw.iloc[header_row + 1 :].copy()
    body.columns = header
    body = body.rename(columns=_map_columns(header))

    missing = [column for column in _REQUIRED_COLUMNS if column not in body.columns]
    if missing:
        raise DataSchemaError(f"Missing required columns: {', '.join(missing)}")

    body = body[pd.to_numeric(body["date"], errors="coerce").notna()].copy()
    body.index = pd.DatetimeIndex([_parse_shiller_date(value) for value in body["date"]], name="month")
    body = body.drop(columns=["date"])
    body = body.loc[:, ~body.columns.duplicated()]
    return _derive_fields(body)


def _read_fred_source(source: str | Path | bytes | None) -> pd.DataFrame:
    if source is None:
        return pd.read_csv(BytesIO(_download(FRED_TB3MS_CSV_URL)))
    if isinstance(source, bytes):
        return pd.read_csv(BytesIO(source))

    path = Path(source)
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path)


def load_fred_risk_free_rate(source: str | Path | bytes | None = None) -> pd.Series:
    """Load FRED TB3MS as an annual decimal risk-free-rate series.

    TB3MS is a monthly average of business-day 3-month Treasury-bill rates on a
    discount basis. Missing observations remain missing; no synthetic pre-series
    history is manufactured.
    """

    raw = _read_fred_source(source)
    columns = {_normalise_name(column): column for column in raw.columns}
    date_column = columns.get("date") or columns.get("observationdate")
    value_column = columns.get("tb3ms")
    if date_column is None or value_column is None:
        raise DataSchemaError("FRED risk-free data must contain DATE and TB3MS columns")

    dates = pd.to_datetime(raw[date_column], errors="coerce")
    values = pd.to_numeric(raw[value_column], errors="coerce") / 100.0
    valid = dates.notna() & values.notna()
    if not valid.any():
        raise DataSchemaError("FRED risk-free data contains no valid observations")

    month_index = dates[valid].dt.to_period("M").dt.to_timestamp()
    series = pd.Series(values[valid].to_numpy(), index=month_index, name="risk_free_rate")
    series.index.name = "month"
    return series.groupby(level=0).last().sort_index()


def enrich_with_risk_free_rate(
    market: pd.DataFrame,
    source: str | Path | bytes | None = None,
) -> pd.DataFrame:
    """Join FRED TB3MS onto monthly market data without pre-inception fallback."""

    rates = load_fred_risk_free_rate(source)
    enriched = market.join(rates, how="left")
    enriched["risk_free_rate"] = enriched["risk_free_rate"].ffill()
    return enriched


def synthetic_market_data(periods: int = 240, seed: int = 7) -> pd.DataFrame:
    """Create deterministic monthly data for demos and tests, not research."""

    if periods < 24:
        raise ValueError("periods must be at least 24")
    rng = np.random.default_rng(seed)
    index = pd.date_range("2000-01-01", periods=periods, freq="MS")
    returns = rng.normal(loc=0.007, scale=0.04, size=periods)
    price = 100.0 * np.cumprod(1.0 + returns)
    cpi = 170.0 * np.cumprod(np.full(periods, 1.002))
    earnings = price / np.clip(rng.normal(20.0, 3.0, periods), 10.0, 35.0)
    dividend = price * 0.018

    frame = pd.DataFrame(
        {
            "price": price,
            "dividend": dividend,
            "earnings": earnings,
            "cpi": cpi,
            "cape": np.clip(rng.normal(24.0, 5.0, periods), 8.0, 45.0),
            "long_rate": np.clip(rng.normal(4.0, 1.0, periods), 0.0, 10.0),
            "risk_free_rate": np.clip(rng.normal(0.025, 0.008, periods), 0.0, 0.08),
        },
        index=index,
    )
    frame.index.name = "month"
    return _derive_fields(frame)
