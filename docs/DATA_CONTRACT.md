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

## Live grid context

Forecast-day mode may query the official Elexon Insights day-ahead demand API and then explicitly filter to the target settlement date. The grid adapter validates one complete 46/48/50-period National Demand Forecast series. This grid context is external public data and is not part of the renewable forecast bundle.

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
