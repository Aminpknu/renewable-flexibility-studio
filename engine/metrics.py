"""Decision-oriented metrics for renewable forecast firming."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .battery import BatteryConfig


def calculate_firming_metrics(
    simulation: pd.DataFrame,
    config: BatteryConfig,
) -> dict[str, Any]:
    """Summarise forecast improvement and battery use for one simulation."""

    required = {
        "forecast_error_mw",
        "residual_error_mw",
        "charge_mw",
        "discharge_mw",
        "conversion_loss_mwh",
        "soc_fraction",
        "power_limited",
        "energy_limited",
    }
    missing = sorted(required.difference(simulation.columns))
    if missing:
        raise ValueError(f"Simulation frame is missing columns: {missing}")
    if simulation.empty:
        raise ValueError("Simulation frame is empty.")

    dt = config.interval_hours
    before = simulation["forecast_error_mw"].to_numpy(dtype=float)
    after = simulation["residual_error_mw"].to_numpy(dtype=float)
    absolute_before_mwh = float(np.abs(before).sum() * dt)
    absolute_after_mwh = float(np.abs(after).sum() * dt)
    error_reduction = (
        100.0 * (1.0 - absolute_after_mwh / absolute_before_mwh)
        if absolute_before_mwh > 0
        else 0.0
    )
    charge_energy = float(simulation["charge_mw"].sum() * dt)
    discharge_energy = float(simulation["discharge_mw"].sum() * dt)
    throughput = charge_energy + discharge_energy
    usable = config.usable_energy_mwh

    return {
        "mae_before_mw": float(np.mean(np.abs(before))),
        "mae_after_mw": float(np.mean(np.abs(after))),
        "rmse_before_mw": float(np.sqrt(np.mean(before**2))),
        "rmse_after_mw": float(np.sqrt(np.mean(after**2))),
        "absolute_error_before_mwh": absolute_before_mwh,
        "absolute_error_after_mwh": absolute_after_mwh,
        "error_reduction_pct": float(error_reduction),
        "deviations_absorbed_pct": float(error_reduction),
        "uncovered_deficit_mwh": float(np.clip(-after, 0.0, None).sum() * dt),
        "uncaptured_surplus_mwh": float(np.clip(after, 0.0, None).sum() * dt),
        "charge_energy_mwh": charge_energy,
        "discharge_energy_mwh": discharge_energy,
        "throughput_mwh": throughput,
        "conversion_losses_mwh": float(simulation["conversion_loss_mwh"].sum()),
        "equivalent_full_cycles": float(throughput / (2 * usable)) if usable > 0 else 0.0,
        "minimum_soc_pct": float(simulation["soc_fraction"].min() * 100),
        "maximum_soc_pct": float(simulation["soc_fraction"].max() * 100),
        "ending_soc_pct": float(simulation["soc_fraction"].iloc[-1] * 100),
        "power_limited_periods": int(simulation["power_limited"].sum()),
        "energy_limited_periods": int(simulation["energy_limited"].sum()),
        "battery_power_mw": config.power_mw,
        "battery_energy_mwh": config.energy_capacity_mwh,
        "battery_duration_hours": config.duration_hours,
        "round_trip_efficiency_pct": config.round_trip_efficiency * 100,
    }
