from __future__ import annotations

from datetime import date
import json
from urllib.parse import parse_qs, urlparse

import pandas as pd
import pytest

import retail_sp500.daily_data as daily_data_module
from retail_sp500.daily_data import (
    DailyDataError,
    daily_data_summary,
    fetch_twelve_data_daily,
    parse_twelve_data_daily,
)


def _payload() -> dict[str, object]:
    return {
        "meta": {"symbol": "SPY", "interval": "1day", "exchange": "NYSE Arca"},
        "values": [
            {
                "datetime": "2024-01-03",
                "open": "470.00",
                "high": "472.00",
                "low": "468.00",
                "close": "471.00",
                "volume": "1000",
            },
            {
                "datetime": "2024-01-02",
                "open": "469.00",
                "high": "471.00",
                "low": "467.00",
                "close": "470.00",
                "volume": "900",
            },
        ],
        "status": "ok",
    }


def test_parses_real_daily_ohlcv_in_ascending_order() -> None:
    frame = parse_twelve_data_daily(_payload(), today=date(2024, 1, 4))
    assert frame.index.tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]
    assert frame.loc["2024-01-03", "low"] == pytest.approx(468.0)
    assert frame.attrs["symbol"] == "SPY"
    assert frame.attrs["source"] == "Twelve Data"
    assert daily_data_summary(frame)["interval"] == "1day"


def test_rejects_future_sessions() -> None:
    with pytest.raises(DailyDataError, match="future-dated"):
        parse_twelve_data_daily(_payload(), today=date(2024, 1, 2))


def test_rejects_invalid_ohlc_relationships() -> None:
    payload = _payload()
    payload["values"][0]["low"] = "473.00"  # type: ignore[index]
    with pytest.raises(DailyDataError, match="low"):
        parse_twelve_data_daily(payload, today=date(2024, 1, 4))


def test_rejects_provider_error() -> None:
    with pytest.raises(DailyDataError, match="rate limit"):
        parse_twelve_data_daily(
            {"status": "error", "code": 429, "message": "rate limit"},
            today=date(2024, 1, 4),
        )


def test_fetch_requests_full_daily_window(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(_payload()).encode("utf-8")

    def fake_urlopen(request: object, timeout: int) -> Response:
        captured["url"] = request.full_url  # type: ignore[attr-defined]
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(daily_data_module, "urlopen", fake_urlopen)
    frame = fetch_twelve_data_daily(
        "secret",
        start_date="2024-01-01",
        end_date="2024-01-03",
    )

    query = parse_qs(urlparse(str(captured["url"])).query)
    assert query["interval"] == ["1day"]
    assert query["outputsize"] == ["5000"]
    assert query["order"] == ["asc"]
    assert query["start_date"] == ["2024-01-01"]
    assert frame.index.max() == pd.Timestamp("2024-01-03")
