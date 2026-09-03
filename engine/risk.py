"""Physical risk metrics for renewable forecast error and BESS intervention."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .battery import BatteryConfig, simulate_reactive_firming


@dataclass(frozen=True)
class PhysicalRiskConfig:
    """Transparent settings for empirical physical-risk measurement."""

    large_deviation_threshold_mw: float = 10.0
    interval_hours: float = 0.50
    annual_days: float = 365.25

    def __post_init__(self) -> None:
        values = (
            self.large_deviation_threshold_mw,
            self.interval_hours,
            self.annual_days,
        )
        if not all(np.isfinite(float(value)) for value in values):
            raise ValueError("Physical risk settings must be finite.")
        if self.large_deviation_threshold_mw < 0:
            raise ValueError("Large-deviation threshold cannot be negative.")
        if self.interval_hours <= 0 or self.annual_days <= 0:
            raise ValueError("Interval hours and annual days must be positive.")

def _observation_days(frame: pd.DataFrame, interval_hours: float) -> float:
    """Return the observed duration in days without assuming 48-period days."""
    if "settlement_date" in frame.columns:
        dates = pd.to_datetime(frame["settlement_date"], errors="raise").dt.normalize()
        days = float(dates.nunique())
    else:
        days = float(len(frame) * interval_hours / 24.0)
    if days <= 0:
        raise ValueError("Observation period must be positive.")
    return days


def _safe_reduction_pct(before: float, after: float) -> float:
    if before <= 0:
        return 0.0
    return float(100.0 * (1.0 - after / before))


def summarise_physical_risk(
    simulation: pd.DataFrame,
    config: PhysicalRiskConfig | None = None,
) -> dict[str, Any]:
    """Summarise empirical baseline and residual physical forecast-error risk."""
    cfg = config or PhysicalRiskConfig()
    required = {
        "forecast_error_mw", "residual_error_mw",
        "power_limited", "energy_limited",
    }
    missing = sorted(required.difference(simulation.columns))
    if missing:
        raise ValueError(f"Simulation frame is missing physical-risk columns: {missing}")
    if simulation.empty:
        raise ValueError("Simulation frame is empty.")
    before = simulation["forecast_error_mw"].to_numpy(dtype=float)
    after = simulation["residual_error_mw"].to_numpy(dtype=float)
    if not np.isfinite(np.column_stack([before, after])).all():
        raise ValueError("Physical-risk power values must be finite.")

    dt = cfg.interval_hours
    observed_days = _observation_days(simulation, dt)
    annualisation_factor = cfg.annual_days / observed_days
    before_abs = np.abs(before)
    after_abs = np.abs(after)
    baseline_exposure = float(before_abs.sum() * dt)
    residual_exposure = float(after_abs.sum() * dt)
    avoided_exposure = baseline_exposure - residual_exposure
    threshold = cfg.large_deviation_threshold_mw
    baseline_large = before_abs > threshold
    residual_large = after_abs > threshold
    power_limited = simulation["power_limited"].astype(bool).to_numpy()
    energy_limited = simulation["energy_limited"].astype(bool).to_numpy()

    baseline_deficit = float(np.clip(-before, 0.0, None).sum() * dt)
    baseline_surplus = float(np.clip(before, 0.0, None).sum() * dt)
    residual_deficit = float(np.clip(-after, 0.0, None).sum() * dt)
    residual_surplus = float(np.clip(after, 0.0, None).sum() * dt)
    result: dict[str, Any] = {
        "large_deviation_threshold_mw": float(threshold),
        "period_count": int(len(simulation)),
        "observed_days": observed_days,
        "annualisation_factor": float(annualisation_factor),
        "baseline_absolute_exposure_mwh": baseline_exposure,
        "residual_absolute_exposure_mwh": residual_exposure,
        "avoided_absolute_exposure_mwh": float(avoided_exposure),
        "physical_exposure_reduction_pct": _safe_reduction_pct(
            baseline_exposure, residual_exposure
        ),
        "baseline_large_deviation_periods": int(baseline_large.sum()),
        "residual_large_deviation_periods": int(residual_large.sum()),
        "large_deviation_period_reduction_pct": _safe_reduction_pct(
            float(baseline_large.sum()), float(residual_large.sum())
        ),
        "annualised_baseline_large_deviation_periods": float(
            baseline_large.sum() * annualisation_factor
        ),
        "annualised_residual_large_deviation_periods": float(
            residual_large.sum() * annualisation_factor
        ),
        "baseline_deficit_exposure_mwh": baseline_deficit,
        "baseline_surplus_exposure_mwh": baseline_surplus,
        "residual_deficit_exposure_mwh": residual_deficit,
        "residual_surplus_exposure_mwh": residual_surplus,
        "power_limited_periods": int(power_limited.sum()),
        "energy_limited_periods": int(energy_limited.sum()),
        "residual_exposure_on_power_limited_mwh": float(
            after_abs[power_limited].sum() * dt
        ),
        "residual_exposure_on_energy_limited_mwh": float(
            after_abs[energy_limited].sum() * dt
        ),
        "annualised_baseline_exposure_mwh": float(
            baseline_exposure * annualisation_factor
        ),
        "annualised_residual_exposure_mwh": float(
            residual_exposure * annualisation_factor
        ),
        "annualised_avoided_exposure_mwh": float(
            avoided_exposure * annualisation_factor
        ),
    }
    if residual_exposure > baseline_exposure + 1e-9:
        raise AssertionError("Residual physical exposure exceeds baseline exposure.")
    return result

def evaluate_derating_scenario(
    portfolio: pd.DataFrame,
    battery: BatteryConfig,
    risk_config: PhysicalRiskConfig | None = None,
    *,
    power_fraction: float = 1.0,
    energy_fraction: float = 1.0,
) -> dict[str, Any]:
    """Compare reference risk with a deterministic BESS derating scenario."""
    for name, value in {
        "power_fraction": power_fraction,
        "energy_fraction": energy_fraction,
    }.items():
        if not np.isfinite(float(value)) or not 0 < float(value) <= 1:
            raise ValueError(f"{name} must be in (0, 1].")

    reference = simulate_reactive_firming(portfolio, battery)
    reference_risk = summarise_physical_risk(reference, risk_config)
    derated_power = battery.power_mw * float(power_fraction)
    derated_energy = battery.energy_capacity_mwh * float(energy_fraction)
    derated = BatteryConfig(
        power_mw=derated_power,
        duration_hours=derated_energy / derated_power,
        round_trip_efficiency=battery.round_trip_efficiency,
        initial_soc_fraction=battery.initial_soc_fraction,
        minimum_soc_fraction=battery.minimum_soc_fraction,
        maximum_soc_fraction=battery.maximum_soc_fraction,
        interval_hours=battery.interval_hours,
    )
    derated_simulation = simulate_reactive_firming(portfolio, derated)
    derated_risk = summarise_physical_risk(derated_simulation, risk_config)
    return {
        "power_fraction": float(power_fraction),
        "energy_fraction": float(energy_fraction),
        "reference_battery_power_mw": battery.power_mw,
        "reference_battery_energy_mwh": battery.energy_capacity_mwh,
        "derated_battery_power_mw": derated.power_mw,
        "derated_battery_energy_mwh": derated.energy_capacity_mwh,
        "reference": reference_risk,
        "derated": derated_risk,
        "incremental_residual_exposure_mwh": float(
            derated_risk["residual_absolute_exposure_mwh"]
            - reference_risk["residual_absolute_exposure_mwh"]
        ),
    }