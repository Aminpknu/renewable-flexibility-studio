"""Forecast-defined seasonal and renewable operating-regime helpers."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

SEASON_ORDER = ["Winter", "Spring", "Summer", "Autumn"]
OUTLOOK_ORDER = ["Low", "Medium", "High"]
RAMP_ORDER = ["Normal", "High-ramp"]


def season_from_month(month: int) -> str:
    if month in (12, 1, 2):
        return "Winter"
    if month in (3, 4, 5):
        return "Spring"
    if month in (6, 7, 8):
        return "Summer"
    return "Autumn"


def classify_tercile(value: float, low: float, high: float) -> str:
    if value <= low:
        return "Low"
    if value >= high:
        return "High"
    return "Medium"

def build_daily_forecast_regimes(
    historical: pd.DataFrame,
    calibration_segment: str = "development_oof",
) -> tuple[pd.DataFrame, dict[str, Any]]:
    required = {
        "settlement_date", "settlement_period", "wind_pred_cf", "solar_pred_cf",
        "evaluation_segment",
    }
    missing = sorted(required.difference(historical.columns))
    if missing:
        raise ValueError(f"Historical evidence is missing regime columns: {missing}")
    frame = historical.copy()
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"]).dt.normalize()
    frame["mixed_pred_cf"] = 0.5 * frame["wind_pred_cf"] + 0.5 * frame["solar_pred_cf"]
    frame["mixed_ramp_abs"] = frame.groupby("settlement_date")["mixed_pred_cf"].diff().abs().fillna(0.0)
    daily = frame.groupby("settlement_date", as_index=False).agg(
        evaluation_segment=("evaluation_segment", "first"),
        wind_forecast_mean_cf=("wind_pred_cf", "mean"),
        solar_forecast_mean_cf=("solar_pred_cf", "mean"),
        mixed_forecast_mean_cf=("mixed_pred_cf", "mean"),
        mixed_mean_abs_ramp_cf=("mixed_ramp_abs", "mean"),
        mixed_max_abs_ramp_cf=("mixed_ramp_abs", "max"),
    )
    calibration = daily.loc[daily["evaluation_segment"].eq(calibration_segment)]
    if calibration.empty:
        raise ValueError("No calibration days exist for regime thresholds.")
    wind_low, wind_high = calibration["wind_forecast_mean_cf"].quantile([1/3, 2/3])
    solar_low, solar_high = calibration["solar_forecast_mean_cf"].quantile([1/3, 2/3])
    ramp_high = float(calibration["mixed_mean_abs_ramp_cf"].quantile(0.75))
    daily["season"] = daily["settlement_date"].dt.month.map(season_from_month)
    daily["wind_outlook"] = [
        classify_tercile(value, float(wind_low), float(wind_high))
        for value in daily["wind_forecast_mean_cf"]
    ]
    daily["solar_outlook"] = [
        classify_tercile(value, float(solar_low), float(solar_high))
        for value in daily["solar_forecast_mean_cf"]
    ]
    daily["ramp_stress"] = np.where(
        daily["mixed_mean_abs_ramp_cf"].ge(ramp_high), "High-ramp", "Normal"
    )
    thresholds = {
        "calibration_segment": calibration_segment,
        "calibration_days": int(len(calibration)),
        "wind_mean_cf_terciles": [float(wind_low), float(wind_high)],
        "solar_mean_cf_terciles": [float(solar_low), float(solar_high)],
        "mixed_mean_abs_ramp_cf_p75": ramp_high,
        "label_boundary": (
            "Regimes use only V2 forecast quantities and calendar season; "
            "they are renewable operating regimes, not formal meteorological weather regimes."
        ),
    }
    return daily, thresholds


def summarise_regime_range(
    daily: pd.DataFrame,
    group_column: str,
    start_date: str | pd.Timestamp | None = None,
    end_date: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    if group_column not in {"season", "wind_outlook", "solar_outlook", "ramp_stress"}:
        raise ValueError("Unsupported regime grouping column.")
    work = daily.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"]).dt.normalize()
    if start_date is not None:
        work = work.loc[work["settlement_date"].ge(pd.Timestamp(start_date).normalize())]
    if end_date is not None:
        work = work.loc[work["settlement_date"].le(pd.Timestamp(end_date).normalize())]
    if work.empty:
        raise ValueError("No regime evidence exists in the selected date range.")
    result = work.groupby(group_column, as_index=False).agg(
        days=("settlement_date", "nunique"),
        mean_abs_error_mwh=("absolute_forecast_error_mwh", "mean"),
        mean_firming_pct=("firming_absorbed_pct", "mean"),
        days_meeting_90_pct=("meets_90pct_firming", "mean"),
        mean_forecast_market_value_gbp=("forecast_strategy_margin_gbp", "mean"),
        mean_reserve_market_value_gbp=("reserve_aware_forecast_margin_gbp", "mean"),
        stage14_days=("stage14_available", "sum"),
        mean_stage14_coverage_pct=("stage14_day_coverage_pct", "mean"),
        mean_stage14_width_mw=("stage14_mean_width_mw", "mean"),
        stage14_energy_band_feasible_pct=("stage14_energy_band_feasible", "mean"),
        mean_stage14_start_soc_pct=("stage14_recommended_start_soc_pct", "mean"),
        mean_stage14_down_reserve_mwh=("stage14_downward_reserve_mwh", "mean"),
        mean_stage14_up_headroom_mwh=("stage14_upward_headroom_mwh", "mean"),
    )
    result["days_meeting_90_pct"] *= 100.0
    result["stage14_energy_band_feasible_pct"] *= 100.0
    result = result.rename(columns={group_column: "group"})
    return result
