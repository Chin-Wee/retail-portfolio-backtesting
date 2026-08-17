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


def _age_phases(start_age: int, target_fire_age: int) -> list[tuple[int, int]]:
    phases: list[tuple[int, int]] = []
    for start in range(start_age, target_fire_age, 5):
        phases.append((start, min(start + 4, target_fire_age - 1)))
    return phases


st.title("Singapore HiFIRE Life Plan")
st.caption(
    "Map salary, living costs, HDB, car, children and big-ticket expenses onto one FIRE timeline. "
    "This is an educational planning projection, not personalised financial advice."
)

st.markdown("### 1. Your FIRE target")
goal1, goal2, goal3 = st.columns(3)
with goal1:
    current_age = int(
        st.slider("Current age", min_value=18, max_value=55, value=25, step=1, key="hf_current_age")
    )
    target_fire_age = int(
        st.slider(
            "Target FIRE age",
            min_value=current_age + 3,
            max_value=70,
            value=max(current_age + 15, 40),
            step=1,
            key="hf_fire_age",
        )
    )
    end_age = int(
        st.slider(
            "Plan until age",
            min_value=target_fire_age + 10,
            max_value=100,
            value=max(target_fire_age + 40, 85),
            step=1,
            key="hf_end_age",
        )
    )
with goal2:
    current_cash = float(
        st.number_input(
            "Current cash",
            min_value=0.0,
            value=20_000.0,
            step=5_000.0,
            format="%.0f",
            key="hf_cash",
        )
    )
    current_investments = float(
        st.number_input(
            "Current liquid investments",
            min_value=0.0,
            value=100_000.0,
            step=10_000.0,
            format="%.0f",
            key="hf_investments",
        )
    )
    expected_return = float(
        st.slider(
            "Expected investment return (% p.a.)",
            min_value=-2.0,
            max_value=12.0,
            value=6.0,
            step=0.25,
            key="hf_return",
        )
    )
with goal3:
    retirement_spend = float(
        st.slider(
            "Desired retirement spending / month (today's SGD)",
            min_value=1_000,
            max_value=30_000,
            value=8_000,
            step=250,
            key="hf_retirement_spend",
        )
    )
    withdrawal_rate = float(
        st.slider(
            "Planning withdrawal rate (%)",
            min_value=2.0,
            max_value=6.0,
            value=3.5,
            step=0.1,
            key="hf_withdrawal",
        )
    )
    inflation = float(
        st.slider(
            "Living-cost inflation (% p.a.)",
            min_value=0.0,
            max_value=8.0,
            value=2.5,
            step=0.25,
            key="hf_inflation",
        )
    )

policy1, policy2, policy3 = st.columns(3)
with policy1:
    emergency_months = float(
        st.slider("Emergency fund (months)", 0, 18, 6, 1, key="hf_emergency")
    )
with policy2:
    cpf_enabled = st.checkbox(
        "Apply current-rule CPF employee deductions",
        value=True,
        key="hf_cpf",
        help="Uses the existing 2026 CPF planning table. Future CPF policy is not predicted.",
    )
with policy3:
    stop_salary_at_fire = st.checkbox(
        "Stop salary at target FIRE age",
        value=True,
        key="hf_stop_salary",
    )

st.markdown("### 2. Expected salary and living costs")
st.caption(
    "Set each career phase directly. Salary is the expected nominal gross monthly amount for that age band. "
    "Living expenses are entered in today's SGD and inflated automatically."
)

salary_bands: list[AgeBand] = []
living_bands: list[AgeBand] = []
phases = _age_phases(current_age, target_fire_age)
for index, (start, end) in enumerate(phases):
    left, right = st.columns(2)
    default_salary = min(5_000 + index * 2_000, 25_000)
    default_living = min(2_500 + index * 500, 8_000)
    with left:
        salary = float(
            st.slider(
                f"Age {start}-{end}: expected gross monthly salary",
                min_value=0,
                max_value=50_000,
                value=default_salary,
                step=500,
                key=f"hf_salary_{start}",
            )
        )
    with right:
        living = float(
            st.slider(
                f"Age {start}-{end}: monthly living expenses (today's SGD)",
                min_value=0,
                max_value=20_000,
                value=default_living,
                step=250,
                key=f"hf_living_{start}",
            )
        )
    salary_bands.append(AgeBand(start, end, salary))
    living_bands.append(AgeBand(start, end, living))

st.markdown("### 3. Major Singapore life commitments")

with st.expander("HDB / BTO housing", expanded=True):
    housing_enabled = st.checkbox("Include an HDB / BTO purchase", value=True, key="hf_housing_enabled")
    if housing_enabled:
        h1, h2, h3 = st.columns(3)
        with h1:
            housing_age = int(
                st.slider(
                    "Purchase / key-collection age",
                    min_value=current_age,
                    max_value=min(end_age - 1, 70),
                    value=min(max(current_age + 5, 30), min(end_age - 1, 70)),
                    step=1,
                    key="hf_housing_age",
                )
            )
            housing_price = float(
                st.slider(
                    "Flat purchase price",
                    min_value=100_000,
                    max_value=2_000_000,
                    value=600_000,
                    step=25_000,
                    key="hf_housing_price",
                )
            )
            downpayment_pct = float(
                st.slider(
                    "Planning equity / downpayment (%)",
                    min_value=0,
                    max_value=100,
                    value=25,
                    step=1,
                    key="hf_housing_dp",
                    help="25% is the planning default derived from the current 75% maximum HDB loan LTV. Actual payment milestones can differ.",
                )
            )
        with h2:
            housing_rate = float(
                st.slider(
                    "Housing loan interest (% p.a.)",
                    min_value=0.0,
                    max_value=8.0,
                    value=2.6,
                    step=0.1,
                    key="hf_housing_rate",
                )
            )
            housing_years = int(
                st.slider(
                    "Housing loan tenure (years)",
                    min_value=5,
                    max_value=25,
                    value=25,
                    step=1,
                    key="hf_housing_years",
                )
            )
            property_running = float(
                st.slider(
                    "Monthly property running cost (today's SGD)",
                    min_value=0,
                    max_value=5_000,
                    value=500,
                    step=100,
                    key="hf_property_running",
                )
            )
        with h3:
            cash_dp_pct = float(
                st.slider(
                    "Downpayment paid from cash (%)",
                    min_value=0,
                    max_value=100,
                    value=100,
                    step=5,
                    key="hf_cash_dp",
                    help="The remainder is reported as CPF-funded housing usage. CPF OA balance sufficiency is not modelled in v1.",
                )
            )
            cash_instalment_pct = float(
                st.slider(
                    "Monthly instalment paid from cash (%)",
                    min_value=0,
                    max_value=100,
                    value=100,
                    step=5,
                    key="hf_cash_instalment",
                    help="Lower this only if you intend CPF OA to cover the remainder.",
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
        loan_payment = monthly_amortized_payment(
            housing.loan_principal,
            housing.annual_interest_rate,
            housing.loan_years,
        )
        hm1, hm2, hm3 = st.columns(3)
        hm1.metric("Planning loan", _money(housing.loan_principal))
        hm2.metric("Full monthly instalment", _money(loan_payment))
        hm3.metric("Cash monthly instalment", _money(loan_payment * housing.cash_installment_fraction))
        st.caption(
            "Current planning references: HDB loan LTV up to 75%; HDB concessionary rate 2.6% p.a. for Jul-Sep 2026. "
            "CPF OA can be used for eligible housing payments."
        )
    else:
        housing = HousingPlan()

with st.expander("Car", expanded=False):
    car_enabled = st.checkbox("Include a car purchase", value=False, key="hf_car_enabled")
    if car_enabled:
        c1, c2, c3 = st.columns(3)
        with c1:
            car_age = int(
                st.slider(
                    "Car purchase age",
                    min_value=current_age,
                    max_value=min(end_age - 1, 75),
                    value=min(current_age + 7, min(end_age - 1, 75)),
                    key="hf_car_age",
                )
            )
            car_price = float(
                st.slider(
                    "Car purchase price",
                    min_value=20_000,
                    max_value=500_000,
                    value=120_000,
                    step=5_000,
                    key="hf_car_price",
                )
            )
            car_dp_pct = float(
                st.slider("Car downpayment (%)", 0, 100, 40, 5, key="hf_car_dp")
            )
        with c2:
            car_rate = float(
                st.slider(
                    "Car flat interest rate (% p.a.)",
                    min_value=0.0,
                    max_value=10.0,
                    value=2.5,
                    step=0.1,
                    key="hf_car_rate",
                )
            )
            car_loan_years = int(
                st.slider("Car loan tenure (years)", 1, 10, 7, 1, key="hf_car_loan_years")
            )
            car_ownership = int(
                st.slider("Ownership period (years)", 1, 20, 10, 1, key="hf_car_ownership")
            )
        with c3:
            car_running = float(
                st.slider(
                    "Monthly car running cost (today's SGD)",
                    min_value=0,
                    max_value=5_000,
                    value=1_000,
                    step=100,
                    key="hf_car_running",
                )
            )
            car_resale = float(
                st.number_input(
                    "Resale value at end of ownership",
                    min_value=0.0,
                    value=0.0,
                    step=5_000.0,
                    format="%.0f",
                    key="hf_car_resale",
                )
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
                    min_value=current_age,
                    max_value=min(end_age - 1, 65),
                    value=min(current_age + 7 + child_index * 2, min(end_age - 1, 65)),
                    key=f"hf_child_birth_{child_index}",
                )
            )
            monthly_support = float(
                st.slider(
                    "Monthly support cost (today's SGD)",
                    min_value=0,
                    max_value=10_000,
                    value=1_000,
                    step=100,
                    key=f"hf_child_monthly_{child_index}",
                )
            )
        with ch2:
            support_years = int(
                st.slider(
                    "Years of monthly support",
                    min_value=0,
                    max_value=30,
                    value=21,
                    step=1,
                    key=f"hf_child_years_{child_index}",
                )
            )
            education_age = int(
                st.slider(
                    "Child age for education lump sum",
                    min_value=0,
                    max_value=30,
                    value=18,
                    step=1,
                    key=f"hf_child_education_age_{child_index}",
                )
            )
        with ch3:
            education_fund = float(
                st.number_input(
                    "Education lump sum",
                    min_value=0.0,
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
                "Expense label",
                value=f"Big-ticket expense {event_index + 1}",
                key=f"hf_event_label_{event_index}",
            )
        with e2:
            event_age = int(
                st.slider(
                    "Your age when paid",
                    min_value=current_age,
                    max_value=end_age - 1,
                    value=min(current_age + 5 + event_index * 3, end_age - 1),
                    key=f"hf_event_age_{event_index}",
                )
            )
        with e3:
            event_amount = float(
                st.number_input(
                    "Future SGD amount",
                    min_value=0.0,
                    value=20_000.0,
                    step=5_000.0,
                    format="%.0f",
                    key=f"hf_event_amount_{event_index}",
                )
            )
        one_offs.append(OneOffExpense(label=label, age=event_age, amount=event_amount))

st.markdown("### 4. Projection")
run = st.button("Run HiFIRE life plan", type="primary", key="hf_run")

if run:
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
        status = "ON TRACK" if bool(summary["on_track"]) else "NOT ON TRACK"
        if bool(summary["on_track"]):
            st.success(f"{status} for the configured deterministic assumptions")
        else:
            st.warning(f"{status} for the configured deterministic assumptions")

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Liquid wealth at FIRE age", _money(float(summary["target_liquid_wealth"])))
        m2.metric("FIRE number at target age", _money(float(summary["target_fire_number"])))
        m3.metric("Gap / surplus", _money(float(summary["target_gap"])))
        m4.metric("FIRE funding ratio", f"{float(summary['target_fire_ratio']):.0%}")
        m5.metric("Plan-end liquid wealth", _money(float(summary["ending_liquid_wealth"])))

        first_cross = summary["first_fire_cross_age"]
        if first_cross is not None:
            st.caption(f"The projected liquid portfolio first crosses the base FIRE number around age {float(first_cross):.1f}.")

        chart_data = path[["age", "liquid_net_worth", "fire_target"]].melt(
            id_vars="age",
            var_name="series",
            value_name="SGD",
        )
        chart_data["series"] = chart_data["series"].map(
            {"liquid_net_worth": "Projected liquid wealth", "fire_target": "FIRE number"}
        )
        wealth_chart = px.line(
            chart_data,
            x="age",
            y="SGD",
            color="series",
            labels={"age": "Age", "series": "", "SGD": "SGD"},
            title="Liquid wealth versus FIRE target",
        )
        st.plotly_chart(wealth_chart, use_container_width=True)

        annual = (
            path.assign(
                housing_cash=(
                    path["housing_downpayment_cash"]
                    + path["housing_installment_cash"]
                    + path["housing_running_cost"]
                ),
                car_cash=(
                    path["car_downpayment"]
                    + path["car_loan_payment"]
                    + path["car_running_cost"]
                    - path["car_resale_proceeds"]
                ),
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
                cash=("cash", "last"),
                investments=("investments", "last"),
                liquid_net_worth=("liquid_net_worth", "last"),
                fire_target=("fire_target", "last"),
            )
        )

        expense_chart_data = annual[["age_year", "living", "housing", "car", "children", "other_one_off"]].melt(
            id_vars="age_year",
            var_name="category",
            value_name="annual_cost",
        )
        expense_chart = px.bar(
            expense_chart_data,
            x="age_year",
            y="annual_cost",
            color="category",
            labels={"age_year": "Age", "annual_cost": "Annual cash cost (SGD)", "category": ""},
            title="Annual life-plan cash commitments",
        )
        st.plotly_chart(expense_chart, use_container_width=True)

        st.markdown("#### Major commitment totals")
        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Housing paid from cash", _money(float(summary["total_housing_cash"])))
        t2.metric("Housing reported as CPF-funded", _money(float(summary["total_housing_cpf"])))
        t3.metric("Net car cash cost", _money(float(summary["total_car_cost"])))
        t4.metric("Child costs", _money(float(summary["total_child_cost"])))

        if bool(summary["had_unfunded_shortfall"]):
            st.error(
                "At least one month could not be funded even after selling the available liquid investments. "
                "The plan contains an explicit unfunded shortfall."
            )
        elif bool(summary["had_liquidity_stress"]):
            st.warning("The plan requires selling investments in at least one month to meet cash commitments.")

        st.markdown("#### Annual timeline")
        display = annual.copy()
        for column in [
            "gross_salary",
            "living",
            "housing",
            "car",
            "children",
            "other_one_off",
            "cash",
            "investments",
            "liquid_net_worth",
            "fire_target",
        ]:
            display[column] = display[column].round(0)
        st.dataframe(display, hide_index=True, use_container_width=True)

        with st.expander("Model boundaries and Singapore assumptions"):
            st.markdown(
                "- This page is a deterministic expected-return projection; use the Auto Strategy page for historical investment-strategy testing.\n"
                "- HDB planning defaults were checked 17 Aug 2026: maximum HDB-loan LTV up to 75%, and the concessionary HDB rate is 2.6% p.a. for Jul-Sep 2026.\n"
                "- CPF OA may be used for eligible housing payments, but this v1 does not model an OA account balance or prove that enough OA will be available.\n"
                "- CPF contribution calculations use the app's current 2026 planning table; future CPF rules are not predicted.\n"
                "- Salary assumptions are nominal amounts chosen by you. Pre-retirement living, child and running-cost assumptions are entered in today's SGD and inflated.\n"
                "- The FIRE number excludes CPF balances, home equity and car value.\n"
                "- Singapore income tax, insurance, SRS, CPF LIFE, housing grants, exact BTO payment milestones and childcare subsidies are not yet modelled.\n"
                "- Car financing uses a configurable flat-rate model; no regulatory car-loan limit is assumed."
            )
