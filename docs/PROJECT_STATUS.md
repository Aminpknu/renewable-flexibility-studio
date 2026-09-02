# Project status

## Completed

- standalone Flexibility Studio with no runtime dependency on the forecasting website;
- V2 out-of-sample historical bundle: 21,600 half-hours across 450 target days;
- 360 development OOF days plus 90 locked-test days;
- wind, solar and mixed virtual portfolio construction;
- physically constrained reactive BESS simulation;
- continuous multi-day SOC with no midnight reset;
- power, duration, initial SOC and round-trip-efficiency controls;
- decision-oriented error, energy, cycling and limitation metrics;
- interactive 1h/2h/4h sizing grid;
- 450-day continuous-SOC benchmark;
- extended 4–48h energy-duration diagnostic;
- leakage-safe rolling 80% forecast-uncertainty interval with historical/locked coverage validation;
- out-of-range historical markers and selected-day uncertainty summary in the generation chart;
- Tomorrow planning from the latest V2 forecast bundle, with no future actual/dispatch assumption;
- live half-hourly GB National Demand Forecast context from Elexon/NESO;
- one-page Dash interface and CSV export;
- Render/GitHub Actions configuration;
- 26 passing automated tests;
- successful local Dash HTTP/layout smoke test;
- methodology, schema 2.0 data contract, validation report and learning checkpoint.

## Forecasting dependency status

Forecasting V2 is packaged separately on branch `feature/v2-spatial-production`, commit `c918a8c`, and pushed to GitHub. It is not merged into `master` and is not deployed to the existing live forecasting service. The Flexibility Studio consumes only the exported historical bundle.

## Next analytical stages

1. add date-range, seasonal and weather-regime comparison to the Studio interface;
2. quantify performance by OOF versus locked-test segment and by wind/solar mix;
3. upgrade Tomorrow planning to dedicated probabilistic P10/P50/P90 or weather-ensemble uncertainty and compare it with the residual-based range;
4. backtest and refine uncertainty-aware initial SOC/reserve allocation;
5. build the Risk & Value decision layer: consequence value, avoided exposure, CAPEX/OPEX, NPV, BCR, switching values and sensitivity;
6. add Monte Carlo/block-bootstrap downside metrics after the deterministic value layer is stable;
7. publish the already-initialized standalone Git repository and deploy the Flexibility Studio separately.

## Learning fixture

`python -m scripts.run_demo` and `data/sample_historical.csv` are retained for the original four-period manual learning checkpoint. They are not the main research evidence now.
