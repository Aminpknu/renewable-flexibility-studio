"""Extended energy-capacity and initial-SOC sensitivity for the 450-day benchmark."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from adapters.forecast_data import load_historical_predictions
from engine.portfolio import build_virtual_portfolio
from engine.sizing import find_minimum_battery

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "historical_backtest.csv"
OUTPUT = ROOT / "outputs" / "extended_sizing.csv"

PROFILES = (
    ("initial_50pct", 0.50),
    ("start_at_minimum_10pct", 0.10),
)
DURATIONS = (4.0, 8.0, 12.0, 16.0, 24.0, 36.0, 48.0)


def main() -> None:
    data = load_historical_predictions(DATA)
    rows = []
    for profile, initial_soc in PROFILES:
        for kind in ("wind", "solar", "mixed"):
            portfolio = build_virtual_portfolio(data, kind, 100.0, 0.5)
            best, table = find_minimum_battery(
                portfolio,
                target_absorbed_pct=80.0,
                power_candidates_mw=(25.0, 50.0),
                duration_candidates_hours=DURATIONS,
                initial_soc_fraction=initial_soc,
                minimum_soc_fraction=0.10,
                maximum_soc_fraction=0.90,
            )
            table.insert(0, "portfolio_type", kind)
            table.insert(1, "initial_soc_case", profile)
            rows.append(table)
            print(profile, kind, best)
    result = pd.concat(rows, ignore_index=True)
    OUTPUT.parent.mkdir(exist_ok=True)
    result.to_csv(OUTPUT, index=False)
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
