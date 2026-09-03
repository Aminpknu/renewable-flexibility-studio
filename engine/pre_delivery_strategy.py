"""Pre-delivery reserve constraints for forecast-price battery scheduling."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .battery import BatteryConfig


def build_reserve_soc_corridor(
    reserve_series: pd.DataFrame,
    battery: BatteryConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Convert rolling reserve/headroom energy needs into a period SOC corridor."""
    required = {
        "settlement_period", "downward_reserve_requirement_mwh",
        "upward_headroom_requirement_mwh",
    }
    missing = sorted(required.difference(reserve_series.columns))
    if missing:
        raise ValueError(f"Reserve series is missing SOC-corridor columns: {missing}")
    if reserve_series.empty:
        raise ValueError("Reserve series is empty.")
    frame = reserve_series.copy().sort_values("settlement_period").reset_index(drop=True)
    down = pd.to_numeric(
        frame["downward_reserve_requirement_mwh"], errors="raise"
    ).to_numpy(float)
    up = pd.to_numeric(
        frame["upward_headroom_requirement_mwh"], errors="raise"
    ).to_numpy(float)
    if not np.isfinite(np.column_stack([down, up])).all() or (down < 0).any() or (up < 0).any():
        raise ValueError("Reserve-energy requirements must be finite and non-negative.")
    floor = battery.minimum_soc_mwh + down / battery.discharge_efficiency
    ceiling = battery.maximum_soc_mwh - up * battery.charge_efficiency
    floor = np.maximum(floor, battery.minimum_soc_mwh)
    ceiling = np.minimum(ceiling, battery.maximum_soc_mwh)
    feasible = floor <= ceiling + 1e-9
    frame["soc_floor_mwh"] = floor
    frame["soc_ceiling_mwh"] = ceiling
    frame["soc_corridor_feasible"] = feasible
    return frame, {
        "all_periods_feasible": bool(feasible.all()),
        "feasible_periods_pct": float(100.0 * feasible.mean()),
        "mean_corridor_width_mwh": float(np.maximum(ceiling - floor, 0.0).mean()),
        "minimum_corridor_width_mwh": float(np.min(ceiling - floor)),
    }
