from __future__ import annotations

import pandas as pd
import pytest

from engine.battery import BatteryConfig
from engine.market_optimisation import WholesaleArbitrageConfig, optimise_wholesale_arbitrage
from engine.quick_reserve import (
    QuickReserveStackingConfig,
    optimise_arbitrage_and_quick_reserve,
)


def _market(prices) -> pd.DataFrame:
    times = pd.date_range("2026-04-01T00:00Z", periods=len(prices), freq="30min")
    return pd.DataFrame({
        "valid_time_utc": times,
        "market_index_price_gbp_per_mwh": prices,
    })


def _qr(n: int, pqr_price: float, nqr_price: float, volume: float = 100.0) -> pd.DataFrame:
    times = pd.date_range("2026-04-01T00:00Z", periods=n, freq="30min")
    rows = []
    for time in times:
        for product, price in (("PQR", pqr_price), ("NQR", nqr_price)):
            rows.append({
                "delivery_start_utc": time, "product": product,
                "cleared_volume_mw": volume,
                "clearing_price_gbp_per_mw_per_hour": price,
                "window_hours": 0.5,
            })
    return pd.DataFrame(rows)


def test_qr_availability_payment_uses_half_hour_price_unit() -> None:
    battery = BatteryConfig(
        power_mw=2.0, duration_hours=4.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    result, summary = optimise_arbitrage_and_quick_reserve(
        _market([100.0] * 4), _qr(4, 10.0, 0.0), battery,
        QuickReserveStackingConfig(enable_arbitrage=False, crossover_guard_windows=2),
    )
    assert result["pqr_contracted_mw"].eq(2.0).all()
    assert result["nqr_contracted_mw"].eq(0.0).all()
    assert summary["pqr_availability_payment_gbp"] == pytest.approx(40.0)
    assert summary["nqr_availability_payment_gbp"] == pytest.approx(0.0)
    assert summary["total_availability_payment_gbp"] == pytest.approx(40.0)
    assert summary["utilisation_revenue_included"] is False


def test_qr_contracts_are_integer_mw() -> None:
    battery = BatteryConfig(
        power_mw=1.5, duration_hours=4.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    result, _ = optimise_arbitrage_and_quick_reserve(
        _market([100.0] * 2), _qr(2, 20.0, 0.0), battery,
        QuickReserveStackingConfig(enable_arbitrage=False),
    )
    assert set(result["pqr_contracted_mw"].unique()).issubset({0.0, 1.0})


def test_zero_qr_price_reduces_to_arbitrage_problem() -> None:
    battery = BatteryConfig(
        power_mw=1.0, duration_hours=2.0, round_trip_efficiency=0.90,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.1, maximum_soc_fraction=0.9,
    )
    market = _market([20.0, 30.0, 150.0, 180.0])
    plain_frame = market.copy()
    plain_frame["settlement_period"] = range(1, 5)
    _plain, plain_summary = optimise_wholesale_arbitrage(
        plain_frame, battery, WholesaleArbitrageConfig(2.0)
    )
    _stacked, stacked_summary = optimise_arbitrage_and_quick_reserve(
        market, _qr(4, 0.0, 0.0), battery,
        QuickReserveStackingConfig(2.0, crossover_guard_windows=2),
    )
    assert stacked_summary["total_availability_payment_gbp"] == pytest.approx(0.0)
    assert stacked_summary["net_stacked_value_gbp"] == pytest.approx(
        plain_summary["net_arbitrage_margin_gbp"], abs=1e-6
    )


def test_two_window_energy_guard_limits_back_to_back_pqr() -> None:
    battery = BatteryConfig(
        power_mw=2.0, duration_hours=1.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    result, _ = optimise_arbitrage_and_quick_reserve(
        _market([100.0] * 2), _qr(2, 100.0, 0.0), battery,
        QuickReserveStackingConfig(enable_arbitrage=False, crossover_guard_windows=2),
    )
    assert result["pqr_contracted_mw"].sum() <= 2.0 + 1e-9


def test_pqr_and_nqr_split_one_nameplate_capacity() -> None:
    battery = BatteryConfig(
        power_mw=2.0, duration_hours=4.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    result, _ = optimise_arbitrage_and_quick_reserve(
        _market([100.0] * 4), _qr(4, 10.0, 10.0), battery,
        QuickReserveStackingConfig(enable_arbitrage=False, crossover_guard_windows=1),
    )
    assert (result["pqr_contracted_mw"] + result["nqr_contracted_mw"] <= 2.0 + 1e-9).all()
