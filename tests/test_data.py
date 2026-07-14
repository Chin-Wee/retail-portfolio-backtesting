from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from retail_sp500.data import (
    DataSchemaError,
    enrich_with_risk_free_rate,
    load_fred_risk_free_rate,
    load_shiller_data,
    synthetic_market_data,
)


def test_synthetic_market_has_required_derived_fields() -> None:
    frame = synthetic_market_data(periods=36)
    assert {
        "pe",
        "total_return",
        "realized_vol_12m",
        "moving_average_10m",
        "risk_free_rate",
    }.issubset(frame.columns)
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


def test_loads_fred_tb3ms_as_annual_decimal(tmp_path: Path) -> None:
    path = tmp_path / "tb3ms.csv"
    path.write_text("DATE,TB3MS\n2020-01-01,1.50\n2020-02-01,.\n2020-03-01,0.25\n")
    rates = load_fred_risk_free_rate(path)
    assert rates.loc["2020-01-01"] == pytest.approx(0.015)
    assert pd.Timestamp("2020-02-01") not in rates.index
    assert rates.loc["2020-03-01"] == pytest.approx(0.0025)


def test_risk_free_enrichment_does_not_backfill_before_inception(tmp_path: Path) -> None:
    path = tmp_path / "tb3ms.csv"
    path.write_text("DATE,TB3MS\n2000-03-01,3.00\n2000-04-01,3.50\n")
    market = synthetic_market_data(periods=24)
    enriched = enrich_with_risk_free_rate(market.drop(columns="risk_free_rate"), path)
    assert pd.isna(enriched.loc["2000-01-01", "risk_free_rate"])
    assert enriched.loc["2000-03-01", "risk_free_rate"] == pytest.approx(0.03)
    assert enriched.loc["2000-05-01", "risk_free_rate"] == pytest.approx(0.035)
