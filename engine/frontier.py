"""Risk-value frontier construction from precomputed BESS design evidence."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .value import ValueAssumptions, appraise_intervention


def _mark_dominated(frame: pd.DataFrame) -> pd.Series:
    """Mark options weakly dominated on lifecycle cost and avoided-loss benefit."""
    dominated = []
    for index, row in frame.iterrows():
        others = frame.drop(index)
        better_or_equal = (
            others["lifecycle_cost_gbp"].le(row["lifecycle_cost_gbp"] + 1e-9)
            & others["pv_avoided_loss_gbp"].ge(row["pv_avoided_loss_gbp"] - 1e-9)
        )
        strictly_better = (
            others["lifecycle_cost_gbp"].lt(row["lifecycle_cost_gbp"] - 1e-9)
            | others["pv_avoided_loss_gbp"].gt(row["pv_avoided_loss_gbp"] + 1e-9)
        )
        dominated.append(bool((better_or_equal & strictly_better).any()))
    return pd.Series(dominated, index=frame.index, dtype=bool)


def build_risk_value_frontier(
    designs: pd.DataFrame,
    *,
    baseline_exposure_total_mwh: float,
    observed_days: float,
    reference_energy_mwh: float,
    reference_capex_gbp: float,
    reference_fixed_opex_gbp_per_year: float,
    consequence_value_gbp_per_mwh: float,
    variable_opex_gbp_per_mwh: float,
    asset_life_years: int,
    discount_rate: float,
    annual_degradation_fraction: float,
    availability_fraction: float = 1.0,
    usable_soc_fraction: float = 0.80,
) -> pd.DataFrame:
    """Appraise each design using physical evidence and transparent scaled costs."""
    required = {
        "power_mw", "duration_hours", "energy_mwh",
        "full_overall_absorbed_pct", "equivalent_full_cycles",
    }
    missing = sorted(required.difference(designs.columns))
    if missing:
        raise ValueError(f"Design evidence is missing frontier columns: {missing}")
    if designs.empty:
        raise ValueError("Design evidence is empty.")
    numeric = {
        "baseline_exposure_total_mwh": baseline_exposure_total_mwh,
        "observed_days": observed_days,
        "reference_energy_mwh": reference_energy_mwh,
        "reference_capex_gbp": reference_capex_gbp,
        "reference_fixed_opex_gbp_per_year": reference_fixed_opex_gbp_per_year,
        "consequence_value_gbp_per_mwh": consequence_value_gbp_per_mwh,
        "variable_opex_gbp_per_mwh": variable_opex_gbp_per_mwh,
        "discount_rate": discount_rate,
        "annual_degradation_fraction": annual_degradation_fraction,
        "availability_fraction": availability_fraction,
        "usable_soc_fraction": usable_soc_fraction,
    }
    if not all(np.isfinite(float(value)) for value in numeric.values()):
        raise ValueError("Frontier assumptions must be finite.")
    if baseline_exposure_total_mwh < 0 or observed_days <= 0 or reference_energy_mwh <= 0:
        raise ValueError("Exposure must be non-negative and observation/reference energy positive.")
    if not 0 <= availability_fraction <= 1:
        raise ValueError("Availability fraction must be in [0, 1].")
    if not 0 < usable_soc_fraction <= 1:
        raise ValueError("Usable SOC fraction must be in (0, 1].")

    annualisation = 365.25 / float(observed_days)
    rows: list[dict[str, float | int | bool | str | None]] = []
    for _, design in designs.iterrows():
        energy = float(design["energy_mwh"])
        scale = energy / float(reference_energy_mwh)
        capex = float(reference_capex_gbp) * scale
        fixed_opex = float(reference_fixed_opex_gbp_per_year) * scale
        avoided_total = baseline_exposure_total_mwh * float(design["full_overall_absorbed_pct"]) / 100.0
        annual_avoided = avoided_total * annualisation * availability_fraction
        throughput_total = (
            float(design["equivalent_full_cycles"])
            * 2.0 * usable_soc_fraction * energy
        )
        annual_throughput = throughput_total * annualisation * availability_fraction
        assumptions = ValueAssumptions(
            consequence_value_gbp_per_mwh=consequence_value_gbp_per_mwh,
            total_capex_gbp=capex,
            fixed_opex_gbp_per_year=fixed_opex,
            variable_opex_gbp_per_mwh=variable_opex_gbp_per_mwh,
            asset_life_years=asset_life_years,
            discount_rate=discount_rate,
            annual_degradation_fraction=annual_degradation_fraction,
        )
        value = appraise_intervention(annual_avoided, annual_throughput, assumptions)
        rows.append({
            "power_mw": float(design["power_mw"]),
            "duration_hours": float(design["duration_hours"]),
            "energy_mwh": energy,
            "annual_avoided_exposure_mwh": float(annual_avoided),
            "annual_throughput_mwh": float(annual_throughput),
            "scaled_capex_gbp": capex,
            "scaled_fixed_opex_gbp_per_year": fixed_opex,
            "pv_avoided_loss_gbp": float(value["pv_benefit_gbp"]),
            "lifecycle_cost_gbp": float(value["pv_total_cost_gbp"]),
            "npv_gbp": float(value["npv_gbp"]),
            "benefit_cost_ratio": float(value["benefit_cost_ratio"]),
            "simple_payback_years": value["simple_payback_years"],
        })
    result = pd.DataFrame(rows)
    result["economically_dominated"] = _mark_dominated(result)
    result["frontier_status"] = np.where(
        result["economically_dominated"], "dominated", "value-efficient"
    )
    efficient = result.loc[~result["economically_dominated"]].sort_values("lifecycle_cost_gbp")
    incremental_ratio = efficient["pv_avoided_loss_gbp"].diff() / efficient["lifecycle_cost_gbp"].diff()
    result["incremental_value_ratio"] = np.nan
    result.loc[efficient.index, "incremental_value_ratio"] = incremental_ratio
    result["diminishing_return"] = (
        result["incremental_value_ratio"].notna()
        & result["incremental_value_ratio"].lt(1.0)
    )
    return result.sort_values(["energy_mwh", "power_mw"]).reset_index(drop=True)