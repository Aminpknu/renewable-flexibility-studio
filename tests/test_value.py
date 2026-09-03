from __future__ import annotations

import pytest

from engine.value import (
    ValueAssumptions,
    appraise_intervention,
    break_even_consequence_value_gbp_per_mwh,
    capex_from_power,
    maximum_capex_for_zero_npv_gbp,
    minimum_annual_avoided_exposure_for_zero_npv_mwh,
)


def test_npv_matches_hand_calculated_one_year_case() -> None:
    assumptions = ValueAssumptions(
        consequence_value_gbp_per_mwh=100.0,
        total_capex_gbp=1000.0,
        fixed_opex_gbp_per_year=100.0,
        variable_opex_gbp_per_mwh=0.0,
        asset_life_years=1,
        discount_rate=0.10,
        annual_degradation_fraction=0.0,
    )
    result = appraise_intervention(20.0, 0.0, assumptions)
    expected = -1000.0 + (2000.0 - 100.0) / 1.10
    assert result["npv_gbp"] == pytest.approx(expected)
    assert result["pv_benefit_gbp"] == pytest.approx(2000.0 / 1.10)
    assert result["pv_opex_gbp"] == pytest.approx(100.0 / 1.10)

def test_bcr_and_payback_match_simple_case() -> None:
    assumptions = ValueAssumptions(
        consequence_value_gbp_per_mwh=100.0,
        total_capex_gbp=1000.0,
        asset_life_years=2,
        discount_rate=0.0,
        annual_degradation_fraction=0.0,
    )
    result = appraise_intervention(10.0, 0.0, assumptions)
    assert result["benefit_cost_ratio"] == pytest.approx(2.0)
    assert result["simple_payback_years"] == 1


def test_break_even_consequence_value_has_zero_npv() -> None:
    assumptions = ValueAssumptions(
        consequence_value_gbp_per_mwh=50.0,
        total_capex_gbp=1000.0,
        fixed_opex_gbp_per_year=100.0,
        asset_life_years=2,
        discount_rate=0.0,
        annual_degradation_fraction=0.0,
    )
    value = break_even_consequence_value_gbp_per_mwh(10.0, 0.0, assumptions)
    assert value == pytest.approx(60.0)
    check = ValueAssumptions(
        consequence_value_gbp_per_mwh=value,
        total_capex_gbp=1000.0,
        fixed_opex_gbp_per_year=100.0,
        asset_life_years=2,
        discount_rate=0.0,
        annual_degradation_fraction=0.0,
    )
    assert appraise_intervention(10.0, 0.0, check)["npv_gbp"] == pytest.approx(0.0)

def test_maximum_capex_and_minimum_risk_reduction_switching_values() -> None:
    assumptions = ValueAssumptions(
        consequence_value_gbp_per_mwh=100.0,
        total_capex_gbp=500.0,
        fixed_opex_gbp_per_year=100.0,
        asset_life_years=2,
        discount_rate=0.0,
        annual_degradation_fraction=0.0,
    )
    assert maximum_capex_for_zero_npv_gbp(10.0, 0.0, assumptions) == pytest.approx(1800.0)
    assert minimum_annual_avoided_exposure_for_zero_npv_mwh(
        0.0, assumptions
    ) == pytest.approx(3.5)


def test_higher_consequence_value_increases_npv_and_higher_capex_reduces_it() -> None:
    base = dict(
        fixed_opex_gbp_per_year=0.0,
        asset_life_years=5,
        discount_rate=0.05,
        annual_degradation_fraction=0.0,
    )
    low_value = appraise_intervention(
        100.0, 0.0, ValueAssumptions(10.0, 1000.0, **base)
    )["npv_gbp"]
    high_value = appraise_intervention(
        100.0, 0.0, ValueAssumptions(20.0, 1000.0, **base)
    )["npv_gbp"]
    high_capex = appraise_intervention(
        100.0, 0.0, ValueAssumptions(20.0, 2000.0, **base)
    )["npv_gbp"]
    assert high_value > low_value
    assert high_capex < high_value


def test_capex_kw_conversion_is_explicit() -> None:
    assert capex_from_power(25.0, 1000.0) == pytest.approx(25_000_000.0)

def test_zero_consequence_value_produces_zero_monetised_risk() -> None:
    from engine.value import monetise_physical_risk

    result = monetise_physical_risk(1000.0, 250.0, 0.0)
    assert result["annual_baseline_risk_cost_gbp"] == 0.0
    assert result["annual_residual_risk_cost_gbp"] == 0.0
    assert result["annual_risk_reduction_gbp"] == 0.0