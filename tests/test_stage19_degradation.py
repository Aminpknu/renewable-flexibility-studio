import pytest

from engine.degradation import (
    DegradationConfig, annual_degradation_screen, equivalent_full_cycles,
    estimate_degradation,
)


def test_degradation_cost_and_efc_are_traceable():
    cfg = DegradationConfig(
        nominal_energy_mwh=200, state_of_health_fraction=.9,
        cycle_life=6000, reference_depth_of_discharge_fraction=.8,
        replacement_cost_gbp_per_kwh=100,
    )
    assert cfg.usable_energy_mwh == pytest.approx(180)
    assert cfg.lifetime_total_throughput_mwh == pytest.approx(2*180*.8*6000)
    assert equivalent_full_cycles(360, 180) == pytest.approx(1)
    expected = cfg.replacement_cost_gbp / cfg.lifetime_total_throughput_mwh
    assert cfg.marginal_wear_cost_gbp_per_mwh_throughput == pytest.approx(expected)


def test_degradation_screen_combines_cycle_and_calendar_fade():
    cfg = DegradationConfig(nominal_energy_mwh=100, calendar_fade_fraction_per_year=.01)
    result = estimate_degradation(total_throughput_mwh=200, days=365.25, config=cfg)
    assert result["equivalent_full_cycles"] == pytest.approx(1)
    assert result["calendar_fade_fraction"] == pytest.approx(.01)
    assert result["cycle_fade_fraction"] > 0
    assert result["end_state_of_health_fraction"] < 1
    assert result["estimated_wear_cost_gbp"] > 0


def test_annual_screen_and_validation():
    cfg = DegradationConfig(nominal_energy_mwh=50)
    result = annual_degradation_screen(20, cfg)
    assert result["annual_total_throughput_mwh"] == pytest.approx(20*365.25)
    with pytest.raises(ValueError):
        annual_degradation_screen(-1, cfg)
    with pytest.raises(ValueError):
        DegradationConfig(nominal_energy_mwh=0)
