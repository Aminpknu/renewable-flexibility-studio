"""Generate Stage 6A Packet 1 physical-risk evidence for the default portfolio."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.portfolio import build_virtual_portfolio
from engine.risk import PhysicalRiskConfig, summarise_physical_risk

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "historical_backtest.csv"
OUTPUT_DIR = ROOT / "outputs" / "risk_value"
SUMMARY_PATH = OUTPUT_DIR / "physical_risk_default.json"

PORTFOLIO_CAPACITY_MW = 100.0
WIND_SHARE = 0.50
LARGE_DEVIATION_THRESHOLD_MW = 10.0

CONFIGURATIONS = {
    "25mw_2h": BatteryConfig(power_mw=25.0, duration_hours=2.0),
    "25mw_4h": BatteryConfig(power_mw=25.0, duration_hours=4.0),
    "25mw_8h_selected": BatteryConfig(power_mw=25.0, duration_hours=8.0),
}

def _simulate_daily_restored(portfolio: pd.DataFrame, battery: BatteryConfig) -> pd.DataFrame:
    """Reset to configured initial SOC before each historical target day."""
    parts: list[pd.DataFrame] = []
    dates = pd.to_datetime(portfolio["settlement_date"], errors="raise").dt.normalize()
    for target in dates.drop_duplicates().sort_values():
        day = portfolio.loc[dates.eq(target)].copy()
        simulated = simulate_reactive_firming(day, battery)
        parts.append(simulated)
    return pd.concat(parts, ignore_index=True)


def main() -> None:
    history = load_historical_predictions(HISTORY_PATH)
    portfolio = build_virtual_portfolio(
        history,
        portfolio_type="mixed",
        capacity_mw=PORTFOLIO_CAPACITY_MW,
        wind_share=WIND_SHARE,
    )
    risk_config = PhysicalRiskConfig(
        large_deviation_threshold_mw=LARGE_DEVIATION_THRESHOLD_MW
    )
    summaries: dict[str, object] = {}
    for label, battery in CONFIGURATIONS.items():
        simulation = _simulate_daily_restored(portfolio, battery)
        risk = summarise_physical_risk(simulation, risk_config)
        risk.update({
            "battery_power_mw": battery.power_mw,
            "battery_energy_mwh": battery.energy_capacity_mwh,
            "battery_duration_hours": battery.duration_hours,
            "initial_soc_pct": battery.initial_soc_fraction * 100.0,
        })
        summaries[label] = risk
    payload = {
        "schema_version": "1.0",
        "stage": "6A_packet1_physical_risk",
        "portfolio_type": "mixed",
        "portfolio_capacity_mw": PORTFOLIO_CAPACITY_MW,
        "wind_share_pct": WIND_SHARE * 100.0,
        "large_deviation_threshold_mw": LARGE_DEVIATION_THRESHOLD_MW,
        "operating_convention": "SOC restored to 50% before each target day",
        "observation_start": str(pd.to_datetime(portfolio["settlement_date"]).min().date()),
        "observation_end": str(pd.to_datetime(portfolio["settlement_date"]).max().date()),
        "summaries": summaries,
        "limitations": [
            "physical exposure only; no monetary consequence value is applied",
            "annualisation extrapolates the observed historical period",
            "large-deviation threshold is an explicit scenario assumption",
        ],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print(f"saved {SUMMARY_PATH}")


if __name__ == "__main__":
    main()