"""Transparent pre-feasibility value appraisal for BESS risk reduction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class ValueAssumptions:
    """User/scenario assumptions for discounted lifecycle appraisal."""

    consequence_value_gbp_per_mwh: float
    total_capex_gbp: float
    fixed_opex_gbp_per_year: float = 0.0
    variable_opex_gbp_per_mwh: float = 0.0
    asset_life_years: int = 15
    discount_rate: float = 0.08
    annual_degradation_fraction: float = 0.02

    def __post_init__(self) -> None:
        numeric = {
            "consequence_value_gbp_per_mwh": self.consequence_value_gbp_per_mwh,
            "total_capex_gbp": self.total_capex_gbp,
            "fixed_opex_gbp_per_year": self.fixed_opex_gbp_per_year,
            "variable_opex_gbp_per_mwh": self.variable_opex_gbp_per_mwh,
            "discount_rate": self.discount_rate,
            "annual_degradation_fraction": self.annual_degradation_fraction,
        }
        if not all(np.isfinite(float(value)) for value in numeric.values()):
            raise ValueError("Value assumptions must be finite.")
        if any(float(value) < 0 for key, value in numeric.items() if key != "discount_rate"):
            raise ValueError("Cost, consequence and degradation assumptions cannot be negative.")
        if self.asset_life_years <= 0:
            raise ValueError("Asset life must be a positive integer.")
        if self.discount_rate <= -1:
            raise ValueError("Discount rate must be greater than -100%.")
        if not 0 <= self.annual_degradation_fraction < 1:
            raise ValueError("Annual degradation must be in [0, 1).")

def capex_from_power(power_mw: float, capex_gbp_per_kw: float) -> float:
    """Convert a transparent £/kW assumption to total CAPEX."""
    if power_mw <= 0 or capex_gbp_per_kw < 0:
        raise ValueError("Power must be positive and CAPEX per kW cannot be negative.")
    return float(power_mw * 1000.0 * capex_gbp_per_kw)


def _discount_factor(rate: float, year: int) -> float:
    return float((1.0 + rate) ** year)


def _degradation_factor(annual_fraction: float, year: int) -> float:
    return float((1.0 - annual_fraction) ** (year - 1))


def appraise_intervention(
    annual_avoided_exposure_mwh: float,
    annual_throughput_mwh: float,
    assumptions: ValueAssumptions,
) -> dict[str, Any]:
    """Calculate lifecycle value from physical risk reduction and visible assumptions."""
    for name, value in {
        "annual_avoided_exposure_mwh": annual_avoided_exposure_mwh,
        "annual_throughput_mwh": annual_throughput_mwh,
    }.items():
        if not np.isfinite(float(value)) or float(value) < 0:
            raise ValueError(f"{name} must be finite and non-negative.")

    yearly: list[dict[str, float | int]] = []
    pv_benefit = 0.0
    pv_opex = 0.0
    cumulative_undiscounted = -assumptions.total_capex_gbp
    payback_year: int | None = None
    for year in range(1, assumptions.asset_life_years + 1):
        degradation = _degradation_factor(assumptions.annual_degradation_fraction, year)
        avoided_mwh = annual_avoided_exposure_mwh * degradation
        benefit = avoided_mwh * assumptions.consequence_value_gbp_per_mwh
        variable_opex = annual_throughput_mwh * assumptions.variable_opex_gbp_per_mwh
        opex = assumptions.fixed_opex_gbp_per_year + variable_opex
        net = benefit - opex
        discount = _discount_factor(assumptions.discount_rate, year)
        discounted_benefit = benefit / discount
        discounted_opex = opex / discount
        pv_benefit += discounted_benefit
        pv_opex += discounted_opex
        cumulative_undiscounted += net
        if payback_year is None and cumulative_undiscounted >= 0:
            payback_year = year
        yearly.append({
            "year": year,
            "degradation_factor": degradation,
            "avoided_exposure_mwh": avoided_mwh,
            "gross_benefit_gbp": benefit,
            "opex_gbp": opex,
            "net_benefit_gbp": net,
            "discounted_net_benefit_gbp": net / discount,
        })
    pv_cost = assumptions.total_capex_gbp + pv_opex
    npv = pv_benefit - pv_cost
    bcr = pv_benefit / pv_cost if pv_cost > 0 else float("inf")
    return {
        "annual_avoided_exposure_mwh_year1": float(annual_avoided_exposure_mwh),
        "annual_throughput_mwh": float(annual_throughput_mwh),
        "consequence_value_gbp_per_mwh": assumptions.consequence_value_gbp_per_mwh,
        "total_capex_gbp": assumptions.total_capex_gbp,
        "pv_benefit_gbp": float(pv_benefit),
        "pv_opex_gbp": float(pv_opex),
        "pv_total_cost_gbp": float(pv_cost),
        "npv_gbp": float(npv),
        "benefit_cost_ratio": float(bcr),
        "simple_payback_years": payback_year,
        "yearly_cashflows": yearly,
    }


def break_even_consequence_value_gbp_per_mwh(
    annual_avoided_exposure_mwh: float,
    annual_throughput_mwh: float,
    assumptions: ValueAssumptions,
) -> float | None:
    """Return the £/MWh consequence value that makes lifecycle NPV equal zero."""
    if annual_avoided_exposure_mwh <= 0:
        return None
    unit = ValueAssumptions(
        consequence_value_gbp_per_mwh=1.0,
        total_capex_gbp=assumptions.total_capex_gbp,
        fixed_opex_gbp_per_year=assumptions.fixed_opex_gbp_per_year,
        variable_opex_gbp_per_mwh=assumptions.variable_opex_gbp_per_mwh,
        asset_life_years=assumptions.asset_life_years,
        discount_rate=assumptions.discount_rate,
        annual_degradation_fraction=assumptions.annual_degradation_fraction,
    )
    appraisal = appraise_intervention(
        annual_avoided_exposure_mwh, annual_throughput_mwh, unit
    )
    unit_pv_benefit = float(appraisal["pv_benefit_gbp"])
    if unit_pv_benefit <= 0:
        return None
    return float(appraisal["pv_total_cost_gbp"] / unit_pv_benefit)

def maximum_capex_for_zero_npv_gbp(
    annual_avoided_exposure_mwh: float,
    annual_throughput_mwh: float,
    assumptions: ValueAssumptions,
) -> float:
    """Return the largest upfront CAPEX consistent with zero NPV."""
    zero_capex = ValueAssumptions(
        consequence_value_gbp_per_mwh=assumptions.consequence_value_gbp_per_mwh,
        total_capex_gbp=0.0,
        fixed_opex_gbp_per_year=assumptions.fixed_opex_gbp_per_year,
        variable_opex_gbp_per_mwh=assumptions.variable_opex_gbp_per_mwh,
        asset_life_years=assumptions.asset_life_years,
        discount_rate=assumptions.discount_rate,
        annual_degradation_fraction=assumptions.annual_degradation_fraction,
    )
    appraisal = appraise_intervention(
        annual_avoided_exposure_mwh, annual_throughput_mwh, zero_capex
    )
    return float(max(appraisal["pv_benefit_gbp"] - appraisal["pv_opex_gbp"], 0.0))


def minimum_annual_avoided_exposure_for_zero_npv_mwh(
    annual_throughput_mwh: float,
    assumptions: ValueAssumptions,
) -> float | None:
    """Return year-one avoided MWh required for zero lifecycle NPV."""
    if assumptions.consequence_value_gbp_per_mwh <= 0:
        return None
    unit = appraise_intervention(1.0, annual_throughput_mwh, assumptions)
    unit_benefit = float(unit["pv_benefit_gbp"])
    costs = float(unit["pv_total_cost_gbp"])
    if unit_benefit <= 0:
        return None
    return float(costs / unit_benefit)

def monetise_physical_risk(
    annual_baseline_exposure_mwh: float,
    annual_residual_exposure_mwh: float,
    consequence_value_gbp_per_mwh: float,
) -> dict[str, float]:
    """Apply a visible scenario £/MWh consequence value to annual physical exposure."""
    values = {
        "annual_baseline_exposure_mwh": annual_baseline_exposure_mwh,
        "annual_residual_exposure_mwh": annual_residual_exposure_mwh,
        "consequence_value_gbp_per_mwh": consequence_value_gbp_per_mwh,
    }
    if not all(np.isfinite(float(value)) and float(value) >= 0 for value in values.values()):
        raise ValueError("Risk monetisation inputs must be finite and non-negative.")
    if annual_residual_exposure_mwh > annual_baseline_exposure_mwh + 1e-9:
        raise ValueError("Residual exposure cannot exceed baseline exposure for this intervention comparison.")
    baseline_cost = annual_baseline_exposure_mwh * consequence_value_gbp_per_mwh
    residual_cost = annual_residual_exposure_mwh * consequence_value_gbp_per_mwh
    return {
        "annual_baseline_risk_cost_gbp": float(baseline_cost),
        "annual_residual_risk_cost_gbp": float(residual_cost),
        "annual_risk_reduction_gbp": float(baseline_cost - residual_cost),
        "consequence_value_gbp_per_mwh": float(consequence_value_gbp_per_mwh),
    }