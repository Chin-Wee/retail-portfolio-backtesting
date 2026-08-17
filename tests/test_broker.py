from __future__ import annotations

import pytest

from retail_sp500.broker import (
    BrokerFeeConfig,
    execute_buy,
    fx_conversion_fee,
    ibkr_pro_preset,
    stock_commission,
)


def test_us_fixed_and_tiered_commissions() -> None:
    fixed = ibkr_pro_preset(market="us", pricing="fixed", fx_method="none")
    tiered = ibkr_pro_preset(market="us", pricing="tiered", fx_method="none")

    assert stock_commission(25_000.0, 1_000.0, fixed) == pytest.approx(5.0)
    assert stock_commission(2_500.0, 100.0, tiered) == pytest.approx(0.35)


def test_lse_usd_fixed_and_tiered_commissions() -> None:
    fixed = ibkr_pro_preset(market="lse_usd", pricing="fixed", fx_method="none")
    tiered = ibkr_pro_preset(market="lse_usd", pricing="tiered", fx_method="none")

    assert stock_commission(8_000.0, 100.0, fixed) == pytest.approx(4.0)
    assert stock_commission(100_000.0, 1_000.0, fixed) == pytest.approx(50.0)
    assert stock_commission(1_000_000.0, 10_000.0, tiered) == pytest.approx(39.0)


def test_manual_spot_fx_and_autofx_costs() -> None:
    manual = ibkr_pro_preset(fx_method="manual_spot")
    autofx = ibkr_pro_preset(fx_method="autofx")

    assert fx_conversion_fee(100_000.0, manual) == pytest.approx(2.0)
    assert fx_conversion_fee(1_000_000.0, manual) == pytest.approx(20.0)
    assert fx_conversion_fee(1_000_000.0, autofx) == pytest.approx(300.0)


def test_custom_fee_override_combines_bps_and_per_share() -> None:
    custom = BrokerFeeConfig(
        market="custom",
        pricing="custom",
        fx_method="custom",
        custom_stock_bps=2.0,
        custom_stock_per_share=0.01,
        custom_stock_min=1.0,
        custom_stock_max=50.0,
        custom_fx_bps=1.0,
        custom_fx_min=3.0,
    )

    assert stock_commission(10_000.0, 100.0, custom) == pytest.approx(3.0)
    assert fx_conversion_fee(10_000.0, custom) == pytest.approx(3.0)


def test_execute_buy_deducts_fees_from_allocation() -> None:
    config = ibkr_pro_preset(market="us", pricing="fixed", fx_method="manual_spot")
    execution = execute_buy(
        10_000.0,
        asset_price=100.0,
        sgd_per_trade_currency=1.35,
        config=config,
    )

    assert execution.units > 0.0
    assert execution.total_fees_sgd > 0.0
    assert execution.total_spent_sgd <= 10_000.0
    assert execution.trade_currency_notional * 1.35 < 10_000.0
