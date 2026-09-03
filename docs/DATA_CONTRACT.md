# Historical bundle data contract

## Schema version 2.0

The current application reads `data/historical_backtest.csv`, a 450-day out-of-sample V2 forecast bundle covering 1 April 2025 to 30 June 2026.

Required analytical fields:

| Field | Type | Meaning |
|---|---|---|
| `settlement_date` | date | GB local target date |
| `settlement_period` | integer | Physical settlement period number |
| `valid_time_utc` | timezone-aware timestamp | Interval time in UTC |
| `wind_cf` | float | Actual embedded wind capacity factor |
| `solar_cf` | float | Actual embedded solar capacity factor |
| `wind_pred_cf` | float | Out-of-sample day-ahead wind CF prediction |
| `solar_pred_cf` | float | Out-of-sample day-ahead solar CF prediction |

The installed bundle also records `evaluation_segment` (`development_oof` or `locked_test`), fold identifier where relevant, technology MW values, and embedded capacities for auditability.

A valid GB target day has 46, 48 or 50 settlement periods. Duplicate keys, incomplete days, missing required values and invalid timestamps are rejected by the adapter.

## Out-of-sample rule

The 360 development days use expanding-window out-of-fold predictions. The 90 April–June 2026 days use frozen locked-test predictions. Final-refit in-sample predictions are not used for battery backtesting.

Explicit source exclusions are 6–10 August 2025 and 24 June 2026. They are not synthetically filled.

## Latest forecast bundle

Forecast-day planning reads `data/latest_forecast.csv`, validated separately from the historical archive. The battery shown in forecast-day planning is resolved from `outputs/design_sizing_grid_100mw.csv` using the currently selected future-design target/reliability gate; the historical battery controls do not determine the installed design. Required fields are forecast creation time, one target date, settlement period, valid time, wind/solar predicted capacity factors and embedded capacities. The bundle must contain exactly one complete 46/48/50-period target day. `data/latest_forecast_manifest.json` records target date, creation time, row count and SHA-256 checksum.

The standalone Studio does not run or import the forecasting ML models. The forecasting project remains the producer of the forecast bundle; `scripts/sync_latest_forecast.py` is the local/manual handoff until automated cross-repository publishing is enabled.

`data/latest_spatial_forecast.csv` is the companion ten-zone allocation bundle produced from the same target-day weather run. It contains one row per `(settlement_period, zone)` and therefore 10?46/48/50 rows. Wind and solar allocation shares must each sum to one within every settlement period. The bundle is reconciled to the national V2 forecast; it is not an independently observed city-generation target.

`data/spatial_capacity_weights.csv` contains fixed DESNZ REPD operational wind/solar proxy shares assigned to the nearest of the ten V2 weather locations. Its manifest records the July 2026 REPD source URL, checksum, OGL status and limitations. NESO national embedded capacity remains authoritative for total MW.

## Live grid context

Forecast-day mode may query the official Elexon Insights day-ahead demand API and then explicitly filter to the target settlement date. A complete pre-delivery series must contain 46/48/50 contiguous periods. After the target day has started, Elexon may return only the remaining contiguous periods; the adapter accepts such a suffix only when it ends at SP46/48/50 and labels it `partial_remaining_day`. This grid context is external public data and is not part of the renewable forecast bundle.

## Forecast-day reserve-planning evidence

Operational reserve planning derives its directional q10–q90 range at runtime from `data/historical_backtest.csv` plus `data/latest_forecast.csv`; it does not require a separate external forecast service. The operator supplies current SOC in the UI, while battery MW/MWh comes from the selected row in `outputs/design_sizing_grid_100mw.csv` after scaling to portfolio capacity.

`outputs/reserve_planning_validation.json` is the frozen validation summary for the baseline 50% current-SOC policy and Stage A 90%/90% designs. `outputs/reserve_planning_daily.csv` contains the corresponding daily audit rows for solar, 50/50 mixed and wind. These files are **validation evidence**, not runtime inputs to the forecast-day callback. The runtime planner recalculates the reserve band from the current forecast bundle and operator-entered SOC.

## Future sizing design grid

`outputs/design_sizing_grid_100mw.csv` is the precomputed practical future-sizing evidence for a 100 MW reference portfolio. It contains 2,541 rows covering every 5% wind-share step, 11 power fractions and 11 durations. Required performance fields include development/Apr–Jun overall absorption, daily reliability at 80/90/95% targets, grid SOC-restoration import/export, limitation counts and operating-mode label.

`outputs/design_sizing_grid_manifest.json` locks the candidate grid, SOC/efficiency assumptions, selection rule, default 90%/90% designs and a line-ending-independent SHA-256. Power, MWh and grid-restoration energy scale linearly with portfolio nameplate MW; duration and percentage performance remain unchanged.

The operating-mode value is `grid_connected_daily_soc_restore_50pct`. This means SOC is restored to 50% before each operating day; no intraday grid charging is included in the firming simulation.

## Historical Elexon settlement bundle

Historical grid-settlement analysis reads `data/elexon_system_prices.csv`. It contains one official Elexon System Price and Net Imbalance Volume record for every settlement period in the same 450 target days as `historical_backtest.csv`: 21,600 rows in total, including the one 46-period and one 50-period daylight-saving days.

The key is `(settlement_date, settlement_period)`. Required fields are System Price, System Buy Price, System Sell Price, Net Imbalance Volume and system direction. The adapter verifies the current single-price condition (System Buy Price = System Sell Price) and rejects missing or duplicate settlement keys. `data/elexon_system_prices_manifest.json` records the endpoint, coverage, row count and SHA-256 checksum.

The final frozen archive was rebuilt atomically after a write-integrity check identified two local OneDrive line collisions. The affected dates were re-fetched independently and the full 21,600-row file was revalidated before use.

## Independence rule

The flexibility website reads a versioned file bundle. It must not call the forecasting Dash service or import its page modules. A later automated publishing workflow may replace the bundle, but the standalone product retains its own schema validation, checksum and deployment lifecycle.

## Historical Elexon Market Index bundle

Market optimisation reads `data/elexon_market_index_prices.csv`, containing APX Market Index Data (`APXMIDP`) for the same 450 V2 target days and 21,600 settlement periods. Required fields are settlement date/period, UTC valid time, provider, Market Index Price and Market Index Volume.

The public semantic label is **short-term GB wholesale market reference; not day-ahead auction price**. `data/elexon_market_index_prices_manifest.json` records provider, endpoint, coverage, row count and a line-ending-independent SHA-256.

A separate licensed day-ahead adapter accepts `settlement_date`, `settlement_period`, `valid_time_utc`, `publication_time_utc`, `day_ahead_price_gbp_per_mwh` and `source`. It rejects duplicate or incomplete GB days and can enforce that every price was published before an explicit issue cutoff. Licensed NEMO prices are not bundled in the public repository.

## Market-price forecast and pre-delivery strategy evidence

`outputs/market_optimisation/price_forecast_backtest.csv` contains 420 expanding-window APX Market Index forecasts generated only from earlier settlement dates. `pre_delivery_strategy_daily.csv` and `pre_delivery_strategy_summary.json` record realised margins for schedules selected from those forecasts, the matching perfect-information upper bound, and the Stage B reserve-aware variant.

`data/latest_market_price_forecast.csv` is the compact forecast-day price-signal bundle. Its manifest records source-history coverage, generation time, target start time, leakage-safe issue rule and whether the bundle was actually created before delivery or later as an as-if reconstruction. It forecasts the public short-term APX Market Index reference and must never be relabelled as a licensed day-ahead auction price.

## Operational market-forecast publication state

`data/latest_market_price_forecast.csv` and its manifest are the current published market-price forecast bundle. Schema 1.1 adds `row_count`, SHA-256 and line-ending normalisation. Publication is atomic and occurs only after the candidate bundle validates.

`data/last_valid_market_price_forecast.csv` plus its manifest preserve the previous validated bundle before replacement. `data/market_forecast_pipeline_status.json` records refresh/publish/fallback state and the current bundle-health classification. A fallback can remain available for audit while being explicitly marked stale if its target does not match the renewable forecast target.

## NESO Quick Reserve clearing-price archive

`data/neso_quick_reserve_prices.csv` contains PQR/NQR Enduring Auction Capability clearing results used by the first ancillary-service stacking benchmark. It covers the Apr–Jun 2026 market regime plus the UTC crossover required to align the first GB delivery day, with one PQR and one NQR result per 30-minute delivery window where available.

Required fields are product/direction, UTC delivery start/end, 0.5 h window length, system cleared volume (MW), clearing price (£/MW/h) and the derived availability payment per contracted MW. The manifest records the NESO EAC resource ID, NESO Open Data Licence, query window, row/window counts and SHA-256. These are system auction results, not asset-specific accepted bids or utilisation instructions.

## Quick Reserve forecast-history and pre-delivery evidence

`data/neso_quick_reserve_forecast_history.csv` stitches the FY2025 archived and current EAC Results Summary resources for prior-date QR price forecasting. Its manifest records both source resource IDs, NESO Open Data Licence, 28,992 rows / 14,496 paired PQR/NQR windows and SHA-256. This extended history supports model training only; current-rule value validation remains Apr–Jun 2026.

`outputs/quick_reserve/quick_reserve_price_forecast_backtest.csv` contains prior-date-only PQR/NQR price forecasts and naive lag references. `quick_reserve_predelivery_daily.csv` and `quick_reserve_predelivery_allocations.csv` store the 90 locked-date capacity-allocation audit. `quick_reserve_predelivery_summary.json` locks the value-capture metrics and explicitly states that asset merit-order acceptance is not identified.

`quick_reserve_acceptance_diagnostic.json` stores aggregate Apr–Jun Sell Orders diagnostics showing that clearing-price threshold alone does not reliably identify execution. No participant names, unit identifiers or individual bid rows are copied into the repository; only aggregate validation counts/metrics are retained.
