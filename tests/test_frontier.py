from __future__ import annotations

import pandas as pd

from engine.frontier import build_risk_value_frontier


def _designs() -> pd.DataFrame:
    return pd.DataFrame({
        "power_mw": [10.0, 10.0, 10.0],
        "duration_hours": [1.0, 2.0, 4.0],
        "energy_mwh": [10.0, 20.0, 40.0],
        "full_overall_absorbed_pct": [50.0, 75.0, 80.0],
        "equivalent_full_cycles": [100.0, 90.0, 70.0],
    })


def test_frontier_scales_cost_from_reference_energy() -> None:
    result = build_risk_value_frontier(
        _designs(),
        baseline_exposure_total_mwh=1000.0,
        observed_days=365.25,
        reference_energy_mwh=20.0,
        reference_capex_gbp=2_000_000.0,
        reference_fixed_opex_gbp_per_year=100_000.0,
        consequence_value_gbp_per_mwh=1000.0,
        variable_opex_gbp_per_mwh=0.0,
        asset_life_years=10,
        discount_rate=0.0,
        annual_degradation_fraction=0.0,
    )
    capex = result.set_index("energy_mwh")["scaled_capex_gbp"].to_dict()
    assert capex[10.0] == 1_000_000.0
    assert capex[20.0] == 2_000_000.0
    assert capex[40.0] == 4_000_000.0

def test_frontier_marks_dominated_high_cost_low_incremental_value_option() -> None:
    designs = pd.DataFrame({
        "power_mw": [10.0, 20.0, 30.0],
        "duration_hours": [1.0, 1.0, 1.0],
        "energy_mwh": [10.0, 20.0, 30.0],
        "full_overall_absorbed_pct": [70.0, 90.0, 90.0],
        "equivalent_full_cycles": [100.0, 80.0, 60.0],
    })
    result = build_risk_value_frontier(
        designs,
        baseline_exposure_total_mwh=1000.0,
        observed_days=365.25,
        reference_energy_mwh=10.0,
        reference_capex_gbp=100_000.0,
        reference_fixed_opex_gbp_per_year=0.0,
        consequence_value_gbp_per_mwh=1000.0,
        variable_opex_gbp_per_mwh=0.0,
        asset_life_years=10,
        discount_rate=0.0,
        annual_degradation_fraction=0.0,
    )
    row_30 = result.loc[result["energy_mwh"].eq(30.0)].iloc[0]
    assert bool(row_30["economically_dominated"]) is True
    assert row_30["frontier_status"] == "dominated"


def test_frontier_reports_diminishing_incremental_value() -> None:
    result = build_risk_value_frontier(
        _designs(),
        baseline_exposure_total_mwh=1000.0,
        observed_days=365.25,
        reference_energy_mwh=20.0,
        reference_capex_gbp=100_000.0,
        reference_fixed_opex_gbp_per_year=0.0,
        consequence_value_gbp_per_mwh=100.0,
        variable_opex_gbp_per_mwh=0.0,
        asset_life_years=1,
        discount_rate=0.0,
        annual_degradation_fraction=0.0,
    )
    assert result["diminishing_return"].any()

def test_expected_availability_scales_benefit_not_upfront_capex() -> None:
    kwargs = dict(
        baseline_exposure_total_mwh=1000.0, observed_days=365.25,
        reference_energy_mwh=20.0, reference_capex_gbp=2_000_000.0,
        reference_fixed_opex_gbp_per_year=100_000.0,
        consequence_value_gbp_per_mwh=100.0, variable_opex_gbp_per_mwh=2.0,
        asset_life_years=10, discount_rate=0.05, annual_degradation_fraction=0.0,
    )
    full = build_risk_value_frontier(_designs(), availability_fraction=1.0, **kwargs)
    half = build_risk_value_frontier(_designs(), availability_fraction=0.5, **kwargs)
    assert half["annual_avoided_exposure_mwh"].iloc[0] == full["annual_avoided_exposure_mwh"].iloc[0] * 0.5
    assert half["annual_throughput_mwh"].iloc[0] == full["annual_throughput_mwh"].iloc[0] * 0.5
    assert half["scaled_capex_gbp"].iloc[0] == full["scaled_capex_gbp"].iloc[0]