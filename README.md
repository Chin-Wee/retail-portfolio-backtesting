# Singapore Money Planner

A small personal-finance backtesting app for young Singaporeans.

The MVP answers one practical question:

> Given my salary, CPF, expenses, cash buffer and current investments, how resilient would my plan have been across different real market starting points?

The main interface is now a Streamlit app. The older execution-strategy research remains available as an advanced lab instead of being the product homepage.

## What the MVP does

- starts from monthly gross salary, expenses, current cash and current investments;
- applies the 2026 CPF full-rate employee table and Ordinary Wage ceiling when enabled;
- builds an emergency fund first, then invests monthly surplus above that reserve;
- sells investments when monthly cash flow cannot be covered by cash;
- downloads real daily market data from Twelve Data;
- requests dividend- and split-adjusted prices;
- converts USD assets into SGD with real historical `USD/SGD` data;
- replays the same personal-finance plan across every complete historical market window;
- shows worst, median and best inflation-adjusted ending liquid wealth plus liquidity-stress frequency.

The historical runs are stress scenarios, not forecasts.

## Quick start

```bash
./scripts/setup.sh
source .venv/bin/activate
export TWELVE_DATA_API_KEY="your-key"
python -m streamlit run app.py
```

Or after setup:

```bash
bash scripts/app.sh
```

The default app configuration uses:

```text
Asset:       SPY
Currency:    USD
FX to SGD:   USD/SGD
History:     2007-06-01 onward
```

Downloaded data is cached under `data/*_adjusted_daily.csv`.

## App flow

### 1. Enter your current finances

The app asks for:

- age;
- gross monthly salary;
- monthly expenses;
- current cash;
- current investments already held in the selected ETF;
- emergency-fund target in months of expenses;
- planning horizon;
- expected salary growth;
- expected expense inflation.

It immediately shows estimated take-home pay, monthly surplus and CPF contributions.

### 2. Load real market history

The app uses the repository's existing validated Twelve Data loader and local CSV cache.

For USD assets it also loads `USD/SGD`, then converts each historical asset session into SGD before simulation. This prevents a USD ETF path from being incorrectly treated as if its prices were already in Singapore dollars.

Twelve Data is requested with `adjust=all`, so supported instruments are adjusted for dividends and splits before the planner uses them.

### 3. Stress-test the plan

For every complete historical start window, the planner:

1. applies salary and expense growth assumptions;
2. deducts employee CPF from take-home pay;
3. adds monthly expenses;
4. keeps cash up to the emergency-fund target;
5. invests cash above the reserve into the selected ETF;
6. sells ETF units if cash goes below zero;
7. records liquid wealth and cumulative employee/employer CPF contributions.

The result is a distribution of outcomes instead of one cherry-picked historical start date.

## CPF assumptions

The MVP uses the CPF Board's 2026 full-rate table for Singapore Citizens and third-year-and-onward Singapore Permanent Residents.

For employees aged 55 and below with monthly wages above S$750, the 2026 rates are:

```text
Employer: 17%
Employee: 20%
Total:    37%
```

The 2026 Ordinary Wage ceiling is S$8,000 per month.

The app deliberately does not approximate the graduated CPF contribution table for monthly wages of S$750 or below. Disable CPF for those scenarios until that table is modelled explicitly.

Official references:

- CPF Board: https://www.cpf.gov.sg/employer/employer-obligations/how-much-cpf-contributions-to-pay
- CPF Board Ordinary Wage ceiling: https://www.cpf.gov.sg/service/article/what-is-the-ordinary-wage-ow-ceiling

The selected 2026 rule set is held constant through each historical scenario. It is not a prediction of future CPF policy.

## Current model boundaries

The MVP currently excludes:

- personal income tax;
- bonuses and Additional Wage CPF rules;
- CPF OA/SA/MA allocation and account interest;
- housing purchases, mortgages and CPF housing withdrawals;
- insurance and dependants;
- brokerage commissions and bid/ask spread;
- platform-specific FX conversion fees;
- cash interest;
- retirement withdrawals.

These are visible omissions rather than hidden assumptions.

## Advanced execution research

The original research engine is still present for testing monthly ETF purchase policies:

```text
notebooks/retail_portfolio.ipynb
src/retail_sp500/models.py
src/retail_sp500/engine.py
src/retail_sp500/stacking.py
src/retail_sp500/research.py
src/retail_sp500/cli.py
```

Run the CLI with:

```bash
./scripts/run.sh
```

That lab compares immediate buying, fixed pullback limits, ATR-scaled limits and historical fill-probability limits using a common contribution schedule and holdout period.

## Code layout

```text
app.py                            Streamlit personal-finance MVP
src/retail_sp500/planner.py       CPF-aware cash-flow and rolling stress tests
src/retail_sp500/currency.py      historical FX conversion into SGD
src/retail_sp500/data.py          validated adjusted Twelve Data loader/cache
src/retail_sp500/engine.py        existing common backtest/accounting engine
notebooks/retail_portfolio.ipynb  advanced execution research interface
tests/                            deterministic unit tests
```

## Validation

```bash
python -m pytest -q
python -m compileall -q src app.py
python -m json.tool notebooks/retail_portfolio.ipynb >/dev/null
bash -n scripts/setup.sh scripts/run.sh scripts/app.sh
```

The tests use synthetic deterministic price series. Live-data behavior still depends on the configured Twelve Data account, symbol availability and API service.
