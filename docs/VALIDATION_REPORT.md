# Validation report

## Automated analytical validation

Command:

```bash
python -m pytest -q
```

Latest verified result:

```text
22 passed
```

Coverage includes historical-bundle validation, complete 46/48/50-period days, wind/solar/mixed portfolio scaling, battery power/SOC/efficiency constraints, no simultaneous charge/discharge, firming metrics, sizing search, V2 manifest integrity, and explicit proof that multi-day SOC carries across midnight without a daily reset.

## V2 historical evidence

The installed bundle contains 21,600 half-hour observations across 450 out-of-sample target days from 1 April 2025 to 30 June 2026. It combines 360 expanding-window out-of-fold development days and 90 frozen locked-test days. Final-refit in-sample predictions are not used for the battery backtest.

## Forecast-uncertainty interval validation

The generation chart now uses a nominal 80% rolling prediction interval calibrated only from earlier out-of-sample residuals. The method uses a 90-day lookback, requires at least 30 prior target days, and uses up to 600 prior forecasts with the closest forecast capacity factor for the local residual scale.

| Portfolio | Eligible-history coverage | Locked Apr-Jun 2026 coverage | Mean interval width for 100 MW portfolio |
|---|---:|---:|---:|
| Wind | 80.60% | 80.74% | 13.56 MW |
| Solar | 76.99% | 81.13% | 4.18 MW |
| Mixed 50/50 | 79.92% | 80.79% | 7.62 MW |

The selected target day's actual output is not used to construct its own band. Tests explicitly verify that calibration ends before the selected date and that dates with fewer than 30 prior days show no interval. For 30 June 2026 wind, the expected range contains actual output in only 21 of 48 periods (43.75%), with 27 periods outside the band; this supports the interpretation that the day was an unusually difficult forecast realization.

The interval is a rolling residual-based uncertainty estimate and should not be described as a true ECMWF ensemble P10/P50/P90 forecast or as having an exact exchangeable-data conformal guarantee under time-series dependence.

## 450-day continuous-SOC benchmark

Configuration: 100 MW virtual portfolio, 25 MW / 50 MWh battery, 90% round-trip efficiency, 50% initial SOC, 10–90% SOC limits, 30-minute intervals, reactive firming and no grid charging.

| Portfolio | Error-energy reduction | Ending SOC |
|---|---:|---:|
| Wind | 33.47% | 10% |
| Solar | 50.23% | 10% |
| Mixed 50/50 | 44.39% | 10% |

The result differs sharply from the original one-day demonstration because the battery receives no artificial daily SOC reset. With continuous operation, slight net deficit bias plus round-trip losses progressively reduce stored energy.

Within the original 1h/2h/4h grid, the strongest tested 50 MW / 200 MWh battery achieves 58.14% wind, 70.85% solar and 66.45% mixed firming. None reaches the 80% long-run target; the simulations are dominated by energy-limited periods rather than power-limited periods.

## Extended energy-duration diagnostic

Because the standard grid misses 80%, `scripts/run_extended_sizing.py` tests 25/50 MW batteries with 4–48 hour durations. The first tested configurations meeting 80% are:

| Portfolio | First tested ≥80% | Reduction |
|---|---:|---:|
| Wind | 50 MW / 1,800 MWh (36 h) | 81.11% |
| Solar | 25 MW / 400 MWh (16 h) | 80.55% |
| Mixed 50/50 | 25 MW / 900 MWh (36 h) | 80.10% |

The table uses the conservative start-at-minimum-SOC sensitivity so no one-time initial stored-energy reserve is available. With the standard 50% initial SOC, wind and solar require the same tested energy capacities, while mixed first reaches 80% at 800 MWh. These results show that, under the current no-grid-charging reactive strategy, long-horizon firming is primarily an energy/SOC problem. They are virtual portfolio benchmarks, not site-specific battery recommendations.

## Runtime smoke validation

The Dash application was launched on the user's workstation with `data/historical_backtest.csv`. The root endpoint and `/_dash-layout` both returned HTTP 200; the rendered layout included dates from 1 April 2025 through 30 June 2026. The server was then terminated cleanly.

The original 1 June 2025 scenario remains only as a compact learning/unit-test fixture and should not be used as the headline sizing result.
