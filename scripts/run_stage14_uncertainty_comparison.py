from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from adapters.forecast_data import load_historical_predictions
from engine.battery import BatteryConfig
from engine.portfolio import build_virtual_portfolio
from engine.reserve_planning import ReservePlanningConfig, build_reserve_plan
from engine.uncertainty import PredictionIntervalConfig, build_forecast_only_directional_interval

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = ROOT / "data" / "historical_backtest.csv"
PROBABILISTIC = ROOT / "outputs" / "probabilistic" / "stage14_locked_predictions.csv"
OUT = ROOT / "outputs" / "probabilistic"
SHARES = (0.0, 0.5, 1.0)
BATTERY = BatteryConfig(25.0, 8.0, 0.90, 0.50)
CONFIG = PredictionIntervalConfig(nominal_coverage=0.80, lookback_days=180, minimum_history_days=30, neighbour_count=600)
def _new_interval(day: pd.DataFrame, capacity_mw: float) -> pd.DataFrame:
    result = day.copy().sort_values("settlement_period").reset_index(drop=True)
    result["forecast_mw"] = result["portfolio_forecast_cf"] * capacity_mw
    point = result["portfolio_forecast_cf"].to_numpy(float)
    low = np.minimum(result["p10_cf"].to_numpy(float), point)
    high = np.maximum(result["p90_cf"].to_numpy(float), point)
    result["prediction_interval_lower_mw"] = low * capacity_mw
    result["prediction_interval_upper_mw"] = high * capacity_mw
    result["actual_mw"] = result["portfolio_actual_cf"] * capacity_mw
    return result


def _reserve_metrics(interval: pd.DataFrame) -> dict[str, float | bool]:
    _, meta = build_reserve_plan(
        interval, BATTERY, ReservePlanningConfig(current_soc_fraction=0.50)
    )
    return {
        "energy_band_feasible": bool(meta["energy_band_feasible"]),
        "recommended_start_soc_pct": float(meta["recommended_start_soc_pct"]),
        "downward_reserve_required_mwh": float(meta["downward_reserve_required_mwh"]),
        "upward_headroom_required_mwh": float(meta["upward_headroom_required_mwh"]),
    }
def _summarise(rows: pd.DataFrame, prefix: str) -> dict[str, float]:
    inside = rows["actual_mw"].between(rows[f"{prefix}_lower_mw"], rows[f"{prefix}_upper_mw"])
    width = rows[f"{prefix}_upper_mw"] - rows[f"{prefix}_lower_mw"]
    return {
        "coverage_pct": float(100.0 * inside.mean()),
        "mean_width_mw": float(width.mean()),
    }


def main() -> None:
    source = load_historical_predictions(HISTORICAL)
    probabilistic = pd.read_csv(PROBABILISTIC)
    probabilistic["settlement_date"] = pd.to_datetime(probabilistic["settlement_date"]).dt.normalize()
    probabilistic["valid_time_utc"] = pd.to_datetime(probabilistic["valid_time_utc"], utc=True)
    evidence_rows: list[dict[str, object]] = []
    day_rows: list[dict[str, object]] = []
    for share in SHARES:
        portfolio = build_virtual_portfolio(source, "mixed", 100.0, wind_share=share)
        locked = probabilistic.loc[np.isclose(probabilistic["wind_share"], share)].copy()
        for target in sorted(locked["settlement_date"].unique()):
            hist_day = portfolio.loc[portfolio["settlement_date"].eq(target)].copy()
            old, meta = build_forecast_only_directional_interval(portfolio, hist_day, target, CONFIG)
            if not meta.get("available"):
                continue
            new_day = _new_interval(locked.loc[locked["settlement_date"].eq(target)], 100.0)
            old_actual = hist_day["actual_mw"].to_numpy(float)
            if not np.allclose(old_actual, new_day["actual_mw"].to_numpy(float)):
                raise AssertionError("Stage 14 and historical actual portfolio MW do not align.")
            old_reserve = _reserve_metrics(old)
            new_reserve = _reserve_metrics(new_day)
            for period, old_row, new_row in zip(
                hist_day["settlement_period"], old.itertuples(index=False), new_day.itertuples(index=False)
            ):
                evidence_rows.append({
                    "settlement_date": pd.Timestamp(target).date().isoformat(),
                    "settlement_period": int(period),
                    "wind_share": share,
                    "actual_mw": float(new_row.actual_mw),
                    "old_lower_mw": float(old_row.prediction_interval_lower_mw),
                    "old_upper_mw": float(old_row.prediction_interval_upper_mw),
                    "new_lower_mw": float(new_row.prediction_interval_lower_mw),
                    "new_upper_mw": float(new_row.prediction_interval_upper_mw),
                })
            day_rows.append({
                "settlement_date": pd.Timestamp(target).date().isoformat(),
                "wind_share": share,
                "old_energy_band_feasible": old_reserve["energy_band_feasible"],
                "new_energy_band_feasible": new_reserve["energy_band_feasible"],
                "old_recommended_start_soc_pct": old_reserve["recommended_start_soc_pct"],
                "new_recommended_start_soc_pct": new_reserve["recommended_start_soc_pct"],
                "old_downward_reserve_required_mwh": old_reserve["downward_reserve_required_mwh"],
                "new_downward_reserve_required_mwh": new_reserve["downward_reserve_required_mwh"],
                "old_upward_headroom_required_mwh": old_reserve["upward_headroom_required_mwh"],
                "new_upward_headroom_required_mwh": new_reserve["upward_headroom_required_mwh"],
            })
    evidence = pd.DataFrame(evidence_rows)
    daily = pd.DataFrame(day_rows)
    summaries: dict[str, object] = {}
    for share, group in evidence.groupby("wind_share"):
        day_group = daily.loc[np.isclose(daily["wind_share"], float(share))]
        old_summary = _summarise(group, "old")
        new_summary = _summarise(group, "new")
        summaries[f"{float(share):.2f}"] = {
            "periods": int(len(group)),
            "days": int(day_group["settlement_date"].nunique()),
            "old_directional_residual": old_summary,
            "stage14_probabilistic": new_summary,
            "width_change_pct": float(
                100.0 * (new_summary["mean_width_mw"] / old_summary["mean_width_mw"] - 1.0)
            ),
            "old_energy_band_feasible_days_pct": float(100.0 * day_group["old_energy_band_feasible"].mean()),
            "new_energy_band_feasible_days_pct": float(100.0 * day_group["new_energy_band_feasible"].mean()),
            "mean_abs_start_soc_change_pct_points": float(
                (day_group["new_recommended_start_soc_pct"] - day_group["old_recommended_start_soc_pct"]).abs().mean()
            ),
            "mean_new_start_soc_pct": float(day_group["new_recommended_start_soc_pct"].mean()),
            "mean_old_start_soc_pct": float(day_group["old_recommended_start_soc_pct"].mean()),
        }
    payload = {
        "schema_version": "1.0",
        "stage": "14_probabilistic_vs_directional_residual_comparison",
        "locked_period": "2026-04-01 to 2026-06-30",
        "battery": {"power_mw": 25.0, "energy_mwh": 200.0, "duration_hours": 8.0},
        "portfolio_capacity_mw": 100.0,
        "old_method": "rolling 180-day local signed-residual q10-q90 envelope",
        "new_method": "mix-aware conditional quantile regression with rolling prior-date conformal calibration",
        "by_wind_share": summaries,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    evidence.to_csv(OUT / "stage14_uncertainty_comparison_periods.csv", index=False)
    daily.to_csv(OUT / "stage14_uncertainty_comparison_days.csv", index=False)
    (OUT / "stage14_uncertainty_comparison_summary.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()


