# Singapore Money Planner

A personal-finance backtesting app for young Singaporeans with two practical workflows:

1. **Personal plan** — stress-test salary, CPF, expenses, emergency cash and monthly investing across real historical market/FX paths.
2. **S$1m DCA lab** — compare investing an available lump sum immediately against spreading the same capital across monthly purchases, including configurable IBKR Pro trading and FX costs.

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

The default market-data configuration uses:

```text
Asset:       SPY
Currency:    USD
FX to SGD:   USD/SGD
History:     2008-01-01 onward
```

Downloaded data is cached under `data/*_adjusted_daily.csv`.

## Personal-plan workflow

The personal-plan tab:

- starts from monthly gross salary, expenses, current cash and current investments;
- applies the 2026 CPF full-rate employee table and Ordinary Wage ceiling when enabled;
- builds an emergency fund first, then invests monthly surplus above that reserve;
- sells investments when monthly cash flow cannot be covered by cash;
- uses real daily ETF and FX data;
- converts USD assets into SGD with the most recent prior `USD/SGD` close to avoid same-date daily-close lookahead;
- replays the same plan across every complete historical start window;
- reports worst, median and best inflation-adjusted ending liquid wealth plus liquidity-stress frequency.

Brokerage costs are not yet wired into the personal cash-flow planner. The DCA lab below includes explicit buy-side IBKR transaction costs.

## S$1m DCA lab

The DCA tab is designed for the question:

> I already have S$1,000,000 available. Should I invest it now or spread it out?

The default capital is **S$1,000,000**, but it is editable.

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

You can also configure:

- evaluation horizon;
- calendar buy day;
- historical start-date spacing;
- annual yield earned by undeployed cash;
- ETF venue;
- IBKR Pro Fixed or Tiered pricing;
- manual spot FX or AutoFX;
- an extra Tiered venue/clearing cost estimate;
- fully custom stock and FX fee overrides.

### Fair comparison rule

For each historical starting month, every deployment strategy:

- starts with the same SGD capital;
- begins on the same historical start month;
- ends on the same historical terminal date;
- uses equal monthly deployment tranches;
- values the final portfolio in SGD using historical FX.

This avoids giving slower DCA strategies an extra holding period.

### DCA outputs

The app reports:

- median, 10th-percentile, worst and best ending wealth;
- median total transaction costs;
- stock commissions and FX fees separately;
- median ending-wealth difference versus lump sum;
- percentage of historical start windows where a DCA strategy beat lump sum;
- full outcome distributions by deployment period.

Historical outcomes are stress scenarios, not forecasts.

## IBKR Pro fee presets

Published schedule checked: **17 August 2026**.

The built-in presets currently model buy-side costs for USD-traded ETFs.

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

Useful for modelling USD-denominated London Stock Exchange ETFs such as an Irish UCITS ETF listing.

IBKR Pro Fixed SmartRouting preset:

```text
0.05% of trade value
USD 4.00 minimum per order
```

IBKR Pro Tiered preset:

```text
0.05% of trade value
USD 1.70 minimum per order
USD 39.00 maximum per order
+ configurable venue / clearing estimate
```

Tiered exchange and clearing charges vary with routing and execution venue, so the app does not invent a single universal all-in figure.

### SGD to USD conversion

Manual spot FX preset:

```text
0.20 basis point of trade value
USD 2.00 minimum per conversion
```

IBKR Pro AutoFX preset:

```text
3 basis points
```

This matters for DCA because many small conversions can repeatedly hit the manual-FX minimum.

Official references:

- IBKR Singapore stocks/ETFs commissions: https://www.interactivebrokers.com.sg/en/pricing/commissions-stocks.php
- IBKR Singapore spot-currency commissions: https://www.interactivebrokers.com.sg/en/pricing/commissions-spot-currencies.php
- IBKR Singapore ETF / Pro vs Lite pricing comparison: https://www.interactivebrokers.com.sg/en/trading/products-etfs.php
- IBKR Singapore recurring investments: https://www.interactivebrokers.com.sg/en/trading/recurring-investments.php

Fee schedules can change. The app stamps the preset date and exposes custom overrides so backtests do not depend on pretending the current schedule is permanent.

## Market and FX data

The app reuses the repository's validated Twelve Data loader and local CSV cache.

For USD assets it also loads `USD/SGD`. The currency helper aligns the **most recent prior FX close** to each asset session before converting values into SGD.

Twelve Data is requested with `adjust=all`, so supported instruments are adjusted for dividends and splits. Instruments such as FX that do not provide volume are represented with zero volume because volume is not used by these simulations.

The default 2008 start date stays below the existing 5,000-row provider response ceiling while retaining enough history for the supported horizons.

## CPF assumptions

The personal-plan MVP uses the CPF Board's 2026 full-rate table for Singapore Citizens and third-year-and-onward Singapore Permanent Residents.

For employees aged 55 and below with monthly wages above S$750:

```text
Employer: 17%
Employee: 20%
Total:    37%
```

The 2026 Ordinary Wage ceiling is S$8,000 per month.

The app does not approximate the graduated CPF table for monthly wages of S$750 or below. Disable CPF for those scenarios until that table is modelled explicitly.

Official references:

- CPF Board: https://www.cpf.gov.sg/employer/employer-obligations/how-much-cpf-contributions-to-pay
- CPF Board Ordinary Wage ceiling: https://www.cpf.gov.sg/service/article/what-is-the-ordinary-wage-ow-ceiling

The selected 2026 rule set is held constant through historical scenarios. It is not a prediction of future CPF policy.

## Current model boundaries

Still excluded or simplified:

- personal income tax;
- bonuses and Additional Wage CPF rules;
- CPF OA/SA/MA allocation and account interest;
- housing purchases, mortgages and CPF housing withdrawals;
- insurance and dependants;
- bid/ask spread and market impact;
- eventual selling costs and sale-side regulatory fees;
- exact Tiered exchange/clearing charges unless entered through the configurable extra-cost field;
- securities lending;
- retirement withdrawals.

The personal-plan tab still excludes broker costs; the DCA tab includes buy-side commissions and FX conversion costs.

## Advanced execution research

The original research engine remains available for testing monthly ETF purchase policies:

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

That lab compares immediate buying, fixed pullback limits, ATR-scaled limits and historical fill-probability limits using a common contribution schedule and holdout period.

## Code layout

```text
app.py                            Streamlit personal-finance + DCA MVP
src/retail_sp500/planner.py       CPF-aware cash-flow stress tests
src/retail_sp500/broker.py        configurable IBKR Pro transaction costs
src/retail_sp500/dca.py           lump-sum versus DCA historical analysis
src/retail_sp500/currency.py      lookahead-safe historical FX alignment
src/retail_sp500/data.py          validated adjusted Twelve Data loader/cache
src/retail_sp500/engine.py        existing common research engine
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

The deterministic tests do not require live market access. Live behavior still depends on the configured Twelve Data account, supported symbols and API service.
