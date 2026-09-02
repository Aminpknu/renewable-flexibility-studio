"""Run 450-day BSC-style System Price exposure analysis for default portfolios."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from adapters.imbalance_settlement import load_system_price_history
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.imbalance import apply_imbalance_settlement, summarise_imbalance_settlement
from engine.portfolio import build_virtual_portfolio

ROOT = Path(__file__).resolve().parents[1]
HISTORY = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
PRICES = load_system_price_history(ROOT / "data" / "elexon_system_prices.csv")
SUMMARY_PATH = ROOT / "outputs" / "imbalance_backtest_summary.json"
DAILY_PATH = ROOT / "outputs" / "daily_imbalance_exposure.csv"

CONFIG = BatteryConfig(
    power_mw=25.0,
    duration_hours=2.0,
    round_trip_efficiency=0.90,
    initial_soc_fraction=0.50,
)


def main() -> None:
    summaries = {}
    daily_parts = []
    for kind in ("wind", "solar", "mixed"):
        portfolio = build_virtual_portfolio(HISTORY, kind, 100.0, wind_share=0.5)
        simulation = simulate_reactive_firming(portfolio, CONFIG)
        settled = apply_imbalance_settlement(simulation, PRICES)
        summary = summarise_imbalance_settlement(settled)
        summary["portfolio_type"] = kind
        summary["portfolio_capacity_mw"] = 100.0
        summary["battery_power_mw"] = CONFIG.power_mw
        summary["battery_energy_mwh"] = CONFIG.energy_capacity_mwh
        summary["target_days"] = int(settled["settlement_date"].nunique())
        summaries[kind] = summary

        daily = settled.groupby("settlement_date", as_index=False).agg(
            gross_exposure_before_gbp=("gross_cashout_exposure_before_gbp", "sum"),
            gross_exposure_after_gbp=("gross_cashout_exposure_after_gbp", "sum"),
            signed_cashflow_before_gbp=("settlement_cashflow_before_gbp", "sum"),
            signed_cashflow_after_gbp=("settlement_cashflow_after_gbp", "sum"),
            absolute_imbalance_before_mwh=("imbalance_before_mwh", lambda s: s.abs().sum()),
            absolute_imbalance_after_mwh=("imbalance_after_mwh", lambda s: s.abs().sum()),
            peak_system_price_gbp_per_mwh=("system_price_gbp_per_mwh", "max"),
        )
        daily.insert(0, "portfolio_type", kind)
        daily["gross_exposure_reduction_gbp"] = (
            daily["gross_exposure_before_gbp"] - daily["gross_exposure_after_gbp"]
        )
        summary["mean_daily_gross_exposure_before_gbp"] = float(
            daily["gross_exposure_before_gbp"].mean()
        )
        summary["mean_daily_gross_exposure_after_gbp"] = float(
            daily["gross_exposure_after_gbp"].mean()
        )
        summary["p95_daily_gross_exposure_before_gbp"] = float(
            daily["gross_exposure_before_gbp"].quantile(0.95)
        )
        summary["p95_daily_gross_exposure_after_gbp"] = float(
            daily["gross_exposure_after_gbp"].quantile(0.95)
        )
        summary["days_with_lower_gross_exposure"] = int(
            (daily["gross_exposure_after_gbp"] < daily["gross_exposure_before_gbp"]).sum()
        )
        daily_parts.append(daily)
        print(kind, json.dumps(summary, indent=2))

    daily_all = pd.concat(daily_parts, ignore_index=True)
    daily_all.to_csv(DAILY_PATH, index=False)
    SUMMARY_PATH.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print("saved", SUMMARY_PATH)
    print("saved", DAILY_PATH)


if __name__ == "__main__":
    main()
