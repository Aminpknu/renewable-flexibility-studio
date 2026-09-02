"""Run the leakage-safe 450-day V2 continuous-SOC battery benchmark."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.metrics import calculate_firming_metrics
from engine.portfolio import build_virtual_portfolio
from engine.sizing import find_minimum_battery

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "historical_backtest.csv"
OUTPUTS = ROOT / "outputs"


def _run_portfolio(kind: str) -> tuple[dict, pd.DataFrame]:
    source = load_historical_predictions(DATA)
    portfolio = build_virtual_portfolio(source, kind, capacity_mw=100.0, wind_share=0.5)
    config = BatteryConfig(power_mw=25.0, duration_hours=2.0)
    simulation = simulate_reactive_firming(portfolio, config)
    metrics = calculate_firming_metrics(simulation, config)
    metrics["portfolio_type"] = kind
    metrics["target_days"] = int(source["settlement_date"].nunique())
    metrics["initial_soc_pct"] = config.initial_soc_fraction * 100
    metrics["net_soc_change_mwh"] = float(simulation["soc_end_mwh"].iloc[-1] - config.initial_soc_mwh)
    powers = [5, 10, 15, 20, 25, 30, 40, 50]
    best, comparison = find_minimum_battery(
        portfolio,
        target_absorbed_pct=80.0,
        power_candidates_mw=powers,
        duration_candidates_hours=(1.0, 2.0, 4.0),
    )
    comparison.insert(0, "portfolio_type", kind)
    metrics["minimum_tested_80pct_configuration"] = best
    return metrics, comparison


def main() -> None:
    OUTPUTS.mkdir(exist_ok=True)
    summaries: dict[str, dict] = {}
    tables = []
    for kind in ("wind", "solar", "mixed"):
        metrics, comparison = _run_portfolio(kind)
        summaries[kind] = metrics
        tables.append(comparison)
        print(kind, json.dumps({
            "error_reduction_pct": metrics["error_reduction_pct"],
            "ending_soc_pct": metrics["ending_soc_pct"],
            "minimum_80pct": metrics["minimum_tested_80pct_configuration"],
        }, indent=2))
    pd.concat(tables, ignore_index=True).to_csv(OUTPUTS / "full_backtest_sizing.csv", index=False)
    (OUTPUTS / "full_backtest_summary.json").write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
