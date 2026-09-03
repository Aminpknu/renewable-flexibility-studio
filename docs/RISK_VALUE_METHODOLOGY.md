# Risk & Value Methodology

## Stage 6A Packet 1: physical risk

This stage converts renewable forecast-error firming results into explicit intervention-risk evidence. It remains a virtual portfolio pre-feasibility benchmark, not a bankable BESS valuation or a live trading model.

The physical-risk engine compares the unmitigated forecast error with the residual error after the same physically constrained reactive BESS simulation already used by the Studio.

### Core exposure

For interval duration `dt`:

```text
baseline absolute exposure = sum(abs(forecast_error_mw) * dt)
residual absolute exposure = sum(abs(residual_error_mw) * dt)
avoided exposure = baseline - residual
```

All three quantities are in MWh. No £/MWh value is applied in Packet 1.
## Risk categories

- **Large-deviation risk:** number of settlement periods where absolute error exceeds a declared MW threshold, before and after BESS.
- **Power-limit risk:** periods flagged by the physical battery simulation because requested response exceeded the MW limit. Residual MWh on these periods is reported as exposure associated with power limitation; it is not treated as a mutually exclusive causal attribution.
- **Energy-limit risk:** periods where SOC/energy headroom prevented the requested response. Residual MWh on these periods is reported separately.
- **Derating risk:** a deterministic scenario can reduce available battery MW and/or MWh and compare the resulting residual exposure with the reference battery.

Deficit and surplus exposure are reported separately so directional risk remains visible.

## Annualisation

Historical exposure is annualised using the actual number of distinct observed settlement dates:

```text
annualisation factor = 365.25 / observed days
annualised exposure = observed exposure * annualisation factor
```

This is an extrapolation of empirical exposure, not a forecast of future market revenue. DST days are not forced to 48 periods.

## Packet boundary

Packet 1 contains no monetary consequence value, CAPEX, OPEX, NPV, BCR, payback, Monte Carlo, VaR or CVaR. Those belong to later Stage 6 packets after the physical-risk equations and tests are accepted.
## Stage 6A Packet 2: value appraisal

Packet 2 monetises **avoided physical exposure** using a visible user/scenario consequence value in £/MWh. This value is not presented as an observed market price or trading revenue.

```text
annual baseline risk cost = annual baseline exposure * consequence value
annual residual risk cost = annual residual exposure * consequence value
annual risk reduction = baseline risk cost - residual risk cost
```

Lifecycle appraisal then combines risk-reduction benefit with upfront CAPEX, fixed OPEX, variable OPEX, asset life, discount rate and a simple annual degradation assumption.

```text
NPV = -CAPEX + sum((benefit_t - OPEX_t) / (1+r)^t)
BCR = PV(benefits) / (CAPEX + PV(OPEX))
```

Simple payback is the first year in which cumulative undiscounted net benefit recovers CAPEX. If that point is not reached within the assumed asset life, payback is reported as unavailable.
### Switching values

The engine reports decision thresholds rather than only one NPV:

- break-even consequence value (£/MWh) for NPV = 0;
- maximum upfront CAPEX consistent with NPV = 0;
- minimum year-one annual avoided exposure required for NPV = 0.

These are calculated from the same discounted cash-flow assumptions, not by a separate heuristic.

### Sensitivity

A reusable sensitivity table varies consequence value and CAPEX while holding the remaining assumptions constant. NPV must rise monotonically with consequence value and fall with CAPEX; this behaviour is unit tested.

Detailed tax, debt/equity financing, ancillary-service revenue stacking, site-specific grid connection costs and market trading P&L remain out of scope. Monte Carlo, P10/P50/P90 NPV and CVaR remain Stage 6B.
## Stage 6A Packet 3: interactive decision layer

The Studio reuses the precomputed 450-day design grid so risk/value controls recalculate quickly without rerunning every historical battery simulation. Each tested configuration inherits its observed full-period firming percentage and equivalent-full-cycle evidence.

Candidate CAPEX and fixed OPEX are scaled in proportion to MWh relative to the Stage A selected technical design. This is deliberately labelled as a screening assumption, not a supplier cost curve. The risk-value frontier may display configurations that fail the selected technical firming/reliability gate; economic efficiency does not make such a configuration technically acceptable.

Expected availability is a Stage 6A scalar assumption: annual avoided exposure and throughput are multiplied by the entered availability fraction, while upfront CAPEX and fixed OPEX remain. This approximates randomly distributed expected unavailability only. Explicit outage timing, correlated derating and outage blocks belong to Stage 6B stress/Monte Carlo analysis.

The interface also shows a CAPEX/consequence sensitivity heatmap and downloads all portfolio, design-gate, cost, lifetime, degradation and availability assumptions with the selected results and frontier. Default monetary values are illustrative starting inputs only and are not sourced market prices or bankable project estimates.
## Stage 6B: quantitative downside risk

Stage 6B resamples the same daily-restored-SOC historical BESS evidence used by the practical sizing benchmark. It never samples individual half-hours independently. Each simulated year is assembled from contiguous circular blocks of complete historical settlement days, so 46/48/50-period DST days remain intact and short-run forecast-error regimes remain grouped.

For each Monte Carlo run, transparent triangular scenario distributions are applied to consequence value, CAPEX, OPEX, expected availability and degradation. These parameter multipliers are sampled independently. Cross-parameter correlations are therefore **not** claimed. Given the sampled availability fraction, complete simulated days are independently marked available/unavailable; unavailable days receive zero BESS firming benefit and zero throughput. This makes availability affect both economic value and the probability of meeting the selected daily-firming/reliability gate.

The default distribution multipliers are:

```text
consequence value: 0.70 / 1.00 / 1.30
CAPEX:             0.85 / 1.00 / 1.20
OPEX:              0.90 / 1.00 / 1.15
degradation:       0.75 / 1.00 / 1.25
availability:      entered value ±5 percentage points, clipped to [0,1]
```
NPV uncertainty is reported as P10/P50/P90 plus the probability of NPV < 0. Tail risk uses the explicit convention:

```text
investment loss = -NPV
```

The 95% VaR is the 95th percentile of this loss distribution. The 95% CVaR / Expected Shortfall is the average loss at or beyond that threshold and is the preferred tail-severity metric.

The technical gate is also resampled. For each simulated year the share of days meeting the selected firming target is calculated after availability outages. The reported probability of failing the firming gate is the share of Monte Carlo years in which this day-reliability percentage falls below the selected design reliability.

Named deterministic stresses cover poor forecast performance, availability/derating loss, adverse cost/value assumptions and a combined downside case. They are scenario tests, not calibrated event probabilities.
### Default Stage 6B evidence

For the default 100 MW 50/50 portfolio, 90% firming / 90%-of-days gate and illustrative Stage 6A monetary assumptions, 2,000-run comparisons show an important technical/economic trade-off. The 25 MW / 50 MWh option has a positive median NPV under these assumptions but fails the 90/90 technical gate in every bootstrap year. The selected 25 MW / 200 MWh design remains technically much stronger, but its median NPV is negative and daily availability uncertainty makes the 90/90 gate fail in a material share of bootstrap years. This is exactly why technical sufficiency and investment value are reported separately.

For the selected 25 MW / 200 MWh case, increasing simulation count from 1,000 to 5,000 changes P10/P50/P90 NPV and 95% CVaR by about 0.1–1.7% in the frozen default run. The project therefore reports results to sensible screening precision and does not imply false monetary accuracy.

The frozen default evidence is stored in `outputs/risk_value/stage6b_default_summary.json`.
