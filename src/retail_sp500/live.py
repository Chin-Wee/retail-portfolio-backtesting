from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from typing import Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TWELVE_DATA_QUOTE_URL = "https://api.twelvedata.com/quote"


class LiveDataError(RuntimeError):
    """Raised when a live market-data provider returns unusable data."""


@dataclass(frozen=True)
class LiveQuote:
    symbol: str
    price: float
    timestamp: str
    currency: str | None = None
    exchange: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def parse_twelve_data_quote(payload: Mapping[str, object]) -> LiveQuote:
    if payload.get("status") == "error" or "code" in payload:
        message = str(payload.get("message") or "Twelve Data returned an error")
        raise LiveDataError(message)

    symbol = str(payload.get("symbol") or "").strip()
    price_raw = payload.get("close") or payload.get("price")
    timestamp = str(payload.get("datetime") or payload.get("timestamp") or "").strip()
    if not symbol or price_raw is None or not timestamp:
        raise LiveDataError("Twelve Data quote is missing symbol, price, or timestamp")

    try:
        price = float(price_raw)
    except (TypeError, ValueError) as error:
        raise LiveDataError("Twelve Data quote contains an invalid price") from error
    if price <= 0.0:
        raise LiveDataError("Twelve Data quote price must be positive")

    return LiveQuote(
        symbol=symbol,
        price=price,
        timestamp=timestamp,
        currency=str(payload["currency"]) if payload.get("currency") else None,
        exchange=str(payload["exchange"]) if payload.get("exchange") else None,
    )


def fetch_twelve_data_quote(
    api_key: str,
    symbol: str = "SPY",
    timeout_seconds: int = 15,
) -> LiveQuote:
    if not api_key.strip():
        raise ValueError("a Twelve Data API key is required")
    if not symbol.strip():
        raise ValueError("symbol is required")

    query = urlencode({"symbol": symbol.upper(), "apikey": api_key})
    request = Request(
        f"{TWELVE_DATA_QUOTE_URL}?{query}",
        headers={"User-Agent": "retail-sp500-backtesting/0.2"},
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise LiveDataError("Twelve Data returned a non-object response")
    return parse_twelve_data_quote(payload)
