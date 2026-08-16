from __future__ import annotations

import os
from pathlib import Path
import re

import pandas as pd
import plotly.express as px
import streamlit as st

from retail_sp500.currency import convert_daily_prices
from retail_sp500.data import DEFAULT_START_DATE, MarketDataError, load_market, market_summary
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


st.title("Singapore Money Planner")
st.caption(
    "Stress-test your salary, expenses, emergency fund and monthly investing against real market and FX history. "
    "This is an educational planning tool, not personalised financial advice."
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
            help="Used to convert each historical asset price into Singapore dollars.",
        )
    start_date = st.text_input("History start date", value=DEFAULT_START_DATE)
    default_key = os.getenv("TWELVE_DATA_API_KEY", "") or _secret("TWELVE_DATA_API_KEY")
    api_key = st.text_input("Twelve Data API key", value=default_key, type="password")
    refresh = st.checkbox("Refresh market data", value=False)
    st.caption("The first successful request is cached locally using dividend/split-adjusted daily prices.")

st.subheader("1. Your monthly finances")
left, middle, right = st.columns(3)
with left:
    age = st.number_input("Age", min_value=16, max_value=70, value=25, step=1)
    salary = st.number_input("Gross monthly salary", min_value=0.0, value=5_000.0, step=100.0, format="%.0f")
    expenses = st.number_input("Monthly expenses", min_value=0.0, value=2_000.0, step=100.0, format="%.0f")
with middle:
    current_cash = st.number_input("Current cash", min_value=0.0, value=10_000.0, step=500.0, format="%.0f")
    current_investments = st.number_input(
        "Current investments in this ETF",
        min_value=0.0,
        value=10_000.0,
        step=500.0,
        format="%.0f",
    )
    emergency_months = st.slider("Emergency fund", min_value=0, max_value=12, value=6, step=1)
with right:
    horizon = st.slider("Planning horizon (years)", min_value=3, max_value=15, value=10, step=1)
    salary_growth = st.number_input("Annual salary growth (%)", value=3.0, step=0.5, format="%.1f")
    expense_inflation = st.number_input("Annual expense inflation (%)", value=2.5, step=0.5, format="%.1f")

cpf_enabled = st.checkbox(
    "Apply 2026 CPF employee/employer contribution rules",
    value=True,
    help="Uses the 2026 full-rate CPF table and S$8,000 Ordinary Wage ceiling throughout each scenario.",
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
    st.stop()

b1, b2, b3, b4 = st.columns(4)
b1.metric("Take-home pay", _money(budget["take_home"]))
b2.metric("Monthly surplus", _money(budget["monthly_surplus"]))
b3.metric("Employee CPF", _money(budget["employee_cpf"]))
b4.metric("Employer CPF", _money(budget["employer_cpf"]))

reserve_target = float(emergency_months) * float(expenses)
if budget["monthly_surplus"] < 0:
    st.warning("Your current monthly cash flow is negative before investing. Historical scenarios may require ETF sales to fund expenses.")
elif current_cash < reserve_target:
    st.info(
        f"The model sends your monthly surplus to cash until the emergency fund reaches {_money(reserve_target)}, then invests the excess."
    )
else:
    st.info(f"Cash above the {_money(reserve_target)} emergency-fund target is invested at the next modelled salary session.")

st.subheader("2. Backtest the plan")
st.write(
    "Each scenario applies the same future salary and expense assumptions to a different historical market window. "
    "USD assets are converted with the matching historical USD/SGD series before the plan is simulated."
)

run = st.button("Run historical stress test", type="primary")
if run:
    required_symbols = [symbol.strip()]
    if asset_currency == "USD":
        required_symbols.append(fx_symbol.strip())
    missing_cache = any(item and not _cache_path(item).exists() for item in required_symbols)
    if not api_key and missing_cache:
        st.error("A Twelve Data API key is required for the first download. Add it in the sidebar or set TWELVE_DATA_API_KEY.")
        st.stop()

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
        with st.spinner("Loading market history and running scenarios..."):
            asset = _load_market_cached(api_key, symbol.strip().upper(), start_date, refresh)
            if asset_currency == "USD":
                fx = _load_market_cached(api_key, fx_symbol.strip().upper(), start_date, refresh)
                daily = convert_daily_prices(asset, fx, label="SGD")
            else:
                daily = asset
                daily.attrs["currency"] = "SGD"
            scenarios = rolling_plan_backtest(daily, config=config)
            summary = scenario_summary(scenarios)
    except (ValueError, MarketDataError, OSError) as exc:
        st.error(f"Could not run the backtest: {exc}")
        st.stop()

    source = market_summary(daily, symbol=symbol.strip().upper())
    conversion_note = f", converted through {fx_symbol.strip().upper()}" if asset_currency == "USD" else ""
    st.success(
        f"Loaded {source['sessions']:,} daily sessions for {symbol.strip().upper()} from {source['start']} to {source['end']}{conversion_note}."
    )

    st.subheader("3. Results")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Worst real ending wealth", _money(summary["worst_real_ending"]))
    r2.metric("Median real ending wealth", _money(summary["median_real_ending"]))
    r3.metric("Best real ending wealth", _money(summary["best_real_ending"]))
    r4.metric("Liquidity-stress scenarios", f"{summary['cash_shortfall_rate']:.0%}")

    cpf_total = float(scenarios["total_cpf_contributions"].median())
    st.caption(
        f"Results cover {summary['scenarios']} complete historical start windows. "
        f"Median cumulative CPF contributions (employee + employer) are {_money(cpf_total)}; CPF interest and withdrawals are not modelled."
    )

    chart_data = scenarios[["start", "ending_real_liquid_net_worth"]].copy()
    chart_data["start"] = pd.to_datetime(chart_data["start"])
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

    table = scenarios.copy()
    for column in [
        "ending_cash",
        "ending_portfolio",
        "ending_liquid_net_worth",
        "ending_real_liquid_net_worth",
        "total_cpf_contributions",
        "total_invested",
    ]:
        table[column] = table[column].round(0)
    st.dataframe(
        table[
            [
                "start",
                "end",
                "ending_real_liquid_net_worth",
                "ending_liquid_net_worth",
                "ending_cash",
                "ending_portfolio",
                "total_cpf_contributions",
                "had_cash_shortfall",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Model boundaries")
    st.markdown(
        "- CPF uses the 2026 full-rate age table and S$8,000 Ordinary Wage ceiling for the whole scenario; future policy changes are not predicted.\n"
        "- Twelve Data is requested with dividend and split adjustment enabled. USD assets are converted to SGD using the configured historical FX series.\n"
        "- Cash earns 0%; brokerage fees, taxes, bonuses, income tax, housing and CPF account interest/withdrawals are not modelled.\n"
        "- Current investments are assumed to already be invested in the selected symbol.\n"
        "- Historical outcomes are stress scenarios, not forecasts."
    )
