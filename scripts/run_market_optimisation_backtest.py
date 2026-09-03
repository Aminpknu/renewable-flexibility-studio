"""Backtest ex-post settlement-aware firming against error-minimising reactive firming."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.design_grid import load_design_grid, scaled_design_grid
from adapters.forecast_data import load_historical_predictions
from adapters.imbalance_settlement import load_system_price_history, select_system_prices
from adapters.market_reference import load_market_index_history, select_market_index_prices
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.design_sizing import select_stable_design
from engine.imbalance import apply_imbalance_settlement, summarise_imbalance_settlement
from engine.market_optimisation import (
    SettlementOptimisationConfig, WholesaleArbitrageConfig,
    optimise_firming_and_arbitrage, optimise_settlement_aware_firming,
    optimise_wholesale_arbitrage,
)
from engine.portfolio import build_virtual_portfolio

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs" / "market_optimisation"
DAILY_PATH = OUTPUT_DIR / "default_mixed_daily.csv"
SUMMARY_PATH = OUTPUT_DIR / "default_mixed_summary.json"
THROUGHPUT_COST = 2.0


def _market_vwap(frame: pd.DataFrame) -> float:
    volume = float(frame["market_index_volume_mwh"].sum())
    if volume <= 0:
        raise ValueError("Market-index daily volume must be positive for VWAP restoration price.")
    return float(
        (frame["market_index_price_gbp_per_mwh"] * frame["market_index_volume_mwh"]).sum()
        / volume
    )


def _reactive_value(
    portfolio: pd.DataFrame,
    system_prices: pd.DataFrame,
    battery: BatteryConfig,
    restoration_price: float,
) -> dict[str, float]:
    simulation = simulate_reactive_firming(portfolio, battery)
    settlement = apply_imbalance_settlement(simulation, system_prices)
    summary = summarise_imbalance_settlement(settlement)
    ending_soc = float(simulation["soc_end_mwh"].iloc[-1])
    if ending_soc < battery.initial_soc_mwh:
        restore_import = (battery.initial_soc_mwh - ending_soc) / battery.charge_efficiency
        restore_export = 0.0
    else:
        restore_import = 0.0
        restore_export = (ending_soc - battery.initial_soc_mwh) * battery.discharge_efficiency
    restoration_net_cost = (restore_import - restore_export) * restoration_price
    throughput = float(
        (simulation["charge_mw"].sum() + simulation["discharge_mw"].sum())
        * battery.interval_hours
    )
    throughput_cost = throughput * THROUGHPUT_COST
    settlement_improvement = (
        float(summary["signed_cashflow_before_gbp"])
        - float(summary["signed_cashflow_after_gbp"])
    )
    return {
        "reactive_error_reduction_pct": float(
            100.0 * (1.0 - summary["absolute_imbalance_after_mwh"] / summary["absolute_imbalance_before_mwh"])
            if summary["absolute_imbalance_before_mwh"] > 0 else 0.0
        ),
        "reactive_settlement_improvement_gbp": settlement_improvement,
        "reactive_restore_import_mwh": float(restore_import),
        "reactive_restore_export_mwh": float(restore_export),
        "reactive_restoration_net_cost_gbp": float(restoration_net_cost),
        "reactive_throughput_mwh": throughput,
        "reactive_throughput_cost_gbp": throughput_cost,
        "reactive_net_value_improvement_gbp": float(
            settlement_improvement - restoration_net_cost - throughput_cost
        ),
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    history = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
    system_history = load_system_price_history(ROOT / "data" / "elexon_system_prices.csv")
    market_history = load_market_index_history(ROOT / "data" / "elexon_market_index_prices.csv")
    design_grid = scaled_design_grid(
        load_design_grid(ROOT / "outputs" / "design_sizing_grid_100mw.csv"),
        "mixed", 100.0, 50.0,
    )
    selected = select_stable_design(design_grid, 90, 90)
    if selected is None:
        raise RuntimeError("No default 90/90 mixed design is available.")
    battery = BatteryConfig(
        power_mw=float(selected["power_mw"]),
        duration_hours=float(selected["duration_hours"]),
        round_trip_efficiency=0.90,
        initial_soc_fraction=0.50,
    )
    portfolio = build_virtual_portfolio(history, "mixed", 100.0, wind_share=0.5)
    dates = sorted(pd.to_datetime(portfolio["settlement_date"]).dt.normalize().unique())
    rows: list[dict[str, float | str]] = []
    for index, target in enumerate(dates, start=1):
        target_text = pd.Timestamp(target).date().isoformat()
        day = portfolio.loc[pd.to_datetime(portfolio["settlement_date"]).dt.normalize().eq(target)].copy()
        system = select_system_prices(system_history, target_text)
        market = select_market_index_prices(market_history, target_text)
        restoration_price = _market_vwap(market)
        _optimised_frame, optimised = optimise_settlement_aware_firming(
            day,
            system,
            battery,
            SettlementOptimisationConfig(
                restoration_price_gbp_per_mwh=restoration_price,
                throughput_cost_gbp_per_mwh=THROUGHPUT_COST,
            ),
        )
        reactive = _reactive_value(day, system, battery, restoration_price)
        _arbitrage_frame, arbitrage = optimise_wholesale_arbitrage(
            market, battery, WholesaleArbitrageConfig(THROUGHPUT_COST)
        )
        _coopt_frame, coopt = optimise_firming_and_arbitrage(
            day, system, market, battery, THROUGHPUT_COST
        )
        rows.append({
            "settlement_date": target_text,
            "market_index_vwap_gbp_per_mwh": restoration_price,
            "system_price_mean_gbp_per_mwh": float(system["system_price_gbp_per_mwh"].mean()),
            "system_price_max_gbp_per_mwh": float(system["system_price_gbp_per_mwh"].max()),
            "market_error_reduction_pct": float(optimised["error_reduction_pct"]),
            "market_settlement_improvement_gbp": float(
                optimised["settlement_value_improvement_before_costs_gbp"]
            ),
            "market_restore_import_mwh": float(optimised["grid_restoration_import_mwh"]),
            "market_restore_export_mwh": float(optimised["grid_restoration_export_mwh"]),
            "market_restoration_net_cost_gbp": float(optimised["restoration_net_cost_gbp"]),
            "market_throughput_mwh": float(optimised["throughput_mwh"]),
            "market_throughput_cost_gbp": float(optimised["throughput_cost_gbp"]),
            "market_net_value_improvement_gbp": float(
                optimised["net_settlement_value_improvement_gbp"]
            ),
            "arbitrage_gross_margin_gbp": float(arbitrage["gross_arbitrage_margin_gbp"]),
            "arbitrage_net_margin_gbp": float(arbitrage["net_arbitrage_margin_gbp"]),
            "arbitrage_throughput_mwh": float(arbitrage["throughput_mwh"]),
            "coopt_net_value_gbp": float(coopt["net_cooptimised_value_gbp"]),
            "coopt_firming_value_gbp": float(coopt["firming_settlement_value_gbp"]),
            "coopt_arbitrage_value_gbp": float(coopt["wholesale_arbitrage_value_gbp"]),
            "coopt_throughput_mwh": float(coopt["throughput_mwh"]),
            "coopt_error_reduction_pct": float(coopt["error_reduction_pct"]),
            **reactive,
        })
        if index % 50 == 0:
            print(f"completed {index}/{len(dates)}", flush=True)
    daily = pd.DataFrame(rows)
    daily.to_csv(DAILY_PATH, index=False, lineterminator="\n")
    annualisation = 365.25 / float(len(daily))
    market_total = float(daily["market_net_value_improvement_gbp"].sum())
    reactive_total = float(daily["reactive_net_value_improvement_gbp"].sum())
    arbitrage_total = float(daily["arbitrage_net_margin_gbp"].sum())
    coopt_total = float(daily["coopt_net_value_gbp"].sum())
    if (daily["coopt_net_value_gbp"] + 1e-5 < daily["arbitrage_net_margin_gbp"]).any():
        raise AssertionError("Co-optimisation underperformed the feasible arbitrage-only strategy.")
    delta = daily["market_net_value_improvement_gbp"] - daily["reactive_net_value_improvement_gbp"]
    summary = {
        "schema_version": "1.0",
        "stage": "9_market_optimisation_packet1",
        "method": "ex-post System Price settlement-aware directional firming",
        "perfect_information": True,
        "portfolio": {"type": "mixed", "capacity_mw": 100.0, "wind_share_pct": 50.0},
        "battery": {
            "power_mw": battery.power_mw,
            "energy_mwh": battery.energy_capacity_mwh,
            "duration_hours": battery.duration_hours,
            "initial_soc_pct": battery.initial_soc_fraction * 100.0,
        },
        "market_reference": {
            "source": "Elexon APXMIDP Market Index Data",
            "semantic_label": "short-term GB wholesale reference; not day-ahead auction price",
            "daily_restoration_price": "APXMIDP volume-weighted average price",
        },
        "throughput_cost_gbp_per_mwh": THROUGHPUT_COST,
        "observed_days": int(len(daily)),
        "market_aware_total_net_value_improvement_gbp": market_total,
        "reactive_total_net_value_improvement_gbp": reactive_total,
        "market_aware_annualised_net_value_improvement_gbp": market_total * annualisation,
        "reactive_annualised_net_value_improvement_gbp": reactive_total * annualisation,
        "arbitrage_total_net_margin_gbp": arbitrage_total,
        "arbitrage_annualised_net_margin_gbp": arbitrage_total * annualisation,
        "arbitrage_positive_margin_days_pct": float(100.0 * daily["arbitrage_net_margin_gbp"].gt(0).mean()),
        "cooptimised_total_net_value_gbp": coopt_total,
        "cooptimised_annualised_net_value_gbp": coopt_total * annualisation,
        "cooptimised_incremental_value_vs_arbitrage_gbp": coopt_total - arbitrage_total,
        "cooptimised_positive_value_days_pct": float(100.0 * daily["coopt_net_value_gbp"].gt(0).mean()),
        "market_aware_positive_value_days_pct": float(100.0 * daily["market_net_value_improvement_gbp"].gt(0).mean()),
        "reactive_positive_value_days_pct": float(100.0 * daily["reactive_net_value_improvement_gbp"].gt(0).mean()),
        "market_aware_better_than_reactive_days_pct": float(100.0 * delta.gt(1e-9).mean()),
        "mean_daily_error_reduction_pct_market_aware": float(daily["market_error_reduction_pct"].mean()),
        "mean_daily_error_reduction_pct_reactive": float(daily["reactive_error_reduction_pct"].mean()),
        "market_aware_daily_net_value_p10_gbp": float(daily["market_net_value_improvement_gbp"].quantile(0.10)),
        "market_aware_daily_net_value_p50_gbp": float(daily["market_net_value_improvement_gbp"].quantile(0.50)),
        "market_aware_daily_net_value_p90_gbp": float(daily["market_net_value_improvement_gbp"].quantile(0.90)),
        "reactive_daily_net_value_p50_gbp": float(daily["reactive_net_value_improvement_gbp"].quantile(0.50)),
        "arbitrage_daily_net_margin_p10_gbp": float(daily["arbitrage_net_margin_gbp"].quantile(0.10)),
        "arbitrage_daily_net_margin_p50_gbp": float(daily["arbitrage_net_margin_gbp"].quantile(0.50)),
        "arbitrage_daily_net_margin_p90_gbp": float(daily["arbitrage_net_margin_gbp"].quantile(0.90)),
        "cooptimised_daily_net_value_p10_gbp": float(daily["coopt_net_value_gbp"].quantile(0.10)),
        "cooptimised_daily_net_value_p50_gbp": float(daily["coopt_net_value_gbp"].quantile(0.50)),
        "cooptimised_daily_net_value_p90_gbp": float(daily["coopt_net_value_gbp"].quantile(0.90)),
        "mean_daily_error_reduction_pct_cooptimised": float(daily["coopt_error_reduction_pct"].mean()),
        "limitations": [
            "perfect-information benchmark uses realised System Price and realised forecast error",
            "Market Index Data is a public short-term wholesale reference, not a day-ahead auction price",
            "throughput cost is a transparent scenario assumption",
            "no ancillary-service revenue, taxes, financing or site-specific grid constraints",
        ],
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("saved", DAILY_PATH)
    print("saved", SUMMARY_PATH)


if __name__ == "__main__":
    main()
