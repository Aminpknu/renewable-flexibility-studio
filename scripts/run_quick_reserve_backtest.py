"""Backtest Quick Reserve availability stacking on the locked Apr-Jun 2026 regime."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from adapters.forecast_data import load_historical_predictions
from adapters.market_reference import load_market_index_history, select_market_index_prices
from adapters.quick_reserve import load_quick_reserve_history
from engine.battery import BatteryConfig
from engine.market_optimisation import WholesaleArbitrageConfig, optimise_wholesale_arbitrage
from engine.quick_reserve import QuickReserveStackingConfig, optimise_arbitrage_and_quick_reserve

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
MARKET = load_market_index_history(ROOT / "data" / "elexon_market_index_prices.csv")
QR = load_quick_reserve_history(str(ROOT / "data" / "neso_quick_reserve_prices.csv"))
OUTPUT_DIR = ROOT / "outputs" / "quick_reserve"
BATTERY = BatteryConfig(power_mw=25.0, duration_hours=8.0, round_trip_efficiency=0.90, initial_soc_fraction=0.50)
THROUGHPUT_COST = 2.0


def _quick_reserve_for_market_day(market: pd.DataFrame) -> pd.DataFrame:
    valid = pd.to_datetime(market["valid_time_utc"], utc=True)
    selected = QR.loc[QR["delivery_start_utc"].isin(valid)].copy()
    expected = 2 * len(market)
    if len(selected) != expected:
        raise ValueError(f"Expected {expected} PQR/NQR rows, found {len(selected)}.")
    return selected


def _run_day(date_text: str, guard_windows: int = 2) -> dict:
    market = select_market_index_prices(MARKET, date_text)
    qr = _quick_reserve_for_market_day(market)
    _arb_frame, arb = optimise_wholesale_arbitrage(
        market, BATTERY, WholesaleArbitrageConfig(THROUGHPUT_COST)
    )
    _qr_frame, qr_only = optimise_arbitrage_and_quick_reserve(
        market, qr, BATTERY,
        QuickReserveStackingConfig(
            THROUGHPUT_COST, crossover_guard_windows=guard_windows,
            enable_arbitrage=False,
        ),
    )
    _stack_frame, stacked = optimise_arbitrage_and_quick_reserve(
        market, qr, BATTERY,
        QuickReserveStackingConfig(
            THROUGHPUT_COST, crossover_guard_windows=guard_windows,
            enable_arbitrage=True,
        ),
    )
    return {
        "settlement_date": date_text,
        "guard_windows": guard_windows,
        "arbitrage_value_gbp": arb["net_arbitrage_margin_gbp"],
        "qr_only_value_gbp": qr_only["net_stacked_value_gbp"],
        "stacked_value_gbp": stacked["net_stacked_value_gbp"],
        "stacked_availability_payment_gbp": stacked["total_availability_payment_gbp"],
        "stacked_pqr_mw_hours": stacked["pqr_contracted_mw_hours"],
        "stacked_nqr_mw_hours": stacked["nqr_contracted_mw_hours"],
    }


def _summarise(frame: pd.DataFrame) -> dict:
    days = int(frame["settlement_date"].nunique())
    annualisation = 365.25 / days
    independent = frame["arbitrage_value_gbp"] + frame["qr_only_value_gbp"]
    conflict = independent - frame["stacked_value_gbp"]
    return {
        "days": days,
        "annualisation_factor": annualisation,
        "arbitrage_annualised_gbp": float(frame["arbitrage_value_gbp"].sum() * annualisation),
        "qr_only_annualised_gbp": float(frame["qr_only_value_gbp"].sum() * annualisation),
        "stacked_annualised_gbp": float(frame["stacked_value_gbp"].sum() * annualisation),
        "stacked_availability_annualised_gbp": float(
            frame["stacked_availability_payment_gbp"].sum() * annualisation
        ),
        "incremental_stacked_vs_arbitrage_annualised_gbp": float(
            (frame["stacked_value_gbp"] - frame["arbitrage_value_gbp"]).sum() * annualisation
        ),
        "naive_independent_sum_annualised_gbp": float(independent.sum() * annualisation),
        "double_count_avoided_annualised_gbp": float(conflict.sum() * annualisation),
        "stacked_positive_value_days_pct": float(100.0 * frame["stacked_value_gbp"].gt(0).mean()),
        "mean_pqr_contracted_mw": float(frame["stacked_pqr_mw_hours"].sum() / (days * 24.0)),
        "mean_nqr_contracted_mw": float(frame["stacked_nqr_mw_hours"].sum() / (days * 24.0)),
        "daily_stacked_value_p10_gbp": float(frame["stacked_value_gbp"].quantile(0.10)),
        "daily_stacked_value_p50_gbp": float(frame["stacked_value_gbp"].quantile(0.50)),
        "daily_stacked_value_p90_gbp": float(frame["stacked_value_gbp"].quantile(0.90)),
    }


def main() -> None:
    locked_dates = sorted(
        pd.to_datetime(
            HISTORICAL.loc[HISTORICAL["evaluation_segment"].eq("locked_test"), "settlement_date"]
        ).dt.strftime("%Y-%m-%d").unique()
    )
    guard_frames = {}
    summaries = {}
    for guard in (1, 2, 4):
        rows = []
        for index, date_text in enumerate(locked_dates, start=1):
            rows.append(_run_day(date_text, guard))
            if index % 30 == 0:
                print(f"guard {guard}: completed {index}/{len(locked_dates)}", flush=True)
        frame = pd.DataFrame(rows)
        guard_frames[guard] = frame
        summaries[str(guard)] = _summarise(frame)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    baseline = guard_frames[2]
    baseline.to_csv(OUTPUT_DIR / "quick_reserve_daily.csv", index=False)
    payload = {
        "schema_version": "1.0",
        "stage": "9_quick_reserve_availability_stacking",
        "service": "Quick Reserve",
        "products": ["PQR", "NQR"],
        "price_source": "NESO EAC Results Summary",
        "price_unit": "GBP/MW/h",
        "payment_scope": "availability only; utilisation excluded",
        "acceptance_assumption": "price-taker capacity accepted at observed clearing price",
        "battery": {"power_mw": 25.0, "energy_mwh": 200.0, "duration_hours": 8.0},
        "throughput_cost_gbp_per_mwh": THROUGHPUT_COST,
        "baseline_crossover_guard_windows": 2,
        "guard_sensitivity": summaries,
        "limitations": [
            "perfect-information EAC clearing prices and APX Market Index prices",
            "individual asset auction acceptance is not modelled",
            "QR utilisation revenue and activation energy are excluded",
            "two-window guard is a screening rule, not proof of service prequalification",
            "site grid connection, telemetry and bid execution are not modelled",
        ],
    }
    (OUTPUT_DIR / "quick_reserve_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
