# Methodology

## 1. Virtual portfolio construction

For a wind portfolio of nameplate capacity \(K\):

\[
G_t^{actual}=K\,CF_{wind,t}^{actual}
\]

\[
G_t^{forecast}=K\,\widehat{CF}_{wind,t}
\]

Solar is constructed identically. A mixed portfolio with wind share \(w\) uses:

\[
CF_t=w\,CF_{wind,t}+(1-w)CF_{solar,t}
\]

The national capacity-factor patterns are used as evidence for a virtual portfolio. The method is not claimed to recreate an individual asset.

## 2. Forecast error

\[
e_t=G_t^{actual}-G_t^{forecast}
\]

A positive value is surplus renewable generation relative to the forecast. A negative value is a deficit.

## 3. Battery state of charge

Battery energy capacity is \(E=P_{max}D\), where \(D\) is duration. The charging and discharging efficiencies are both set to the square root of round-trip efficiency.

\[
SOC_{t+1}=SOC_t+\eta_cP_t^{charge}\Delta t-\frac{P_t^{discharge}\Delta t}{\eta_d}
\]

The simulation uses 30-minute intervals. When multiple target days are supplied, SOC is continuous across midnight: the first period of the next day starts from the previous period's ending SOC. The battery is initialized only once at the beginning of the analysis horizon.

## 4. Reactive operation

If \(e_t>0\), the battery charges up to the minimum of:

- current renewable surplus;
- battery power limit;
- remaining SOC headroom adjusted for charging efficiency.

If \(e_t<0\), it discharges up to the minimum of:

- current renewable deficit;
- battery power limit;
- available stored energy adjusted for discharging efficiency.

The strategy has no knowledge of future settlement periods. It assumes the current portfolio deviation can be observed operationally.

## 5. Firmed delivery and residual error

\[
G_t^{firmed}=G_t^{actual}-P_t^{charge}+P_t^{discharge}
\]

\[
r_t=G_t^{firmed}-G_t^{forecast}
\]

The primary firming metric is the reduction in absolute forecast-error energy:

\[
Reduction=100\left(1-\frac{\sum_t|r_t|\Delta t}{\sum_t|e_t|\Delta t}\right)
\]

## 6. Equivalent full cycles

Usable battery energy is the difference between maximum and minimum allowed SOC. Equivalent cycles are estimated from charge plus discharge throughput:

\[
EFC=\frac{E^{charge}+E^{discharge}}{2E^{usable}}
\]

This is an operational throughput indicator, not a detailed degradation model.

## 7. Sizing search

The interactive sizing view evaluates a controlled grid of battery power and 1h/2h/4h durations. The 450-day benchmark applies the same rule with continuous SOC. Because the 1h/2h/4h grid does not reach 80% long-run absorption, `scripts/run_extended_sizing.py` separately explores 4–48h energy-duration cases as a diagnostic. Feasible configurations are ranked by energy capacity first, followed by power and duration.

## 8. Forecast uncertainty band

The historical chart includes a nominal **80% rolling prediction interval** around the point forecast when sufficient prior evidence exists. The interval is built only from out-of-sample forecast errors on target dates strictly earlier than the selected day.

For each selected settlement-period forecast, the method looks back up to 90 target days, requires at least 30 prior days, and selects up to 600 prior forecast points with the most similar forecast capacity factor. The calibration score is the absolute capacity-factor residual:

\[
s_i=|CF_i^{actual}-\widehat{CF}_i|
\]

The interval half-width uses the conservative finite-sample empirical quantile at the requested 80% coverage level. Bounds are clipped to the physical capacity-factor range [0,1] and then scaled to the selected virtual portfolio capacity.

The selected day's actual output is **not** used to construct its own interval. Actual output is used only afterward to report how many periods landed inside the range and to mark historical misses on the chart. Across eligible historical dates, achieved coverage is 80.6% for wind, 77.0% for solar and 79.9% for a 50/50 mixed portfolio; on the locked Apr-Jun 2026 period coverage is 80.7%, 81.1% and 80.8%, respectively.

This is a rolling residual-based uncertainty estimate. It is not yet an ECMWF ensemble forecast or a dedicated probabilistic P10/P50/P90 model, and temporal dependence means the usual exchangeable-data conformal guarantee should not be claimed literally.

## 9. Future battery sizing benchmark

The main future-design mode is separate from the renewable-only continuous-SOC stress test. It represents a grid-connected reserve battery whose SOC is restored to 50% immediately before each operating day. During the day, the battery still follows the same reactive renewable-error rule and does not charge from the grid.

If stored energy before the daily reset is below the 50% target, required grid import is $(E_{target}-E_{SOC})/\eta_c$. If it is above target, potential grid export is $(E_{SOC}-E_{target})\eta_d$. These pre-day import/export quantities are recorded for later economics; the present sizing stage does not assume they are free. The timing, power constraint and market cost of the pre-day reset are not yet optimised.

For a 100 MW reference portfolio, the design grid contains power fractions {5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 100}% and durations {1, 2, 4, 6, 8, 12, 16, 24, 36, 48, 72} h. The same 121 cells are precomputed for wind-share values from 0% to 100% in 5% increments, giving 2,541 rows. Results scale linearly with portfolio capacity.

A design target is one of 80%, 90% or 95% absorbed forecast-error energy. Reliability is the percentage of target days whose own absolute forecast-error energy is reduced by at least that target. A stable candidate must satisfy both the overall target and the requested daily reliability in **both** historical regimes: development OOF (Apr 2025–Mar 2026) and Apr–Jun 2026. Candidates are ranked by minimum MWh, then MW, then duration.

The Apr–Jun period is a robustness regime, not a new sealed battery-design holdout, because it has already been examined during this project. The objective is stability across materially different out-of-sample forecast-error periods, not a claim of untouched future validation.

Durations ≤4 h are labelled short-duration BESS, 6–12 h extended-duration BESS, and >12 h long-duration storage territory. The renewable-only continuous-SOC analysis remains as a stress test showing what happens if grid SOC restoration is prohibited entirely.

## 10. Forecast-day directional reserve and SOC planning

Operational planning uses an **asymmetric signed-residual range**, separate from the symmetric historical-review band. For each forecast level, up to 600 earlier out-of-sample residuals with the closest forecast capacity factor are selected from a 180-day lookback window (minimum 30 prior dates). With residual \(r=CF^{actual}-\widehat{CF}\), the lower and upper bounds use conservative empirical q10 and q90 residual quantiles:

\[
L_t=\widehat G_t+q_{0.10}(r),\qquad U_t=\widehat G_t+q_{0.90}(r)
\]

with physical clipping to [0, portfolio capacity]. This is directional empirical reserve evidence, not an ECMWF ensemble or dedicated probabilistic P10/P90 forecast.

The instantaneous downward and upward requirements are:

\[
d_t=\max(\widehat G_t-L_t,0),\qquad u_t=\max(U_t-\widehat G_t,0)
\]

The reserve horizon \(H\) equals the installed battery duration (capped at the remaining forecast day). For every possible window start, the planner sums half-hourly requirements over the following \(H\) hours. Let \(D^*\) be the largest rolling downward-output energy requirement and \(U^*\) the largest rolling upward-input energy requirement. The stored-energy requirements are then:

\[
E^{down}_{req}=D^*/\eta_d,\qquad E^{up}_{req}=U^*\eta_c
\]

For battery stored-energy limits \(E_{min}\) and \(E_{max}\), the energy-feasible starting-SOC band is:

\[
E_{safe,low}=E_{min}+E^{down}_{req}
\]

\[
E_{safe,high}=E_{max}-E^{up}_{req}
\]

If \(E_{safe,low}\le E_{safe,high}\), the recommended starting SOC is the **minimum adjustment** from the operator-entered current SOC into this band. If current SOC is already inside the band, it is held. Grid import required to raise SOC is \(\Delta E/\eta_c\); potential export when lowering SOC is \(\Delta E\eta_d\). Peak downward/upward MW requirements are also compared with installed battery power.

If the two-sided energy envelope is infeasible (\(E_{safe,low}>E_{safe,high}\)), no SOC can fully cover both directions. The planner therefore **holds current SOC and reports the reserve-coverage shortfall** instead of forcing a risk-balanced SOC shift that has not been validated. The output is reserve readiness and pre-day preparation guidance; no future actual generation or battery dispatch trajectory is simulated.

## 11. GB imbalance settlement exposure

For each historical settlement period, the V2 point forecast is treated as an illustrative contracted/scheduled export. With a 30-minute interval, the portfolio energy imbalance is:

\[
Q_t^{imb}=(G_t^{actual}-G_t^{schedule})\times0.5
\]

A positive value means the portfolio is long (more generation than scheduled); a negative value means it is short. Under the current GB single-price imbalance design, System Buy Price and System Sell Price are equal to the System Price. The Studio preserves the BSC cashflow sign convention:

\[
C_t^{imb}=-Q_t^{imb}\,P_t^{system}
\]

so positive cashflow is a payment by the portfolio and negative cashflow is a receipt to the portfolio. The same calculation is repeated using the residual imbalance after battery firming.

The reported **gross cash-out exposure** is \(\sum_t |C_t^{imb}|\). It is used as a measure of settlement-risk magnitude. A reduction in this quantity is not automatically profit or avoided cost because a long or short imbalance can itself create a favourable settlement receipt. The Studio therefore reports signed cashflow separately and does not label gross exposure reduction as battery savings.

The frozen Elexon System Price/NIV archive covers all 450 historical target days and 21,600 settlement periods. A proper trading-value calculation still requires a contracted/day-ahead reference price and battery operating/degradation costs.

## 12. Spatial renewable allocation zones

The authoritative V2 forecast remains a national embedded wind/solar forecast. For presentation and flexibility screening, the forecast-day bundle is reconciled into ten spatial zones matching the V2 weather sampling locations. Fixed technology weights come from operational wind/solar projects in the July 2026 DESNZ Renewable Energy Planning Database (REPD), assigned to the nearest V2 weather location. REPD is used only as a spatial proxy because its project threshold/history does not constitute a complete census of embedded capacity.

Within each half-hour, wind raw allocation is proportional to the fixed wind-capacity proxy multiplied by the local 100 m wind-speed cubed; solar raw allocation is proportional to the fixed solar-capacity proxy multiplied by local instantaneous shortwave radiation. Each technology is then normalised across all ten zones so allocated MW sums exactly to the national V2 wind/solar forecast. If all weather signals are zero, the fixed capacity-proxy shares are used as the fallback.

For a user-defined virtual portfolio, wind and solar nameplate are split by the selected portfolio mix and the same dynamic spatial shares are applied. The displayed city/zone BESS is the national Stage A MW/MWh design multiplied by that zone's fixed virtual-capacity proxy share. It is therefore an **indicative proportional allocation**, not an independently optimised city battery. No city-specific actual generation/error history or distribution-network constraint is inferred.

## 13. Spatial underlying-demand and net-load proxy

DESNZ 2024 Local Authority electricity consumption provides annual spatial weights for the ten zones. Each Local Authority is assigned to its nearest V2 zone and to the containing NESO GSP region. Elexon CDCA-I029 GSP Group Take is used only to learn within-day regional shape because it is net regional grid take, not gross customer consumption. Month, weekday/Saturday/Sunday and settlement period define the historical shape cells.

Because embedded wind and solar suppress NESO National Demand, the national underlying-demand proxy is:

\[
D^{under}_{GB,t}=D^{NDF}_{t}+G^{wind,emb}_{t}+G^{solar,emb}_{t}
\]

If \(a_z\) is the DESNZ annual-consumption share and \(p_{z,t}\) the zone's weighted GSP within-day profile, the period allocation weight is normalised across zones and applied to \(D^{under}_{GB,t}\). Thus \(\sum_z D^{under}_{z,t}=D^{under}_{GB,t}\). Zone net load is then \(L_{z,t}=D^{under}_{z,t}-G^{wind,emb}_{z,t}-G^{solar,emb}_{z,t}\), so \(\sum_z L_{z,t}=D^{NDF}_{t}\) by construction. These are system-zone allocation proxies, not measured city feeder loads.

The GSP shape is validated with training through March 2026 and an Apr-Jun 2026 check. Mean absolute within-day profile error is 0.268 percentage points of daily energy versus 0.415 for a flat-period baseline, a 35.4% improvement.

## 14. Market-backed lifecycle investment appraisal

Stage 10 uses the realised daily operating value of the **forecast-selected** wholesale schedule as the core investment-benefit series. The schedule itself is chosen from prior-date APX Market Index price forecasts; realised APX Market Index prices are used only afterward to score the fixed schedule. The base annual operating value is the observed daily sum annualised by `365.25 / observed_days`. The reserve-aware case uses the same price forecast while constraining SOC inside the Stage B reserve corridor.

For annual operating value `V_1`, revenue degradation `g`, fixed annual OPEX `O`, discount rate `r`, lifetime `N`, optional replacement cost `R_y` and upfront CAPEX `C_0`, lifecycle NPV is:

```text
NPV = -C_0 + sum[y=1..N] ((V_1 (1-g)^(y-1) - O - R_y) / (1+r)^y)
```

The market-backed BCR is present value of market operating value divided by present value of CAPEX + fixed OPEX + replacement. The switching values are the maximum CAPEX compatible with zero NPV and the minimum year-one annual operating value required for zero NPV. Historical dispatch margins already include the frozen ?2/MWh throughput-cost assumption, so that cost is not applied again.

The market-backed Monte Carlo resamples contiguous blocks of realised daily forecast-selected market value, preserving short-run market-regime dependence, and varies CAPEX, fixed OPEX, availability and degradation. It reports P10/P50/P90 NPV, probability of negative NPV, VaR and CVaR using `investment loss = -NPV`. Quick Reserve is excluded from the probabilistic base until asset-specific auction acceptance is identified. The aligned Apr?Jun QR case is deterministic upside screening only.


## 15. NESO multi-service availability stacking

Stage 11 represents each EAC ancillary product as one contract variable over its actual delivery window. Firming, wholesale arbitrage and every enabled ancillary product compete for one BESS power/SOC trajectory. Upward products consume discharge headroom; downward products consume charge headroom. A conservative nameplate rule additionally requires the sum of simultaneous ancillary commitments to remain within BESS MW, so the same physical MW is not counted twice.

Quick Reserve and Slow Reserve use 30-minute EAC windows; Dynamic Containment, Dynamic Moderation and Dynamic Regulation retain their 4-hour EFA delivery blocks. Positive Slow Reserve applies identical contracted MW across the current linked morning (06:00-10:30 local), midday (10:30-15:00) and evening (15:00-21:00) transition windows. Balancing Reserve is available only when the scenario explicitly assumes BM-unit eligibility.

Each product also carries a transparent screening energy-headroom duration used to prevent physically impossible reserve sales. These durations are conservative modelling guards, not substitutes for the complete service terms. Stage 11 values availability at observed EAC clearing prices and excludes utilisation energy/payments, performance penalties and asset-specific auction acceptance. Therefore the 90-day evidence is an ex-post price-taker upper-bound screen, not a deployable revenue forecast.

## 16. Current exclusions

The current release excludes a licensed contracted/day-ahead auction price benchmark, detailed cell-level degradation, site-specific grid-connection/network constraints, weather-ensemble probabilistic forecasts and independently validated city-level generation/error targets. The historical firming evidence remains national forecast-error behaviour scaled to a virtual portfolio. Spatial-zone outputs are reconciled allocation proxies, not individual-asset forecasts.
