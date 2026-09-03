"""Backtest prior-date QR price forecasts and pre-delivery capacity allocation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from adapters.forecast_data import load_historical_predictions
from adapters.quick_reserve import load_quick_reserve_history
from engine.battery import BatteryConfig
from engine.quick_reserve import QuickReserveStackingConfig, optimise_arbitrage_and_quick_reserve
from engine.quick_reserve_forecast import (
    QuickReserveForecastConfig,
    backtest_quick_reserve_price_forecast,
)
from engine.quick_reserve_strategy import (
    build_qr_capacity_schedule_from_signal,
    evaluate_qr_capacity_schedule,
)

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "neso_quick_reserve_forecast_history.csv"
CURRENT_QR_PATH = ROOT / "data" / "neso_quick_reserve_prices.csv"
V2_PATH = ROOT / "data" / "historical_backtest.csv"
OUTPUT_DIR = ROOT / "outputs" / "quick_reserve"
BATTERY = BatteryConfig(
    power_mw=25.0, duration_hours=8.0, round_trip_efficiency=0.90,
    initial_soc_fraction=0.50,
)
CONFIG = QuickReserveForecastConfig(
    minimum_history_days=60, lookback_days=180, ridge_alpha=20.0
)
GUARD_WINDOWS = 2


def _realised_for_signal(signal_day: pd.DataFrame, realised: pd.DataFrame) -> pd.DataFrame:
    times = pd.Index(pd.to_datetime(signal_day["delivery_start_utc"], utc=True).unique())
    selected = realised.loc[realised["delivery_start_utc"].isin(times)].copy()
    expected = 2 * len(times)
    if len(selected) != expected:
        raise ValueError(f"Expected {expected} realised QR product/windows, found {len(selected)}.")
    return selected


def _dummy_market(signal_day: pd.DataFrame) -> pd.DataFrame:
    times = pd.Index(pd.to_datetime(signal_day["delivery_start_utc"], utc=True).unique()).sort_values()
    return pd.DataFrame({
        "valid_time_utc": times,
        "market_index_price_gbp_per_mwh": np.zeros(len(times), dtype=float),
    })


def _perfect_qr_schedule(realised_day: pd.DataFrame, signal_day: pd.DataFrame):
    schedule, summary = optimise_arbitrage_and_quick_reserve(
        _dummy_market(signal_day),
        realised_day,
        BATTERY,
        QuickReserveStackingConfig(
            throughput_cost_gbp_per_mwh=0.0,
            crossover_guard_windows=GUARD_WINDOWS,
            enable_arbitrage=False,
        ),
    )
    return schedule[[
        "valid_time_utc", "pqr_contracted_mw", "nqr_contracted_mw"
    ]].rename(columns={"valid_time_utc": "delivery_start_utc"}), summary


def _schedule_distance(schedule: pd.DataFrame, perfect: pd.DataFrame) -> float:
    left = schedule.copy()
    right = perfect.copy()
    left["delivery_start_utc"] = pd.to_datetime(left["delivery_start_utc"], utc=True)
    right["delivery_start_utc"] = pd.to_datetime(right["delivery_start_utc"], utc=True)
    joined = left.merge(
        right, on="delivery_start_utc", suffixes=("_signal", "_perfect"),
        how="inner", validate="one_to_one",
    )
    distance = (
        (joined["pqr_contracted_mw_signal"] - joined["pqr_contracted_mw_perfect"]).abs()
        + (joined["nqr_contracted_mw_signal"] - joined["nqr_contracted_mw_perfect"]).abs()
    )
    return float(distance.mean())


def _mean_commitments(schedule: pd.DataFrame) -> tuple[float, float]:
    return (
        float(schedule["pqr_contracted_mw"].mean()),
        float(schedule["nqr_contracted_mw"].mean()),
    )


def main() -> None:
    history = pd.read_csv(HISTORY_PATH)
    realised = load_quick_reserve_history(str(CURRENT_QR_PATH))
    v2 = load_historical_predictions(V2_PATH)
    forecast_rows, price_summary = backtest_quick_reserve_price_forecast(history, CONFIG)
    locked_dates = sorted(
        pd.to_datetime(
            v2.loc[v2["evaluation_segment"].eq("locked_test"), "settlement_date"]
        ).dt.strftime("%Y-%m-%d").unique()
    )
    rows = []
    allocation_records = []
    for index, date_text in enumerate(locked_dates, start=1):
        target = pd.Timestamp(date_text).normalize()
        signal_day = forecast_rows.loc[
            pd.to_datetime(forecast_rows["settlement_date"]).dt.normalize().eq(target)
        ].copy()
        if signal_day.empty:
            continue
        realised_day = _realised_for_signal(signal_day, realised)
        perfect_schedule, perfect = _perfect_qr_schedule(realised_day, signal_day)
        forecast_schedule = build_qr_capacity_schedule_from_signal(
            signal_day, BATTERY,
            price_column="forecast_qr_clearing_price_gbp_per_mw_per_hour",
            crossover_guard_windows=GUARD_WINDOWS,
        )
        naive_schedule = build_qr_capacity_schedule_from_signal(
            signal_day, BATTERY,
            price_column="naive_qr_clearing_price_gbp_per_mw_per_hour",
            crossover_guard_windows=GUARD_WINDOWS,
        )
        _forecast_scored, forecast_value = evaluate_qr_capacity_schedule(
            forecast_schedule, realised_day
        )
        _naive_scored, naive_value = evaluate_qr_capacity_schedule(
            naive_schedule, realised_day
        )
        perfect_value = float(perfect["net_stacked_value_gbp"])
        forecast_payment = float(forecast_value["realised_availability_payment_gbp"])
        naive_payment = float(naive_value["realised_availability_payment_gbp"])
        forecast_pqr, forecast_nqr = _mean_commitments(forecast_schedule)
        naive_pqr, naive_nqr = _mean_commitments(naive_schedule)
        perfect_pqr, perfect_nqr = _mean_commitments(perfect_schedule)
        rows.append({
            "settlement_date": date_text,
            "perfect_qr_availability_gbp": perfect_value,
            "forecast_selected_qr_availability_gbp": forecast_payment,
            "naive_selected_qr_availability_gbp": naive_payment,
            "forecast_capture_pct": (
                100.0 * forecast_payment / perfect_value if perfect_value > 0 else 100.0
            ),
            "naive_capture_pct": (
                100.0 * naive_payment / perfect_value if perfect_value > 0 else 100.0
            ),
            "forecast_regret_gbp": perfect_value - forecast_payment,
            "naive_regret_gbp": perfect_value - naive_payment,
            "forecast_mean_abs_commitment_error_mw": _schedule_distance(
                forecast_schedule, perfect_schedule
            ),
            "naive_mean_abs_commitment_error_mw": _schedule_distance(
                naive_schedule, perfect_schedule
            ),
            "forecast_mean_pqr_mw": forecast_pqr,
            "forecast_mean_nqr_mw": forecast_nqr,
            "naive_mean_pqr_mw": naive_pqr,
            "naive_mean_nqr_mw": naive_nqr,
            "perfect_mean_pqr_mw": perfect_pqr,
            "perfect_mean_nqr_mw": perfect_nqr,
        })
        allocation = forecast_schedule.copy()
        allocation["settlement_date"] = date_text
        allocation_records.append(allocation)
        if index % 30 == 0:
            print(f"completed {index}/{len(locked_dates)}", flush=True)
    daily = pd.DataFrame(rows)
    if daily.empty:
        raise RuntimeError("No locked QR allocation days were evaluated.")
    annualisation = 365.25 / float(len(daily))
    perfect_total = float(daily["perfect_qr_availability_gbp"].sum())
    forecast_total = float(daily["forecast_selected_qr_availability_gbp"].sum())
    naive_total = float(daily["naive_selected_qr_availability_gbp"].sum())
    locked_price_rows = forecast_rows.loc[
        pd.to_datetime(forecast_rows["settlement_date"]).dt.strftime("%Y-%m-%d").isin(
            set(daily["settlement_date"])
        )
    ].copy()
    actual_price = locked_price_rows["clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    forecast_price = locked_price_rows[
        "forecast_qr_clearing_price_gbp_per_mw_per_hour"
    ].to_numpy(float)
    naive_price = locked_price_rows[
        "naive_qr_clearing_price_gbp_per_mw_per_hour"
    ].to_numpy(float)
    locked_forecast_mae = float(np.mean(np.abs(forecast_price - actual_price)))
    locked_naive_mae = float(np.mean(np.abs(naive_price - actual_price)))
    payload = {
        "schema_version": "1.0",
        "stage": "9_quick_reserve_predelivery_capacity_signal",
        "method": "prior-date QR clearing-price forecast -> whole-MW PQR/NQR allocation",
        "guard_windows": GUARD_WINDOWS,
        "locked_days": int(len(daily)),
        "price_forecast": price_summary,
        "locked_price_mae_gbp_per_mw_per_hour": locked_forecast_mae,
        "locked_naive_price_mae_gbp_per_mw_per_hour": locked_naive_mae,
        "perfect_qr_availability_annualised_gbp": perfect_total * annualisation,
        "forecast_selected_availability_annualised_gbp": forecast_total * annualisation,
        "naive_selected_availability_annualised_gbp": naive_total * annualisation,
        "forecast_value_capture_pct": float(
            100.0 * forecast_total / perfect_total if perfect_total > 0 else 100.0
        ),
        "naive_value_capture_pct": float(
            100.0 * naive_total / perfect_total if perfect_total > 0 else 100.0
        ),
        "forecast_uplift_vs_naive_annualised_gbp": (
            forecast_total - naive_total
        ) * annualisation,
        "forecast_beats_naive_days_pct": float(
            100.0
            * daily["forecast_selected_qr_availability_gbp"].gt(
                daily["naive_selected_qr_availability_gbp"]
            ).mean()
        ),
        "mean_forecast_commitment_error_mw": float(
            daily["forecast_mean_abs_commitment_error_mw"].mean()
        ),
        "mean_naive_commitment_error_mw": float(
            daily["naive_mean_abs_commitment_error_mw"].mean()
        ),
        "mean_forecast_pqr_mw": float(daily["forecast_mean_pqr_mw"].mean()),
        "mean_forecast_nqr_mw": float(daily["forecast_mean_nqr_mw"].mean()),
        "mean_perfect_pqr_mw": float(daily["perfect_mean_pqr_mw"].mean()),
        "mean_perfect_nqr_mw": float(daily["perfect_mean_nqr_mw"].mean()),
        "daily_forecast_value_p10_gbp": float(
            daily["forecast_selected_qr_availability_gbp"].quantile(0.10)
        ),
        "daily_forecast_value_p50_gbp": float(
            daily["forecast_selected_qr_availability_gbp"].quantile(0.50)
        ),
        "daily_forecast_value_p90_gbp": float(
            daily["forecast_selected_qr_availability_gbp"].quantile(0.90)
        ),
        "acceptance_assumption": (
            "forecast-selected capacity is accepted up to realised system-cleared volume; "
            "asset bid merit-order position is not identified"
        ),
        "limitations": [
            "capacity allocation is selected before the target date using prior-date clearing-price evidence only",
            "realised clearing price and system-cleared volume are used only for ex-post scoring",
            "individual asset bid price and merit-order acceptance are not yet simulated",
            "Quick Reserve utilisation payment and activation energy are excluded",
            "current-rule economic validation uses the 90 V2 locked Apr-Jun 2026 dates",
        ],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    daily.to_csv(OUTPUT_DIR / "quick_reserve_predelivery_daily.csv", index=False)
    pd.concat(allocation_records, ignore_index=True).to_csv(
        OUTPUT_DIR / "quick_reserve_predelivery_allocations.csv", index=False
    )
    forecast_rows.to_csv(
        OUTPUT_DIR / "quick_reserve_price_forecast_backtest.csv", index=False
    )
    (OUTPUT_DIR / "quick_reserve_predelivery_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
