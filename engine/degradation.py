"""Stage 19 battery state-of-health and degradation screening model.

This is a transparent pre-feasibility wear model, not a cell-chemistry digital twin.
It converts usable capacity, cycle-life assumptions and replacement cost into a
marginal throughput wear cost that can be carried into dispatch optimisation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class DegradationConfig:
    nominal_energy_mwh: float
    state_of_health_fraction: float = 1.0
    cycle_life: float = 6000.0
    reference_depth_of_discharge_fraction: float = 0.80
    end_of_life_soh_fraction: float = 0.80
    calendar_fade_fraction_per_year: float = 0.015
    replacement_cost_gbp_per_kwh: float = 100.0

    def __post_init__(self) -> None:
        values = [
            self.nominal_energy_mwh, self.state_of_health_fraction, self.cycle_life,
            self.reference_depth_of_discharge_fraction, self.end_of_life_soh_fraction,
            self.calendar_fade_fraction_per_year, self.replacement_cost_gbp_per_kwh,
        ]
        if not all(np.isfinite(float(v)) for v in values):
            raise ValueError("Degradation assumptions must be finite.")
        if self.nominal_energy_mwh <= 0 or self.cycle_life <= 0:
            raise ValueError("Nominal energy and cycle life must be positive.")
        if not 0 < self.state_of_health_fraction <= 1:
            raise ValueError("State of health must lie in (0, 1].")
        if not 0 < self.reference_depth_of_discharge_fraction <= 1:
            raise ValueError("Reference depth of discharge must lie in (0, 1].")
        if not 0 < self.end_of_life_soh_fraction < 1:
            raise ValueError("End-of-life SOH must lie in (0, 1).")
        if self.calendar_fade_fraction_per_year < 0 or self.replacement_cost_gbp_per_kwh < 0:
            raise ValueError("Calendar fade and replacement cost cannot be negative.")

    @property
    def usable_energy_mwh(self) -> float:
        return float(self.nominal_energy_mwh * self.state_of_health_fraction)

    @property
    def replacement_cost_gbp(self) -> float:
        return float(self.nominal_energy_mwh * 1000.0 * self.replacement_cost_gbp_per_kwh)

    @property
    def lifetime_discharge_mwh(self) -> float:
        return float(
            self.usable_energy_mwh
            * self.reference_depth_of_discharge_fraction
            * self.cycle_life
        )

    @property
    def lifetime_total_throughput_mwh(self) -> float:
        # Charge + discharge energy is counted as total physical throughput.
        return float(2.0 * self.lifetime_discharge_mwh)

    @property
    def marginal_wear_cost_gbp_per_mwh_throughput(self) -> float:
        if self.lifetime_total_throughput_mwh <= 0:
            return 0.0
        return float(self.replacement_cost_gbp / self.lifetime_total_throughput_mwh)


def equivalent_full_cycles(total_throughput_mwh: float, usable_energy_mwh: float) -> float:
    if not np.isfinite(total_throughput_mwh) or total_throughput_mwh < 0:
        raise ValueError("Throughput must be finite and non-negative.")
    if not np.isfinite(usable_energy_mwh) or usable_energy_mwh <= 0:
        raise ValueError("Usable energy must be finite and positive.")
    return float(total_throughput_mwh / (2.0 * usable_energy_mwh))


def estimate_degradation(
    total_throughput_mwh: float,
    days: float,
    config: DegradationConfig,
) -> dict[str, Any]:
    if not np.isfinite(days) or days < 0:
        raise ValueError("Days must be finite and non-negative.")
    efc = equivalent_full_cycles(total_throughput_mwh, config.usable_energy_mwh)
    cycle_fade = (
        efc / config.cycle_life
        * (1.0 - config.end_of_life_soh_fraction)
        / config.reference_depth_of_discharge_fraction
    )
    calendar_fade = config.calendar_fade_fraction_per_year * (days / 365.25)
    total_fade = float(max(cycle_fade + calendar_fade, 0.0))
    end_soh = float(max(config.state_of_health_fraction - total_fade, 0.0))
    wear_cost = float(
        total_throughput_mwh * config.marginal_wear_cost_gbp_per_mwh_throughput
    )
    return {
        "equivalent_full_cycles": float(efc),
        "cycle_fade_fraction": float(cycle_fade),
        "calendar_fade_fraction": float(calendar_fade),
        "total_fade_fraction": total_fade,
        "end_state_of_health_fraction": end_soh,
        "throughput_mwh": float(total_throughput_mwh),
        "marginal_wear_cost_gbp_per_mwh_throughput": (
            config.marginal_wear_cost_gbp_per_mwh_throughput
        ),
        "estimated_wear_cost_gbp": wear_cost,
        "model_boundary": "screening_throughput_plus_calendar_fade_not_cell_chemistry_twin",
    }


def annual_degradation_screen(
    daily_total_throughput_mwh: float,
    config: DegradationConfig,
) -> dict[str, Any]:
    if not np.isfinite(daily_total_throughput_mwh) or daily_total_throughput_mwh < 0:
        raise ValueError("Daily throughput must be finite and non-negative.")
    result = estimate_degradation(daily_total_throughput_mwh * 365.25, 365.25, config)
    result["daily_total_throughput_mwh"] = float(daily_total_throughput_mwh)
    result["annual_total_throughput_mwh"] = float(daily_total_throughput_mwh * 365.25)
    return result
