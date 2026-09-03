from __future__ import annotations

import pandas as pd
import pytest

from engine.battery import BatteryConfig
from engine.reserve_planning import ReservePlanningConfig, build_reserve_plan


def _frame(lower: float, forecast: float, upper: float, periods: int = 4) -> pd.DataFrame:
    return pd.DataFrame({
        "settlement_period": range(1, periods + 1),
        "valid_time_utc": pd.date_range("2026-09-02T23:00:00Z", periods=periods, freq="30min"),
        "forecast_mw": forecast,
        "prediction_interval_lower_mw": lower,
        "prediction_interval_upper_mw": upper,
    })


def test_current_soc_is_held_when_already_inside_safe_band() -> None:
    battery = BatteryConfig(power_mw=5, duration_hours=4, initial_soc_fraction=0.5)
    _series, plan = build_reserve_plan(
        _frame(9, 10, 11), battery,
        ReservePlanningConfig(current_soc_fraction=0.5),
    )
    assert plan["energy_band_feasible"] is True
    assert plan["safe_soc_lower_pct"] < 50 < plan["safe_soc_upper_pct"]
    assert plan["recommended_start_soc_pct"] == 50.0
    assert plan["preparation_action"] == "hold current SOC"


def test_low_current_soc_is_charged_only_to_safe_boundary() -> None:
    battery = BatteryConfig(power_mw=5, duration_hours=4, initial_soc_fraction=0.1)
    _series, plan = build_reserve_plan(
        _frame(5, 10, 10), battery,
        ReservePlanningConfig(current_soc_fraction=0.1),
    )
    assert plan["energy_band_feasible"] is True
    assert plan["recommended_start_soc_pct"] == pytest.approx(plan["safe_soc_lower_pct"])
    assert plan["recommended_start_soc_pct"] > 10
    assert plan["grid_import_to_recommendation_mwh"] > 0
    assert plan["grid_export_to_recommendation_mwh"] == 0
    assert plan["preparation_action"] == "charge before target day"


def test_high_current_soc_is_discharged_only_to_safe_boundary() -> None:
    battery = BatteryConfig(power_mw=5, duration_hours=4, initial_soc_fraction=0.9)
    _series, plan = build_reserve_plan(
        _frame(10, 10, 15), battery,
        ReservePlanningConfig(current_soc_fraction=0.9),
    )
    assert plan["energy_band_feasible"] is True
    assert plan["recommended_start_soc_pct"] == pytest.approx(plan["safe_soc_upper_pct"])
    assert plan["recommended_start_soc_pct"] < 90
    assert plan["grid_export_to_recommendation_mwh"] > 0
    assert plan["grid_import_to_recommendation_mwh"] == 0
    assert plan["preparation_action"] == "discharge/export before target day"


def test_infeasible_two_sided_energy_envelope_is_flagged() -> None:
    battery = BatteryConfig(power_mw=5, duration_hours=1, initial_soc_fraction=0.5)
    _series, plan = build_reserve_plan(
        _frame(5, 10, 15, periods=4), battery,
        ReservePlanningConfig(current_soc_fraction=0.5, reserve_horizon_hours=2),
    )
    assert plan["energy_band_feasible"] is False
    assert plan["recommendation_mode"] == "hold_current_soc_when_no_full_safe_band"
    assert plan["recommended_start_soc_pct"] == 50.0
    assert plan["preparation_action"] == "hold current SOC"
    assert plan["overall_reserve_coverage_pct"] < 100
