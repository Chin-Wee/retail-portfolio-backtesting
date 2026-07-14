from __future__ import annotations

import pytest

from retail_sp500.live import LiveDataError, parse_twelve_data_quote


def test_parses_twelve_data_quote() -> None:
    quote = parse_twelve_data_quote(
        {
            "symbol": "SPY",
            "close": "650.25",
            "datetime": "2026-07-14 15:42:00",
            "currency": "USD",
            "exchange": "NYSE Arca",
        }
    )
    assert quote.symbol == "SPY"
    assert quote.price == pytest.approx(650.25)
    assert quote.currency == "USD"


def test_rejects_provider_error() -> None:
    with pytest.raises(LiveDataError, match="rate limit"):
        parse_twelve_data_quote({"status": "error", "code": 429, "message": "rate limit"})


def test_rejects_incomplete_quote() -> None:
    with pytest.raises(LiveDataError, match="missing"):
        parse_twelve_data_quote({"symbol": "SPY", "close": "650.25"})
