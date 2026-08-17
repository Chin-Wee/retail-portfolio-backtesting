from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from retail_sp500.data import MarketDataError, parse_twelve_data, validate_daily


def _payload() -> dict[str, object]:
    return {
        "meta": {"symbol": "SPY", "interval": "1day"},
        "values": [
            {
                "datetime": "2024-01-03",
                "open": "101",
                "high": "103",
                "low": "100",
                "close": "102",
                "volume": "1000",
            },
            {
                "datetime": "2024-01-02",
                "open": "100",
                "high": "102",
                "low": "99",
                "close": "101",
                "volume": "900",
            },
        ],
    }


def test_parse_twelve_data_sorts_and_validates() -> None:
    frame = parse_twelve_data(_payload(), today=date(2024, 1, 4))
    assert frame.index.tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert frame.attrs["source"] == "Twelve Data"


def test_parse_twelve_data_supports_instruments_without_volume() -> None:
    payload = _payload()
    for row in payload["values"]:
        row.pop("volume")
    frame = parse_twelve_data(payload, today=date(2024, 1, 4))
    assert (frame["volume"] == 0.0).all()


def test_rejects_future_or_invalid_ohlc() -> None:
    with pytest.raises(MarketDataError, match="future-dated"):
        parse_twelve_data(_payload(), today=date(2024, 1, 2))

    frame = parse_twelve_data(_payload(), today=date(2024, 1, 4))
    frame.loc[pd.Timestamp("2024-01-03"), "low"] = 104.0
    with pytest.raises(MarketDataError, match="low"):
        validate_daily(frame, today=date(2024, 1, 4))
