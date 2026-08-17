# Singapore Money Planner

A personal-finance planning and investment-backtesting app for Singapore retail investors with four workflows:

1. **HiFIRE Plan** — project salary, living costs, HDB/BTO, car, children and big-ticket expenses against a target early-retirement age.
2. **Auto strategy** — automatically search for a historically robust lump-sum/DCA and IBKR configuration for a non-technical user.
3. **Personal plan** — stress-test a simpler salary/CPF/monthly-investing plan across real historical market/FX paths.
4. **Manual DCA** — inspect lump-sum versus DCA choices with full control over deployment and brokerage assumptions.

The older limit-order research remains available as an advanced lab instead of being the product homepage.

## Quick start

```bash
./scripts/setup.sh
source .venv/bin/activate
export TWELVE_DATA_API_KEY="your-key"
python -m streamlit run app.py
```

Or:

```bash
bash scripts/app.sh
```

Streamlit exposes the dedicated `HiFIRE Plan` page through the multipage navigation. The market-data workflows default to:

```text
Asset:       SPY
Currency:    USD
FX to SGD:   USD/SGD
History:     2008-01-01 onward
```

Downloaded market data is cached under `data/*_adjusted_daily.csv`.

## Singapore HiFIRE life plan

The HiFIRE page is designed for the question:

> Given the career I expect, the lifestyle I want and the major Singapore commitments I expect to take on, am I still on track to stop working at my target age?

The life-plan engine is deliberately separate from the historical DCA optimizer. A 40-60 year household plan cannot be represented by complete chronological windows from the repository's post-2008 market history, so the HiFIRE page uses an explicit deterministic expected-return assumption while Auto Strategy remains the historical investment-strategy test.

### Salary and living-cost timeline

From the current age to the target FIRE age, the page creates five-year planning phases. Each phase has sliders for:

- expected gross monthly salary;
- monthly living expenses in today's SGD.

Salary is treated as the expected nominal monthly salary for the selected future age band. Living expenses are inflated using the user's configured living-cost inflation assumption.

At the target FIRE age, salary can automatically fall to zero. If the user chooses to continue working, additional salary bands are exposed through age 69 or the plan end. Post-retirement living costs switch to the configured desired retirement spending amount, inflated from today.

### HDB / BTO planning

The housing section models:

- purchase/key-collection age;
- purchase price;
- planning equity/downpayment;
- housing-loan rate and tenure;
- cash share versus reported CPF-funded share of the downpayment;
- cash share versus reported CPF-funded share of monthly instalments;
- ongoing property running costs.

Planning defaults checked **17 August 2026**:

```text
Maximum ordinary HDB-loan LTV: up to 75%
Planning equity default:       25%
HDB concessionary rate:        2.6% p.a. for Jul-Sep 2026
Ordinary HDB loan-period cap:   25 years, subject to age/lease restrictions
```

The loan uses monthly-rest amortisation. CPF OA may be used for eligible housing payments, so the app allows the user to split housing payments between cash and CPF. It **does not** fabricate a future CPF OA balance or claim that enough OA will definitely be available.

Official references:

- HDB housing loan: https://www.hdb.gov.sg/buying-a-flat/flat-grant-and-loan-eligibility/housing-loan/housing-loan-from-hdb
- HDB housing-loan interest: https://www.hdb.gov.sg/managing-my-home/finances/loan-matters/interest-rate
- CPF housing usage: https://www.cpf.gov.sg/service/article/can-i-use-my-special-account-savings-to-pay-my-housing-loan

### Car planning

The optional car section models:

- purchase age and price;
- downpayment;
- configurable flat annual interest rate;
- loan tenure;
- monthly running cost;
- ownership period;
- optional resale proceeds.

The loan uses flat-rate repayment mathematics. The app does not hard-code a regulatory LTV or a guessed car price.

Reference: https://www.moneysense.gov.sg/costs-of-borrowing-flat-rate-monthly-rest-and-effective-interest-rate/

### Children and big-ticket expenses

For each child the user can set:

- the planner's age when the child is born;
- monthly support cost in today's SGD;
- support duration;
- optional education lump sum and child age when it is paid.

No child-cost figure is presented as a factual Singapore default.

The page also supports up to five generic one-off expenses such as renovation, wedding, parental support, further education, sabbatical or major travel.

### FIRE output

The HiFIRE page reports:

- projected liquid wealth at the target FIRE age;
- inflation-adjusted FIRE number at the target age;
- target-age gap or surplus;
- FIRE funding ratio;
- plan-end liquid wealth;
- first projected age at which liquid wealth crosses the base FIRE number;
- cash/CPF housing totals;
- car and child cash costs;
- liquidity-stress and unfunded-shortfall warnings;
- annual cash-flow and wealth timelines.

The base FIRE number is:

```text
inflation-adjusted annual retirement spending / configured withdrawal rate
```

CPF balances, home equity and car value are intentionally excluded from the liquid FIRE number in v1.

The full implementation contract is in:

```text
docs/specs/singapore-hifire-life-plan-v1.md
```

## Auto strategy: non-technical investment flow

Auto Strategy is designed for the question:

> I have a lump sum. Search the sensible choices and tell me which configuration was most robust historically.

The default capital is **S$1,000,000**, but it is editable.

The user chooses assumptions that the optimizer should not be allowed to cherry-pick:

- starting capital;
- ETF and asset currency;
- evaluation horizon;
- annual yield earned by undeployed cash;
- US or LSE USD ETF venue;
- optional extra Tiered venue/clearing cost estimate.

The app searches controllable execution choices automatically:

- lump sum or DCA deployment length;
- monthly buy day;
- IBKR Pro Fixed or Tiered pricing;
- manual spot FX or AutoFX for USD assets.

### Search process

The optimizer does not simply try hundreds of settings and report the best result from the same data.

It uses a deterministic staged search:

1. build only complete historical evaluation windows;
2. split starts chronologically into roughly **60% selection / 20% validation / 20% newest holdout**;
3. run a coarse grid over deployment length, buy day, IBKR pricing and FX method on selection starts;
4. refine locally around the strongest coarse regions;
5. rank finalists on validation using median performance, downside performance and performance versus immediate deployment;
6. check nearby parameter choices so a broad stable region is preferred over an isolated spike;
7. lock one recommendation;
8. only then evaluate that locked recommendation on the newest holdout starts.

The holdout is not used to retune the winner. Material holdout deterioration is reported instead of searching for a replacement.

This reduces direct backtest overfitting but cannot remove it. Historical start windows can overlap and past market/FX paths are not forecasts.

### Automatic-search outputs

The app shows:

- recommended deployment period and buy day;
- IBKR Pro Fixed or Tiered choice;
- manual FX or AutoFX choice;
- number of configurations searched;
- stability label based on nearby configurations;
- validation and newest-holdout results versus immediate deployment;
- holdout median and 10th-percentile ending wealth;
- holdout win rate;
- pre-holdout finalists;
- an overfitting/degradation warning when appropriate.

## Fair-comparison rules

Both automatic and manual DCA analysis enforce:

- same SGD starting capital;
- common historical comparison start;
- same terminal date for each historical window;
- a fully present requested evaluation horizon;
- no extra holding period for slower deployment;
- only the configured yield on undeployed cash;
- final SGD valuation using historical FX.

The DCA engine rejects incomplete trailing windows instead of silently shortening the requested horizon.

## Personal-plan workflow

The older personal-plan tab remains as a compact historical stress test:

- starting monthly gross salary, expenses, cash and investments;
- 2026 CPF planning rules when enabled;
- emergency-fund-first allocation;
- monthly investing above the reserve;
- forced investment sales when cash is insufficient;
- real daily ETF and FX data;
- rolling complete historical start windows.

For long-horizon career, family and FIRE planning, use the HiFIRE page instead.

## Manual DCA workflow

Manual DCA is retained for users who want to inspect or override automatic assumptions.

Easy deployment presets:

```text
Lump sum
3 months
6 months
12 months
18 months
24 months
36 months
```

You can configure evaluation horizon, buy day, start-date spacing, cash yield, ETF venue, IBKR pricing, FX method, Tiered venue-cost estimate and fully custom stock/FX fee overrides.

## IBKR Pro fee presets

Published schedule checked: **17 August 2026**.

Built-in buy-side presets for USD-traded ETFs include:

### US exchange-listed ETFs

IBKR Pro Fixed:

```text
USD 0.005 / share
USD 1.00 minimum per order
1% of trade value maximum
```

IBKR Pro Tiered first volume tier:

```text
USD 0.0035 / share
USD 0.35 minimum per order
1% of trade value maximum in the preset
+ configurable venue / clearing estimate
```

### LSE USD-denominated ETFs

IBKR Pro Fixed SmartRouting:

```text
0.05% of trade value
USD 4.00 minimum per order
```

IBKR Pro Tiered:

```text
0.05% of trade value
USD 1.70 minimum per order
USD 39.00 maximum per order
+ configurable venue / clearing estimate
```

### SGD to USD conversion

Manual spot FX:

```text
0.20 basis point of trade value
USD 2.00 minimum per conversion
```

IBKR Pro AutoFX:

```text
3 basis points
```

Official references:

- https://www.interactivebrokers.com.sg/en/pricing/commissions-stocks.php
- https://www.interactivebrokers.com.sg/en/pricing/commissions-spot-currencies.php
- https://www.interactivebrokers.com.sg/en/trading/products-etfs.php
- https://www.interactivebrokers.com.sg/en/trading/recurring-investments.php

Fee schedules can change. Presets are date-stamped and remain overrideable.

## Market and FX data

The investment-analysis flows reuse the repository's validated Twelve Data loader and local CSV cache.

For USD assets the app also loads `USD/SGD`. The currency helper aligns the most recent prior FX close to each asset session before converting values into SGD.

Twelve Data is requested with `adjust=all`. The default 2008 start date remains below the existing 5,000-row provider response ceiling while retaining enough history for supported DCA horizons.

## CPF assumptions

The current planner uses the CPF Board's 2026 full-rate contribution table as a planning baseline. For employees aged 55 and below with monthly wages above S$750:

```text
Employer: 17%
Employee: 20%
Total:    37%
```

The 2026 Ordinary Wage ceiling is S$8,000 per month.

The HiFIRE page reuses this take-home calculation but does not claim that the current contribution rates or wage ceiling will remain unchanged for decades. CPF balances are not counted as liquid FIRE wealth, and housing CPF usage is reported without pretending to know the future OA balance.

Official references:

- https://www.cpf.gov.sg/employer/employer-obligations/how-much-cpf-contributions-to-pay
- https://www.cpf.gov.sg/service/article/what-is-the-ordinary-wage-ow-ceiling

## Current model boundaries

Still excluded or simplified:

- Singapore resident income tax and individual tax reliefs;
- bonuses and Additional Wage CPF rules;
- exact CPF OA/SA/MA balances, allocation, interest and future-policy changes;
- SRS and CPF LIFE;
- spouse/dual-income household modelling;
- insurance adequacy and healthcare claims;
- housing grants, eligibility, exact BTO staged-payment milestones, property resale/upgrading and CPF housing withdrawal limits;
- car regulatory financing limits, replacement cycles, COE renewal and depreciation;
- childcare grants/subsidies and Baby Bonus/CDA;
- Monte Carlo/sequence-of-returns analysis for the life plan;
- bid/ask spread, market impact and eventual sale-side investment costs;
- estate/legacy planning.

The automatic investment optimizer searches only explicitly supported DCA/execution parameters. It does not optimize the ETF, the user's salary/lifestyle assumptions, evaluation horizon or assumed cash yield.

## Advanced execution research

The original research engine remains available:

```text
notebooks/retail_portfolio.ipynb
src/retail_sp500/models.py
src/retail_sp500/engine.py
src/retail_sp500/stacking.py
src/retail_sp500/research.py
src/retail_sp500/cli.py
```

Run it with:

```bash
./scripts/run.sh
```

## Code layout

```text
app.py                                      Auto strategy / simple planner / Manual DCA
pages/1_HiFIRE_Plan.py                      long-horizon Singapore HiFIRE UI
src/retail_sp500/lifeplan.py                salary/life-event/FIRE projection engine
src/retail_sp500/optimizer.py               coarse grid, refinement, validation, holdout
src/retail_sp500/planner.py                 compact CPF-aware historical cash-flow tests
src/retail_sp500/broker.py                  configurable IBKR Pro transaction costs
src/retail_sp500/dca.py                     common DCA execution and historical analysis
src/retail_sp500/currency.py                lookahead-safe historical FX alignment
src/retail_sp500/data.py                    validated adjusted market-data loader/cache
docs/specs/singapore-hifire-life-plan-v1.md implementation contract
notebooks/retail_portfolio.ipynb            advanced execution research interface
tests/                                      deterministic regressions
```

## Validation

```bash
python -m pytest -q
python -m compileall -q src app.py pages
python -m json.tool notebooks/retail_portfolio.ipynb >/dev/null
bash -n scripts/setup.sh scripts/run.sh scripts/app.sh
```

Deterministic tests do not require live market access. Live market-data behavior still depends on the configured Twelve Data account, supported symbols and API service.
