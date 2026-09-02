"""Run the default historical scenario without starting the web interface."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.forecast_data import load_historical_predictions, select_date
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.metrics import calculate_firming_metrics
from engine.portfolio import build_virtual_portfolio
from engine.sizing import find_minimum_battery

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    data = load_historical_predictions(ROOT / "data" / "sample_historical.csv")
    day = select_date(data, "2025-06-01")
    portfolio = build_virtual_portfolio(day, "mixed", capacity_mw=100, wind_share=0.5)
    config = BatteryConfig(
        power_mw=25,
        duration_hours=2,
        round_trip_efficiency=0.90,
        initial_soc_fraction=0.50,
    )
    simulation = simulate_reactive_firming(portfolio, config)
    metrics = calculate_firming_metrics(simulation, config)
    best, _comparison = find_minimum_battery(
        portfolio,
        target_absorbed_pct=80,
        power_candidates_mw=[5, 10, 15, 20, 25, 30, 40, 50],
        duration_candidates_hours=[1, 2, 4],
    )

    print("DEFAULT SCENARIO METRICS")
    print(json.dumps(metrics, indent=2))
    print("\nMINIMUM TESTED CONFIGURATION FOR 80% TARGET")
    print(json.dumps(best, indent=2))
    print("\nFirst four settlement-period calculations:")
    print(
        simulation[
            [
                "settlement_period",
                "actual_mw",
                "forecast_mw",
                "forecast_error_mw",
                "charge_mw",
                "discharge_mw",
                "soc_start_mwh",
                "soc_end_mwh",
                "firmed_delivery_mw",
                "residual_error_mw",
            ]
        ]
        .head(4)
        .round(4)
        .to_string(index=False)
    )


if __name__ == "__main__":
    main()
