from __future__ import annotations

from engine.stress import run_value_stress_scenarios
from engine.value import ValueAssumptions


def test_stress_scenarios_include_required_downside_cases() -> None:
    base = ValueAssumptions(100.0, 1_000_000.0, 20_000.0, 2.0, 10, 0.05, 0.01)
    result = run_value_stress_scenarios(20_000.0, 5_000.0, base).set_index("scenario")
    assert {"poor_forecast_accuracy", "derating_availability_loss", "adverse_cost_value", "combined_downside"}.issubset(result.index)
    assert result.loc["combined_downside", "npv_gbp"] < result.loc["base", "npv_gbp"]
    assert result.loc["adverse_cost_value", "benefit_cost_ratio"] < result.loc["base", "benefit_cost_ratio"]