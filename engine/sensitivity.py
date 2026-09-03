"""Sensitivity utilities for Stage 6A risk-value appraisal."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .value import ValueAssumptions, appraise_intervention


def build_capex_consequence_sensitivity(
    annual_avoided_exposure_mwh: float,
    annual_throughput_mwh: float,
    base: ValueAssumptions,
    consequence_values_gbp_per_mwh: Iterable[float],
    capex_multipliers: Iterable[float],
) -> pd.DataFrame:
    """Evaluate NPV/BCR over transparent consequence-value and CAPEX assumptions."""
    rows: list[dict[str, float | int | None]] = []
    for consequence in consequence_values_gbp_per_mwh:
        if consequence < 0:
            raise ValueError("Consequence values cannot be negative.")
        for multiplier in capex_multipliers:
            if multiplier < 0:
                raise ValueError("CAPEX multipliers cannot be negative.")
            assumptions = ValueAssumptions(
                consequence_value_gbp_per_mwh=float(consequence),
                total_capex_gbp=base.total_capex_gbp * float(multiplier),
                fixed_opex_gbp_per_year=base.fixed_opex_gbp_per_year,
                variable_opex_gbp_per_mwh=base.variable_opex_gbp_per_mwh,
                asset_life_years=base.asset_life_years,
                discount_rate=base.discount_rate,
                annual_degradation_fraction=base.annual_degradation_fraction,
            )
            result = appraise_intervention(
                annual_avoided_exposure_mwh,
                annual_throughput_mwh,
                assumptions,
            )
            rows.append({
                "consequence_value_gbp_per_mwh": float(consequence),
                "capex_multiplier": float(multiplier),
                "total_capex_gbp": assumptions.total_capex_gbp,
                "npv_gbp": float(result["npv_gbp"]),
                "benefit_cost_ratio": float(result["benefit_cost_ratio"]),
                "simple_payback_years": result["simple_payback_years"],
            })
    return pd.DataFrame(rows).sort_values(
        ["consequence_value_gbp_per_mwh", "capex_multiplier"]
    ).reset_index(drop=True)