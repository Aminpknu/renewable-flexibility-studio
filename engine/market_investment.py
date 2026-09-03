"""Lifecycle appraisal driven by observed/forecast-selected market operating value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class MarketInvestmentAssumptions:
    """Pre-feasibility investment assumptions for market-backed BESS value."""

    total_capex_gbp: float
    fixed_opex_gbp_per_year: float = 0.0
    asset_life_years: int = 15
    discount_rate: float = 0.08
    annual_revenue_degradation_fraction: float = 0.02
    replacement_year: int | None = None
    replacement_cost_gbp: float = 0.0

    def __post_init__(self) -> None:
        numeric = {
            "total_capex_gbp": self.total_capex_gbp,
            "fixed_opex_gbp_per_year": self.fixed_opex_gbp_per_year,
            "discount_rate": self.discount_rate,
            "annual_revenue_degradation_fraction": self.annual_revenue_degradation_fraction,
            "replacement_cost_gbp": self.replacement_cost_gbp,
        }
        if not all(np.isfinite(float(v)) for v in numeric.values()):
            raise ValueError("Market investment assumptions must be finite.")
        if self.total_capex_gbp < 0 or self.fixed_opex_gbp_per_year < 0 or self.replacement_cost_gbp < 0:
            raise ValueError("Market investment costs cannot be negative.")
        if self.asset_life_years <= 0:
            raise ValueError("Asset life must be positive.")
        if self.discount_rate <= -1:
            raise ValueError("Discount rate must be greater than -100%.")
        if not 0 <= self.annual_revenue_degradation_fraction < 1:
            raise ValueError("Revenue degradation must be in [0, 1).")
        if self.replacement_year is not None:
            if not 1 <= int(self.replacement_year) <= self.asset_life_years:
                raise ValueError("Replacement year must lie within asset life.")
        elif self.replacement_cost_gbp > 0:
            raise ValueError("A replacement cost requires a replacement year.")


def appraise_market_operating_value(
    annual_operating_value_gbp: float,
    assumptions: MarketInvestmentAssumptions,
) -> dict[str, Any]:
    """Discount an annual market-operating value into lifecycle investment metrics."""
    if not np.isfinite(float(annual_operating_value_gbp)):
        raise ValueError("Annual market operating value must be finite.")
    yearly: list[dict[str, float | int]] = []
    pv_revenue = 0.0
    pv_fixed_opex = 0.0
    pv_replacement = 0.0
    cumulative = -assumptions.total_capex_gbp
    payback_year: int | None = None
    for year in range(1, assumptions.asset_life_years + 1):
        degradation = (1.0 - assumptions.annual_revenue_degradation_fraction) ** (year - 1)
        operating_value = float(annual_operating_value_gbp * degradation)
        replacement = (
            assumptions.replacement_cost_gbp
            if assumptions.replacement_year == year else 0.0
        )
        discount = (1.0 + assumptions.discount_rate) ** year
        pv_revenue += operating_value / discount
        pv_fixed_opex += assumptions.fixed_opex_gbp_per_year / discount
        pv_replacement += replacement / discount
        net = operating_value - assumptions.fixed_opex_gbp_per_year - replacement
        cumulative += net
        if payback_year is None and cumulative >= 0:
            payback_year = year
        yearly.append({
            "year": year,
            "degradation_factor": float(degradation),
            "operating_value_gbp": operating_value,
            "fixed_opex_gbp": float(assumptions.fixed_opex_gbp_per_year),
            "replacement_cost_gbp": float(replacement),
            "net_cashflow_gbp": float(net),
            "discounted_net_cashflow_gbp": float(net / discount),
        })
    pv_cost = assumptions.total_capex_gbp + pv_fixed_opex + pv_replacement
    npv = pv_revenue - pv_cost
    bcr = pv_revenue / pv_cost if pv_cost > 0 else float("inf")
    return {
        "annual_operating_value_gbp_year1": float(annual_operating_value_gbp),
        "total_capex_gbp": float(assumptions.total_capex_gbp),
        "pv_market_value_gbp": float(pv_revenue),
        "pv_fixed_opex_gbp": float(pv_fixed_opex),
        "pv_replacement_gbp": float(pv_replacement),
        "pv_total_cost_gbp": float(pv_cost),
        "npv_gbp": float(npv),
        "benefit_cost_ratio": float(bcr),
        "simple_payback_years": payback_year,
        "yearly_cashflows": yearly,
    }


def maximum_capex_for_market_zero_npv_gbp(
    annual_operating_value_gbp: float,
    assumptions: MarketInvestmentAssumptions,
) -> float:
    """Return upfront CAPEX consistent with zero NPV for the market cashflow."""
    zero = MarketInvestmentAssumptions(
        total_capex_gbp=0.0,
        fixed_opex_gbp_per_year=assumptions.fixed_opex_gbp_per_year,
        asset_life_years=assumptions.asset_life_years,
        discount_rate=assumptions.discount_rate,
        annual_revenue_degradation_fraction=assumptions.annual_revenue_degradation_fraction,
        replacement_year=assumptions.replacement_year,
        replacement_cost_gbp=assumptions.replacement_cost_gbp,
    )
    result = appraise_market_operating_value(annual_operating_value_gbp, zero)
    return float(max(result["pv_market_value_gbp"] - result["pv_fixed_opex_gbp"] - result["pv_replacement_gbp"], 0.0))


def minimum_annual_market_value_for_zero_npv_gbp(
    assumptions: MarketInvestmentAssumptions,
) -> float:
    """Return year-one annual market value required for lifecycle NPV=0."""
    unit = appraise_market_operating_value(1.0, assumptions)
    pv_per_gbp = float(unit["pv_market_value_gbp"])
    costs = float(unit["pv_total_cost_gbp"])
    if pv_per_gbp <= 0:
        raise ValueError("Discounted market-value factor must be positive.")
    return float(costs / pv_per_gbp)
