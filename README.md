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
- inspect the latest **tomorrow** V2 renewable forecast as a planning schedule with a future uncertainty band;
- place that schedule in real GB grid context using the official half-hourly NESO National Demand Forecast served by Elexon Insights;
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

## Current 450-day continuous-SOC evidence

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

- P10/P50/P90 forecast bundles;
- uncertainty-aware initial SOC and reserve allocation;
- upgrade the current Tomorrow planning band to dedicated P10/P50/P90 or weather-ensemble probabilistic forecasts.

### Release 4

- automated versioned bundle publishing from the forecasting pipeline;
- stale-data and schema checks;
- last-valid-bundle fallback;
- data/model version display.

A later commercial module may add correctly defined price forecasting and dispatch economics, but it remains outside the initial firming scope.

## Learning checkpoints

The project includes `docs/LEARNING_CHECKPOINT_1.md`. It asks the project owner to verify four settlement periods manually, identify power versus energy constraints and explain the result in interview-ready language.
