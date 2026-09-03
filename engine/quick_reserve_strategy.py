"""Pre-delivery Quick Reserve capacity allocation and ex-post scoring."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .battery import BatteryConfig
from .quick_reserve import QuickReserveStackingConfig, optimise_arbitrage_and_quick_reserve


def build_qr_capacity_schedule_from_signal(
    price_signal: pd.DataFrame,
    battery: BatteryConfig,
    *,
    price_column: str = "forecast_qr_clearing_price_gbp_per_mw_per_hour",
    crossover_guard_windows: int = 2,
) -> pd.DataFrame:
    required = {"delivery_start_utc", "product", price_column}
    missing = sorted(required.difference(price_signal.columns))
    if missing:
        raise ValueError(f"QR price signal is missing columns: {missing}")
    signal = price_signal.copy()
    signal["delivery_start_utc"] = pd.to_datetime(signal["delivery_start_utc"], utc=True)
    signal["clearing_price_gbp_per_mw_per_hour"] = pd.to_numeric(
        signal[price_column], errors="raise"
    )
    if (signal["clearing_price_gbp_per_mw_per_hour"] < 0).any():
        raise ValueError("QR capacity-allocation price signals must be non-negative.")
    signal["cleared_volume_mw"] = battery.power_mw
    signal["window_hours"] = battery.interval_hours
    times = pd.Index(signal["delivery_start_utc"].drop_duplicates()).sort_values()
    market = pd.DataFrame({
        "valid_time_utc": times,
        "market_index_price_gbp_per_mwh": np.zeros(len(times), dtype=float),
    })
    schedule_frame, _summary = optimise_arbitrage_and_quick_reserve(
        market,
        signal[[
            "delivery_start_utc", "product", "cleared_volume_mw",
            "clearing_price_gbp_per_mw_per_hour", "window_hours",
        ]],
        battery,
        QuickReserveStackingConfig(
            throughput_cost_gbp_per_mwh=0.0,
            crossover_guard_windows=int(crossover_guard_windows),
            enable_arbitrage=False,
        ),
    )
    return schedule_frame[[
        "valid_time_utc", "pqr_contracted_mw", "nqr_contracted_mw"
    ]].rename(columns={"valid_time_utc": "delivery_start_utc"})


def evaluate_qr_capacity_schedule(
    schedule: pd.DataFrame,
    realised_quick_reserve: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required_schedule = {
        "delivery_start_utc", "pqr_contracted_mw", "nqr_contracted_mw"
    }
    missing = sorted(required_schedule.difference(schedule.columns))
    if missing:
        raise ValueError(f"QR capacity schedule is missing columns: {missing}")
    required_realised = {
        "delivery_start_utc", "product", "cleared_volume_mw",
        "clearing_price_gbp_per_mw_per_hour", "window_hours",
    }
    missing = sorted(required_realised.difference(realised_quick_reserve.columns))
    if missing:
        raise ValueError(f"Realised QR frame is missing columns: {missing}")
    schedule_work = schedule.copy()
    schedule_work["delivery_start_utc"] = pd.to_datetime(
        schedule_work["delivery_start_utc"], utc=True
    )
    long = schedule_work.melt(
        id_vars=["delivery_start_utc"],
        value_vars=["pqr_contracted_mw", "nqr_contracted_mw"],
        var_name="schedule_product", value_name="offered_capacity_mw",
    )
    long["product"] = long["schedule_product"].map({
        "pqr_contracted_mw": "PQR", "nqr_contracted_mw": "NQR"
    })
    realised = realised_quick_reserve[list(required_realised)].copy()
    realised["delivery_start_utc"] = pd.to_datetime(
        realised["delivery_start_utc"], utc=True
    )
    if realised.duplicated(["delivery_start_utc", "product"]).any():
        raise ValueError("Realised QR frame contains duplicate product/windows.")
    scored = long.merge(
        realised, on=["delivery_start_utc", "product"], how="left",
        validate="one_to_one",
    )
    if scored[["cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour"]].isna().any().any():
        raise ValueError("QR capacity scoring produced missing realised auction results.")
    offered = pd.to_numeric(scored["offered_capacity_mw"], errors="raise").to_numpy(float)
    system_volume = pd.to_numeric(scored["cleared_volume_mw"], errors="raise").to_numpy(float)
    if (offered < -1e-9).any() or (system_volume < -1e-9).any():
        raise ValueError("QR offered/system capacity cannot be negative.")
    scored["accepted_capacity_mw"] = np.minimum(offered, system_volume)
    scored["realised_availability_payment_gbp"] = (
        scored["accepted_capacity_mw"]
        * scored["clearing_price_gbp_per_mw_per_hour"].astype(float)
        * scored["window_hours"].astype(float)
    )
    payment = float(scored["realised_availability_payment_gbp"].sum())
    offered_hours = float(
        (scored["offered_capacity_mw"] * scored["window_hours"].astype(float)).sum()
    )
    accepted_hours = float(
        (scored["accepted_capacity_mw"] * scored["window_hours"].astype(float)).sum()
    )
    summary: dict[str, Any] = {
        "realised_availability_payment_gbp": payment,
        "offered_mw_hours": offered_hours,
        "accepted_mw_hours_under_price_taker_assumption": accepted_hours,
        "acceptance_assumption": (
            "offered capacity is accepted up to realised system-cleared volume; "
            "asset merit-order position is not identified"
        ),
    }
    return scored, summary
