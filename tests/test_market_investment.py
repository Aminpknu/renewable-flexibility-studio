from __future__ import annotations

import pytest

from engine.market_investment import (
    MarketInvestmentAssumptions,
    appraise_market_operating_value,
    maximum_capex_for_market_zero_npv_gbp,
    minimum_annual_market_value_for_zero_npv_gbp,
)


def test_market_investment_matches_hand_calculation_without_discounting() -> None:
    assumptions = MarketInvestmentAssumptions(
        total_capex_gbp=200.0,
        fixed_opex_gbp_per_year=10.0,
        asset_life_years=3,
        discount_rate=0.0,
        annual_revenue_degradation_fraction=0.0,
    )
    result = appraise_market_operating_value(100.0, assumptions)
    assert result["pv_market_value_gbp"] == pytest.approx(300.0)
    assert result["pv_total_cost_gbp"] == pytest.approx(230.0)
    assert result["npv_gbp"] == pytest.approx(70.0)
    assert result["benefit_cost_ratio"] == pytest.approx(300.0 / 230.0)
    assert result["simple_payback_years"] == 3


def test_market_investment_includes_replacement_cost_in_selected_year() -> None:
    assumptions = MarketInvestmentAssumptions(
        total_capex_gbp=200.0, fixed_opex_gbp_per_year=10.0,
        asset_life_years=3, discount_rate=0.0,
        annual_revenue_degradation_fraction=0.0,
        replacement_year=2, replacement_cost_gbp=50.0,
    )
    result = appraise_market_operating_value(100.0, assumptions)
    assert result["pv_replacement_gbp"] == pytest.approx(50.0)
    assert result["npv_gbp"] == pytest.approx(20.0)
    assert result["yearly_cashflows"][1]["replacement_cost_gbp"] == pytest.approx(50.0)


def test_market_investment_switching_values() -> None:
    assumptions = MarketInvestmentAssumptions(
        total_capex_gbp=200.0, fixed_opex_gbp_per_year=10.0,
        asset_life_years=3, discount_rate=0.0,
        annual_revenue_degradation_fraction=0.0,
    )
    assert maximum_capex_for_market_zero_npv_gbp(100.0, assumptions) == pytest.approx(270.0)
    assert minimum_annual_market_value_for_zero_npv_gbp(assumptions) == pytest.approx(230.0 / 3.0)


def test_replacement_cost_requires_replacement_year() -> None:
    with pytest.raises(ValueError, match="replacement year"):
        MarketInvestmentAssumptions(
            total_capex_gbp=1.0, replacement_cost_gbp=1.0
        )
