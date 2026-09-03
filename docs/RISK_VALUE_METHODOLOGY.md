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