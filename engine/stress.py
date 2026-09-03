"""Deterministic adverse scenarios for Stage 6B risk-value appraisal."""

from __future__ import annotations

import pandas as pd

from .value import ValueAssumptions, appraise_intervention


STRESS_SCENARIOS = {
    "base": {"avoided": 1.00, "throughput": 1.00, "consequence": 1.00, "capex": 1.00, "opex": 1.00},
    "poor_forecast_accuracy": {"avoided": 0.75, "throughput": 0.85, "consequence": 1.00, "capex": 1.00, "opex": 1.00},
    "derating_availability_loss": {"avoided": 0.80, "throughput": 0.80, "consequence": 1.00, "capex": 1.00, "opex": 1.00},
    "adverse_cost_value": {"avoided": 1.00, "throughput": 1.00, "consequence": 0.75, "capex": 1.20, "opex": 1.15},
    "combined_downside": {"avoided": 0.70, "throughput": 0.75, "consequence": 0.70, "capex": 1.20, "opex": 1.15},
}


def run_value_stress_scenarios(
    annual_avoided_exposure_mwh: float,
    annual_throughput_mwh: float,
    base: ValueAssumptions,
) -> pd.DataFrame:
    """Evaluate transparent named stress multipliers against the deterministic case."""
    rows = []
    for name, multipliers in STRESS_SCENARIOS.items():
        assumptions = ValueAssumptions(
            consequence_value_gbp_per_mwh=base.consequence_value_gbp_per_mwh * multipliers["consequence"],
            total_capex_gbp=base.total_capex_gbp * multipliers["capex"],
            fixed_opex_gbp_per_year=base.fixed_opex_gbp_per_year * multipliers["opex"],
            variable_opex_gbp_per_mwh=base.variable_opex_gbp_per_mwh * multipliers["opex"],
            asset_life_years=base.asset_life_years,
            discount_rate=base.discount_rate,
            annual_degradation_fraction=base.annual_degradation_fraction,
        )
        value = appraise_intervention(
            annual_avoided_exposure_mwh * multipliers["avoided"],
            annual_throughput_mwh * multipliers["throughput"],
            assumptions,
        )
        rows.append({"scenario": name, "npv_gbp": value["npv_gbp"], "benefit_cost_ratio": value["benefit_cost_ratio"], **multipliers})
    return pd.DataFrame(rows)