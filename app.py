from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from retail_sp500.broker import (
    IBKR_FEE_SCHEDULE_AS_OF,
    BrokerFeeConfig,
    execute_buy,
    ibkr_pro_preset,
)
from retail_sp500.currency import convert_daily_prices, prior_fx_close
from retail_sp500.data import DEFAULT_START_DATE, MarketDataError, load_market, market_summary
from retail_sp500.dca import DcaConfig, rolling_dca_backtest, summarize_dca
from retail_sp500.planner import PlanConfig, monthly_budget, rolling_plan_backtest, scenario_summary

st.set_page_config(page_title="Singapore Money Planner", page_icon="💰", layout="wide")


def _secret(name: str) -> str:
    try:
        value = st.secrets.get(name, "")
    except Exception:
        value = ""
    return str(value or "")


def _money(value: float) -> str:
    return f"S${value:,.0f}"


def _cache_path(symbol: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", symbol.strip().lower()) or "market"
    return Path("data") / f"{safe}_adjusted_daily.csv"


@st.cache_data(ttl=24 * 60 * 60, show_spinner=False)
def _load_market_cached(
    api_key: str,
    symbol: str,
    start_date: str,
    refresh: bool,
) -> pd.DataFrame:
    return load_market(
        api_key or None,
        cache_path=_cache_path(symbol),
        refresh=refresh,
        symbol=symbol,
        start_date=start_date,
    )


def _load_asset_bundle(
    *,
    api_key: str,
    symbol: str,
    asset_currency: str,
    fx_symbol: str,
    start_date: str,
    refresh: bool,
) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame]:
    asset = _load_market_cached(api_key, symbol.strip().upper(), start_date, refresh)
    if asset_currency == "USD":
        fx = _load_market_cached(api_key, fx_symbol.strip().upper(), start_date, refresh)
        daily_sgd = convert_daily_prices(asset, fx, label="SGD")
        return asset, fx, daily_sgd
    daily_sgd = asset.copy()
    daily_sgd.attrs["currency"] = "SGD"
    return asset, None, daily_sgd


st.title("Singapore Money Planner")
st.caption(
    "Plan monthly finances or compare a lump sum with dollar-cost averaging using real market and FX history. "
    "Historical backtests are educational scenarios, not personalised financial advice."
)

with st.sidebar:
    st.header("Market data")
    symbol = st.text_input("ETF / market symbol", value="SPY", help="Symbol supported by your Twelve Data plan.")
    asset_currency = st.selectbox("Asset price currency", options=["USD", "SGD"], index=0)
    fx_symbol = ""
    if asset_currency == "USD":
        fx_symbol = st.text_input(
            "FX pair to SGD",
            value="USD/SGD",
            help="Used to convert historical investment values and transaction costs into SGD.",
        )
    start_date = st.text_input("History start date", value=DEFAULT_START_DATE)
    default_key = os.getenv("TWELVE_DATA_API_KEY", "") or _secret("TWELVE_DATA_API_KEY")
    api_key = st.text_input("Twelve Data API key", value=default_key, type="password")
    refresh = st.checkbox("Refresh market data", value=False)
    st.caption("Successful requests are cached locally using dividend/split-adjusted daily prices.")

personal_tab, dca_tab = st.tabs(["Personal plan", "S$1m DCA lab"])

with personal_tab:
    st.subheader("Monthly finances")
    left, middle, right = st.columns(3)
    with left:
        age = st.number_input("Age", min_value=16, max_value=70, value=25, step=1, key="plan_age")
        salary = st.number_input(
            "Gross monthly salary",
            min_value=0.0,
            value=5_000.0,
            step=100.0,
            format="%.0f",
            key="plan_salary",
        )
        expenses = st.number_input(
            "Monthly expenses",
            min_value=0.0,
            value=2_000.0,
            step=100.0,
            format="%.0f",
            key="plan_expenses",
        )
    with middle:
        current_cash = st.number_input(
            "Current cash",
            min_value=0.0,
            value=10_000.0,
            step=500.0,
            format="%.0f",
            key="plan_cash",
        )
        current_investments = st.number_input(
            "Current investments in this ETF",
            min_value=0.0,
            value=10_000.0,
            step=500.0,
            format="%.0f",
            key="plan_investments",
        )
        emergency_months = st.slider(
            "Emergency fund",
            min_value=0,
            max_value=12,
            value=6,
            step=1,
            key="plan_emergency",
        )
    with right:
        horizon = st.slider(
            "Planning horizon (years)",
            min_value=3,
            max_value=15,
            value=10,
            step=1,
            key="plan_horizon",
        )
        salary_growth = st.number_input(
            "Annual salary growth (%)", value=3.0, step=0.5, format="%.1f", key="plan_growth"
        )
        expense_inflation = st.number_input(
            "Annual expense inflation (%)", value=2.5, step=0.5, format="%.1f", key="plan_inflation"
        )

    cpf_enabled = st.checkbox(
        "Apply 2026 CPF employee/employer contribution rules",
        value=True,
        help="Uses the 2026 full-rate CPF table and S$8,000 Ordinary Wage ceiling throughout each scenario.",
        key="plan_cpf",
    )

    try:
        budget = monthly_budget(
            float(salary),
            float(expenses),
            age=int(age),
            cpf_enabled=cpf_enabled,
        )
    except ValueError as exc:
        st.error(str(exc))
        budget = None

    if budget is not None:
        b1, b2, b3, b4 = st.columns(4)
        b1.metric("Take-home pay", _money(budget["take_home"]))
        b2.metric("Monthly surplus", _money(budget["monthly_surplus"]))
        b3.metric("Employee CPF", _money(budget["employee_cpf"]))
        b4.metric("Employer CPF", _money(budget["employer_cpf"]))

        reserve_target = float(emergency_months) * float(expenses)
        if budget["monthly_surplus"] < 0:
            st.warning(
                "Your current monthly cash flow is negative before investing. Historical scenarios may require ETF sales to fund expenses."
            )
        elif current_cash < reserve_target:
            st.info(
                f"The model sends monthly surplus to cash until the emergency fund reaches {_money(reserve_target)}, then invests the excess."
            )
        else:
            st.info(f"Cash above the {_money(reserve_target)} emergency-fund target is invested monthly.")

    run_plan = st.button("Run personal-plan stress test", type="primary", key="run_plan")
    if run_plan and budget is not None:
        required_symbols = [symbol.strip()]
        if asset_currency == "USD":
            required_symbols.append(fx_symbol.strip())
        missing_cache = any(item and not _cache_path(item).exists() for item in required_symbols)
        if not api_key and missing_cache:
            st.error("A Twelve Data API key is required for the first download.")
        else:
            config = PlanConfig(
                start_age=int(age),
                gross_monthly_salary=float(salary),
                monthly_expenses=float(expenses),
                current_cash=float(current_cash),
                current_investments=float(current_investments),
                annual_salary_growth=float(salary_growth) / 100.0,
                annual_expense_inflation=float(expense_inflation) / 100.0,
                emergency_months=float(emergency_months),
                horizon_years=int(horizon),
                cpf_enabled=cpf_enabled,
            )
            try:
                with st.spinner("Loading market history and running personal-finance scenarios..."):
                    _, _, daily = _load_asset_bundle(
                        api_key=api_key,
                        symbol=symbol,
                        asset_currency=asset_currency,
                        fx_symbol=fx_symbol,
                        start_date=start_date,
                        refresh=refresh,
                    )
                    scenarios = rolling_plan_backtest(daily, config=config)
                    summary = scenario_summary(scenarios)
            except (ValueError, MarketDataError, OSError) as exc:
                st.error(f"Could not run the backtest: {exc}")
            else:
                r1, r2, r3, r4 = st.columns(4)
                r1.metric("Worst real ending wealth", _money(summary["worst_real_ending"]))
                r2.metric("Median real ending wealth", _money(summary["median_real_ending"]))
                r3.metric("Best real ending wealth", _money(summary["best_real_ending"]))
                r4.metric("Liquidity-stress scenarios", f"{summary['cash_shortfall_rate']:.0%}")

                chart_data = scenarios[["start", "ending_real_liquid_net_worth"]].copy()
                figure = px.line(
                    chart_data,
                    x="start",
                    y="ending_real_liquid_net_worth",
                    labels={
                        "start": "Historical start date",
                        "ending_real_liquid_net_worth": "Inflation-adjusted ending liquid wealth (SGD)",
                    },
                    title=f"{horizon}-year outcome by historical starting month",
                )
                st.plotly_chart(figure, use_container_width=True)
                st.caption(
                    "The personal-plan model still excludes brokerage costs. Use the DCA lab for explicit IBKR transaction-cost analysis."
                )

with dca_tab:
    st.subheader("Deploy an existing lump sum")
    st.write(
        "Compare investing everything immediately with spreading the same starting capital across equal monthly purchases. "
        "Every strategy uses the same historical start date and the same terminal date."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        dca_capital = st.number_input(
            "Starting capital (SGD)",
            min_value=1_000.0,
            value=1_000_000.0,
            step=10_000.0,
            format="%.0f",
            key="dca_capital",
        )
    with c2:
        dca_horizon = st.slider(
            "Evaluation horizon (years)", min_value=3, max_value=15, value=10, step=1, key="dca_horizon"
        )
    with c3:
        dca_buy_day = st.number_input(
            "Monthly buy day",
            min_value=1,
            max_value=28,
            value=1,
            step=1,
            help="Uses the first trading session on or after this calendar day.",
            key="dca_buy_day",
        )
    with c4:
        cash_yield = st.number_input(
            "Undeployed cash yield (% p.a.)",
            min_value=-10.0,
            max_value=20.0,
            value=0.0,
            step=0.25,
            format="%.2f",
            key="dca_cash_yield",
        )

    selected_deployments = st.multiselect(
        "Deployment strategies",
        options=[1, 3, 6, 12, 18, 24, 36],
        default=[1, 3, 6, 12, 18, 24, 36],
        format_func=lambda months: "Lump sum" if months == 1 else f"{months} months",
        help="Lump sum is always included as the comparison baseline.",
        key="dca_deployments",
    )
    deployments = sorted(set([1, *selected_deployments]))
    deployments = [months for months in deployments if months <= int(dca_horizon) * 12]

    st.markdown("#### IBKR Pro trading costs")
    f1, f2, f3 = st.columns(3)
    with f1:
        venue_label = st.selectbox(
            "ETF venue",
            ["US exchange-listed ETF", "LSE USD-denominated ETF"],
            key="dca_venue",
        )
        venue = "us" if venue_label.startswith("US") else "lse_usd"
    with f2:
        pricing_label = st.selectbox("IBKR Pro pricing", ["Tiered", "Fixed"], key="dca_pricing")
        pricing = pricing_label.lower()
    with f3:
        fx_options = ["Manual spot FX", "AutoFX"] if asset_currency == "USD" else ["No FX"]
        fx_label = st.selectbox("Currency conversion", fx_options, key="dca_fx_method")
        fx_method = {
            "Manual spot FX": "manual_spot",
            "AutoFX": "autofx",
            "No FX": "none",
        }[fx_label]

    broker = ibkr_pro_preset(
        market=venue,
        pricing=pricing,
        fx_method=fx_method,
    )

    with st.expander("Advanced fee settings"):
        st.caption(
            f"Published IBKR Singapore preset checked {IBKR_FEE_SCHEDULE_AS_OF}. Tiered exchange/clearing costs vary by execution venue."
        )
        extra_bps = st.number_input(
            "Extra Tiered venue / clearing estimate (bps)",
            min_value=0.0,
            value=0.0,
            step=0.01,
            format="%.3f",
            key="dca_extra_bps",
        )
        broker = replace(broker, extra_trade_cost_bps=float(extra_bps))

        custom_override = st.checkbox("Override the published preset", value=False, key="dca_custom_override")
        if custom_override:
            o1, o2, o3 = st.columns(3)
            with o1:
                custom_stock_bps = st.number_input(
                    "Stock commission (bps)", min_value=0.0, value=0.0, step=0.01, key="custom_stock_bps"
                )
                custom_per_share = st.number_input(
                    "Stock commission per share", min_value=0.0, value=0.0, step=0.0001, format="%.4f", key="custom_per_share"
                )
            with o2:
                custom_min = st.number_input(
                    "Minimum stock commission", min_value=0.0, value=0.0, step=0.1, key="custom_stock_min"
                )
                custom_max_enabled = st.checkbox("Cap stock commission", value=False, key="custom_max_enabled")
                custom_max = st.number_input(
                    "Maximum stock commission",
                    min_value=0.0,
                    value=100.0,
                    step=1.0,
                    disabled=not custom_max_enabled,
                    key="custom_stock_max",
                )
            with o3:
                custom_fx_bps = st.number_input(
                    "FX cost (bps)", min_value=0.0, value=0.0, step=0.01, key="custom_fx_bps"
                )
                custom_fx_min = st.number_input(
                    "Minimum FX cost", min_value=0.0, value=0.0, step=0.1, key="custom_fx_min"
                )
            broker = BrokerFeeConfig(
                market="custom",
                pricing="custom",
                fx_method="custom" if asset_currency == "USD" else "none",
                custom_stock_bps=float(custom_stock_bps),
                custom_stock_per_share=float(custom_per_share),
                custom_stock_min=float(custom_min),
                custom_stock_max=float(custom_max) if custom_max_enabled else None,
                custom_fx_bps=float(custom_fx_bps),
                custom_fx_min=float(custom_fx_min),
            )

    if venue == "us" and pricing == "fixed":
        st.caption("US Fixed preset: USD 0.005/share, USD 1 minimum per order; buy-side model.")
    elif venue == "us":
        st.caption("US Tiered preset: first tier USD 0.0035/share, USD 0.35 minimum, plus configurable venue/clearing costs.")
    elif pricing == "fixed":
        st.caption("LSE USD Fixed preset: 0.05% of trade value, USD 4 minimum for SmartRouted USD orders.")
    else:
        st.caption("LSE USD Tiered preset: 0.05% of trade value, USD 1.70 minimum, USD 39 maximum, plus venue/clearing costs.")
    if asset_currency == "USD":
        st.caption(
            "Manual spot FX preset: 0.20 bp with USD 2 minimum per conversion. AutoFX preset: 3 bps."
        )

    spacing_label = st.selectbox(
        "Historical start-date spacing",
        ["Monthly", "Quarterly", "Yearly"],
        index=0,
        help="Monthly gives the most complete sample but takes more computation.",
        key="dca_spacing",
    )
    step_months = {"Monthly": 1, "Quarterly": 3, "Yearly": 12}[spacing_label]

    run_dca = st.button("Compare lump sum vs DCA", type="primary", key="run_dca")
    if run_dca:
        if asset_currency != "USD" and not custom_override:
            st.error("The built-in IBKR presets here are for USD-traded ETFs. Use the advanced custom override for an SGD-traded asset.")
        elif not deployments:
            st.error("Choose at least one deployment strategy.")
        else:
            required_symbols = [symbol.strip()]
            if asset_currency == "USD":
                required_symbols.append(fx_symbol.strip())
            missing_cache = any(item and not _cache_path(item).exists() for item in required_symbols)
            if not api_key and missing_cache:
                st.error("A Twelve Data API key is required for the first download.")
            else:
                dca_config = DcaConfig(
                    capital_sgd=float(dca_capital),
                    deployment_months=tuple(deployments),
                    evaluation_years=int(dca_horizon),
                    buy_day=int(dca_buy_day),
                    cash_yield_annual=float(cash_yield) / 100.0,
                )
                try:
                    with st.spinner("Running identical-start-date lump-sum and DCA scenarios..."):
                        asset, fx, _ = _load_asset_bundle(
                            api_key=api_key,
                            symbol=symbol,
                            asset_currency=asset_currency,
                            fx_symbol=fx_symbol,
                            start_date=start_date,
                            refresh=refresh,
                        )
                        results = rolling_dca_backtest(
                            asset,
                            fx_daily=fx,
                            config=dca_config,
                            broker=broker,
                            step_months=step_months,
                        )
                        summary = summarize_dca(results)
                except (ValueError, MarketDataError, OSError) as exc:
                    st.error(f"Could not run the DCA analysis: {exc}")
                else:
                    if fx is None:
                        latest_fx = 1.0
                    else:
                        latest_fx = float(prior_fx_close(asset.index, fx).iloc[-1])
                    current_estimate = execute_buy(
                        float(dca_capital),
                        asset_price=float(asset["close"].iloc[-1]),
                        sgd_per_trade_currency=latest_fx,
                        config=broker,
                    )

                    lump_row = summary.loc[summary["deployment_months"] == 1].iloc[0]
                    non_lump = summary.loc[summary["deployment_months"] > 1]
                    best_row = summary.loc[summary["median_ending_wealth_sgd"].idxmax()]

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Historical start windows", f"{int(lump_row['scenarios']):,}")
                    m2.metric("Lump-sum median ending", _money(float(lump_row["median_ending_wealth_sgd"])))
                    m3.metric("Highest median strategy", str(best_row["strategy"]))
                    m4.metric("Current full-deployment fee estimate", _money(current_estimate.total_fees_sgd))

                    st.caption(
                        "The fee estimate uses the latest loaded price/FX rate only to illustrate the selected brokerage settings. "
                        "Each historical scenario uses the rate and price from its own purchase dates."
                    )

                    display = summary.copy()
                    display["Median ending wealth"] = display["median_ending_wealth_sgd"].map(_money)
                    display["10th percentile ending"] = display["p10_ending_wealth_sgd"].map(_money)
                    display["Median fees"] = display["median_fees_sgd"].map(_money)
                    display["Median vs lump sum"] = display["median_delta_vs_lump_sum_sgd"].map(
                        lambda value: f"S${value:+,.0f}"
                    )
                    display["Win rate vs lump sum"] = display["win_rate_vs_lump_sum"].map(
                        lambda value: "Baseline" if pd.isna(value) else f"{value:.0%}"
                    )
                    st.dataframe(
                        display[
                            [
                                "strategy",
                                "Median ending wealth",
                                "10th percentile ending",
                                "Median vs lump sum",
                                "Win rate vs lump sum",
                                "Median fees",
                            ]
                        ].rename(columns={"strategy": "Strategy"}),
                        hide_index=True,
                        use_container_width=True,
                    )

                    order = summary.sort_values("deployment_months")["strategy"].tolist()
                    box = px.box(
                        results,
                        x="strategy",
                        y="ending_wealth_sgd",
                        category_orders={"strategy": order},
                        points=False,
                        labels={"strategy": "Deployment", "ending_wealth_sgd": "Ending wealth (SGD)"},
                        title=f"{dca_horizon}-year ending wealth across historical start dates",
                    )
                    st.plotly_chart(box, use_container_width=True)

                    if not non_lump.empty:
                        relative = non_lump[["strategy", "median_delta_vs_lump_sum_sgd"]].copy()
                        relative_chart = px.bar(
                            relative,
                            x="strategy",
                            y="median_delta_vs_lump_sum_sgd",
                            category_orders={"strategy": order},
                            labels={
                                "strategy": "Deployment",
                                "median_delta_vs_lump_sum_sgd": "Median ending difference vs lump sum (SGD)",
                            },
                            title="Median historical cost or benefit of delaying deployment",
                        )
                        st.plotly_chart(relative_chart, use_container_width=True)

                    st.markdown("#### Model boundaries")
                    st.markdown(
                        f"- IBKR presets are based on the Singapore commission schedule checked {IBKR_FEE_SCHEDULE_AS_OF}; use the override if the schedule changes.\n"
                        "- Tiered venue, exchange and clearing charges vary by execution venue; the extra-bps field is intentionally user-configurable.\n"
                        "- Buy-side commissions and SGD-to-USD conversion costs are modelled. Taxes, bid/ask spread, market impact and eventual selling costs are not.\n"
                        "- Fractional units are allowed so equal SGD tranches can be compared without whole-share rounding noise.\n"
                        "- Undeployed capital earns only the cash yield you enter.\n"
                        "- Historical outcomes measure what happened in prior market/FX paths; they are not a forecast of the next deployment period."
                    )
