from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.battery import BatteryConfig
from engine.quick_reserve_forecast import (
    QuickReserveForecastConfig,
    build_quick_reserve_features,
    forecast_quick_reserve_day,
)
from engine.quick_reserve_strategy import (
    build_qr_capacity_schedule_from_signal,
    evaluate_qr_capacity_schedule,
)


def _synthetic_history(days: int = 80) -> pd.DataFrame:
    rows = []
    for day_index, date in enumerate(pd.date_range("2026-01-01", periods=days, freq="D")):
        for sp in range(1, 49):
            time = date.tz_localize("UTC") + pd.Timedelta(minutes=30 * (sp - 1))
            for product, product_add in (("NQR", 0.0), ("PQR", 1.5)):
                price = max(0.0, 2.0 + product_add + 0.8 * np.sin(2 * np.pi * sp / 48) + 0.01 * day_index)
                rows.append({
                    "delivery_start_utc": time,
                    "product": product,
                    "clearing_price_gbp_per_mw_per_hour": price,
                    "cleared_volume_mw": 100.0 + sp,
                })
    return pd.DataFrame(rows)


def test_qr_price_forecast_does_not_use_target_day_clearing_price() -> None:
    history = _synthetic_history()
    target = "2026-03-11"
    features = build_quick_reserve_features(history)
    first, meta = forecast_quick_reserve_day(
        features, target,
        QuickReserveForecastConfig(minimum_history_days=30, lookback_days=60, ridge_alpha=5.0),
    )
    mutated = history.copy()
    target_start = pd.Timestamp(target, tz="UTC")
    mask = mutated["delivery_start_utc"].between(
        target_start, target_start + pd.Timedelta(hours=23, minutes=59)
    )
    mutated.loc[mask, "clearing_price_gbp_per_mw_per_hour"] += 500.0
    second, _ = forecast_quick_reserve_day(
        build_quick_reserve_features(mutated), target,
        QuickReserveForecastConfig(minimum_history_days=30, lookback_days=60, ridge_alpha=5.0),
    )
    assert np.allclose(
        first["forecast_qr_clearing_price_gbp_per_mw_per_hour"],
        second["forecast_qr_clearing_price_gbp_per_mw_per_hour"],
    )
    assert meta["uses_target_date_clearing_price"] is False


def test_qr_capacity_signal_is_integer_and_splits_nameplate() -> None:
    times = pd.date_range("2026-04-01T00:00Z", periods=4, freq="30min")
    rows = []
    for time in times:
        rows.extend([
            {"delivery_start_utc": time, "product": "PQR", "forecast_qr_clearing_price_gbp_per_mw_per_hour": 10.0},
            {"delivery_start_utc": time, "product": "NQR", "forecast_qr_clearing_price_gbp_per_mw_per_hour": 5.0},
        ])
    battery = BatteryConfig(
        power_mw=2.0, duration_hours=4.0, round_trip_efficiency=1.0,
        initial_soc_fraction=0.5, minimum_soc_fraction=0.0, maximum_soc_fraction=1.0,
    )
    schedule = build_qr_capacity_schedule_from_signal(
        pd.DataFrame(rows), battery, crossover_guard_windows=1
    )
    assert np.allclose(schedule["pqr_contracted_mw"] % 1.0, 0.0)
    assert np.allclose(schedule["nqr_contracted_mw"] % 1.0, 0.0)
    assert (
        schedule["pqr_contracted_mw"] + schedule["nqr_contracted_mw"]
        <= battery.power_mw + 1e-9
    ).all()


def test_qr_scoring_caps_price_taker_acceptance_at_system_volume() -> None:
    time = pd.Timestamp("2026-04-01T00:00Z")
    schedule = pd.DataFrame({
        "delivery_start_utc": [time],
        "pqr_contracted_mw": [2.0],
        "nqr_contracted_mw": [0.0],
    })
    realised = pd.DataFrame([
        {"delivery_start_utc": time, "product": "PQR", "cleared_volume_mw": 1.0, "clearing_price_gbp_per_mw_per_hour": 10.0, "window_hours": 0.5},
        {"delivery_start_utc": time, "product": "NQR", "cleared_volume_mw": 5.0, "clearing_price_gbp_per_mw_per_hour": 5.0, "window_hours": 0.5},
    ])
    scored, summary = evaluate_qr_capacity_schedule(schedule, realised)
    pqr = scored.loc[scored["product"].eq("PQR")].iloc[0]
    assert pqr["accepted_capacity_mw"] == pytest.approx(1.0)
    assert summary["realised_availability_payment_gbp"] == pytest.approx(5.0)
