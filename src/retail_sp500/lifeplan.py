from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .planner import monthly_budget


@dataclass(frozen=True)
class AgeBand:
    """A monthly amount that applies for inclusive planner ages."""

    start_age: int
    end_age: int
    monthly_amount: float

    def __post_init__(self) -> None:
        if self.start_age < 16 or self.end_age < self.start_age:
            raise ValueError("age band must have a valid age range")
        if self.monthly_amount < 0.0:
            raise ValueError("age-band amount cannot be negative")

    def contains(self, age: int) -> bool:
        return self.start_age <= age <= self.end_age


@dataclass(frozen=True)
class HousingPlan:
    enabled: bool = False
    purchase_age: int = 30
    purchase_price: float = 500_000.0
    downpayment_fraction: float = 0.25
    annual_interest_rate: float = 0.026
    loan_years: int = 25
    cash_downpayment_fraction: float = 1.0
    cash_installment_fraction: float = 1.0
    monthly_running_cost_today: float = 0.0

    def __post_init__(self) -> None:
        if self.purchase_age < 16:
            raise ValueError("housing purchase age is invalid")
        if self.purchase_price < 0.0 or self.monthly_running_cost_today < 0.0:
            raise ValueError("housing amounts cannot be negative")
        for value, name in [
            (self.downpayment_fraction, "downpayment_fraction"),
            (self.cash_downpayment_fraction, "cash_downpayment_fraction"),
            (self.cash_installment_fraction, "cash_installment_fraction"),
        ]:
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if self.annual_interest_rate < 0.0:
            raise ValueError("housing interest rate cannot be negative")
        if self.loan_years < 1:
            raise ValueError("housing loan years must be positive")

    @property
    def equity(self) -> float:
        return self.purchase_price * self.downpayment_fraction

    @property
    def loan_principal(self) -> float:
        return max(self.purchase_price - self.equity, 0.0)


@dataclass(frozen=True)
class CarPlan:
    enabled: bool = False
    purchase_age: int = 32
    purchase_price: float = 120_000.0
    downpayment_fraction: float = 0.40
    flat_annual_interest_rate: float = 0.025
    loan_years: int = 7
    monthly_running_cost_today: float = 0.0
    ownership_years: int = 10
    resale_value: float = 0.0

    def __post_init__(self) -> None:
        if self.purchase_age < 16:
            raise ValueError("car purchase age is invalid")
        if min(
            self.purchase_price,
            self.monthly_running_cost_today,
            self.resale_value,
            self.flat_annual_interest_rate,
        ) < 0.0:
            raise ValueError("car amounts and rates cannot be negative")
        if not 0.0 <= self.downpayment_fraction <= 1.0:
            raise ValueError("car downpayment_fraction must be between 0 and 1")
        if self.loan_years < 1 or self.ownership_years < 1:
            raise ValueError("car loan and ownership years must be positive")

    @property
    def downpayment(self) -> float:
        return self.purchase_price * self.downpayment_fraction

    @property
    def loan_principal(self) -> float:
        return max(self.purchase_price - self.downpayment, 0.0)


@dataclass(frozen=True)
class ChildPlan:
    label: str = "Child"
    birth_age: int = 32
    monthly_support_today: float = 0.0
    support_years: int = 21
    education_lump_sum: float = 0.0
    education_child_age: int = 18

    def __post_init__(self) -> None:
        if self.birth_age < 16:
            raise ValueError("child birth age is invalid")
        if min(self.monthly_support_today, self.education_lump_sum) < 0.0:
            raise ValueError("child costs cannot be negative")
        if self.support_years < 0 or self.education_child_age < 0:
            raise ValueError("child ages and durations cannot be negative")


@dataclass(frozen=True)
class OneOffExpense:
    label: str
    age: int
    amount: float

    def __post_init__(self) -> None:
        if self.age < 16:
            raise ValueError("one-off expense age is invalid")
        if self.amount < 0.0:
            raise ValueError("one-off expense amount cannot be negative")


@dataclass(frozen=True)
class LifePlanConfig:
    start_age: int = 25
    target_fire_age: int = 45
    end_age: int = 90
    current_cash: float = 20_000.0
    current_investments: float = 100_000.0
    salary_bands: tuple[AgeBand, ...] = field(default_factory=tuple)
    living_expense_bands: tuple[AgeBand, ...] = field(default_factory=tuple)
    annual_investment_return: float = 0.06
    annual_inflation: float = 0.025
    retirement_monthly_spend_today: float = 6_000.0
    withdrawal_rate: float = 0.035
    emergency_months: float = 6.0
    cpf_enabled: bool = True
    stop_salary_at_fire: bool = True
    housing: HousingPlan = field(default_factory=HousingPlan)
    car: CarPlan = field(default_factory=CarPlan)
    children: tuple[ChildPlan, ...] = field(default_factory=tuple)
    one_off_expenses: tuple[OneOffExpense, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.start_age < 16:
            raise ValueError("start_age must be at least 16")
        if self.target_fire_age <= self.start_age:
            raise ValueError("target_fire_age must be above start_age")
        if self.end_age <= self.target_fire_age:
            raise ValueError("end_age must be above target_fire_age")
        if min(
            self.current_cash,
            self.current_investments,
            self.retirement_monthly_spend_today,
            self.emergency_months,
        ) < 0.0:
            raise ValueError("cash, investments, spending and emergency months cannot be negative")
        if self.annual_investment_return <= -1.0 or self.annual_inflation <= -1.0:
            raise ValueError("annual return and inflation must be greater than -100%")
        if not 0.0 < self.withdrawal_rate <= 1.0:
            raise ValueError("withdrawal_rate must be between 0 and 1")


def monthly_amortized_payment(principal: float, annual_rate: float, years: int) -> float:
    """Monthly-rest amortising loan payment."""

    if principal < 0.0 or annual_rate < 0.0 or years < 1:
        raise ValueError("loan principal/rate/years are invalid")
    if principal == 0.0:
        return 0.0
    months = years * 12
    monthly_rate = annual_rate / 12.0
    if monthly_rate == 0.0:
        return principal / months
    return principal * monthly_rate / (1.0 - (1.0 + monthly_rate) ** (-months))


def monthly_flat_rate_payment(principal: float, annual_flat_rate: float, years: int) -> float:
    """Monthly payment when interest is charged as a flat rate on original principal."""

    if principal < 0.0 or annual_flat_rate < 0.0 or years < 1:
        raise ValueError("loan principal/rate/years are invalid")
    if principal == 0.0:
        return 0.0
    total = principal * (1.0 + annual_flat_rate * years)
    return total / (years * 12)


def _band_amount(bands: tuple[AgeBand, ...], age: int) -> float:
    matches = [band.monthly_amount for band in bands if band.contains(age)]
    if len(matches) > 1:
        raise ValueError(f"overlapping age bands at age {age}")
    return float(matches[0]) if matches else 0.0


def _event_month(start_age: int, event_age: int) -> int:
    return (event_age - start_age) * 12


def _inflation_factor(config: LifePlanConfig, month_number: int) -> float:
    return (1.0 + config.annual_inflation) ** (month_number / 12.0)


def _housing_values(config: LifePlanConfig, month_number: int, inflation: float) -> dict[str, float]:
    plan = config.housing
    if not plan.enabled:
        return {
            "housing_downpayment_cash": 0.0,
            "housing_downpayment_cpf": 0.0,
            "housing_installment_cash": 0.0,
            "housing_installment_cpf": 0.0,
            "housing_running_cost": 0.0,
        }

    purchase_month = _event_month(config.start_age, plan.purchase_age)
    elapsed = month_number - purchase_month
    cash_downpayment = 0.0
    cpf_downpayment = 0.0
    installment_cash = 0.0
    installment_cpf = 0.0
    running = 0.0

    if month_number == purchase_month:
        cash_downpayment = plan.equity * plan.cash_downpayment_fraction
        cpf_downpayment = plan.equity - cash_downpayment

    if elapsed >= 0:
        running = plan.monthly_running_cost_today * inflation
        if elapsed < plan.loan_years * 12:
            payment = monthly_amortized_payment(
                plan.loan_principal,
                plan.annual_interest_rate,
                plan.loan_years,
            )
            installment_cash = payment * plan.cash_installment_fraction
            installment_cpf = payment - installment_cash

    return {
        "housing_downpayment_cash": cash_downpayment,
        "housing_downpayment_cpf": cpf_downpayment,
        "housing_installment_cash": installment_cash,
        "housing_installment_cpf": installment_cpf,
        "housing_running_cost": running,
    }


def _car_values(config: LifePlanConfig, month_number: int, inflation: float) -> dict[str, float]:
    plan = config.car
    if not plan.enabled:
        return {
            "car_downpayment": 0.0,
            "car_loan_payment": 0.0,
            "car_running_cost": 0.0,
            "car_resale_proceeds": 0.0,
        }

    purchase_month = _event_month(config.start_age, plan.purchase_age)
    elapsed = month_number - purchase_month
    downpayment = plan.downpayment if month_number == purchase_month else 0.0
    loan_payment = 0.0
    running = 0.0
    resale = 0.0

    if 0 <= elapsed < plan.loan_years * 12:
        loan_payment = monthly_flat_rate_payment(
            plan.loan_principal,
            plan.flat_annual_interest_rate,
            plan.loan_years,
        )
    if 0 <= elapsed < plan.ownership_years * 12:
        running = plan.monthly_running_cost_today * inflation
    if elapsed == plan.ownership_years * 12:
        resale = plan.resale_value

    return {
        "car_downpayment": downpayment,
        "car_loan_payment": loan_payment,
        "car_running_cost": running,
        "car_resale_proceeds": resale,
    }


def _child_values(config: LifePlanConfig, month_number: int, inflation: float) -> tuple[float, float]:
    support = 0.0
    education = 0.0
    for child in config.children:
        birth_month = _event_month(config.start_age, child.birth_age)
        elapsed = month_number - birth_month
        if 0 <= elapsed < child.support_years * 12:
            support += child.monthly_support_today * inflation
        education_month = birth_month + child.education_child_age * 12
        if month_number == education_month:
            education += child.education_lump_sum
    return support, education


def _one_off_value(config: LifePlanConfig, month_number: int) -> float:
    return sum(
        event.amount
        for event in config.one_off_expenses
        if month_number == _event_month(config.start_age, event.age)
    )


def project_life_plan(config: LifePlanConfig) -> pd.DataFrame:
    """Project one deterministic Singapore household cash-flow path month by month."""

    months = (config.end_age - config.start_age) * 12
    if months < 1:
        raise ValueError("life plan contains no months")

    monthly_investment_return = (1.0 + config.annual_investment_return) ** (1.0 / 12.0) - 1.0
    cash = float(config.current_cash)
    investments = float(config.current_investments)
    cumulative_invested = float(config.current_investments)
    cumulative_sold = 0.0
    cumulative_employee_cpf = 0.0
    cumulative_employer_cpf = 0.0
    cumulative_housing_cash = 0.0
    cumulative_housing_cpf = 0.0
    cumulative_car_cost = 0.0
    cumulative_child_cost = 0.0
    cumulative_one_off = 0.0
    rows: list[dict[str, object]] = []

    for month_number in range(months):
        age_year = config.start_age + month_number // 12
        age = config.start_age + month_number / 12.0
        inflation = _inflation_factor(config, month_number)

        investments *= 1.0 + monthly_investment_return

        gross_salary = _band_amount(config.salary_bands, age_year)
        if config.stop_salary_at_fire and age >= config.target_fire_age:
            gross_salary = 0.0

        if age >= config.target_fire_age:
            living = config.retirement_monthly_spend_today * inflation
        else:
            living = _band_amount(config.living_expense_bands, age_year) * inflation

        budget = monthly_budget(
            gross_salary,
            0.0,
            age=age_year,
            cpf_enabled=config.cpf_enabled,
        )
        take_home = float(budget["take_home"])
        employee_cpf = float(budget["employee_cpf"])
        employer_cpf = float(budget["employer_cpf"])
        cumulative_employee_cpf += employee_cpf
        cumulative_employer_cpf += employer_cpf

        housing = _housing_values(config, month_number, inflation)
        car = _car_values(config, month_number, inflation)
        child_support, child_education = _child_values(config, month_number, inflation)
        one_off = _one_off_value(config, month_number)

        housing_cash = (
            housing["housing_downpayment_cash"]
            + housing["housing_installment_cash"]
            + housing["housing_running_cost"]
        )
        housing_cpf = housing["housing_downpayment_cpf"] + housing["housing_installment_cpf"]
        car_cost = car["car_downpayment"] + car["car_loan_payment"] + car["car_running_cost"]
        child_cost = child_support + child_education
        recurring_cash_expenses = (
            living
            + housing["housing_installment_cash"]
            + housing["housing_running_cost"]
            + car["car_loan_payment"]
            + car["car_running_cost"]
            + child_support
        )
        event_cash_expenses = (
            housing["housing_downpayment_cash"]
            + car["car_downpayment"]
            + child_education
            + one_off
        )

        cash += (
            take_home
            + car["car_resale_proceeds"]
            - recurring_cash_expenses
            - event_cash_expenses
        )

        cumulative_housing_cash += housing_cash
        cumulative_housing_cpf += housing_cpf
        cumulative_car_cost += car_cost - car["car_resale_proceeds"]
        cumulative_child_cost += child_cost
        cumulative_one_off += one_off

        reserve_target = config.emergency_months * recurring_cash_expenses
        liquidity_stress = cash < 0.0
        sold = 0.0
        invested = 0.0

        if liquidity_stress and investments > 0.0:
            sold = min(investments, -cash)
            investments -= sold
            cash += sold
            cumulative_sold += sold

        unfunded_shortfall = max(-cash, 0.0)

        if cash > reserve_target:
            invested = cash - reserve_target
            investments += invested
            cash = reserve_target
            cumulative_invested += invested

        liquid_net_worth = cash + investments
        fire_target = (
            config.retirement_monthly_spend_today
            * inflation
            * 12.0
            / config.withdrawal_rate
        )
        fire_ratio = liquid_net_worth / fire_target if fire_target > 0.0 else float("inf")

        rows.append(
            {
                "month": month_number,
                "age": age,
                "age_year": age_year,
                "gross_salary": gross_salary,
                "take_home": take_home,
                "employee_cpf": employee_cpf,
                "employer_cpf": employer_cpf,
                "living_expenses": living,
                "housing_downpayment_cash": housing["housing_downpayment_cash"],
                "housing_downpayment_cpf": housing["housing_downpayment_cpf"],
                "housing_installment_cash": housing["housing_installment_cash"],
                "housing_installment_cpf": housing["housing_installment_cpf"],
                "housing_running_cost": housing["housing_running_cost"],
                "car_downpayment": car["car_downpayment"],
                "car_loan_payment": car["car_loan_payment"],
                "car_running_cost": car["car_running_cost"],
                "car_resale_proceeds": car["car_resale_proceeds"],
                "child_support": child_support,
                "child_education": child_education,
                "one_off_expenses": one_off,
                "recurring_cash_expenses": recurring_cash_expenses,
                "event_cash_expenses": event_cash_expenses,
                "reserve_target": reserve_target,
                "cash": cash,
                "invested_this_month": invested,
                "sold_this_month": sold,
                "investments": investments,
                "liquid_net_worth": liquid_net_worth,
                "fire_target": fire_target,
                "fire_ratio": fire_ratio,
                "liquidity_stress": liquidity_stress,
                "unfunded_shortfall": unfunded_shortfall,
                "cumulative_invested": cumulative_invested,
                "cumulative_sold": cumulative_sold,
                "cumulative_employee_cpf": cumulative_employee_cpf,
                "cumulative_employer_cpf": cumulative_employer_cpf,
                "cumulative_housing_cash": cumulative_housing_cash,
                "cumulative_housing_cpf": cumulative_housing_cpf,
                "cumulative_car_cost": cumulative_car_cost,
                "cumulative_child_cost": cumulative_child_cost,
                "cumulative_one_off": cumulative_one_off,
            }
        )

    return pd.DataFrame.from_records(rows)


def life_plan_summary(path: pd.DataFrame, config: LifePlanConfig) -> dict[str, float | bool | None]:
    if path.empty:
        raise ValueError("life-plan path cannot be empty")

    target_rows = path.loc[path["age"] >= config.target_fire_age]
    if target_rows.empty:
        raise ValueError("life-plan path does not reach target FIRE age")
    target = target_rows.iloc[0]
    post_fire = path.loc[path["age"] >= config.target_fire_age]
    ending = path.iloc[-1]

    target_wealth = float(target["liquid_net_worth"])
    target_fire_number = float(target["fire_target"])
    target_gap = target_wealth - target_fire_number
    post_fire_unfunded = bool((post_fire["unfunded_shortfall"].astype(float) > 0.0).any())
    on_track = target_gap >= 0.0 and not post_fire_unfunded and float(ending["liquid_net_worth"]) >= 0.0

    crossings = path.loc[path["liquid_net_worth"] >= path["fire_target"]]
    first_cross_age: float | None = None
    if not crossings.empty:
        first_cross_age = float(crossings.iloc[0]["age"])

    housing_payment = 0.0
    housing_loan = 0.0
    if config.housing.enabled:
        housing_loan = config.housing.loan_principal
        housing_payment = monthly_amortized_payment(
            housing_loan,
            config.housing.annual_interest_rate,
            config.housing.loan_years,
        )

    return {
        "on_track": on_track,
        "target_liquid_wealth": target_wealth,
        "target_fire_number": target_fire_number,
        "target_gap": target_gap,
        "target_fire_ratio": float(target["fire_ratio"]),
        "ending_liquid_wealth": float(ending["liquid_net_worth"]),
        "first_fire_cross_age": first_cross_age,
        "had_liquidity_stress": bool(path["liquidity_stress"].any()),
        "had_unfunded_shortfall": bool((path["unfunded_shortfall"].astype(float) > 0.0).any()),
        "post_fire_unfunded_shortfall": post_fire_unfunded,
        "total_invested": float(ending["cumulative_invested"]),
        "total_sold": float(ending["cumulative_sold"]),
        "total_employee_cpf": float(ending["cumulative_employee_cpf"]),
        "total_employer_cpf": float(ending["cumulative_employer_cpf"]),
        "total_housing_cash": float(ending["cumulative_housing_cash"]),
        "total_housing_cpf": float(ending["cumulative_housing_cpf"]),
        "total_car_cost": float(ending["cumulative_car_cost"]),
        "total_child_cost": float(ending["cumulative_child_cost"]),
        "total_one_off": float(ending["cumulative_one_off"]),
        "housing_loan_principal": housing_loan,
        "housing_monthly_payment": housing_payment,
    }
