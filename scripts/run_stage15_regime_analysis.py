from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from adapters.design_grid import load_design_grid, scaled_design_grid
from adapters.forecast_data import load_historical_predictions
from engine.battery import BatteryConfig, simulate_reactive_firming
from engine.design_sizing import select_stable_design
from engine.metrics import calculate_firming_metrics
from engine.portfolio import build_virtual_portfolio
from engine.regimes import build_daily_forecast_regimes, summarise_regime_range
from engine.reserve_planning import ReservePlanningConfig, build_reserve_plan

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "regimes"
HISTORY = ROOT / "data" / "historical_backtest.csv"
STAGE14 = ROOT / "outputs" / "probabilistic" / "stage14_locked_predictions.csv"
MARKET = ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_daily.csv"
DESIGN_GRID = ROOT / "outputs" / "design_sizing_grid_100mw.csv"
BATTERY = BatteryConfig(25.0, 8.0, 0.90, 0.50)
CAPACITY_MW = 100.0
WIND_SHARE = 0.50

def _daily_firming(history: pd.DataFrame) -> pd.DataFrame:
    portfolio = build_virtual_portfolio(history, "mixed", CAPACITY_MW, WIND_SHARE)
    rows = []
    for target, day in portfolio.groupby("settlement_date", sort=True):
        config = BatteryConfig(
            power_mw=BATTERY.power_mw,
            duration_hours=BATTERY.duration_hours,
            round_trip_efficiency=BATTERY.round_trip_efficiency,
            initial_soc_fraction=0.50,
        )
        simulation = simulate_reactive_firming(day, config)
        metrics = calculate_firming_metrics(simulation, config)
        rows.append({
            "settlement_date": pd.Timestamp(target).normalize(),
            "absolute_forecast_error_mwh": metrics["absolute_error_before_mwh"],
            "firming_absorbed_pct": metrics["deviations_absorbed_pct"],
            "meets_90pct_firming": metrics["deviations_absorbed_pct"] >= 90.0,
            "power_limited_periods": metrics["power_limited_periods"],
            "energy_limited_periods": metrics["energy_limited_periods"],
        })
    return pd.DataFrame(rows)


def _stage14_daily() -> pd.DataFrame:
    predictions = pd.read_csv(STAGE14)
    predictions["settlement_date"] = pd.to_datetime(predictions["settlement_date"]).dt.normalize()
    selected = predictions.loc[predictions["wind_share"].sub(WIND_SHARE).abs().lt(1e-9)].copy()
    rows = []
    for target, day in selected.groupby("settlement_date", sort=True):
        day = day.sort_values("settlement_period").copy()
        day["forecast_mw"] = day["portfolio_forecast_cf"] * CAPACITY_MW
        day["prediction_interval_lower_mw"] = day["p10_cf"] * CAPACITY_MW
        day["prediction_interval_upper_mw"] = day["p90_cf"] * CAPACITY_MW
        actual = day["portfolio_actual_cf"] * CAPACITY_MW
        inside = actual.between(
            day["prediction_interval_lower_mw"], day["prediction_interval_upper_mw"],
            inclusive="both",
        )
        reserve_frame, reserve = build_reserve_plan(
            day,
            BATTERY,
            ReservePlanningConfig(current_soc_fraction=0.50),
        )
        rows.append({
            "settlement_date": pd.Timestamp(target).normalize(),
            "stage14_available": True,
            "stage14_day_coverage_pct": 100.0 * float(inside.mean()),
            "stage14_mean_width_mw": float(
                (day["prediction_interval_upper_mw"] - day["prediction_interval_lower_mw"]).mean()
            ),
            "stage14_energy_band_feasible": bool(reserve["energy_band_feasible"]),
            "stage14_recommended_start_soc_pct": reserve["recommended_start_soc_pct"],
            "stage14_downward_reserve_mwh": reserve["downward_reserve_required_mwh"],
            "stage14_upward_headroom_mwh": reserve["upward_headroom_required_mwh"],
        })
    return pd.DataFrame(rows)

def _mix_design_sensitivity() -> pd.DataFrame:
    grid = load_design_grid(DESIGN_GRID)
    rows = []
    for share in range(0, 101, 5):
        comparison = scaled_design_grid(grid, "mixed", 100.0, float(share))
        selected = select_stable_design(comparison, 90.0, 90.0)
        if selected is None:
            rows.append({"wind_share_pct": share, "stable_design_found": False})
            continue
        rows.append({
            "wind_share_pct": share, "stable_design_found": True,
            "power_mw": float(selected["power_mw"]),
            "energy_mwh": float(selected["energy_mwh"]),
            "duration_hours": float(selected["duration_hours"]),
            "development_days90_pct": float(selected["development_days90_pct"]),
            "locked_days90_pct": float(selected["locked_days90_pct"]),
        })
    return pd.DataFrame(rows)


def main() -> None:
    history = load_historical_predictions(HISTORY)
    regimes, thresholds = build_daily_forecast_regimes(history)
    firming = _daily_firming(history)
    stage14 = _stage14_daily()
    market = pd.read_csv(MARKET)
    market["settlement_date"] = pd.to_datetime(market["settlement_date"]).dt.normalize()

    daily = regimes.merge(firming, on="settlement_date", how="left", validate="one_to_one")
    daily = daily.merge(market, on=["settlement_date", "evaluation_segment"], how="left", validate="one_to_one")
    daily = daily.merge(stage14, on="settlement_date", how="left", validate="one_to_one")
    daily["stage14_available"] = daily["stage14_available"].fillna(False).astype(bool)
    daily["stage14_energy_band_feasible"] = daily["stage14_energy_band_feasible"].astype("boolean")

    OUT.mkdir(parents=True, exist_ok=True)
    daily.to_csv(OUT / "stage15_daily_regime_evidence.csv", index=False)
    summaries = []
    for group_column in ("season", "wind_outlook", "solar_outlook", "ramp_stress"):
        summary = summarise_regime_range(daily, group_column)
        summary.insert(0, "group_type", group_column)
        summary = summary.rename(columns={group_column: "group"})
        summaries.append(summary)
    combined = pd.concat(summaries, ignore_index=True)
    combined.to_csv(OUT / "stage15_regime_summary.csv", index=False)
    mix = _mix_design_sensitivity()
    mix.to_csv(OUT / "stage15_mix_design_sensitivity.csv", index=False)
    payload = {
        "schema_version": "1.0",
        "stage": "15_seasonal_and_forecast_defined_regime_analysis",
        "portfolio": {"capacity_mw": CAPACITY_MW, "wind_share": WIND_SHARE},
        "battery": {"power_mw": 25.0, "energy_mwh": 200.0, "duration_hours": 8.0},
        "date_start": daily["settlement_date"].min().date().isoformat(),
        "date_end": daily["settlement_date"].max().date().isoformat(),
        "days": int(daily["settlement_date"].nunique()),
        "thresholds": thresholds,
        "stage14_locked_days": int(daily["stage14_available"].sum()),
        "market_days": int(daily["forecast_strategy_margin_gbp"].notna().sum()),
        "groupings": ["season", "wind_outlook", "solar_outlook", "ramp_stress"],
        "mix_design_steps": int(len(mix)),
        "mix_design_criterion": "minimum-energy design passing 90% firming and 90%-of-days gates on development and locked evidence",
        "boundary": (
            "Regime labels use only V2 forecast quantities and calendar season. "
            "They are not formal meteorological weather-regime classifications."
        ),
    }
    (OUT / "stage15_regime_manifest.json").write_text(
        json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(payload, indent=2), flush=True)
    print(combined.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
