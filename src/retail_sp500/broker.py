from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FeeMarket = Literal["us", "lse_usd", "custom"]
PricingPlan = Literal["fixed", "tiered", "custom"]
FxMethod = Literal["manual_spot", "autofx", "none", "custom"]

IBKR_FEE_SCHEDULE_AS_OF = "2026-08-17"


@dataclass(frozen=True)
class BrokerFeeConfig:
    """Buy-side transaction-cost model for an SGD-funded ETF purchase."""

    market: FeeMarket = "us"
    pricing: PricingPlan = "tiered"
    fx_method: FxMethod = "manual_spot"
    extra_trade_cost_bps: float = 0.0
    custom_stock_bps: float = 0.0
    custom_stock_per_share: float = 0.0
    custom_stock_min: float = 0.0
    custom_stock_max: float | None = None
    custom_fx_bps: float = 0.0
    custom_fx_min: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.extra_trade_cost_bps,
            self.custom_stock_bps,
            self.custom_stock_per_share,
            self.custom_stock_min,
            self.custom_fx_bps,
            self.custom_fx_min,
        )
        if min(values) < 0.0:
            raise ValueError("broker fee settings cannot be negative")
        if self.custom_stock_max is not None and self.custom_stock_max < 0.0:
            raise ValueError("custom_stock_max cannot be negative")
        if (
            self.custom_stock_max is not None
            and self.custom_stock_max < self.custom_stock_min
        ):
            raise ValueError("custom_stock_max cannot be below custom_stock_min")
        if self.market == "custom" and self.pricing != "custom":
            raise ValueError("custom market requires custom pricing")


@dataclass(frozen=True)
class BuyExecution:
    allocation_sgd: float
    trade_currency_per_sgd: float
    trade_currency_notional: float
    units: float
    commission_trade_currency: float
    fx_fee_trade_currency: float
    commission_sgd: float
    fx_fee_sgd: float
    total_fees_sgd: float
    total_spent_sgd: float


def ibkr_pro_preset(
    *,
    market: Literal["us", "lse_usd"] = "us",
    pricing: Literal["fixed", "tiered"] = "tiered",
    fx_method: Literal["manual_spot", "autofx", "none"] = "manual_spot",
    extra_trade_cost_bps: float = 0.0,
) -> BrokerFeeConfig:
    return BrokerFeeConfig(
        market=market,
        pricing=pricing,
        fx_method=fx_method,
        extra_trade_cost_bps=extra_trade_cost_bps,
    )


def stock_commission(
    trade_value: float,
    shares: float,
    config: BrokerFeeConfig,
) -> float:
    """Return commission in the asset's trade currency for one buy order."""

    if min(trade_value, shares) < 0.0:
        raise ValueError("trade value and shares cannot be negative")
    if trade_value == 0.0 or shares == 0.0:
        return 0.0

    if config.market == "us":
        if config.pricing == "fixed":
            base = max(0.005 * shares, 1.00)
        elif config.pricing == "tiered":
            base = max(0.0035 * shares, 0.35)
        else:
            raise ValueError("US preset requires fixed or tiered pricing")
        base = min(base, 0.01 * trade_value)
    elif config.market == "lse_usd":
        if config.pricing == "fixed":
            base = max(0.0005 * trade_value, 4.00)
        elif config.pricing == "tiered":
            base = min(max(0.0005 * trade_value, 1.70), 39.00)
        else:
            raise ValueError("LSE USD preset requires fixed or tiered pricing")
    elif config.market == "custom" and config.pricing == "custom":
        base = (
            config.custom_stock_bps / 10_000.0 * trade_value
            + config.custom_stock_per_share * shares
        )
        base = max(base, config.custom_stock_min)
        if config.custom_stock_max is not None:
            base = min(base, config.custom_stock_max)
    else:
        raise ValueError("unsupported broker fee configuration")

    return base + config.extra_trade_cost_bps / 10_000.0 * trade_value


def fx_conversion_fee(trade_value: float, config: BrokerFeeConfig) -> float:
    """Return the SGD-to-trade-currency conversion cost in trade currency."""

    if trade_value < 0.0:
        raise ValueError("trade value cannot be negative")
    if trade_value == 0.0 or config.fx_method == "none":
        return 0.0
    if config.fx_method == "manual_spot":
        return max(0.20 / 10_000.0 * trade_value, 2.00)
    if config.fx_method == "autofx":
        return 3.0 / 10_000.0 * trade_value
    if config.fx_method == "custom":
        return max(
            config.custom_fx_bps / 10_000.0 * trade_value,
            config.custom_fx_min,
        )
    raise ValueError(f"unsupported FX method: {config.fx_method}")


def execute_buy(
    allocation_sgd: float,
    *,
    asset_price: float,
    sgd_per_trade_currency: float,
    config: BrokerFeeConfig,
) -> BuyExecution:
    """Spend up to allocation_sgd on an ETF, deducting FX and stock commissions."""

    if allocation_sgd < 0.0:
        raise ValueError("allocation_sgd cannot be negative")
    if asset_price <= 0.0 or sgd_per_trade_currency <= 0.0:
        raise ValueError("asset price and FX rate must be positive")
    if allocation_sgd == 0.0:
        return BuyExecution(
            allocation_sgd=0.0,
            trade_currency_per_sgd=1.0 / sgd_per_trade_currency,
            trade_currency_notional=0.0,
            units=0.0,
            commission_trade_currency=0.0,
            fx_fee_trade_currency=0.0,
            commission_sgd=0.0,
            fx_fee_sgd=0.0,
            total_fees_sgd=0.0,
            total_spent_sgd=0.0,
        )

    gross_trade_currency = allocation_sgd / sgd_per_trade_currency
    fx_fee = fx_conversion_fee(gross_trade_currency, config)
    after_fx = max(gross_trade_currency - fx_fee, 0.0)

    commission = 0.0
    shares = after_fx / asset_price
    for _ in range(4):
        investable = max(after_fx - commission, 0.0)
        shares = investable / asset_price
        next_commission = stock_commission(investable, shares, config)
        if abs(next_commission - commission) < 1e-12:
            commission = next_commission
            break
        commission = next_commission

    trade_notional = max(after_fx - commission, 0.0)
    shares = trade_notional / asset_price
    commission = stock_commission(trade_notional, shares, config)
    trade_notional = max(after_fx - commission, 0.0)
    shares = trade_notional / asset_price

    commission_sgd = commission * sgd_per_trade_currency
    fx_fee_sgd = fx_fee * sgd_per_trade_currency
    total_fees_sgd = commission_sgd + fx_fee_sgd
    total_spent_sgd = trade_notional * sgd_per_trade_currency + total_fees_sgd
    total_spent_sgd = min(total_spent_sgd, allocation_sgd)

    return BuyExecution(
        allocation_sgd=allocation_sgd,
        trade_currency_per_sgd=1.0 / sgd_per_trade_currency,
        trade_currency_notional=trade_notional,
        units=shares,
        commission_trade_currency=commission,
        fx_fee_trade_currency=fx_fee,
        commission_sgd=commission_sgd,
        fx_fee_sgd=fx_fee_sgd,
        total_fees_sgd=total_fees_sgd,
        total_spent_sgd=total_spent_sgd,
    )
