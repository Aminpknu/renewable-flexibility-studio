# Repository instructions

## Scientific rules

- Treat this as a virtual portfolio-level benchmark, not a site-specific design or a physical national battery.
- Preserve forecast issue time, valid time and target date as distinct concepts.
- Historical backtests must use forecasts that were genuinely available before the target period.
- Never label perfect-foresight results as deployable operation.
- Keep wind, solar and mixed-portfolio assumptions explicit.
- Do not introduce electricity-market revenue claims without a correctly defined and licensed price product.

## Battery rules

- Charging and discharging cannot occur simultaneously.
- Enforce power, energy, SOC and efficiency constraints at every interval.
- Reactive firming may use the current observed deviation but no future settlement-period information.
- Grid charging is excluded unless a later, separately documented strategy enables it.
- All user-adjustable assumptions must be shown in downloaded results or scenario metadata.

## Engineering rules

- Keep the engine independent of Dash.
- Add offline tests for every material equation or transformation.
- Do not mutate shared global state inside callbacks.
- Validate external bundles against a versioned data contract.
- Keep dependencies minimal and run pytest after substantive changes.
