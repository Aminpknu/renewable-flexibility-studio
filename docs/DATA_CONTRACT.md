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

## Independence rule

The flexibility website reads a versioned file bundle. It must not call the forecasting Dash service or import its page modules. A later automated publishing workflow may replace the bundle, but the standalone product retains its own schema validation, checksum and deployment lifecycle.
