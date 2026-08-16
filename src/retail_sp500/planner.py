from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import validate_daily
from .engine import first_salary_session

CPF_2026_OW_CEILING = 8_000.0


@dataclass(frozen=True)
class PlanConfig:
    start_age: int = 25
    gross_monthly_salary: float = 5_000.0
    monthly_expenses: float = 2_000.0
    current_cash: float = 10_000.0
    current_investments: float = 10_000.0
    annual_salary_growth: float = 0.03
    annual_expense_inflation: float = 0.025
    emergency_months: float = 6.0
    horizon_years: int = 10
    salary_day: int = 1
    cpf_enabled: bool = True

    def __post_init__(self) -> None:
        if self.start_age < 16:
            raise ValueError("start_age must be at least 16")
        if min(
            self.gross_monthly_salary,
            self.monthly_expenses,
            self.current_cash,
            self.current_investments,
        ) < 0.0:
            raise ValueError("salary, expenses, cash and investments cannot be negative")
        if self.annual_salary_growth <= -1.0 or self.annual_expense_inflation <= -1.0:
            raise ValueError("annual growth rates must be greater than -100%")
        if self.emergency_months < 0.0:
            raise ValueError("emergency_months cannot be negative")
        if self.horizon_years < 1:
            raise ValueError("horizon_years must be positive")
        if not 1 <= self.salary_day <= 28:
            raise ValueError("salary_day must be between 1 and 28")


def cpf_2026_rates(age: int) -> tuple[float, float]:
    """Return (employer, employee) CPF rates for the 2026 full-rate employee table."""

    if age <= 55:
        return 0.17, 0.20
    if age <= 60:
        return 0.16, 0.18
    if age <= 65:
        return 0.125, 0.125
    if age <= 70:
        return 0.09, 0.075
    return 0.075, 0.05


def monthly_budget(
    gross_salary: float,
    monthly_expenses: float,
    *,
    age: int,
    cpf_enabled: bool = True,
    ow_ceiling: float = CPF_2026_OW_CEILING,
) -> dict[str, float]:
    if min(gross_salary, monthly_expenses, ow_ceiling) < 0.0:
        raise ValueError("salary, expenses and CPF ceiling cannot be negative")

    employer_rate, employee_rate = cpf_2026_rates(age)
    cpf_wage = min(gross_salary, ow_ceiling) if cpf_enabled else 0.0
    employee_cpf = cpf_wage * employee_rate
    employer_cpf = cpf_wage * employer_rate
    take_home = gross_salary - employee_cpf
    monthly_surplus = take_home - monthly_expenses
    return {
        "gross_salary": gross_salary,
        "employee_cpf": employee_cpf,
        "employer_cpf": employer_cpf,
        "total_cpf": employee_cpf + employer_cpf,
        "take_home": take_home,
        "monthly_expenses": monthly_expenses,
        "monthly_surplus": monthly_surplus,
    }


def _monthly_sessions(
    index: pd.DatetimeIndex,
    *,
    start: pd.Timestamp,
    months: int,
    salary_day: int,
) -> list[pd.Timestamp]:
    start_month = start.to_period("M")
    result: list[pd.Timestamp] = []
    for month in pd.period_range(start_month, periods=months, freq="M"):
        session = first_salary_session(index, month, salary_day)
        if session is None:
            break
        result.append(session)
    return result


def run_plan_window(
    daily: pd.DataFrame,
    *,
    start: pd.Timestamp,
    config: PlanConfig,
) -> pd.DataFrame:
    """Apply one future cash-flow plan to one historical market-price window."""

    frame = validate_daily(daily)
    start = pd.Timestamp(start)
    months = config.horizon_years * 12
    sessions = _monthly_sessions(
        frame.index,
        start=start,
        months=months,
        salary_day=config.salary_day,
    )
    if len(sessions) < months:
        raise ValueError("historical window is shorter than the requested planning horizon")

    first_price = float(frame.loc[sessions[0], "close"])
    units = config.current_investments / first_price if first_price > 0.0 else 0.0
    cash = config.current_cash
    cumulative_employee_cpf = 0.0
    cumulative_employer_cpf = 0.0
    cumulative_invested = config.current_investments
    rows: list[dict[str, float | int | pd.Timestamp | bool]] = []

    for month_number, session in enumerate(sessions):
        elapsed_years = month_number / 12.0
        age = config.start_age + month_number // 12
        salary = config.gross_monthly_salary * (1.0 + config.annual_salary_growth) ** elapsed_years
        expenses = config.monthly_expenses * (1.0 + config.annual_expense_inflation) ** elapsed_years
        budget = monthly_budget(
            salary,
            expenses,
            age=age,
            cpf_enabled=config.cpf_enabled,
        )
        cumulative_employee_cpf += budget["employee_cpf"]
        cumulative_employer_cpf += budget["employer_cpf"]
        cash += budget["monthly_surplus"]

        price = float(frame.loc[session, "close"])
        reserve_target = config.emergency_months * expenses
        sold = 0.0
        invested = 0.0

        if cash < 0.0 and units > 0.0:
            required = -cash
            sold_units = min(units, required / price)
            sold = sold_units * price
            units -= sold_units
            cash += sold

        if cash > reserve_target:
            invested = cash - reserve_target
            units += invested / price
            cash = reserve_target
            cumulative_invested += invested

        portfolio_value = units * price
        liquid_net_worth = cash + portfolio_value
        real_liquid_net_worth = liquid_net_worth / (
            (1.0 + config.annual_expense_inflation) ** elapsed_years
        )
        rows.append(
            {
                "date": session,
                "month": month_number + 1,
                "age": age,
                "salary": salary,
                "expenses": expenses,
                "employee_cpf": budget["employee_cpf"],
                "employer_cpf": budget["employer_cpf"],
                "monthly_surplus": budget["monthly_surplus"],
                "reserve_target": reserve_target,
                "cash": cash,
                "invested_this_month": invested,
                "sold_this_month": sold,
                "cumulative_invested": cumulative_invested,
                "units": units,
                "price": price,
                "portfolio_value": portfolio_value,
                "liquid_net_worth": liquid_net_worth,
                "real_liquid_net_worth": real_liquid_net_worth,
                "cumulative_employee_cpf": cumulative_employee_cpf,
                "cumulative_employer_cpf": cumulative_employer_cpf,
                "cash_shortfall": cash < 0.0,
            }
        )

    result = pd.DataFrame.from_records(rows).set_index("date")
    result.index = pd.DatetimeIndex(result.index)
    return result


def rolling_plan_backtest(
    daily: pd.DataFrame,
    *,
    config: PlanConfig,
    step_months: int = 1,
) -> pd.DataFrame:
    """Run the same plan across every eligible historical start month."""

    if step_months < 1:
        raise ValueError("step_months must be positive")

    frame = validate_daily(daily)
    months = frame.index.to_period("M").unique()
    required_months = config.horizon_years * 12
    if len(months) < required_months:
        raise ValueError("market history is shorter than the requested planning horizon")

    records: list[dict[str, object]] = []
    last_start = len(months) - required_months
    for offset in range(0, last_start + 1, step_months):
        month = months[offset]
        start = first_salary_session(frame.index, month, config.salary_day)
        if start is None:
            continue
        try:
            path = run_plan_window(frame, start=start, config=config)
        except ValueError:
            continue

        ending = path.iloc[-1]
        liquid = path["liquid_net_worth"].astype(float)
        peak = liquid.cummax().replace(0.0, np.nan)
        drawdown = liquid / peak - 1.0
        records.append(
            {
                "start": pd.Timestamp(path.index[0]),
                "end": pd.Timestamp(path.index[-1]),
                "ending_cash": float(ending["cash"]),
                "ending_portfolio": float(ending["portfolio_value"]),
                "ending_liquid_net_worth": float(ending["liquid_net_worth"]),
                "ending_real_liquid_net_worth": float(ending["real_liquid_net_worth"]),
                "total_employee_cpf": float(ending["cumulative_employee_cpf"]),
                "total_employer_cpf": float(ending["cumulative_employer_cpf"]),
                "total_cpf_contributions": float(
                    ending["cumulative_employee_cpf"] + ending["cumulative_employer_cpf"]
                ),
                "total_invested": float(ending["cumulative_invested"]),
                "minimum_liquid_net_worth": float(liquid.min()),
                "max_liquid_drawdown": float(drawdown.min(skipna=True)),
                "had_cash_shortfall": bool(path["cash_shortfall"].any()),
            }
        )

    if not records:
        raise ValueError("no complete historical planning windows were available")
    return pd.DataFrame.from_records(records).sort_values("start").reset_index(drop=True)


def scenario_summary(scenarios: pd.DataFrame) -> dict[str, float | int]:
    if scenarios.empty:
        raise ValueError("at least one scenario is required")

    real = scenarios["ending_real_liquid_net_worth"].astype(float)
    nominal = scenarios["ending_liquid_net_worth"].astype(float)
    return {
        "scenarios": int(len(scenarios)),
        "worst_real_ending": float(real.min()),
        "p25_real_ending": float(real.quantile(0.25)),
        "median_real_ending": float(real.median()),
        "p75_real_ending": float(real.quantile(0.75)),
        "best_real_ending": float(real.max()),
        "median_nominal_ending": float(nominal.median()),
        "cash_shortfall_rate": float(scenarios["had_cash_shortfall"].mean()),
    }
