from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from adapters.forecast_data import load_historical_predictions, select_date
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.metrics import calculate_firming_metrics
from engine.portfolio import build_virtual_portfolio

ROOT = Path(__file__).resolve().parents[1]
SOURCE = load_historical_predictions(ROOT / "data" / "sample_historical.csv")
DAY = select_date(SOURCE, "2025-06-01")


def test_reactive_battery_respects_physical_limits() -> None:
    portfolio = build_virtual_portfolio(DAY, "mixed", 100.0, wind_share=0.5)
    config = BatteryConfig(power_mw=25, duration_hours=2)
    result = simulate_reactive_firming(portfolio, config)

    assert (result["charge_mw"] >= 0).all()
    assert (result["discharge_mw"] >= 0).all()
    assert (result["charge_mw"] <= config.power_mw + 1e-9).all()
    assert (result["discharge_mw"] <= config.power_mw + 1e-9).all()
    assert not ((result["charge_mw"] > 0) & (result["discharge_mw"] > 0)).any()
    assert result["soc_end_mwh"].between(
        config.minimum_soc_mwh - 1e-9,
        config.maximum_soc_mwh + 1e-9,
    ).all()


def test_battery_reduces_or_preserves_absolute_error() -> None:
    portfolio = build_virtual_portfolio(DAY, "mixed", 100.0, wind_share=0.5)
    config = BatteryConfig(power_mw=25, duration_hours=2)
    result = simulate_reactive_firming(portfolio, config)
    assert (result["residual_error_mw"].abs() <= result["forecast_error_mw"].abs() + 1e-9).all()

    metrics = calculate_firming_metrics(result, config)
    assert metrics["mae_after_mw"] <= metrics["mae_before_mw"]
    assert 0 <= metrics["error_reduction_pct"] <= 100
    assert metrics["conversion_losses_mwh"] >= 0


def test_zero_error_does_not_cycle_battery() -> None:
    frame = pd.DataFrame(
        {
            "settlement_date": [pd.Timestamp("2025-01-01")] * 2,
            "settlement_period": [1, 2],
            "valid_time_utc": pd.to_datetime(["2025-01-01T00:00Z", "2025-01-01T00:30Z"]),
            "actual_mw": [10.0, 10.0],
            "forecast_mw": [10.0, 10.0],
        }
    )
    config = BatteryConfig(power_mw=5, duration_hours=2)
    result = simulate_reactive_firming(frame, config)
    assert np.isclose(result["charge_mw"].sum(), 0)
    assert np.isclose(result["discharge_mw"].sum(), 0)
    assert np.isclose(result["soc_end_mwh"].iloc[-1], config.initial_soc_mwh)


def test_multi_day_simulation_carries_soc_across_midnight() -> None:
    source = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
    first_two_dates = sorted(source["settlement_date"].unique())[:2]
    evidence = source[source["settlement_date"].isin(first_two_dates)].copy()
    portfolio = build_virtual_portfolio(evidence, "mixed", capacity_mw=100.0, wind_share=0.5)
    config = BatteryConfig(power_mw=25.0, duration_hours=2.0)
    result = simulate_reactive_firming(portfolio, config)
    day1 = result[result["settlement_date"].eq(first_two_dates[0])]
    day2 = result[result["settlement_date"].eq(first_two_dates[1])]
    assert day2["soc_start_mwh"].iloc[0] == pytest.approx(day1["soc_end_mwh"].iloc[-1])
    assert result["soc_start_mwh"].iloc[0] == pytest.approx(config.initial_soc_mwh)
