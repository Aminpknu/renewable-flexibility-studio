from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.forecast_data import load_historical_predictions, select_date
from adapters.imbalance_settlement import load_system_price_history, select_system_prices
from adapters.market_reference import load_market_index_history, select_market_index_prices
from adapters.neso_services import load_eac_service_history
from engine.battery import BatteryConfig
from engine.multiservice import MultiServiceConfig, optimise_firming_arbitrage_and_services
from engine.portfolio import build_virtual_portfolio

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "multiservice"
OUT.mkdir(parents=True, exist_ok=True)

HIST = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
SYSTEM = load_system_price_history(ROOT / "data" / "elexon_system_prices.csv")
MARKET = load_market_index_history(ROOT / "data" / "elexon_market_index_prices.csv")
SERVICES = load_eac_service_history(ROOT / "data" / "neso_multiservice_prices.csv")
BATTERY = BatteryConfig(power_mw=25.0, duration_hours=8.0, round_trip_efficiency=0.90, initial_soc_fraction=0.50)

SCENARIOS = {
    "qr_sr": MultiServiceConfig(enabled_families=("Quick Reserve", "Slow Reserve")),
    "non_bm_multiservice": MultiServiceConfig(
        enabled_families=("Quick Reserve", "Slow Reserve", "Dynamic Containment", "Dynamic Moderation", "Dynamic Regulation"),
        assume_bm_eligible=False,
    ),
    "bm_multiservice": MultiServiceConfig(assume_bm_eligible=True),
}


def annualise(value: float, days: int) -> float:
    return float(value * 365.25 / days)


def main() -> None:
    locked = HIST.loc[HIST["evaluation_segment"].eq("locked_test"), "settlement_date"].drop_duplicates().sort_values()
    dates = [pd.Timestamp(value).strftime("%Y-%m-%d") for value in locked]
    rows: list[dict] = []
    family_totals: dict[str, dict[str, float]] = {name: {} for name in SCENARIOS}
    for index, date in enumerate(dates, start=1):
        source = select_date(HIST, date)
        portfolio = build_virtual_portfolio(source, "mixed", 100.0, 0.5)
        system = select_system_prices(SYSTEM, date)
        market = select_market_index_prices(MARKET, date)
        for scenario_name, config in SCENARIOS.items():
            _frame, summary = optimise_firming_arbitrage_and_services(
                portfolio, system, market, SERVICES, BATTERY, config
            )
            row = {
                "settlement_date": date,
                "scenario": scenario_name,
                "net_value_gbp": summary["net_stacked_value_gbp"],
                "firming_value_gbp": summary["firming_settlement_value_gbp"],
                "arbitrage_value_gbp": summary["wholesale_arbitrage_value_gbp"],
                "ancillary_availability_gbp": summary["ancillary_availability_payment_gbp"],
                "throughput_cost_gbp": summary["throughput_cost_gbp"],
                "error_reduction_pct": summary["error_reduction_pct"],
                "service_contract_rows": summary["service_contract_rows"],
            }
            for family, payment in summary["family_availability_payment_gbp"].items():
                key = f"{family.lower().replace(' ', '_')}_availability_gbp"
                row[key] = payment
                family_totals[scenario_name][family] = family_totals[scenario_name].get(family, 0.0) + float(payment)
            rows.append(row)
        if index % 5 == 0 or index == len(dates):
            pd.DataFrame(rows).fillna(0.0).to_csv(OUT / "multiservice_daily_partial.csv", index=False)
            (OUT / "progress.json").write_text(
                json.dumps({"completed_dates": index, "total_dates": len(dates), "last_date": date}) + "\n",
                encoding="utf-8",
            )
            print(f"completed {index}/{len(dates)} dates", flush=True)

    daily = pd.DataFrame(rows).fillna(0.0)
    daily.to_csv(OUT / "multiservice_daily.csv", index=False)
    summary_payload: dict = {"stage": "11_neso_multiservice_availability_stacking", "days": len(dates), "battery": {"power_mw": 25.0, "energy_mwh": 200.0}}
    scenario_summary: dict[str, dict] = {}
    for scenario_name in SCENARIOS:
        selected = daily.loc[daily["scenario"].eq(scenario_name)]
        scenario_summary[scenario_name] = {
            "annualised_net_value_gbp": annualise(selected["net_value_gbp"].sum(), len(dates)),
            "annualised_firming_value_gbp": annualise(selected["firming_value_gbp"].sum(), len(dates)),
            "annualised_arbitrage_value_gbp": annualise(selected["arbitrage_value_gbp"].sum(), len(dates)),
            "annualised_ancillary_availability_gbp": annualise(selected["ancillary_availability_gbp"].sum(), len(dates)),
            "annualised_throughput_cost_gbp": annualise(selected["throughput_cost_gbp"].sum(), len(dates)),
            "mean_error_reduction_pct": float(selected["error_reduction_pct"].mean()),
            "family_annualised_availability_gbp": {
                family: annualise(total, len(dates)) for family, total in family_totals[scenario_name].items()
            },
        }
    summary_payload["scenarios"] = scenario_summary
    summary_payload["modelling_boundary"] = [
        "perfect-information/price-taker availability benchmark",
        "utilisation revenue, performance penalties and bid-acceptance uncertainty excluded",
        "one MW cannot be sold to multiple simultaneous ancillary products in this conservative release",
        "Dynamic Response blocks are retained as 4-hour commitments and only complete service windows inside each daily SOC-reset horizon are valued",
        "PSR linked-window identical-MW constraints are enforced for the current transition regime",
        "Balancing Reserve is included only in the explicit BM-eligible scenario",
    ]
    (OUT / "multiservice_summary.json").write_text(json.dumps(summary_payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary_payload, indent=2))


if __name__ == "__main__":
    main()
