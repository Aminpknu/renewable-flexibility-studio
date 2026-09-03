# Validation report

## Automated analytical validation

Command:

```bash
python -m pytest -q
```

Latest verified result:

```text
50 passed
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

## Forecast-day reserve/SOC and GB grid-context validation

The Studio consumes `data/latest_forecast.csv`, a compact V2 forecast-only bundle containing one complete 46/48/50-period target day. Forecast-day mode never creates a future actual-generation series or charge/discharge trajectory. It automatically resolves the battery selected by the current future-sizing target/reliability gate and asks whether the operator's current SOC can support a directional renewable-forecast uncertainty envelope over a rolling horizon equal to the installed battery duration.

Operational uncertainty is separate from the symmetric historical-review band. It uses local **signed** out-of-sample residuals from the previous 180 days, requires at least 30 prior target dates, selects up to 600 forecasts with the closest forecast capacity factor and applies empirical q10/q90 residual bounds. On the Apr–Jun 2026 regime, achieved directional coverage is **81.85% wind, 88.70% solar and 83.31% mixed**. These are empirical residual bounds, not ECMWF ensemble P10/P90 forecasts.

For the current 3 September 2026 bundle and the default 100 MW mixed portfolio, Stage A selects **25 MW / 200 MWh (8 h)**. The q10–q90 range uses 115 earlier out-of-sample days (7 March–30 June 2026), with mean width **7.99 MW**. The largest 8 h rolling downward requirement is **44.80 MWh**, the largest upward charging-headroom requirement is **28.32 MWh**, and peak directional MW needs are **6.18 MW down / 3.75 MW up**. After round-trip-efficiency treatment and the 10–90% SOC limits, the energy-feasible starting band is **33.61–76.57% SOC**. A current 50% SOC therefore receives the recommendation **hold current SOC**, with 100% reserve coverage under this empirical envelope. The critical downside window begins 3 September 08:30 UTC and ends 16:30 UTC; the critical upside window is 08:00–16:00 UTC.

A formal prior-data-only backtest was run for the Stage A 90%/90% designs across **420 eligible dates per portfolio**. For solar (25 MW / 150 MWh) and mixed (25 MW / 200 MWh), a 50% starting SOC was inside the calculated safe band on all 420 eligible dates, so the conservative policy made **zero unnecessary SOC adjustments** and produced exactly the same historical firming performance as the fixed-50% baseline. This is an important validation result: the planner does not manufacture an SOC change simply because the uncertainty band is asymmetric.

For wind (15 MW / 360 MWh, 24 h), the full two-sided directional energy envelope is infeasible on 268 of 420 eligible dates. An earlier proportional-compromise SOC rule was rejected after it could worsen some historical days. The released guardrail holds current SOC whenever no full safe band exists and reports the reserve shortfall. On the Apr–Jun 2026 wind regime this guarded policy made no day worse and left overall firming unchanged at **98.31%**. The planner is therefore a reserve-readiness and preparation tool, not a claim that changing SOC always improves mean forecast error.

The official Elexon Insights day-ahead demand endpoint is explicitly filtered to the target settlement date and validated against the 46/48/50-period GB-day contract. NESO National Demand Forecast remains system-scale context only; the virtual portfolio is not claimed to be a national balancing asset.

## Future battery-sizing validation

The main design grid contains **2,541** precomputed configurations: 21 wind-share mixes × 11 power fractions × 11 durations. It uses the grid-connected reserve mode with 50% pre-day SOC restoration, 10–90% SOC bounds and 90% round-trip efficiency. Grid restoration energy is recorded separately. Canonical grid SHA-256: `3c4a3063cc97fb23f0ded7fc85f21fd3d81a54abbb21df08335eecb040573463`.

A stable design must meet both the selected overall firming target and the selected daily reliability target in Apr 2025–Mar 2026 **and** Apr–Jun 2026. For the default 90%/90% gate on a 100 MW portfolio:

| Portfolio | Minimum stable tested design | Apr25–Mar26 overall / days | Apr–Jun26 overall / days |
|---|---:|---:|---:|
| Solar | 25 MW / 150 MWh (6 h) | 95.42% / 93.89% | 96.09% / 91.11% |
| Mixed 50/50 | **25 MW / 200 MWh (8 h)** | **96.30% / 93.33%** | **97.53% / 95.56%** |
| Wind | 15 MW / 360 MWh (24 h) | 95.08% / 91.11% | 98.31% / 95.56% |

For the default mixed design, restoring SOC to 50% requires on average about **21.1 MWh/day grid import** and **15.4 MWh/day grid export** across the 450-day evidence set. Those flows are inputs to the future economics stage and are not assumed to be free.

The earlier renewable-only continuous design scan is retained as a stress test. Without pre-day grid SOC restoration, even the largest tested mixed cases reached only about **78.9% overall absorption in Apr–Jun 2026**, so no 80% two-period stability design existed. This is why the practical sizing mode is explicitly grid-connected rather than disguising an infeasible no-grid requirement as a battery-sizing answer.

## Historical Elexon imbalance-settlement validation

A frozen Elexon System Price/Net Imbalance Volume archive was built for exactly the same 450 target days and 21,600 settlement periods as the V2 forecast-error bundle. API retrieval completed for all 450 dates with zero request failures. A subsequent CSV-integrity scan detected two local OneDrive line-write collisions; 22 August 2025 and 22 November 2025 were re-fetched, and the full archive was rebuilt atomically and revalidated to 21,600 rows, 450 dates, one 46-period day, 448 48-period days and one 50-period day. Canonical SHA-256 (UTF-8 with LF line endings): `2d566f53f3274d259f7587746039546b88912563437d7ae8b146b458e97e20fd`.

Tests verify 30-minute MW-to-MWh conversion, BSC-style cashflow signs, missing-price rejection and date+settlement-period keys for multi-day joins. For the default 100 MW / 25 MW-50 MWh continuous-SOC benchmark, gross System-Price cash-out exposure changes as follows:

| Portfolio | 450-day gross exposure before | After battery | Reduction |
|---|---:|---:|---:|
| Wind | £3.554m | £2.303m | 35.21% |
| Solar | £1.192m | £0.614m | 48.47% |
| Mixed 50/50 | £2.040m | £1.124m | 44.90% |

For the mixed portfolio, mean daily gross exposure falls from £4,533 to £2,497, the 95th-percentile day falls from £8,711 to £7,186, and exposure is lower on 440 of 450 days. These figures are **settlement-risk magnitudes, not profit or avoided cost**. Signed settlement cashflow is reported separately because some imbalances can produce receipts; a proper trading-value calculation still requires a contracted/day-ahead reference price and battery operating/degradation costs.

For the 30 June 2026 wind example used in the interface review, gross exposure falls from about £13,276 to £10,826 (18.46%) while System Price ranges from about £67 to £175/MWh.

## Renewable-only continuous-SOC stress test

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

## Stage 9 market-optimisation validation

The public Elexon APX Market Index archive covers all 450 V2 target dates and 21,600 settlement periods, including 46/50-period daylight-saving days. The archive is checksum-locked and aligned by settlement date/period with the historical forecast and System Price bundles.

The market optimiser is tested against hand-calculated cases for price-priority firming, terminal SOC restoration, throughput-cost switching, negative wholesale prices, wholesale arbitrage, mutually exclusive charging/discharging and shared MW/SOC constraints in the firming/arbitrage co-optimiser. The full repository suite passes after the market layer is installed.

For the default 100 MW 50/50 portfolio and Stage A 25 MW / 200 MWh design, using a £2/MWh scenario throughput cost, the 450-day ex-post evidence annualises to approximately **-£0.061m reactive firming**, **£0.270m settlement-aware firming**, **£1.904m wholesale arbitrage-only**, and **£2.049m co-optimised firming plus arbitrage**. Mean daily physical error reduction is about **98.3% reactive**, **47.8% settlement-aware**, and **40.1% co-optimised**.

These market values use realised forecast error and/or realised prices and are therefore perfect-information upper-bound evidence. APX Market Index Price is labelled a short-term wholesale reference, not a day-ahead auction price. No public result is described as deployable revenue until an issue-time-correct price forecast or authorised day-ahead price feed is connected.

## Pre-delivery market-price strategy validation

An expanding ridge forecast of APX Market Index Price was backtested on 420 target days after a 30-day warm-up. All target-day features use settlement dates strictly earlier than the target date. MAE is **£20.01/MWh** versus **£22.53/MWh** for a previous-observed-same-period baseline, an **11.2% improvement**; forecast R² is **0.300** versus **-0.077** for that naive baseline.

The forecast-selected 25 MW / 200 MWh arbitrage strategy captures **60.0%** of the matching perfect-information arbitrage upper bound across the 420 days and **63.4%** across Apr-Jun 2026. A Stage B SOC-corridor-constrained version remains feasible on all 420 mixed-portfolio days and captures **49.6%** overall. Positive realised net margin occurs on 89.3% of forecast-strategy days and 90.7% of reserve-aware days.

The current 3 September forecast-day market file is flagged `as_if_reconstruction_after_target_start`. It excludes all target-day Market Index observations but was generated after delivery began, so it is not counted as an operationally issued forecast.

## Automated market-forecast publication validation

The market forecast publisher now writes to temporary files first and validates target date, 46/48/50-period completeness, duplicate keys, finite prices and SHA-256 before replacing the published bundle. Unit tests verify that a failed refresh retains the existing valid bundle and that a post-start reconstruction cannot overwrite an already-issued LIVE pre-delivery bundle.

The scheduled workflow is configured for 18:15 UTC daily plus manual dispatch. The application reads the validated manifest and reports LIVE, RECONSTRUCTED, STALE_TARGET or STALE_TIME alongside pipeline fallback status. The current 3 September 2026 bundle is correctly classified RECONSTRUCTED because it was generated after target start; no claim of a genuinely issued pre-delivery schedule is made for that file.

After this operational pipeline change, the complete offline suite passes **114 tests** and `git diff --check` is clean.

## Quick Reserve availability-stacking validation

The QR archive contains **8,744 PQR/NQR rows across 4,372 half-hour delivery windows** from the NESO EAC Results Summary, checksum-locked under the NESO Open Data Licence. The model enforces whole-MW reserve commitments, `PQR + NQR <= BESS MW`, conservative directional power headroom, 10–90% SOC, terminal SOC restoration and configurable consecutive-window state-of-energy protection.

For the default 25 MW / 200 MWh BESS on the 90 locked Apr–Jun 2026 dates, the two-window guard annualises to **£2.38m wholesale arbitrage-only**, **£1.35m QR availability-only**, and **£3.13m shared-battery stacked** under realised prices and a £2/MWh throughput assumption. The independent sum is **£3.73m/yr**, so physical co-optimisation removes about **£0.61m/yr** of double-counted value. Mean stacked PQR/NQR commitments are about **13.0 / 8.6 MW**.

One-, two- and four-window energy guards give stacked regime annualisations of about **£3.17m, £3.13m and £3.08m/yr**, respectively. QR utilisation payment/activation is excluded; the asset is assumed to be a price taker accepted at the observed clearing price, so these are perfect-information screening values and not proof of prequalification, acceptance or earned service revenue.

After the Quick Reserve packet and UI integration, the complete offline repository suite passes **122 tests** and `git diff --check` is clean.

The three-use extension adds System-Price-valued renewable firming to the same wholesale/QR battery. Under the baseline two-window guard, firming + arbitrage annualises to **£2.51m/yr** and the full firming + arbitrage + QR stack to **£3.27m/yr**, an incremental **£0.76m/yr** QR availability value. The independent firming/arbitrage + QR-only sum is about **£3.86m/yr**, so shared-battery optimisation removes approximately **£0.60m/yr** of double-counting while retaining **37.0%** mean renewable-error reduction.

After the full three-use firming/arbitrage/Quick Reserve integration, the repository suite passes **124 tests** with a clean diff check.
