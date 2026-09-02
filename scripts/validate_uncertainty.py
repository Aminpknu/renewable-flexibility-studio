"""Backtest the rolling 80% prediction interval on out-of-sample evidence."""

from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from engine.portfolio import build_virtual_portfolio
from engine.uncertainty import PredictionIntervalConfig, build_rolling_prediction_interval

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "historical_backtest.csv"
OUTPUT = ROOT / "outputs" / "uncertainty_validation.json"


def main() -> None:
    data = load_historical_predictions(DATA)
    config = PredictionIntervalConfig()
    results = {}
    for kind in ("wind", "solar", "mixed"):
        portfolio = build_virtual_portfolio(data, kind, 100.0, 0.5)
        dates = sorted(portfolio["settlement_date"].unique())
        parts = []
        for date in dates:
            interval, meta = build_rolling_prediction_interval(portfolio, date, config)
            if not meta["available"]:
                continue
            interval = interval[[
                "settlement_date", "actual_inside_prediction_interval",
                "prediction_interval_lower_mw", "prediction_interval_upper_mw",
            ]].copy()
            segment = portfolio.loc[portfolio["settlement_date"].eq(date), "evaluation_segment"].iloc[0]
            interval["evaluation_segment"] = segment
            parts.append(interval)
        combined = pd.concat(parts, ignore_index=True)
        width = combined["prediction_interval_upper_mw"] - combined["prediction_interval_lower_mw"]
        locked = combined.loc[combined["evaluation_segment"].eq("locked_test")]
        results[kind] = {
            "eligible_days": int(combined["settlement_date"].nunique()),
            "rows": int(len(combined)),
            "overall_coverage_pct": float(combined["actual_inside_prediction_interval"].mean() * 100),
            "locked_test_coverage_pct": float(locked["actual_inside_prediction_interval"].mean() * 100),
            "mean_interval_width_mw_100mw_portfolio": float(width.mean()),
        }
        print(kind, results[kind], flush=True)
    OUTPUT.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
