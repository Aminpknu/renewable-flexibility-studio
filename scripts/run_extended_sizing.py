"""Extended energy-capacity diagnostic when 1h/2h/4h storage misses the target."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

from adapters.forecast_data import load_historical_predictions
from engine.portfolio import build_virtual_portfolio
from engine.sizing import find_minimum_battery

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "historical_backtest.csv"
OUTPUT = ROOT / "outputs" / "extended_sizing.csv"


def main() -> None:
    data = load_historical_predictions(DATA)
    rows = []
    for kind in ("wind", "solar", "mixed"):
        portfolio = build_virtual_portfolio(data, kind, 100.0, 0.5)
        best, table = find_minimum_battery(
            portfolio, 80.0, power_candidates_mw=(25.0, 50.0),
            duration_candidates_hours=(4.0, 8.0, 12.0, 16.0, 24.0, 36.0, 48.0),
        )
        table.insert(0, "portfolio_type", kind)
        rows.append(table)
        print(kind, best)
    result = pd.concat(rows, ignore_index=True)
    OUTPUT.parent.mkdir(exist_ok=True)
    result.to_csv(OUTPUT, index=False)
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
