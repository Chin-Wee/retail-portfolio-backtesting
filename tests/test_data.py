from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from retail_sp500.data import DataSchemaError, load_shiller_data, synthetic_market_data


def test_synthetic_market_has_required_derived_fields() -> None:
    frame = synthetic_market_data(periods=36)
    assert {"pe", "total_return", "realized_vol_12m", "moving_average_10m"}.issubset(frame.columns)
    assert len(frame) == 36


def test_load_shiller_style_csv(tmp_path: Path) -> None:
    path = tmp_path / "sample.csv"
    pd.DataFrame(
        [
            ["metadata", None, None, None, None, None, None, None],
            ["Date", "P", "D", "E", "CPI", "Fraction", "Rate GS10", "CAPE"],
            [1871.01, 4.44, 0.26, 0.40, 12.46, 1871.00, 5.32, 18.0],
            [1871.02, 4.50, 0.27, 0.41, 12.50, 1871.08, 5.30, 18.2],
        ]
    ).to_csv(path, index=False, header=False)

    frame = load_shiller_data(path)
    assert list(frame.index) == [pd.Timestamp("1871-01-01"), pd.Timestamp("1871-02-01")]
    assert frame.loc["1871-02-01", "pe"] == pytest.approx(4.50 / 0.41)
    assert frame.loc["1871-02-01", "total_return"] > frame.loc["1871-02-01", "price_return"]


def test_rejects_unknown_schema(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    pd.DataFrame([["when", "close"], [1, 100]]).to_csv(path, index=False, header=False)
    with pytest.raises(DataSchemaError):
        load_shiller_data(path)
