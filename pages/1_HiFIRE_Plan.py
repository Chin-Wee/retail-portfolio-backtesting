from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from retail_sp500.lifeplan import (
    AgeBand,
    CarPlan,
    ChildPlan,
    HousingPlan,
    LifePlanConfig,
    OneOffExpense,
    life_plan_summary,
    monthly_amortized_payment,
    project_life_plan,
)


st.set_page_config(page_title="Singapore HiFIRE Plan", page_icon="📈", layout="wide")


def _money(value: float) -> str:
    return f"S${value:,.0f}"


def _age_phases(start_age: int, end_age_exclusive: int) -> list[tuple[int, int]]:
    return [
        (start, min(start + 4, end_age_exclusive - 1))
        for start in range(start_age, end_age_exclusive, 5)
    ]


st.title("Singapore HiFIRE Life Plan")
st.caption(
    "Plan salary, living costs, HDB/BTO, car, children and major expenses on one FIRE timeline. "
    "This is an educational projection, not personalised financial advice."
)

st.markdown("### 1. FIRE goal and current position")
g1, g2, g3 = st.columns(3)
with g1:
    current_age = int(st.slider("Current age", 18, 55, 25, 1, key="hf_current_age"))
    target_fire_age = int(
        st.slider(
            "Target FIRE age",
            current_age + 3,
            70,
            min(max(current_age + 15, 40), 70),
            1,
            key="hf_fire_age",
        )
    )
    minimum_end = target_fire_age + 10
    default_end = min(max(target_fire_age + 40, 85), 100)
    end_age = int(
        st.slider("Plan until age", minimum_end, 100, default_end, 1, key="hf_end_age")
    )
with g2:
    current_cash = float(
        st.number_input("Current cash", 0.0, value=20_000.0, step=5_000.0, format="%.0f", key="hf_cash")
    )
    current_investments = float(
        st.number_input(
            "Current liquid investments",
            0.0,
            value=100_000.0,
            step=10_000.0,
            format="%.0f",
            key="hf_investments",
        )
    )
    expected_return = float(
        st.slider("Expected investment return (% p.a.)", -2.0, 12.0, 6.0, 0.25, key="hf_return")
    )
with g3:
    retirement_spend = float(
        st.slider(
            "Desired retirement spending / month (today's SGD)",
            1_000,
            30_000,
            8_000,
            250,
            key="hf_retirement_spend",
        )
    )
    withdrawal_rate = float(
        st.slider("Planning withdrawal rate (%)", 2.0, 6.0, 3.5, 0.1, key="hf_withdrawal")
    )
    inflation = float(
        st.slider("Living-cost inflation (% p.a.)", 0.0, 8.0, 2.5, 0.25, key="hf_inflation")
    )

p1, p2, p3 = st.columns(3)
with p1:
    emergency_months = float(st.slider("Emergency fund (months)", 0, 18, 6, 1, key="hf_emergency"))
with p2:
    cpf_enabled = st.checkbox(
        "Apply current-rule CPF employee deductions",
        True,
        key="hf_cpf",
        help="Uses the app's current 2026 planning table. Future CPF policy is not predicted.",
    )
with p3:
    stop_salary_at_fire = st.checkbox(
        "Stop salary at target FIRE age",
        True,
        key="hf_stop_salary",
        help="If disabled, additional salary sliders are shown through age 69 or the plan end, whichever comes first.",
    )

st.markdown("### 2. Expected salary over time")
st.caption("Set expected nominal gross monthly salary directly for each five-year age band.")
salary_end_age = target_fire_age if stop_salary_at_fire else min(end_age, 70)
salary_bands: list[AgeBand] = []
for index, (start, end) in enumerate(_age_phases(current_age, salary_end_age)):
    default_salary = min(5_000 + index * 2_000, 25_000)
    salary = float(
        st.slider(
            f"Age {start}-{end}: expected gross monthly salary",
            0,
            50_000,
            default_salary,
            1_000,
            key=f"hf_salary_{start}",
        )
    )
    salary_bands.append(AgeBand(start, end, salary))

st.markdown("### 3. Living expenses before FIRE")
st.caption("Living expenses are entered in today's SGD and inflated automatically.")
living_bands: list[AgeBand] = []
for index, (start, end) in enumerate(_age_phases(current_age, target_fire_age)):
    default_living = min(2_500 + index * 500, 8_000)
    living = float(
        st.slider(
            f"Age {start}-{end}: monthly living expenses (today's SGD)",
            0,
            20_000,
            default_living,
            250,
            key=f"hf_living_{start}",
        )
    )
    living_bands.append(AgeBand(start, end, living))

st.markdown("### 4. Major Singapore life commitments")

with st.expander("HDB / BTO housing", expanded=True):
    housing_enabled = st.checkbox("Include an HDB / BTO purchase", True, key="hf_housing_enabled")
    if housing_enabled:
        h1, h2, h3 = st.columns(3)
        with h1:
            housing_age = int(
                st.slider(
                    "Purchase / key-collection age",
                    current_age,
                    min(end_age - 1, 70),
                    min(max(current_age + 5, 30), min(end_age - 1, 70)),
                    1,
                    key="hf_housing_age",
                )
            )
            housing_price = float(
                st.slider("Flat purchase price", 100_000, 2_000_000, 600_000, 25_000, key="hf_housing_price")
            )
            downpayment_pct = float(
                st.slider(
                    "Planning equity / downpayment (%)",
                    0,
                    100,
                    25,
                    1,
                    key="hf_housing_dp",
                    help="25% is the planning default derived from the current 75% maximum HDB-loan LTV.",
                )
            )
        with h2:
            housing_rate = float(
                st.slider("Housing loan interest (% p.a.)", 0.0, 8.0, 2.6, 0.1, key="hf_housing_rate")
            )
            housing_years = int(st.slider("Housing loan tenure (years)", 5, 25, 25, 1, key="hf_housing_years"))
            property_running = float(
                st.slider(
                    "Monthly property running cost (today's SGD)",
                    0,
                    5_000,
                    500,
                    100,
                    key="hf_property_running",
                )
            )
        with h3:
            cash_dp_pct = float(
                st.slider(
                    "Downpayment paid from cash (%)",
                    0,
                    100,
                    100,
                    5,
                    key="hf_cash_dp",
                    help="The remainder is reported as CPF-funded. OA balance sufficiency is not modelled in v1.",
                )
            )
            cash_instalment_pct = float(
                st.slider(
                    "Monthly instalment paid from cash (%)",
                    0,
                    100,
                    100,
                    5,
                    key="hf_cash_instalment",
                    help="Lower this only if you intend CPF OA to fund the remainder.",
                )
            )
        housing = HousingPlan(
            enabled=True,
            purchase_age=housing_age,
            purchase_price=housing_price,
            downpayment_fraction=downpayment_pct / 100.0,
            annual_interest_rate=housing_rate / 100.0,
            loan_years=housing_years,
            cash_downpayment_fraction=cash_dp_pct / 100.0,
            cash_installment_fraction=cash_instalment_pct / 100.0,
            monthly_running_cost_today=property_running,
        )
        full_payment = monthly_amortized_payment(
            housing.loan_principal, housing.annual_interest_rate, housing.loan_years
        )
        hm1, hm2, hm3 = st.columns(3)
        hm1.metric("Planning loan", _money(housing.loan_principal))
        hm2.metric("Full monthly instalment", _money(full_payment))
        hm3.metric("Cash monthly instalment", _money(full_payment * housing.cash_installment_fraction))
        st.caption(
            "Planning references checked 17 Aug 2026: HDB loan LTV up to 75%; HDB concessionary rate 2.6% p.a. for Jul-Sep 2026."
        )
    else:
        housing = HousingPlan()

with st.expander("Car", expanded=False):
    car_enabled = st.checkbox("Include a car purchase", False, key="hf_car_enabled")
    if car_enabled:
        c1, c2, c3 = st.columns(3)
        with c1:
            car_age = int(
                st.slider(
                    "Car purchase age",
                    current_age,
                    min(end_age - 1, 75),
                    min(current_age + 7, min(end_age - 1, 75)),
                    1,
                    key="hf_car_age",
                )
            )
            car_price = float(st.slider("Car purchase price", 20_000, 500_000, 120_000, 5_000, key="hf_car_price"))
            car_dp_pct = float(st.slider("Car downpayment (%)", 0, 100, 40, 5, key="hf_car_dp"))
        with c2:
            car_rate = float(st.slider("Car flat interest rate (% p.a.)", 0.0, 10.0, 2.5, 0.1, key="hf_car_rate"))
            car_loan_years = int(st.slider("Car loan tenure (years)", 1, 10, 7, 1, key="hf_car_loan_years"))
            car_ownership = int(st.slider("Ownership period (years)", 1, 20, 10, 1, key="hf_car_ownership"))
        with c3:
            car_running = float(
                st.slider("Monthly car running cost (today's SGD)", 0, 5_000, 1_000, 100, key="hf_car_running")
            )
            car_resale = float(
                st.number_input("Resale value at end", 0.0, value=0.0, step=5_000.0, format="%.0f", key="hf_car_resale")
            )
        car = CarPlan(
            enabled=True,
            purchase_age=car_age,
            purchase_price=car_price,
            downpayment_fraction=car_dp_pct / 100.0,
            flat_annual_interest_rate=car_rate / 100.0,
            loan_years=car_loan_years,
            monthly_running_cost_today=car_running,
            ownership_years=car_ownership,
            resale_value=car_resale,
        )
    else:
        car = CarPlan()

with st.expander("Children", expanded=False):
    child_count = int(st.slider("Number of children", 0, 3, 0, 1, key="hf_child_count"))
    children: list[ChildPlan] = []
    for child_index in range(child_count):
        st.markdown(f"**Child {child_index + 1}**")
        ch1, ch2, ch3 = st.columns(3)
        with ch1:
            birth_age = int(
                st.slider(
                    "Your age when child is born",
                    current_age,
                    min(end_age - 1, 65),
                    min(current_age + 7 + child_index * 2, min(end_age - 1, 65)),
                    1,
                    key=f"hf_child_birth_{child_index}",
                )
            )
            monthly_support = float(
                st.slider(
                    "Monthly support cost (today's SGD)",
                    0,
                    10_000,
                    1_000,
                    100,
                    key=f"hf_child_monthly_{child_index}",
                )
            )
        with ch2:
            support_years = int(st.slider("Years of monthly support", 0, 30, 21, 1, key=f"hf_child_years_{child_index}"))
            education_age = int(
                st.slider("Child age for education lump sum", 0, 30, 18, 1, key=f"hf_child_education_age_{child_index}")
            )
        with ch3:
            education_fund = float(
                st.number_input(
                    "Education lump sum",
                    0.0,
                    value=0.0,
                    step=10_000.0,
                    format="%.0f",
                    key=f"hf_child_education_{child_index}",
                )
            )
        children.append(
            ChildPlan(
                label=f"Child {child_index + 1}",
                birth_age=birth_age,
                monthly_support_today=monthly_support,
                support_years=support_years,
                education_lump_sum=education_fund,
                education_child_age=education_age,
            )
        )

with st.expander("Other big-ticket expenses", expanded=False):
    event_count = int(st.slider("Number of other one-off expenses", 0, 5, 0, 1, key="hf_event_count"))
    one_offs: list[OneOffExpense] = []
    for event_index in range(event_count):
        e1, e2, e3 = st.columns(3)
        with e1:
            label = st.text_input(
                "Expense label", f"Big-ticket expense {event_index + 1}", key=f"hf_event_label_{event_index}"
            )
        with e2:
            event_age = int(
                st.slider(
                    "Your age when paid",
                    current_age,
                    end_age - 1,
                    min(current_age + 5 + event_index * 3, end_age - 1),
                    1,
                    key=f"hf_event_age_{event_index}",
                )
            )
        with e3:
            event_amount = float(
                st.number_input(
                    "Future SGD amount",
                    0.0,
                    value=20_000.0,
                    step=5_000.0,
                    format="%.0f",
                    key=f"hf_event_amount_{event_index}",
                )
            )
        one_offs.append(OneOffExpense(label, event_age, event_amount))

st.markdown("### 5. Projection")
if st.button("Run HiFIRE life plan", type="primary", key="hf_run"):
    try:
        config = LifePlanConfig(
            start_age=current_age,
            target_fire_age=target_fire_age,
            end_age=end_age,
            current_cash=current_cash,
            current_investments=current_investments,
            salary_bands=tuple(salary_bands),
            living_expense_bands=tuple(living_bands),
            annual_investment_return=expected_return / 100.0,
            annual_inflation=inflation / 100.0,
            retirement_monthly_spend_today=retirement_spend,
            withdrawal_rate=withdrawal_rate / 100.0,
            emergency_months=emergency_months,
            cpf_enabled=cpf_enabled,
            stop_salary_at_fire=stop_salary_at_fire,
            housing=housing,
            car=car,
            children=tuple(children),
            one_off_expenses=tuple(one_offs),
        )
        path = project_life_plan(config)
        summary = life_plan_summary(path, config)
    except ValueError as exc:
        st.error(f"Could not project this plan: {exc}")
    else:
        if bool(summary["on_track"]):
            st.success("ON TRACK for the configured deterministic assumptions")
        else:
            st.warning("NOT ON TRACK for the configured deterministic assumptions")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Liquid wealth at FIRE age", _money(float(summary["target_liquid_wealth"])))
        m2.metric("FIRE number", _money(float(summary["target_fire_number"])))
        m3.metric("Gap / surplus", _money(float(summary["target_gap"])))
        m4.metric("FIRE funding ratio", f"{float(summary['target_fire_ratio']):.0%}")
        m5.metric("Plan-end liquid wealth", _money(float(summary["ending_liquid_wealth"])))

        first_cross = summary["first_fire_cross_age"]
        if first_cross is not None:
            st.caption(f"Projected liquid wealth first crosses the base FIRE number around age {float(first_cross):.1f}.")

        chart = path[["age", "liquid_net_worth", "fire_target"]].melt(
            id_vars="age", var_name="series", value_name="SGD"
        )
        chart["series"] = chart["series"].map(
            {"liquid_net_worth": "Projected liquid wealth", "fire_target": "FIRE number"}
        )
        st.plotly_chart(
            px.line(chart, x="age", y="SGD", color="series", labels={"age": "Age", "series": "", "SGD": "SGD"}),
            use_container_width=True,
        )

        annual = (
            path.assign(
                housing_cash=path["housing_downpayment_cash"] + path["housing_installment_cash"] + path["housing_running_cost"],
                car_cash=path["car_downpayment"] + path["car_loan_payment"] + path["car_running_cost"] - path["car_resale_proceeds"],
                child_cash=path["child_support"] + path["child_education"],
            )
            .groupby("age_year", as_index=False)
            .agg(
                gross_salary=("gross_salary", "mean"),
                living=("living_expenses", "sum"),
                housing=("housing_cash", "sum"),
                car=("car_cash", "sum"),
                children=("child_cash", "sum"),
                other_one_off=("one_off_expenses", "sum"),
                liquid_net_worth=("liquid_net_worth", "last"),
                fire_target=("fire_target", "last"),
            )
        )
        st.dataframe(annual.round(0), hide_index=True, use_container_width=True)

        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Housing paid from cash", _money(float(summary["total_housing_cash"])))
        t2.metric("Housing reported CPF-funded", _money(float(summary["total_housing_cpf"])))
        t3.metric("Net car cash cost", _money(float(summary["total_car_cost"])))
        t4.metric("Child costs", _money(float(summary["total_child_cost"])))

        if bool(summary["had_unfunded_shortfall"]):
            st.error("At least one month remains unfunded even after selling available liquid investments.")
        elif bool(summary["had_liquidity_stress"]):
            st.warning("At least one month requires selling investments to meet cash commitments.")

        with st.expander("Model boundaries and Singapore assumptions"):
            st.markdown(
                "- Deterministic expected-return projection; use Auto Strategy for historical investment-strategy testing.\n"
                "- HDB defaults checked 17 Aug 2026: HDB-loan LTV up to 75%; concessionary rate 2.6% p.a. for Jul-Sep 2026.\n"
                "- CPF OA can fund eligible housing payments, but v1 does not model OA balance sufficiency.\n"
                "- CPF deductions use the app's current 2026 planning table; future policy is not predicted.\n"
                "- FIRE wealth excludes CPF balances, home equity and car value.\n"
                "- Income tax, insurance, SRS, CPF LIFE, housing grants, exact BTO milestones, childcare subsidies and Monte Carlo sequence risk are deferred."
            )
