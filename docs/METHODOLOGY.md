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

## 8. Current exclusions

The current release excludes grid charging, market prices, revenue stacking, detailed degradation, grid-connection limits, perfect-foresight optimisation, probabilistic forecasts and site-specific network conditions. The historical evidence is national forecast-error behaviour scaled to a virtual portfolio, not an individual asset's error process.
