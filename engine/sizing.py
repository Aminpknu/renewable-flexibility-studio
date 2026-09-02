"""Grid-search battery sizing for a transparent firming target."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pandas as pd

from .battery import BatteryConfig, simulate_reactive_firming
from .metrics import calculate_firming_metrics


def find_minimum_battery(
    portfolio: pd.DataFrame,
    target_absorbed_pct: float,
    power_candidates_mw: Iterable[float],
    duration_candidates_hours: Iterable[float] = (1.0, 2.0, 4.0),
    round_trip_efficiency: float = 0.90,
    initial_soc_fraction: float = 0.50,
    minimum_soc_fraction: float = 0.10,
    maximum_soc_fraction: float = 0.90,
) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    """Return the smallest candidate meeting a forecast-error absorption target.

    Candidates are ranked first by energy capacity, then by power and duration.
    The complete comparison table is returned even when no candidate meets the
    target, allowing the interface to report the strongest available option.
    """

    if not 0 <= target_absorbed_pct <= 100:
        raise ValueError("target_absorbed_pct must be between 0 and 100.")
    powers = sorted({float(value) for value in power_candidates_mw if float(value) > 0})
    durations = sorted(
        {float(value) for value in duration_candidates_hours if float(value) > 0}
    )
    if not powers or not durations:
        raise ValueError("At least one positive power and duration candidate is required.")

    rows: list[dict[str, Any]] = []
    for power in powers:
        for duration in durations:
            config = BatteryConfig(
                power_mw=power,
                duration_hours=duration,
                round_trip_efficiency=round_trip_efficiency,
                initial_soc_fraction=initial_soc_fraction,
                minimum_soc_fraction=minimum_soc_fraction,
                maximum_soc_fraction=maximum_soc_fraction,
            )
            simulation = simulate_reactive_firming(portfolio, config)
            metrics = calculate_firming_metrics(simulation, config)
            rows.append(
                {
                    "power_mw": power,
                    "duration_hours": duration,
                    "energy_mwh": config.energy_capacity_mwh,
                    "error_reduction_pct": metrics["error_reduction_pct"],
                    "equivalent_full_cycles": metrics["equivalent_full_cycles"],
                    "power_limited_periods": metrics["power_limited_periods"],
                    "energy_limited_periods": metrics["energy_limited_periods"],
                    "meets_target": metrics["error_reduction_pct"] >= target_absorbed_pct,
                }
            )

    comparison = pd.DataFrame(rows).sort_values(
        ["energy_mwh", "power_mw", "duration_hours"]
    ).reset_index(drop=True)
    feasible = comparison.loc[comparison["meets_target"]]
    best = feasible.iloc[0].to_dict() if not feasible.empty else None
    return best, comparison
