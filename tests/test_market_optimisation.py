from __future__ import annotations

import pandas as pd
import pytest

from engine.battery import BatteryConfig
from engine.market_optimisation import (
    SettlementOptimisationConfig,
    optimise_settlement_aware_firming,
)


def _two_deficit_periods() -> tuple[pd.DataFrame, pd.DataFrame]:
    portfolio = pd.DataFrame({
        "settlement_date": [pd.Timestamp("2026-01-01")] * 2,
        "settlement_period": [1, 2],
        "valid_time_utc": pd.to_datetime([
            "2026-01-01T00:00Z", "2026-01-01T00:30Z"
        ]),
        "actual_mw": [9.0, 9.0],
        "forecast_mw": [10.0, 10.0],
    })
    prices = pd.DataFrame({
        "settlement_date": [pd.Timestamp("2026-01-01")] * 2,
        "settlement_period": [1, 2],
        "system_price_gbp_per_mwh": [50.0, 200.0],
    })
    return portfolio, prices


def test_settlement_optimiser_preserves_energy_for_high_value_deficit() -> None:
    portfolio, prices = _two_deficit_periods()
    battery = BatteryConfig(
        power_mw=1.0, duration_hours=2.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0,
        maximum_soc_fraction=1.0,
    )
    result, summary = optimise_settlement_aware_firming(
        portfolio,
        prices,
        battery,
        SettlementOptimisationConfig(restoration_price_gbp_per_mwh=100.0),
    )
    assert result["market_optimised_discharge_mw"].iloc[0] == pytest.approx(0.0)
    assert result["market_optimised_discharge_mw"].iloc[1] == pytest.approx(1.0)
    assert summary["error_reduction_pct"] == pytest.approx(50.0)
    assert summary["settlement_value_improvement_before_costs_gbp"] == pytest.approx(100.0)
    assert summary["grid_restoration_import_mwh"] == pytest.approx(0.5)
    assert summary["restoration_net_cost_gbp"] == pytest.approx(50.0)
    assert summary["net_settlement_value_improvement_gbp"] == pytest.approx(50.0)


def test_high_throughput_cost_can_make_firming_uneconomic() -> None:
    portfolio, prices = _two_deficit_periods()
    battery = BatteryConfig(
        power_mw=1.0, duration_hours=2.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0,
        maximum_soc_fraction=1.0,
    )
    result, summary = optimise_settlement_aware_firming(
        portfolio,
        prices,
        battery,
        SettlementOptimisationConfig(
            restoration_price_gbp_per_mwh=100.0,
            throughput_cost_gbp_per_mwh=120.0,
        ),
    )
    assert result["market_optimised_discharge_mw"].sum() == pytest.approx(0.0)
    assert summary["grid_restoration_import_mwh"] == pytest.approx(0.0)
    assert summary["net_settlement_value_improvement_gbp"] == pytest.approx(0.0)


def test_market_optimiser_never_amplifies_error() -> None:
    portfolio, prices = _two_deficit_periods()
    battery = BatteryConfig(power_mw=1.0, duration_hours=2.0)
    result, _summary = optimise_settlement_aware_firming(
        portfolio, prices, battery,
        SettlementOptimisationConfig(restoration_price_gbp_per_mwh=100.0),
    )
    assert (
        result["market_optimised_residual_error_mw"].abs()
        <= result["forecast_error_mw"].abs() + 1e-8
    ).all()


def test_negative_restoration_price_uses_one_terminal_grid_direction() -> None:
    portfolio, prices = _two_deficit_periods()
    battery = BatteryConfig(power_mw=1.0, duration_hours=2.0)
    _result, summary = optimise_settlement_aware_firming(
        portfolio, prices, battery,
        SettlementOptimisationConfig(restoration_price_gbp_per_mwh=-20.0),
    )
    assert not (
        summary["grid_restoration_import_mwh"] > 1e-8
        and summary["grid_restoration_export_mwh"] > 1e-8
    )


def test_wholesale_arbitrage_charges_low_and_discharges_high() -> None:
    from engine.market_optimisation import WholesaleArbitrageConfig, optimise_wholesale_arbitrage

    market = pd.DataFrame({
        "settlement_period": [1, 2],
        "market_index_price_gbp_per_mwh": [50.0, 200.0],
    })
    battery = BatteryConfig(
        power_mw=1.0, duration_hours=2.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0,
        maximum_soc_fraction=1.0,
    )
    result, summary = optimise_wholesale_arbitrage(
        market, battery, WholesaleArbitrageConfig(throughput_cost_gbp_per_mwh=0.0)
    )
    assert result["arbitrage_charge_mw"].iloc[0] == pytest.approx(1.0)
    assert result["arbitrage_discharge_mw"].iloc[1] == pytest.approx(1.0)
    assert summary["gross_arbitrage_margin_gbp"] == pytest.approx(75.0)
    assert summary["net_arbitrage_margin_gbp"] == pytest.approx(75.0)
    assert summary["ending_soc_pct"] == pytest.approx(50.0)


def test_wholesale_arbitrage_handles_negative_prices_without_simultaneous_cycle() -> None:
    from engine.market_optimisation import optimise_wholesale_arbitrage

    market = pd.DataFrame({
        "settlement_period": [1, 2, 3, 4],
        "market_index_price_gbp_per_mwh": [-50.0, -20.0, 100.0, 150.0],
    })
    battery = BatteryConfig(power_mw=1.0, duration_hours=2.0)
    result, _summary = optimise_wholesale_arbitrage(market, battery)
    assert not (
        result["arbitrage_charge_mw"].gt(1e-8)
        & result["arbitrage_discharge_mw"].gt(1e-8)
    ).any()


def test_cooptimisation_reduces_to_arbitrage_when_forecast_error_is_zero() -> None:
    from engine.market_optimisation import optimise_firming_and_arbitrage

    portfolio = pd.DataFrame({
        "settlement_date": [pd.Timestamp("2026-01-01")] * 2,
        "settlement_period": [1, 2],
        "valid_time_utc": pd.to_datetime(["2026-01-01T00:00Z", "2026-01-01T00:30Z"]),
        "actual_mw": [10.0, 10.0],
        "forecast_mw": [10.0, 10.0],
    })
    system = pd.DataFrame({
        "settlement_date": [pd.Timestamp("2026-01-01")] * 2,
        "settlement_period": [1, 2],
        "system_price_gbp_per_mwh": [100.0, 100.0],
    })
    market = pd.DataFrame({
        "settlement_period": [1, 2],
        "market_index_price_gbp_per_mwh": [50.0, 200.0],
    })
    battery = BatteryConfig(
        power_mw=1.0, duration_hours=2.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    result, summary = optimise_firming_and_arbitrage(
        portfolio, system, market, battery, throughput_cost_gbp_per_mwh=0.0
    )
    assert result["coopt_firm_charge_mw"].sum() == pytest.approx(0.0)
    assert result["coopt_firm_discharge_mw"].sum() == pytest.approx(0.0)
    assert summary["wholesale_arbitrage_value_gbp"] == pytest.approx(75.0)
    assert summary["net_cooptimised_value_gbp"] == pytest.approx(75.0)
    assert summary["ending_soc_pct"] == pytest.approx(50.0)


def test_cooptimisation_shares_single_battery_power_limit() -> None:
    from engine.market_optimisation import optimise_firming_and_arbitrage

    portfolio, system = _two_deficit_periods()
    market = pd.DataFrame({
        "settlement_period": [1, 2],
        "market_index_price_gbp_per_mwh": [0.0, 500.0],
    })
    battery = BatteryConfig(
        power_mw=1.0, duration_hours=2.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    result, _summary = optimise_firming_and_arbitrage(
        portfolio, system, market, battery, throughput_cost_gbp_per_mwh=0.0
    )
    total_discharge = result["coopt_total_discharge_mw"]
    total_charge = result["coopt_total_charge_mw"]
    assert (total_discharge <= 1.0 + 1e-8).all()
    assert (total_charge <= 1.0 + 1e-8).all()
    assert not ((total_discharge > 1e-8) & (total_charge > 1e-8)).any()


def test_arbitrage_schedule_respects_optional_soc_corridor() -> None:
    from engine.market_optimisation import WholesaleArbitrageConfig, optimise_wholesale_arbitrage
    prices = pd.DataFrame({
        "settlement_period": [1, 2, 3, 4],
        "market_index_price_gbp_per_mwh": [0.0, 0.0, 200.0, 200.0],
        "soc_floor_mwh": [0.75, 0.75, 0.75, 0.75],
        "soc_ceiling_mwh": [1.25, 1.25, 1.25, 1.25],
    })
    battery = BatteryConfig(
        power_mw=1.0, duration_hours=2.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    result, _ = optimise_wholesale_arbitrage(prices, battery, WholesaleArbitrageConfig())
    assert result["arbitrage_soc_end_mwh"].between(0.75 - 1e-8, 1.25 + 1e-8).all()


def test_forecast_selected_schedule_is_evaluated_at_realised_prices() -> None:
    from engine.market_optimisation import evaluate_arbitrage_schedule
    schedule = pd.DataFrame({
        "settlement_period": [1, 2],
        "arbitrage_charge_mw": [1.0, 0.0],
        "arbitrage_discharge_mw": [0.0, 1.0],
    })
    realised = pd.DataFrame({
        "settlement_period": [1, 2],
        "market_index_price_gbp_per_mwh": [20.0, 100.0],
    })
    result = evaluate_arbitrage_schedule(schedule, realised, throughput_cost_gbp_per_mwh=2.0)
    assert result["realised_gross_arbitrage_margin_gbp"] == pytest.approx(40.0)
    assert result["throughput_mwh"] == pytest.approx(1.0)
    assert result["realised_net_arbitrage_margin_gbp"] == pytest.approx(38.0)
