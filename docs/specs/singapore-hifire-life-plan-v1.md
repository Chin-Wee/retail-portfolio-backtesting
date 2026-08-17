# Singapore HiFIRE Life Plan v1

Status: implementation spec
Checked: 2026-08-17
Target user: non-technical Singapore retail investor planning for high financial independence / early retirement (HiFIRE)

## 1. Problem

The existing app can compare investment deployment strategies and can run a simple salary/expense plan, but the personal planner assumes one starting salary, one annual salary-growth rate and one starting living-expense number. That is not sufficient for a Singapore household making decisions about career progression, HDB/BTO housing, cars, children and early retirement.

The product needs a time-based household cash-flow model that answers:

- What if my salary changes materially at different ages?
- What happens if I buy an HDB, finance a car or have children?
- How much can I keep investing after those commitments?
- What liquid portfolio do I need at my target FIRE age?
- Does the projected post-retirement path stay funded after the major commitments are included?

## 2. Product principles

1. Keep the main path understandable without finance jargon.
2. User-controlled life assumptions are not optimizer parameters. Do not cherry-pick salary, inflation, future spending or FIRE age to manufacture a successful plan.
3. Separate long-horizon life projection from historical investment-strategy backtesting. A 40-60 year life plan cannot be represented by complete chronological windows from the repository's post-2008 market history.
4. Show cash-flow failures explicitly. Never silently allow negative cash without selling investments or reporting an unfunded shortfall.
5. Version Singapore-specific defaults and make them editable.
6. Do not invent precise CPF OA balances, future CPF policy, child costs, car costs or government grants.

## 3. QA gap list

### P0 — implement in v1

- Time-varying salary by age band.
- Time-varying living expenses before retirement.
- Explicit retirement transition and target FIRE age.
- HDB/BTO purchase, upfront equity and monthly housing loan.
- User-controlled cash-vs-CPF share for housing payments.
- Car purchase, flat-rate loan and running costs.
- Child monthly support and optional education lump sum.
- Generic one-off big-ticket expenses.
- Emergency cash reserve before investing excess cash.
- Forced investment sales when cash is insufficient.
- FIRE target, target-age wealth/gap and post-retirement sustainability status.
- Monthly timeline and category-level cash-flow output.

### P1 — intentionally deferred

- Singapore resident income-tax engine and personal reliefs.
- Exact CPF OA/SA/MA allocation, account balances, interest and future policy changes.
- SRS contributions/withdrawals and CPF LIFE.
- Partner/dual-income household support.
- Insurance adequacy and healthcare claim modelling.
- BTO grant/eligibility logic, exact staged-payment milestones and property resale/upgrading.
- Car regulatory financing limits, replacement cycles, COE renewal and resale/depreciation.
- Childcare subsidies, Baby Bonus/CDA and school-specific costs.
- Monte Carlo/sequence-of-returns simulation and stochastic salary/job-loss scenarios.
- Estate/legacy planning.

## 4. User flow

A dedicated Streamlit page called `HiFIRE Plan` is added to the app's multipage navigation.

### Step A — goal and current position

Inputs:

- current age
- target FIRE age
- plan end age
- current cash
- current liquid investments
- expected annual investment return
- annual living-cost inflation
- desired monthly retirement spending in today's SGD
- withdrawal rate
- emergency-fund months
- whether current-rule CPF employee contributions should be applied
- whether salary stops at target FIRE age

### Step B — salary and living-expense timeline

For each five-year period from current age to target FIRE age, show two sliders:

- expected gross monthly salary
- monthly living expenses in today's SGD

Salary values are treated as the expected nominal gross salary for that age band. Living-expense values are expressed in today's SGD and inflated by the configured inflation rate.

### Step C — life commitments

#### HDB/BTO

Optional toggle with:

- purchase/key-collection age
- purchase price
- downpayment/equity fraction
- annual loan interest rate
- loan tenure
- cash share of downpayment
- cash share of monthly instalment
- monthly property running/maintenance cost

Planning defaults checked 2026-08-17:

- HDB housing loan LTV: up to 75%; therefore v1 uses 25% as the default planning equity fraction.
- HDB concessionary interest rate: 2.6% p.a. for 1 July 2026 to 30 September 2026.
- Ordinary HDB loan-period cap: 25 years, subject to applicant-age and remaining-lease restrictions.
- CPF OA may be used for eligible housing downpayments and monthly instalments. v1 therefore models a user-entered cash share and reports the balance as CPF-funded housing usage. It does not fabricate an OA balance.

Official references:

- https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/housing-loan/housing-loan-from-hdb
- https://www.hdb.gov.sg/managing-my-home/finances/loan-matters/interest-rate
- https://www.cpf.gov.sg/service/article/can-i-use-my-special-account-savings-to-pay-my-housing-loan

#### Car

Optional toggle with:

- purchase age
- purchase price
- downpayment fraction
- flat annual interest rate
- loan tenure
- monthly running cost
- ownership years
- optional resale value at the end of ownership

The loan uses flat-rate repayment mathematics. No regulatory LTV or vehicle-price default is hard-coded in v1.

Reference:

- https://www.moneysense.gov.sg/costs-of-borrowing-flat-rate-monthly-rest-and-effective-interest-rate/

#### Children

0-3 children. Per child:

- birth age of the planner user
- monthly support cost in today's SGD
- support duration
- optional education lump sum
- age of child when education lump sum occurs

No default Singapore child-cost estimate is presented as fact.

#### Other big-ticket items

0-5 generic one-off expenses with:

- label
- planner age when expense occurs
- amount in future SGD

Examples: wedding, renovation, parents, further education, sabbatical, major travel.

## 5. Calculation model

Projection frequency: monthly.

### Salary and CPF

- Select the salary age band for the month.
- If `stop_salary_at_fire` is true, gross salary becomes zero from the target FIRE age.
- Reuse the existing `monthly_budget()` CPF/take-home calculation.
- CPF remains a current-rule estimate. It is not added to liquid FIRE wealth.

### Living expenses

- Select the pre-retirement living-expense age band and inflate from today.
- From target FIRE age onward, use `retirement_monthly_spend_today`, inflated from today.

### Investments

- Current liquid investments compound monthly at the configured expected annual return.
- Cash above the emergency reserve is invested.
- If cash falls below zero, investments are sold to cover the deficit.
- If investment sales cannot restore cash to zero, record an unfunded shortfall.

### HDB loan

Monthly-rest amortising payment:

`P * r / (1 - (1 + r)^-n)`

where `P` is loan principal, `r` monthly interest rate, `n` number of monthly payments.

- Purchase equity = price x downpayment fraction.
- Loan principal = price - purchase equity.
- Cash downpayment = purchase equity x cash-downpayment share.
- CPF housing usage = remaining purchase equity.
- Cash monthly instalment = monthly instalment x cash-instalment share.
- CPF monthly housing usage = remaining instalment.

### Car loan

Flat-rate total repayment:

`principal * (1 + flat annual rate * years)`

Monthly payment is total repayment divided by loan months.

### FIRE target

Base liquid FIRE number at each month:

`inflation-adjusted annual retirement spending / withdrawal rate`

CPF balances, home equity and vehicle value are excluded from the liquid FIRE number in v1.

### On-track status

At target FIRE age:

- projected liquid wealth must be at least the base FIRE target; and
- the projection must not record an unfunded post-retirement cash shortfall through the plan end.

This is a deterministic projection under the configured expected return, not a probability forecast.

## 6. Output

Primary cards:

- On track / Not on track
- projected liquid wealth at FIRE age
- FIRE number at target age
- target-age gap/surplus
- plan-end liquid wealth

Supporting output:

- net-worth vs FIRE-target chart
- monthly salary, living cost, housing, car, children and one-off cash flows
- housing loan amount and monthly instalment
- cumulative cash housing cost and reported CPF housing usage
- cumulative child/car/one-off costs
- liquidity-stress and unfunded-shortfall warnings

## 7. Acceptance criteria

1. Salary changes immediately when an age band changes.
2. Retirement salary can stop exactly at target FIRE age.
3. HDB amortisation payment matches the standard monthly-rest formula.
4. Cash/CPF housing shares sum to the full downpayment and instalment.
5. Car flat-rate payment matches principal + flat interest divided by months.
6. Child support starts at configured birth age and stops after support duration.
7. Education and generic one-off expenses occur once at the configured month.
8. Cash above reserve is invested; deficits sell investments; unrecoverable deficits are flagged.
9. FIRE number is based on inflation-adjusted retirement spending and configured withdrawal rate.
10. CPF is not counted as liquid FIRE wealth.
11. Page parses as valid Python and exposes salary/living-expense sliders plus HDB/car/child controls.

## 8. Files

- `docs/specs/singapore-hifire-life-plan-v1.md` — this specification.
- `src/retail_sp500/lifeplan.py` — deterministic monthly life-plan engine.
- `pages/1_HiFIRE_Plan.py` — non-technical Streamlit UI.
- `tests/test_lifeplan.py` — calculation and cash-flow regressions.
- `tests/test_hifire_page.py` — page syntax/wiring smoke test.
- `README.md` — product overview and model boundaries.
