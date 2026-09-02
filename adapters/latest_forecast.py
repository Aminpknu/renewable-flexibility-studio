"""Validate the compact latest day-ahead renewable forecast bundle."""

from __future__ import annotations

from pathlib import Path
import pandas as pd

REQUIRED_COLUMNS = {
    "forecast_created_utc", "target_date", "settlement_period",
    "valid_time_utc", "wind_pred_cf", "solar_pred_cf",
    "wind_capacity_mw", "solar_capacity_mw",
}


def load_latest_forecast(path: str | Path) -> pd.DataFrame:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Latest forecast bundle not found: {source}")
    frame = pd.read_csv(source)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Latest forecast bundle is missing columns: {missing}")
    frame = frame.copy()
    frame["forecast_created_utc"] = pd.to_datetime(frame["forecast_created_utc"], utc=True)
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    frame["target_date"] = pd.to_datetime(frame["target_date"]).dt.normalize()
    frame["settlement_period"] = pd.to_numeric(frame["settlement_period"], errors="raise").astype(int)
    if frame["target_date"].nunique() != 1:
        raise ValueError("Latest forecast bundle must contain exactly one target date.")
    if frame["settlement_period"].duplicated().any():
        raise ValueError("Latest forecast bundle contains duplicate settlement periods.")
    if frame[["wind_pred_cf", "solar_pred_cf"]].isna().any().any():
        raise ValueError("Latest forecast contains missing capacity-factor predictions.")
    count = frame["settlement_period"].nunique()
    if count not in {46, 48, 50}:
        raise ValueError(f"Latest forecast target day has invalid period count: {count}.")
    return frame.sort_values("settlement_period").reset_index(drop=True)


def latest_target_date(frame: pd.DataFrame) -> str:
    return pd.Timestamp(frame["target_date"].iloc[0]).strftime("%Y-%m-%d")
