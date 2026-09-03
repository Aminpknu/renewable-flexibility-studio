"""Backtest the forecast-day minimum-adjustment SOC reserve policy."""

from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
import pandas as pd

from adapters.design_grid import load_design_grid, scaled_design_grid
from adapters.forecast_data import load_historical_predictions
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.design_sizing import select_stable_design
from engine.portfolio import build_virtual_portfolio
from engine.reserve_planning import ReservePlanningConfig, build_reserve_plan
from engine.uncertainty import PredictionIntervalConfig, build_forecast_only_directional_interval

ROOT = Path(__file__).resolve().parents[1]
HISTORY_PATH = ROOT / "data" / "historical_backtest.csv"
DESIGN_PATH = ROOT / "outputs" / "design_sizing_grid_100mw.csv"
SUMMARY_PATH = ROOT / "outputs" / "reserve_planning_validation.json"
DAILY_PATH = ROOT / "outputs" / "reserve_planning_daily.csv"

PORTFOLIOS = {
    "solar": ("solar", 0.0),
    "mixed": ("mixed", 0.5),
    "wind": ("wind", 1.0),
}


def _daily_metrics(simulation: pd.DataFrame) -> tuple[float, float, float]:
    before = float((simulation["forecast_error_mw"].abs() * 0.5).sum())
    after = float((simulation["residual_error_mw"].abs() * 0.5).sum())
    absorbed = 100.0 * (1.0 - after / before) if before > 0 else 100.0
    return before, after, absorbed


def _segment_summary(frame: pd.DataFrame) -> dict[str, float | int]:
    fixed_before = float(frame["before_mwh"].sum())
    fixed_after = float(frame["fixed_residual_mwh"].sum())
    smart_after = float(frame["smart_residual_mwh"].sum())
    fixed_overall = 100.0 * (1.0 - fixed_after / fixed_before) if fixed_before else 100.0
    smart_overall = 100.0 * (1.0 - smart_after / fixed_before) if fixed_before else 100.0
    residual_reduction = 100.0 * (1.0 - smart_after / fixed_after) if fixed_after else 0.0
    delta = frame["smart_absorbed_pct"] - frame["fixed_absorbed_pct"]
    tol = 1e-9
    return {
        "eligible_days": int(len(frame)),
        "adjustment_days": int(frame["preparation_action"].ne("hold current SOC").sum()),
        "infeasible_safe_band_days": int((~frame["energy_band_feasible"]).sum()),
        "mean_recommended_soc_pct": float(frame["recommended_soc_pct"].mean()),
        "min_recommended_soc_pct": float(frame["recommended_soc_pct"].min()),
        "max_recommended_soc_pct": float(frame["recommended_soc_pct"].max()),
        "fixed_overall_absorbed_pct": fixed_overall,
        "planned_overall_absorbed_pct": smart_overall,
        "residual_error_reduction_vs_fixed_pct": residual_reduction,
        "fixed_days_ge90_pct": float(100.0 * frame["fixed_absorbed_pct"].ge(90).mean()),
        "planned_days_ge90_pct": float(100.0 * frame["smart_absorbed_pct"].ge(90).mean()),
        "fixed_p05_daily_absorbed_pct": float(frame["fixed_absorbed_pct"].quantile(0.05)),
        "planned_p05_daily_absorbed_pct": float(frame["smart_absorbed_pct"].quantile(0.05)),
        "days_better": int(delta.gt(tol).sum()),
        "days_equal": int(delta.abs().le(tol).sum()),
        "days_worse": int(delta.lt(-tol).sum()),
    }


def _run_portfolio(
    history: pd.DataFrame,
    design_grid: pd.DataFrame,
    portfolio_type: str,
    wind_share: float,
) -> tuple[pd.DataFrame, dict[str, object]]:
    portfolio = build_virtual_portfolio(
        history, portfolio_type=portfolio_type, capacity_mw=100.0, wind_share=wind_share
    )
    scaled = scaled_design_grid(
        design_grid, portfolio_type, 100.0, wind_share * 100.0
    )
    selected = select_stable_design(scaled, 90, 90)
    if selected is None:
        raise RuntimeError(f"No 90/90 design for {portfolio_type} {wind_share=}")
    power = float(selected["power_mw"])
    duration = float(selected["duration_hours"])
    dates = pd.Index(pd.to_datetime(portfolio["settlement_date"]).dt.normalize().unique()).sort_values()
    rows: list[dict[str, object]] = []
    interval_cfg = PredictionIntervalConfig(
        nominal_coverage=0.80, lookback_days=180, minimum_history_days=30, neighbour_count=600
    )
    for target in dates:
        day = portfolio.loc[pd.to_datetime(portfolio["settlement_date"]).dt.normalize().eq(target)].copy()
        interval, meta = build_forecast_only_directional_interval(
            portfolio, day, target, interval_cfg
        )
        if not meta.get("available"):
            continue
        fixed_cfg = BatteryConfig(
            power_mw=power, duration_hours=duration,
            round_trip_efficiency=0.90, initial_soc_fraction=0.50,
        )
        reserve_series, reserve = build_reserve_plan(
            interval, fixed_cfg, ReservePlanningConfig(current_soc_fraction=0.50)
        )
        planned_cfg = BatteryConfig(
            power_mw=power, duration_hours=duration,
            round_trip_efficiency=0.90,
            initial_soc_fraction=float(reserve["recommended_start_soc_pct"]) / 100.0,
        )
        fixed_sim = simulate_reactive_firming(day, fixed_cfg)
        planned_sim = simulate_reactive_firming(day, planned_cfg)
        before, fixed_after, fixed_absorbed = _daily_metrics(fixed_sim)
        _before2, planned_after, planned_absorbed = _daily_metrics(planned_sim)
        actual = day["actual_mw"].to_numpy(float)
        inside = (
            (actual >= reserve_series["prediction_interval_lower_mw"].to_numpy(float))
            & (actual <= reserve_series["prediction_interval_upper_mw"].to_numpy(float))
        )
        segment = str(day["evaluation_segment"].iloc[0])
        rows.append({
            "settlement_date": pd.Timestamp(target).date().isoformat(),
            "evaluation_segment": segment,
            "power_mw": power,
            "energy_mwh": power * duration,
            "duration_hours": duration,
            "recommended_soc_pct": reserve["recommended_start_soc_pct"],
            "safe_soc_lower_pct": reserve["safe_soc_lower_pct"],
            "safe_soc_upper_pct": reserve["safe_soc_upper_pct"],
            "energy_band_feasible": reserve["energy_band_feasible"],
            "preparation_action": reserve["preparation_action"],
            "grid_import_to_recommendation_mwh": reserve["grid_import_to_recommendation_mwh"],
            "grid_export_to_recommendation_mwh": reserve["grid_export_to_recommendation_mwh"],
            "reserve_coverage_pct": reserve["overall_reserve_coverage_pct"],
            "downward_reserve_required_mwh": reserve["downward_reserve_required_mwh"],
            "upward_headroom_required_mwh": reserve["upward_headroom_required_mwh"],
            "directional_interval_coverage_pct": 100.0 * float(inside.mean()),
            "before_mwh": before,
            "fixed_residual_mwh": fixed_after,
            "smart_residual_mwh": planned_after,
            "fixed_absorbed_pct": fixed_absorbed,
            "smart_absorbed_pct": planned_absorbed,
        })
    result = pd.DataFrame(rows)
    summary: dict[str, object] = {
        "selected_design": {
            "power_mw": power,
            "energy_mwh": power * duration,
            "duration_hours": duration,
        },
        "all_eligible": _segment_summary(result),
    }
    for segment in ("development_oof", "locked_test"):
        subset = result.loc[result["evaluation_segment"].eq(segment)].copy()
        summary[segment] = _segment_summary(subset)
        summary[segment]["mean_directional_interval_coverage_pct"] = float(
            subset["directional_interval_coverage_pct"].mean()
        )
        summary[segment]["mean_preparation_grid_import_mwh_per_day"] = float(
            subset["grid_import_to_recommendation_mwh"].mean()
        )
        summary[segment]["mean_preparation_grid_export_mwh_per_day"] = float(
            subset["grid_export_to_recommendation_mwh"].mean()
        )
    return result, summary


def main() -> None:
    started = time.time()
    history = load_historical_predictions(HISTORY_PATH)
    grid = load_design_grid(DESIGN_PATH)
    daily_parts: list[pd.DataFrame] = []
    summaries: dict[str, object] = {}
    for label, (kind, share) in PORTFOLIOS.items():
        daily, summary = _run_portfolio(history, grid, kind, share)
        daily.insert(0, "portfolio_type", label)
        daily_parts.append(daily)
        summaries[label] = summary
        print(label, json.dumps(summary, indent=2), flush=True)
    combined = pd.concat(daily_parts, ignore_index=True)
    combined.to_csv(DAILY_PATH, index=False)
    payload = {
        "schema_version": "1.0",
        "method": "minimum_adjustment_to_directional_reserve_safe_soc_band",
        "current_soc_baseline_pct": 50.0,
        "directional_interval": "local signed-residual empirical q10-q90, 180-day lookback, prior dates only",
        "reserve_horizon": "installed battery duration",
        "portfolio_capacity_mw": 100.0,
        "summaries": summaries,
        "runtime_seconds": time.time() - started,
    }
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("saved", SUMMARY_PATH)
    print("saved", DAILY_PATH)


if __name__ == "__main__":
    main()
