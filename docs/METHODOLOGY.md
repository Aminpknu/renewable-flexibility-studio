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

## 10. GB imbalance settlement exposure

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

## 11. Current exclusions

The current release excludes intraday or optimised grid charging beyond the tracked pre-day SOC restoration, revenue stacking, a contracted/day-ahead price benchmark for trading P&L, detailed degradation, grid-connection limits, perfect-foresight optimisation, weather-ensemble probabilistic forecasts and site-specific network conditions. The historical evidence is national forecast-error behaviour scaled to a virtual portfolio, not an individual asset's error process.
