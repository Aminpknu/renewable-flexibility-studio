"""Physically constrained reactive battery firming simulation."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BatteryConfig:
    """Transparent configuration for a virtual battery energy-storage system."""

    power_mw: float
    duration_hours: float
    round_trip_efficiency: float = 0.90
    initial_soc_fraction: float = 0.50
    minimum_soc_fraction: float = 0.10
    maximum_soc_fraction: float = 0.90
    interval_hours: float = 0.50

    def __post_init__(self) -> None:
        values = {
            "power_mw": self.power_mw,
            "duration_hours": self.duration_hours,
            "round_trip_efficiency": self.round_trip_efficiency,
            "initial_soc_fraction": self.initial_soc_fraction,
            "minimum_soc_fraction": self.minimum_soc_fraction,
            "maximum_soc_fraction": self.maximum_soc_fraction,
            "interval_hours": self.interval_hours,
        }
        if not all(np.isfinite(float(value)) for value in values.values()):
            raise ValueError("Battery configuration values must be finite.")
        if self.power_mw <= 0:
            raise ValueError("Battery power must be positive.")
        if self.duration_hours <= 0:
            raise ValueError("Battery duration must be positive.")
        if not 0 < self.round_trip_efficiency <= 1:
            raise ValueError("Round-trip efficiency must be in (0, 1].")
        if not 0 <= self.minimum_soc_fraction < self.maximum_soc_fraction <= 1:
            raise ValueError("SOC bounds must satisfy 0 <= minimum < maximum <= 1.")
        if not self.minimum_soc_fraction <= self.initial_soc_fraction <= self.maximum_soc_fraction:
            raise ValueError("Initial SOC must lie within the configured SOC bounds.")
        if self.interval_hours <= 0:
            raise ValueError("Interval duration must be positive.")

    @property
    def energy_capacity_mwh(self) -> float:
        return float(self.power_mw * self.duration_hours)

    @property
    def charge_efficiency(self) -> float:
        return sqrt(self.round_trip_efficiency)

    @property
    def discharge_efficiency(self) -> float:
        return sqrt(self.round_trip_efficiency)

    @property
    def minimum_soc_mwh(self) -> float:
        return self.minimum_soc_fraction * self.energy_capacity_mwh

    @property
    def maximum_soc_mwh(self) -> float:
        return self.maximum_soc_fraction * self.energy_capacity_mwh

    @property
    def initial_soc_mwh(self) -> float:
        return self.initial_soc_fraction * self.energy_capacity_mwh

    @property
    def usable_energy_mwh(self) -> float:
        return self.maximum_soc_mwh - self.minimum_soc_mwh


def simulate_reactive_firming(
    portfolio: pd.DataFrame,
    config: BatteryConfig,
) -> pd.DataFrame:
    """React to observed renewable deviations without knowledge of future periods.

    Positive forecast error (actual above forecast) charges the battery. Negative
    forecast error discharges it. Grid charging and simultaneous charging and
    discharging are excluded in this first release.
    """

    required = {"actual_mw", "forecast_mw", "settlement_period", "valid_time_utc"}
    missing = sorted(required.difference(portfolio.columns))
    if missing:
        raise ValueError(f"Portfolio frame is missing columns: {missing}")
    if portfolio.empty:
        raise ValueError("Portfolio frame is empty.")
    if portfolio[["actual_mw", "forecast_mw"]].isna().any().any():
        raise ValueError("Portfolio power values contain missing data.")

    frame = portfolio.copy().sort_values(
        ["settlement_date", "settlement_period"]
        if "settlement_date" in portfolio.columns
        else ["settlement_period"]
    ).reset_index(drop=True)

    frame["forecast_error_mw"] = (
        frame["actual_mw"].to_numpy(dtype=float)
        - frame["forecast_mw"].to_numpy(dtype=float)
    )

    dt = config.interval_hours
    eta_c = config.charge_efficiency
    eta_d = config.discharge_efficiency
    soc = config.initial_soc_mwh
    tolerance = 1e-10
    records: list[dict[str, float | bool]] = []

    for actual, forecast in zip(
        frame["actual_mw"].to_numpy(dtype=float),
        frame["forecast_mw"].to_numpy(dtype=float),
        strict=True,
    ):
        error = actual - forecast
        requested = abs(error)
        soc_start = soc
        charge = 0.0
        discharge = 0.0
        power_limited = False
        energy_limited = False

        if error > tolerance:
            power_cap = min(requested, config.power_mw)
            energy_cap = max(config.maximum_soc_mwh - soc, 0.0) / (eta_c * dt)
            charge = min(power_cap, energy_cap)
            power_limited = requested > config.power_mw + tolerance
            energy_limited = power_cap > energy_cap + tolerance
            soc += charge * eta_c * dt
        elif error < -tolerance:
            power_cap = min(requested, config.power_mw)
            energy_cap = max(soc - config.minimum_soc_mwh, 0.0) * eta_d / dt
            discharge = min(power_cap, energy_cap)
            power_limited = requested > config.power_mw + tolerance
            energy_limited = power_cap > energy_cap + tolerance
            soc -= discharge / eta_d * dt

        soc = float(np.clip(soc, config.minimum_soc_mwh, config.maximum_soc_mwh))
        firmed = actual - charge + discharge
        residual = firmed - forecast
        absorbed = max(abs(error) - abs(residual), 0.0)
        charge_loss = charge * dt * (1.0 - eta_c)
        discharge_loss = discharge * dt * (1.0 / eta_d - 1.0)

        records.append(
            {
                "charge_mw": charge,
                "discharge_mw": discharge,
                "net_battery_output_mw": discharge - charge,
                "soc_start_mwh": soc_start,
                "soc_end_mwh": soc,
                "soc_fraction": soc / config.energy_capacity_mwh,
                "firmed_delivery_mw": firmed,
                "residual_error_mw": residual,
                "absorbed_error_mw": absorbed,
                "conversion_loss_mwh": charge_loss + discharge_loss,
                "power_limited": power_limited,
                "energy_limited": energy_limited,
            }
        )

    result = pd.concat([frame, pd.DataFrame.from_records(records)], axis=1)
    if (result["charge_mw"] > tolerance).mul(result["discharge_mw"] > tolerance).any():
        raise AssertionError("Battery charged and discharged simultaneously.")
    if not result["soc_end_mwh"].between(
        config.minimum_soc_mwh - tolerance,
        config.maximum_soc_mwh + tolerance,
    ).all():
        raise AssertionError("Battery SOC escaped configured bounds.")
    return result
