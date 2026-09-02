import pandas as pd

from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.design_sizing import (
    DesignSizingConfig,
    _fast_metrics,
    classify_duration,
    select_stable_design,
)
from engine.metrics import calculate_firming_metrics


def _portfolio() -> pd.DataFrame:
    rows = []
    for day, segment in (("2026-01-01", "development_oof"), ("2026-04-01", "locked_test")):
        for period, (actual, forecast) in enumerate(((12, 10), (8, 10), (11, 10), (9, 10)), 1):
            rows.append({"settlement_date": day, "settlement_period": period,
                         "valid_time_utc": f"{day}T{period-1:02d}:00:00Z",
                         "actual_mw": actual, "forecast_mw": forecast,
                         "evaluation_segment": segment})
    return pd.DataFrame(rows)


def test_fast_design_metrics_match_full_battery_engine() -> None:
    portfolio = _portfolio()
    config = BatteryConfig(power_mw=2, duration_hours=2, initial_soc_fraction=0.5)
    fast = _fast_metrics(portfolio, config)
    detailed = simulate_reactive_firming(portfolio, config)
    metrics = calculate_firming_metrics(detailed, config)
    assert abs(fast["overall_absorbed_pct"] - metrics["error_reduction_pct"]) < 1e-9
    assert fast["power_limited_periods"] == metrics["power_limited_periods"]
    assert fast["energy_limited_periods"] == metrics["energy_limited_periods"]


def test_select_stable_design_uses_both_historical_regimes() -> None:
    grid = pd.DataFrame([
        {"power_mw": 20, "duration_hours": 4, "energy_mwh": 80,
         "development_overall_absorbed_pct": 92, "locked_overall_absorbed_pct": 88,
         "development_days90_pct": 95, "locked_days90_pct": 92},
        {"power_mw": 30, "duration_hours": 8, "energy_mwh": 240,
         "development_overall_absorbed_pct": 93, "locked_overall_absorbed_pct": 91,
         "development_days90_pct": 94, "locked_days90_pct": 91},
    ])
    selected = select_stable_design(grid, 90, 90)
    assert selected is not None
    assert selected["energy_mwh"] == 240


def test_duration_classification_is_explicit() -> None:
    assert classify_duration(4) == "short-duration BESS"
    assert classify_duration(12) == "extended-duration BESS"
    assert classify_duration(24) == "long-duration storage territory"


def test_design_config_accepts_declared_targets() -> None:
    config = DesignSizingConfig(target_absorbed_pct=90, reliability_pct=95)
    assert config.target_absorbed_pct == 90
    assert config.reliability_pct == 95


def test_grid_connected_daily_soc_restoration_is_tracked() -> None:
    portfolio = _portfolio()
    config = BatteryConfig(power_mw=2, duration_hours=2, initial_soc_fraction=0.5)
    continuous = _fast_metrics(portfolio, config)
    restored = _fast_metrics(portfolio, config, daily_soc_target_fraction=0.5)
    assert restored["grid_reset_import_mwh"] >= 0
    assert restored["grid_reset_export_mwh"] >= 0
    assert restored["overall_absorbed_pct"] >= continuous["overall_absorbed_pct"]
