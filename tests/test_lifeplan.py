from __future__ import annotations

import pytest

from retail_sp500.lifeplan import (
    AgeBand,
    CarPlan,
    ChildPlan,
    HousingPlan,
    LifePlanConfig,
    OneOffExpense,
    life_plan_summary,
    monthly_amortized_payment,
    monthly_flat_rate_payment,
    project_life_plan,
)


def _config(**overrides: object) -> LifePlanConfig:
    values: dict[str, object] = {
        "start_age": 25,
        "target_fire_age": 35,
        "end_age": 45,
        "current_cash": 10_000.0,
        "current_investments": 100_000.0,
        "salary_bands": (AgeBand(25, 29, 5_000.0), AgeBand(30, 34, 8_000.0)),
        "living_expense_bands": (AgeBand(25, 29, 2_000.0), AgeBand(30, 34, 3_000.0)),
        "annual_investment_return": 0.0,
        "annual_inflation": 0.0,
        "retirement_monthly_spend_today": 3_000.0,
        "withdrawal_rate": 0.04,
        "emergency_months": 0.0,
        "cpf_enabled": False,
        "stop_salary_at_fire": True,
    }
    values.update(overrides)
    return LifePlanConfig(**values)


def test_salary_bands_change_and_salary_stops_at_fire_age() -> None:
    path = project_life_plan(_config())

    assert path.loc[path["age_year"] == 25, "gross_salary"].iloc[0] == pytest.approx(5_000.0)
    assert path.loc[path["age_year"] == 30, "gross_salary"].iloc[0] == pytest.approx(8_000.0)
    assert path.loc[path["age"] >= 35, "gross_salary"].max() == pytest.approx(0.0)


def test_hdb_monthly_rest_payment_matches_formula() -> None:
    payment = monthly_amortized_payment(300_000.0, 0.026, 25)
    monthly_rate = 0.026 / 12.0
    expected = 300_000.0 * monthly_rate / (1.0 - (1.0 + monthly_rate) ** (-25 * 12))
    assert payment == pytest.approx(expected)


def test_housing_cash_and_cpf_shares_cover_downpayment_and_installment() -> None:
    housing = HousingPlan(
        enabled=True,
        purchase_age=25,
        purchase_price=400_000.0,
        downpayment_fraction=0.25,
        annual_interest_rate=0.026,
        loan_years=25,
        cash_downpayment_fraction=0.40,
        cash_installment_fraction=0.60,
    )
    config = _config(
        current_cash=500_000.0,
        current_investments=0.0,
        salary_bands=(),
        living_expense_bands=(),
        housing=housing,
    )
    path = project_life_plan(config)
    first = path.iloc[0]
    payment = monthly_amortized_payment(housing.loan_principal, 0.026, 25)

    assert first["housing_downpayment_cash"] + first["housing_downpayment_cpf"] == pytest.approx(
        housing.equity
    )
    assert first["housing_installment_cash"] + first["housing_installment_cpf"] == pytest.approx(
        payment
    )
    assert first["housing_downpayment_cash"] == pytest.approx(40_000.0)
    assert first["housing_installment_cash"] == pytest.approx(payment * 0.60)


def test_car_flat_rate_payment_and_running_cost() -> None:
    car = CarPlan(
        enabled=True,
        purchase_age=25,
        purchase_price=100_000.0,
        downpayment_fraction=0.40,
        flat_annual_interest_rate=0.025,
        loan_years=5,
        monthly_running_cost_today=500.0,
        ownership_years=7,
    )
    config = _config(
        current_cash=200_000.0,
        current_investments=0.0,
        salary_bands=(),
        living_expense_bands=(),
        car=car,
    )
    path = project_life_plan(config)
    first = path.iloc[0]
    expected_payment = monthly_flat_rate_payment(60_000.0, 0.025, 5)

    assert first["car_downpayment"] == pytest.approx(40_000.0)
    assert first["car_loan_payment"] == pytest.approx(expected_payment)
    assert first["car_running_cost"] == pytest.approx(500.0)


def test_child_support_education_and_one_off_occur_on_schedule() -> None:
    child = ChildPlan(
        label="Child 1",
        birth_age=27,
        monthly_support_today=1_000.0,
        support_years=2,
        education_lump_sum=20_000.0,
        education_child_age=1,
    )
    config = _config(
        current_cash=100_000.0,
        current_investments=0.0,
        salary_bands=(),
        living_expense_bands=(),
        children=(child,),
        one_off_expenses=(OneOffExpense("Renovation", 28, 30_000.0),),
    )
    path = project_life_plan(config)

    assert path.loc[path["month"] == 24, "child_support"].iloc[0] == pytest.approx(1_000.0)
    assert path.loc[path["month"] == 35, "child_support"].iloc[0] == pytest.approx(1_000.0)
    assert path.loc[path["month"] == 36, "child_education"].iloc[0] == pytest.approx(20_000.0)
    assert path.loc[path["month"] == 36, "one_off_expenses"].iloc[0] == pytest.approx(30_000.0)
    assert path.loc[path["month"] == 48, "child_support"].iloc[0] == pytest.approx(0.0)


def test_fire_summary_uses_liquid_wealth_and_reports_target_gap() -> None:
    config = _config(
        current_cash=0.0,
        current_investments=2_000_000.0,
        salary_bands=(),
        living_expense_bands=(),
        retirement_monthly_spend_today=4_000.0,
        withdrawal_rate=0.04,
    )
    path = project_life_plan(config)
    summary = life_plan_summary(path, config)

    assert summary["target_fire_number"] == pytest.approx(1_200_000.0)
    assert summary["target_liquid_wealth"] >= 1_200_000.0
    assert summary["target_gap"] >= 0.0
    assert summary["on_track"] is True


def test_unfunded_expense_is_not_silently_hidden() -> None:
    config = _config(
        current_cash=0.0,
        current_investments=10_000.0,
        salary_bands=(),
        living_expense_bands=(),
        one_off_expenses=(OneOffExpense("Large commitment", 26, 50_000.0),),
    )
    path = project_life_plan(config)
    summary = life_plan_summary(path, config)

    assert (path["unfunded_shortfall"] > 0.0).any()
    assert summary["had_unfunded_shortfall"] is True
    assert summary["on_track"] is False
