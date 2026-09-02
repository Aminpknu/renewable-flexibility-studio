# Validation report

## Automated analytical validation

Command:

```bash
python -m pytest -q
```

Latest verified result:

```text
15 passed
```

Coverage includes historical-bundle validation, complete 46/48/50-period days, wind/solar/mixed portfolio scaling, battery power/SOC/efficiency constraints, no simultaneous charge/discharge, firming metrics, sizing search, V2 manifest integrity, and explicit proof that multi-day SOC carries across midnight without a daily reset.

## V2 historical evidence

The installed bundle contains 21,600 half-hour observations across 450 out-of-sample target days from 1 April 2025 to 30 June 2026. It combines 360 expanding-window out-of-fold development days and 90 frozen locked-test days. Final-refit in-sample predictions are not used for the battery backtest.

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
| Wind | 50 MW / 1,800 MWh (36 h) | 82.62% |
| Solar | 25 MW / 400 MWh (16 h) | 80.54% |
| Mixed 50/50 | 50 MW / 800 MWh (16 h) | 80.66% |

These results show that, under the current no-grid-charging reactive strategy, long-horizon firming is primarily an energy/SOC problem. They are virtual portfolio benchmarks, not site-specific battery recommendations.

## Runtime smoke validation

The Dash application was launched on the user's workstation with `data/historical_backtest.csv`. The root endpoint and `/_dash-layout` both returned HTTP 200; the rendered layout included dates from 1 April 2025 through 30 June 2026. The server was then terminated cleanly.

The original 1 June 2025 scenario remains only as a compact learning/unit-test fixture and should not be used as the headline sizing result.
