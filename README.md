# Renewable Flexibility Studio

A standalone, interactive decision-support prototype that converts historical wind and solar forecast deviations into transparent battery-firming and storage-sizing results.

The site is deliberately independent from the earlier GB renewable forecasting website. It does not import that dashboard, open it in a tab, use an iframe, or require it to be awake. The two projects exchange only compact, versioned data bundles.

## What the current V2-backed prototype does

A user can:

- select a wind, solar or mixed virtual renewable portfolio;
- change portfolio capacity and the wind/solar mix;
- change battery power, duration, initial state of charge and efficiency;
- simulate a deployable **reactive firming** strategy for any of 450 out-of-sample historical days;
- inspect renewable delivery, charge/discharge and state of charge;
- compare forecast error before and after the battery;
- inspect a leakage-safe rolling **80% prediction interval** and see which historical periods fell outside the expected range;
- size a battery for **future operation** using a 2,541-cell stability grid across 450 out-of-sample days, with 80/90/95% firming and reliability targets;
- inspect the latest V2 **forecast-day** renewable schedule with a directional empirical uncertainty range;
- carry the selected future battery into an operational reserve planner that checks current SOC, calculates a safe starting-SOC band, recommends only the minimum necessary pre-day adjustment, and identifies critical downside/upside reserve windows;
- place that schedule in real GB grid context using the official half-hourly NESO National Demand Forecast served by Elexon Insights;
- translate each historical forecast deviation into a BSC-style imbalance volume and official Elexon System-Price cashflow, before and after battery firming;
- inspect gross imbalance-settlement exposure separately from signed settlement cashflow, without labelling exposure reduction as profit;
- identify power-limited and energy-limited periods;
- search a controlled 1h/2h/4h battery grid for the smallest tested configuration meeting a target;
- download every half-hourly calculation as CSV;
- run a separate 450-day **continuous-SOC** benchmark and extended storage-duration diagnostic from the command line.

The application now uses a **450-day out-of-sample V2 bundle** from 1 April 2025 to 30 June 2026: 360 expanding-window out-of-fold development days plus 90 locked-test days. The original one-day file is retained only as a compact unit-test fixture.

## Product boundary

This is a **virtual portfolio-level firming benchmark**. It is not:

- a site-specific battery design;
- a physical battery capable of correcting all GB renewable output;
- an electricity-trading or revenue-stacking model;
- an investment recommendation;
- direct control software for a battery management system.

National forecast and actual capacity factors are scaled to a user-selected virtual portfolio. The value is comparative: it shows how battery power, duration, efficiency and starting SOC affect the ability to absorb forecast deviations.

## Architecture

```text
Versioned historical forecast bundle
                ↓
        adapters/forecast_data.py
                ↓
        engine/portfolio.py
                ↓
        engine/battery.py
                ↓
   engine/metrics.py + engine/sizing.py
                ↓
        standalone Dash interface
```

The `engine/` package contains no Dash code. This makes the equations independently testable and leaves a clean path to a future API or alternative frontend.

## Reactive firming strategy

For each half-hour:

- actual output above forecast creates a renewable surplus and the battery charges;
- actual output below forecast creates a renewable deficit and the battery discharges;
- charge/discharge power is limited by battery MW;
- energy movement is limited by SOC headroom and round-trip efficiency;
- grid charging and simultaneous charge/discharge are excluded;
- the strategy sees the current deviation but has no future settlement-period knowledge.

Battery energy capacity is:

```text
energy capacity (MWh) = power (MW) × duration (hours)
```

## Forecast uncertainty

The historical generation chart includes a nominal **80% rolling prediction interval** around the point forecast. For each selected day, the interval is calibrated only from earlier out-of-sample forecast residuals, using a 90-day lookback and forecast-level-local residual matching. The selected day's actual output is never used to construct its own band; actuals are used only afterward to assess coverage and mark periods outside the expected range.

Backtesting over eligible dates gives about **80.6% wind**, **77.0% solar** and **79.9% mixed** overall coverage. On the locked Apr–Jun 2026 period, coverage is **80.7%**, **81.1%** and **80.8%**, respectively. This is a residual-based uncertainty band, not yet an ECMWF weather-ensemble or dedicated P10/P50/P90 probabilistic forecast.

## GB imbalance-settlement context

For historical dates, the point forecast is treated as an illustrative contracted/scheduled renewable export. The portfolio imbalance is actual minus scheduled energy for each 30-minute settlement period. The Studio joins the matching official Elexon System Price and Net Imbalance Volume and calculates the corresponding BSC-style signed settlement cashflow. Positive cashflow means a payment by the virtual portfolio; negative means a receipt to it.

The UI also reports **gross cash-out exposure**, defined as the absolute size of those settlement cashflows. This is a risk/volatility measure, not profit or avoided cost. The separate Risk & Value layer monetises physical exposure only through visible user/scenario assumptions; it does not relabel System Price exposure as battery revenue.

The frozen Elexon archive covers the same 450 target days and all 21,600 half-hours as the V2 forecast-error bundle.

## Future battery sizing benchmark

This is now the main design layer. The practical sizing mode assumes a **grid-connected reserve BESS**: SOC is restored to 50% before each operating day, then the battery reacts only to renewable forecast deviations during that day. Grid energy used to restore SOC is measured explicitly and is not treated as free. Intraday grid charging remains excluded.

The design grid tests 11 power levels (5–100% of portfolio MW) and 11 durations (1–72 h) for every 5% wind-share step. A candidate must meet the selected overall firming target and the selected percentage-of-days reliability target in both Apr 2025–Mar 2026 and Apr–Jun 2026. The minimum-energy tested candidate is selected, then lower MW and duration break ties. Because the later period has already been examined in this project, it is described as a second-period stability check, not a new sealed battery-sizing holdout.

For the default **90% firming / 90% of days** gate on a 100 MW portfolio:

| Portfolio | Minimum stable tested design | Development overall / days | Apr–Jun 2026 overall / days |
|---|---:|---:|---:|
| Solar | 25 MW / 150 MWh (6 h) | 95.4% / 93.9% | 96.1% / 91.1% |
| Mixed 50/50 | **25 MW / 200 MWh (8 h)** | **96.3% / 93.3%** | **97.5% / 95.6%** |
| Wind | 15 MW / 360 MWh (24 h) | 95.1% / 91.1% | 98.3% / 95.6% |

Power and energy scale linearly with portfolio nameplate capacity; duration and percentage performance do not. Mixed-portfolio evidence is precomputed at every 5% wind-share value supported by the UI. Durations above 12 h are labelled **long-duration storage territory** rather than conventional short-duration BESS.

## Forecast-day reserve and SOC planning

The Stage B planner carries the selected future design into the latest V2 forecast day. It builds an asymmetric empirical **q10–q90 signed-residual range** using only earlier out-of-sample dates, then converts the distance below/above the scheduled export into downward discharge-reserve and upward charging-headroom requirements.

Reserve energy is evaluated over a rolling horizon equal to the installed battery duration. These requirements define an energy-feasible starting-SOC band. If the operator-entered current SOC is already inside that band, the planner recommends **hold current SOC**. If it is outside, the planner moves only to the nearest safe boundary and reports the grid energy needed for that preparation. If no starting SOC can cover both directional energy requirements simultaneously, it does not force an unvalidated compromise: it holds current SOC and reports the reserve-coverage shortfall.

For the default 100 MW 50/50 portfolio and 25 MW / 200 MWh (8 h) design, the current 3 September forecast gives a safe starting-SOC band around **33.6–76.6%**; therefore a current 50% SOC requires no adjustment. The largest rolling downside requirement is about **44.8 MWh** and the largest upward headroom requirement about **28.3 MWh**. This is a reserve-readiness calculation, not a simulated future dispatch trajectory.

A formal prior-data-only backtest covers 420 eligible dates. At a 50% baseline SOC, the solar and mixed designs remain inside their calculated safe bands on all eligible dates, so the conservative policy makes no unnecessary adjustments. The directional interval achieves about **88.7% solar, 83.3% mixed and 81.9% wind coverage** on Apr–Jun 2026. Wind is explicitly flagged when its 24 h two-sided energy envelope cannot fit inside the installed usable SOC range.

## Risk & Value decision layer

Stage 6 converts the 450-day BESS firming evidence into a transparent pre-feasibility intervention decision. It reports baseline/residual physical exposure, monetised risk reduction, NPV, BCR, simple payback, break-even consequence value, maximum CAPEX, CAPEX/consequence sensitivity and a risk-value frontier. Monetary inputs are explicit scenario assumptions, not observed market revenues or bankable project costs.

Stage 6B adds complete-day block-resampled Monte Carlo with uncertainty in consequence value, CAPEX, OPEX, battery availability and degradation. It reports P10/P50/P90 NPV, probability of negative NPV, 95% VaR/CVaR using `investment loss = -NPV`, probability of failing the selected firming/reliability gate, and named downside stress cases. The default 100 MW 50/50, 25 MW / 200 MWh case is economically negative under the illustrative default assumptions, while smaller batteries can have better NPV but fail the technical 90/90 gate.

## GB market-linked optimisation

Stage 9 connects the battery evidence to real public GB market references. The repository now carries a 450-day / 21,600-period Elexon APX Market Index archive aligned to the V2 forecast-error and System Price evidence. Market Index Price is explicitly labelled **short-term wholesale market reference**, not a day-ahead auction price.

Three ex-post upper-bound strategies are separated: settlement-aware firming using realised System Price plus priced SOC restoration; perfect-foresight wholesale arbitrage using Market Index Price; and a co-optimiser that shares one physical battery MW/SOC/throughput budget between firming and arbitrage. Under the frozen default 100 MW 50/50, 25 MW / 200 MWh case and a £2/MWh scenario throughput cost, annualised values are about **-£0.061m reactive firming**, **£0.270m settlement-aware firming**, **£1.904m arbitrage-only**, and **£2.049m co-optimised**. These are realised-price upper bounds, not deployable revenue forecasts.

A separate adapter validates user-supplied licensed day-ahead prices with publication timestamps and issue-time cutoffs, so an authorised Nord Pool/EPEX feed can be added later without changing the optimisation architecture.

The pre-delivery price forecast is now operationalised as an atomic bundle pipeline. A scheduled GitHub Actions job builds a candidate from prior APX days, validates period count/target/checksum, archives the previous valid bundle and publishes only after validation. The Studio labels the result **LIVE**, **RECONSTRUCTED** or **STALE** and exposes fallback status instead of silently using an invalid refresh.

The forecast-based market layer now removes price perfect foresight using an expanding ridge forecast trained only on earlier Market Index settlement dates. Across 420 eligible days, price MAE is **£20.0/MWh**, 11.2% better than the previous-observed-same-period baseline. A 25 MW / 200 MWh forecast-selected arbitrage schedule captures about **60.0%** of the perfect-information upper bound overall and **63.4%** on Apr-Jun 2026. Preserving the Stage B SOC reserve corridor reduces capture to **49.6%**, quantifying the market opportunity cost of maintaining renewable-risk headroom.

The current 3 September forecast-day market bundle is explicitly marked as an **as-if reconstruction generated after delivery began**, while still excluding all target-day Market Index observations. Future automation should generate this bundle before the target day starts.

## Renewable-only continuous-SOC stress test

For a 100 MW virtual portfolio with a 25 MW / 50 MWh battery, 90% round-trip efficiency, 10–90% SOC limits and no grid charging, continuous operation absorbs about **33.5% of wind**, **50.2% of solar** and **44.4% of 50/50 mixed** absolute forecast-deviation energy. SOC ends at its minimum bound, showing that energy availability and conversion losses matter across long horizons.

The initial 1h/2h/4h sizing grid does **not** reach an 80% long-run target. With the standard 50% starting SOC, the first tested 80% solutions use about **1,800 MWh wind**, **400 MWh solar** and **800 MWh mixed**. A conservative sensitivity that starts at the 10% minimum SOC removes the one-time initial-energy reserve: wind and solar remain about **1,800 MWh** and **400 MWh**, while mixed rises modestly to **900 MWh**. These are virtual benchmark results, not site-design recommendations.

## Run locally

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m pytest -q
python app.py
```

Open `http://127.0.0.1:8050`.

## Deploy separately on Render

1. Create a new GitHub repository for this directory.
2. Push the project to the default branch.
3. Create a new Render Blueprint or web service from that repository.
4. Render reads `render.yaml` and starts `gunicorn app:server`.

The resulting service has its own URL and deployment lifecycle. It does not call the earlier website.

## Data replacement contract

The application reads `data/historical_backtest.csv`. The adapter accepts CSV or Parquet and requires:

```text
settlement_date
settlement_period
valid_time_utc
wind_cf
solar_cf
wind_pred_cf
solar_pred_cf
```

A valid GB target day has 46, 48 or 50 settlement periods. Duplicate or incomplete days are rejected.

## Roadmap

### Release 2

- interactive date-range and seasonal/regime comparison using the installed V2 archive;
- scenario comparison;
- richer storage-sizing evidence by season and weather regime;
- shareable URL state.

### Release 3

- dedicated P10/P50/P90 forecast bundles or weather-ensemble probabilistic forecasts;
- compare the current residual-based directional reserve envelope with true probabilistic forecast tails;
- compare the current residual-based reserve envelope with dedicated probabilistic forecasts and then test price-aware preparation timing using a correctly defined market/contracting model.

### Release 4

- automated versioned bundle publishing from the forecasting pipeline;
- stale-data and schema checks;
- last-valid-bundle fallback;
- data/model version display.

A later commercial module may add correctly defined price forecasting and dispatch economics, but it remains outside the initial firming scope.

## Learning checkpoints

The project includes `docs/LEARNING_CHECKPOINT_1.md`. It asks the project owner to verify four settlement periods manually, identify power versus energy constraints and explain the result in interview-ready language.
