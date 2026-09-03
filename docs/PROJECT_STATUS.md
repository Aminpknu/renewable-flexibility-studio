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
- extended 4–48h renewable-only energy-duration diagnostic;
- main future-sizing engine: 2,541 precomputed grid-connected designs across all 5% wind-share steps;
- 80/90/95% firming targets and 80/90/95% daily reliability gates across two historical regimes;
- tracked pre-day grid import/export required to restore 50% SOC;
- leakage-safe rolling 80% forecast-uncertainty interval with historical/locked coverage validation;
- out-of-range historical markers and selected-day uncertainty summary in the generation chart;
- forecast-day planning from the latest V2 forecast bundle, with no future actual/dispatch assumption;
- directional empirical q10–q90 residual range using prior out-of-sample evidence only;
- Stage B reserve-readiness planner: operator current SOC, rolling downward/upward energy requirements, safe starting-SOC band, minimum pre-day adjustment and critical risk windows;
- guardrail that holds current SOC and reports reserve shortfall when no two-sided safe SOC band exists;
- 420-day-per-portfolio prior-data-only validation of the Stage B policy;
- live half-hourly GB National Demand Forecast context from Elexon/NESO;
- frozen 450-day Elexon System Price/Net Imbalance Volume archive aligned to all 21,600 V2 historical periods;
- selected-day BSC-style imbalance settlement view before/after battery firming;
- 450-day gross cash-out exposure and daily tail-risk benchmark, explicitly separated from profit;
- Stage 6A deterministic physical risk and value appraisal: NPV, BCR, payback, switching values, availability, sensitivity and risk-value frontier;
- Stage 6B block-resampled Monte Carlo: P10/P50/P90 NPV, negative-NPV probability, VaR/CVaR, technical-gate failure probability and stress scenarios;
- Stage 9 market layer: 450-day Elexon APX Market Index archive, settlement-aware firming, perfect-foresight wholesale arbitrage and shared-battery firming/arbitrage co-optimisation;
- one-page Dash interface and CSV export;
- public GitHub repository with GitHub Actions configuration;
- automated test suite covering physical, uncertainty, tomorrow-planning and settlement logic;
- successful local Dash HTTP/layout smoke test;
- methodology, schema 2.0 data contract, validation report and learning checkpoint.

## Forecasting dependency status

Forecasting V2 is packaged separately on branch `feature/v2-spatial-production`, commit `c918a8c`, and pushed to GitHub. It is not merged into `master` and is not deployed to the existing live forecasting service. The Flexibility Studio consumes only the exported historical bundle.

## Next analytical stages

1. Connect an authorised day-ahead auction feed or build an issue-time-correct price forecast, then convert the current perfect-information market benchmarks into deployable strategies.
2. Extend market co-optimisation to balancing/ancillary-service revenue only after service-specific eligibility and commitment constraints are encoded.
3. Add date-range, seasonal and weather-regime comparison and quantify sizing/reserve sensitivity by wind/solar mix.
4. Upgrade the operational directional residual range to dedicated probabilistic P10/P50/P90 or weather-ensemble uncertainty and compare both approaches.
5. Automate the versioned forecast-bundle handoff, freshness/stale-data checks and fallback behavior.

## Learning fixture

`python -m scripts.run_demo` and `data/sample_historical.csv` are retained for the original four-period manual learning checkpoint. They are not the main research evidence now.
