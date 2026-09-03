"""Uncertainty-aware reserve and starting-SOC planning for tomorrow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from engine.battery import BatteryConfig


@dataclass(frozen=True)
class ReservePlanningConfig:
    """Operational planning settings for a future forecast day."""

    current_soc_fraction: float = 0.50
    reserve_horizon_hours: float | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.current_soc_fraction <= 1:
            raise ValueError("current_soc_fraction must be between 0 and 1.")
        if self.reserve_horizon_hours is not None and self.reserve_horizon_hours <= 0:
            raise ValueError("reserve_horizon_hours must be positive when provided.")


def _forward_window_sums(values: np.ndarray, window_periods: int) -> np.ndarray:
    """Return forward-looking sums, shortening the window at the end of day."""
    result = np.zeros(len(values), dtype=float)
    for index in range(len(values)):
        result[index] = float(values[index:min(index + window_periods, len(values))].sum())
    return result


def _window_end_times(
    times: pd.Series,
    window_periods: int,
    interval_hours: float,
) -> list[pd.Timestamp]:
    ends: list[pd.Timestamp] = []
    for index in range(len(times)):
        last = min(index + window_periods, len(times)) - 1
        ends.append(pd.Timestamp(times.iloc[last]) + pd.Timedelta(hours=interval_hours))
    return ends


def build_reserve_plan(
    forecast_interval: pd.DataFrame,
    battery: BatteryConfig,
    config: ReservePlanningConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Calculate the minimum-adjustment SOC plan needed to cover a directional range.

    The uncertainty band is treated as a reserve envelope, not as a future
    dispatch trajectory. If the current SOC already lies inside the energy-safe
    band, the recommendation is to hold the current SOC.
    """
    cfg = config or ReservePlanningConfig()
    required = {
        "valid_time_utc", "forecast_mw",
        "prediction_interval_lower_mw", "prediction_interval_upper_mw",
    }
    missing = sorted(required.difference(forecast_interval.columns))
    if missing:
        raise ValueError(f"Forecast interval is missing reserve columns: {missing}")
    if forecast_interval.empty:
        raise ValueError("Forecast interval is empty.")
    frame = forecast_interval.copy().sort_values("valid_time_utc").reset_index(drop=True)
    times = pd.to_datetime(frame["valid_time_utc"], utc=True, errors="raise")
    forecast = frame["forecast_mw"].to_numpy(float)
    lower = frame["prediction_interval_lower_mw"].to_numpy(float)
    upper = frame["prediction_interval_upper_mw"].to_numpy(float)
    if not np.isfinite(np.column_stack([forecast, lower, upper])).all():
        raise ValueError("Forecast interval contains non-finite reserve values.")

    downward_mw = np.maximum(forecast - lower, 0.0)
    upward_mw = np.maximum(upper - forecast, 0.0)
    dt = battery.interval_hours
    horizon_hours = min(
        float(cfg.reserve_horizon_hours or battery.duration_hours),
        len(frame) * dt,
    )
    window_periods = max(1, min(len(frame), int(round(horizon_hours / dt))))
    down_window_output = _forward_window_sums(downward_mw * dt, window_periods)
    up_window_input = _forward_window_sums(upward_mw * dt, window_periods)

    down_stored = down_window_output / battery.discharge_efficiency
    up_stored = up_window_input * battery.charge_efficiency
    down_index = int(np.argmax(down_stored))
    up_index = int(np.argmax(up_stored))
    down_required_stored = float(down_stored[down_index])
    up_required_stored = float(up_stored[up_index])
    usable_stored = battery.usable_energy_mwh
    safe_low_mwh = battery.minimum_soc_mwh + down_required_stored
    safe_high_mwh = battery.maximum_soc_mwh - up_required_stored
    energy_band_feasible = bool(safe_low_mwh <= safe_high_mwh + 1e-9)
    current_mwh = cfg.current_soc_fraction * battery.energy_capacity_mwh

    if energy_band_feasible:
        recommended_mwh = float(np.clip(current_mwh, safe_low_mwh, safe_high_mwh))
        energy_coverage_fraction = 1.0
        recommendation_mode = "minimum_adjustment_to_safe_band"
    else:
        total_requirement = down_required_stored + up_required_stored
        discharge_allocation = (
            usable_stored * down_required_stored / total_requirement
            if total_requirement > 0 else usable_stored / 2.0
        )
        recommended_mwh = battery.minimum_soc_mwh + discharge_allocation
        energy_coverage_fraction = (
            min(1.0, usable_stored / total_requirement)
            if total_requirement > 0 else 1.0
        )
        recommendation_mode = "risk_balanced_compromise"

    recommended_fraction = float(np.clip(
        recommended_mwh / battery.energy_capacity_mwh,
        battery.minimum_soc_fraction,
        battery.maximum_soc_fraction,
    ))
    recommended_mwh = recommended_fraction * battery.energy_capacity_mwh
    delta_stored = recommended_mwh - current_mwh
    grid_import_mwh = max(delta_stored, 0.0) / battery.charge_efficiency
    grid_export_mwh = max(-delta_stored, 0.0) * battery.discharge_efficiency
    available_discharge_output = max(
        recommended_mwh - battery.minimum_soc_mwh, 0.0
    ) * battery.discharge_efficiency
    available_charge_input = max(
        battery.maximum_soc_mwh - recommended_mwh, 0.0
    ) / battery.charge_efficiency

    down_output_required = float(down_window_output[down_index])
    up_input_required = float(up_window_input[up_index])
    down_energy_coverage = (
        min(1.0, available_discharge_output / down_output_required)
        if down_output_required > 0 else 1.0
    )
    up_energy_coverage = (
        min(1.0, available_charge_input / up_input_required)
        if up_input_required > 0 else 1.0
    )
    peak_down_mw = float(downward_mw.max())
    peak_up_mw = float(upward_mw.max())
    down_power_coverage = min(1.0, battery.power_mw / peak_down_mw) if peak_down_mw > 0 else 1.0
    up_power_coverage = min(1.0, battery.power_mw / peak_up_mw) if peak_up_mw > 0 else 1.0
    overall_coverage = min(
        energy_coverage_fraction,
        down_energy_coverage,
        up_energy_coverage,
        down_power_coverage,
        up_power_coverage,
    )
    window_end = _window_end_times(times, window_periods, dt)
    frame["downward_reserve_requirement_mwh"] = down_window_output
    frame["upward_headroom_requirement_mwh"] = up_window_input
    frame["reserve_window_end_utc"] = window_end

    total_directional = down_required_stored + up_required_stored
    downside_share = (
        down_required_stored / total_directional if total_directional > 0 else 0.5
    )
    if downside_share > 0.55:
        risk_direction = "downside-heavy"
    elif downside_share < 0.45:
        risk_direction = "upside-heavy"
    else:
        risk_direction = "balanced"

    if abs(delta_stored) <= 1e-9:
        preparation_action = "hold current SOC"
    elif delta_stored > 0:
        preparation_action = "charge before target day"
    else:
        preparation_action = "discharge/export before target day"

    metadata: dict[str, Any] = {
        "reserve_horizon_hours": float(horizon_hours),
        "window_periods": int(window_periods),
        "current_soc_pct": float(cfg.current_soc_fraction * 100.0),
        "recommended_start_soc_pct": float(recommended_fraction * 100.0),
        "recommendation_mode": recommendation_mode,
        "preparation_action": preparation_action,
        "grid_import_to_recommendation_mwh": float(grid_import_mwh),
        "grid_export_to_recommendation_mwh": float(grid_export_mwh),
    }
    metadata.update({
        "energy_band_feasible": energy_band_feasible,
        "safe_soc_lower_pct": (
            float(100.0 * safe_low_mwh / battery.energy_capacity_mwh)
            if energy_band_feasible else None
        ),
        "safe_soc_upper_pct": (
            float(100.0 * safe_high_mwh / battery.energy_capacity_mwh)
            if energy_band_feasible else None
        ),
        "downward_reserve_required_mwh": down_output_required,
        "upward_headroom_required_mwh": up_input_required,
        "available_discharge_reserve_mwh": float(available_discharge_output),
        "available_charge_headroom_mwh": float(available_charge_input),
        "peak_downward_reserve_mw": peak_down_mw,
        "peak_upward_headroom_mw": peak_up_mw,
        "downward_energy_coverage_pct": float(100.0 * down_energy_coverage),
        "upward_energy_coverage_pct": float(100.0 * up_energy_coverage),
        "downward_power_coverage_pct": float(100.0 * down_power_coverage),
        "upward_power_coverage_pct": float(100.0 * up_power_coverage),
        "overall_reserve_coverage_pct": float(100.0 * overall_coverage),
        "risk_direction": risk_direction,
        "downside_energy_share_pct": float(100.0 * downside_share),
    })
    metadata.update({
        "critical_down_start_utc": pd.Timestamp(times.iloc[down_index]).isoformat(),
        "critical_down_end_utc": pd.Timestamp(window_end[down_index]).isoformat(),
        "critical_up_start_utc": pd.Timestamp(times.iloc[up_index]).isoformat(),
        "critical_up_end_utc": pd.Timestamp(window_end[up_index]).isoformat(),
        "critical_down_start_period": int(frame.iloc[down_index].get("settlement_period", down_index + 1)),
        "critical_up_start_period": int(frame.iloc[up_index].get("settlement_period", up_index + 1)),
    })
    return frame, metadata
