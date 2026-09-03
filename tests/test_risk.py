from __future__ import annotations

import pandas as pd
import pytest

from engine.battery import BatteryConfig
from engine.risk import (
    PhysicalRiskConfig,
    evaluate_derating_scenario,
    summarise_physical_risk,
)


def _simulation() -> pd.DataFrame:
    return pd.DataFrame({
        "settlement_date": [pd.Timestamp("2026-01-01")] * 4,
        "forecast_error_mw": [-12.0, -4.0, 6.0, 14.0],
        "residual_error_mw": [-7.0, 0.0, 1.0, 8.0],
        "power_limited": [True, False, False, True],
        "energy_limited": [False, False, True, False],
    })


def _portfolio(periods: int = 8) -> pd.DataFrame:
    return pd.DataFrame({
        "settlement_date": [pd.Timestamp("2026-01-01")] * periods,
        "settlement_period": range(1, periods + 1),
        "valid_time_utc": pd.date_range(
            "2026-01-01T00:00:00Z", periods=periods, freq="30min"
        ),
        "actual_mw": [0.0] * periods,
        "forecast_mw": [10.0] * periods,
    })

def test_physical_risk_matches_hand_calculated_exposure() -> None:
    risk = summarise_physical_risk(
        _simulation(), PhysicalRiskConfig(large_deviation_threshold_mw=10.0)
    )
    assert risk["baseline_absolute_exposure_mwh"] == pytest.approx(18.0)
    assert risk["residual_absolute_exposure_mwh"] == pytest.approx(8.0)
    assert risk["avoided_absolute_exposure_mwh"] == pytest.approx(10.0)
    assert risk["physical_exposure_reduction_pct"] == pytest.approx(55.5555556)
    assert risk["baseline_large_deviation_periods"] == 2
    assert risk["residual_large_deviation_periods"] == 0
    assert risk["baseline_deficit_exposure_mwh"] == pytest.approx(8.0)
    assert risk["baseline_surplus_exposure_mwh"] == pytest.approx(10.0)
    assert risk["residual_deficit_exposure_mwh"] == pytest.approx(3.5)
    assert risk["residual_surplus_exposure_mwh"] == pytest.approx(4.5)


def test_limit_exposure_is_reported_on_flagged_periods() -> None:
    risk = summarise_physical_risk(_simulation())
    assert risk["power_limited_periods"] == 2
    assert risk["energy_limited_periods"] == 1
    assert risk["residual_exposure_on_power_limited_mwh"] == pytest.approx(7.5)
    assert risk["residual_exposure_on_energy_limited_mwh"] == pytest.approx(0.5)


def test_zero_error_has_zero_physical_risk() -> None:
    frame = _simulation()
    frame["forecast_error_mw"] = 0.0
    frame["residual_error_mw"] = 0.0
    frame["power_limited"] = False
    frame["energy_limited"] = False
    risk = summarise_physical_risk(frame)
    assert risk["baseline_absolute_exposure_mwh"] == 0
    assert risk["residual_absolute_exposure_mwh"] == 0
    assert risk["annualised_avoided_exposure_mwh"] == 0

def test_annualisation_uses_actual_observed_days() -> None:
    frame = pd.concat([
        _simulation().assign(settlement_date=pd.Timestamp("2026-03-29")),
        _simulation().assign(settlement_date=pd.Timestamp("2026-03-30")),
    ], ignore_index=True)
    risk = summarise_physical_risk(frame, PhysicalRiskConfig(annual_days=365.0))
    assert risk["observed_days"] == 2.0
    assert risk["annualisation_factor"] == pytest.approx(182.5)


def test_derating_cannot_improve_residual_exposure_in_deficit_case() -> None:
    battery = BatteryConfig(power_mw=10.0, duration_hours=2.0)
    scenario = evaluate_derating_scenario(
        _portfolio(), battery, power_fraction=0.5, energy_fraction=0.5
    )
    assert scenario["derated_battery_power_mw"] == pytest.approx(5.0)
    assert scenario["derated_battery_energy_mwh"] == pytest.approx(10.0)
    assert scenario["incremental_residual_exposure_mwh"] >= -1e-9


def test_invalid_derating_fraction_is_rejected() -> None:
    with pytest.raises(ValueError, match="power_fraction"):
        evaluate_derating_scenario(
            _portfolio(), BatteryConfig(power_mw=10.0, duration_hours=2.0),
            power_fraction=0.0,
        )


def test_missing_risk_columns_fail_loudly() -> None:
    with pytest.raises(ValueError, match="physical-risk columns"):
        summarise_physical_risk(pd.DataFrame({"forecast_error_mw": [1.0]}))