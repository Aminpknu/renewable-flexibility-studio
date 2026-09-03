"""Load and scale the V2 ten-zone spatial renewable allocation bundle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def load_latest_spatial_forecast(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "target_date", "settlement_period", "valid_time_utc", "zone",
        "wind_share", "solar_share", "wind_capacity_proxy_share", "solar_capacity_proxy_share",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Spatial forecast bundle is missing columns: {missing}")
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    frame["target_date"] = pd.to_datetime(frame["target_date"]).dt.normalize()
    if frame.duplicated(["target_date", "settlement_period", "zone"]).any():
        raise ValueError("Spatial forecast bundle contains duplicate date/period/zone rows.")
    counts = frame.groupby(["target_date", "settlement_period"])["zone"].nunique()
    if not counts.eq(10).all():
        raise ValueError("Every spatial settlement period must contain exactly ten zones.")
    return frame.sort_values(["target_date", "settlement_period", "zone"]).reset_index(drop=True)


def build_spatial_virtual_forecast(
    spatial: pd.DataFrame,
    latest_forecast: pd.DataFrame,
    portfolio_type: str,
    capacity_mw: float,
    wind_share: float,
) -> pd.DataFrame:
    kind = str(portfolio_type).strip().lower()
    if kind not in {"wind", "solar", "mixed"}:
        raise ValueError("portfolio_type must be wind, solar or mixed.")
    if not np.isfinite(capacity_mw) or capacity_mw <= 0:
        raise ValueError("capacity_mw must be positive and finite.")
    if not np.isfinite(wind_share) or not 0 <= wind_share <= 1:
        raise ValueError("wind_share must lie in [0, 1].")

    latest = latest_forecast.copy()
    latest["target_date"] = pd.to_datetime(latest["target_date"]).dt.normalize()
    latest["valid_time_utc"] = pd.to_datetime(latest["valid_time_utc"], utc=True)
    target_dates = latest["target_date"].drop_duplicates().tolist()
    if len(target_dates) != 1:
        raise ValueError("Latest renewable forecast must contain exactly one target date.")
    selected = spatial.loc[spatial["target_date"].eq(target_dates[0])].copy()
    if selected.empty:
        raise ValueError("Spatial allocation target does not match latest renewable forecast target.")
    selected = selected.merge(
        latest[["settlement_period", "valid_time_utc", "wind_pred_cf", "solar_pred_cf"]],
        on=["settlement_period", "valid_time_utc"], how="left", validate="many_to_one",
    )
    if selected[["wind_pred_cf", "solar_pred_cf"]].isna().any().any():
        raise ValueError("Spatial allocation could not align the latest renewable forecast.")

    if kind == "wind":
        wind_nameplate = float(capacity_mw)
        solar_nameplate = 0.0
    elif kind == "solar":
        wind_nameplate = 0.0
        solar_nameplate = float(capacity_mw)
    else:
        wind_nameplate = float(capacity_mw) * float(wind_share)
        solar_nameplate = float(capacity_mw) * (1.0 - float(wind_share))

    selected["zone_wind_virtual_mw"] = (
        wind_nameplate * selected["wind_pred_cf"] * selected["wind_share"]
    )
    selected["zone_solar_virtual_mw"] = (
        solar_nameplate * selected["solar_pred_cf"] * selected["solar_share"]
    )
    selected["zone_virtual_forecast_mw"] = (
        selected["zone_wind_virtual_mw"] + selected["zone_solar_virtual_mw"]
    )
    selected["zone_virtual_capacity_proxy_mw"] = (
        wind_nameplate * selected["wind_capacity_proxy_share"]
        + solar_nameplate * selected["solar_capacity_proxy_share"]
    )
    selected["zone_capacity_share"] = selected["zone_virtual_capacity_proxy_mw"] / float(capacity_mw)

    expected = (
        wind_nameplate * selected.groupby("settlement_period")["wind_pred_cf"].first()
        + solar_nameplate * selected.groupby("settlement_period")["solar_pred_cf"].first()
    )
    allocated = selected.groupby("settlement_period")["zone_virtual_forecast_mw"].sum()
    if not np.allclose(allocated.to_numpy(), expected.to_numpy(), atol=1e-6):
        raise AssertionError("Spatial virtual forecast does not reconcile to the national virtual forecast.")
    capacity_check = selected.groupby("zone")["zone_virtual_capacity_proxy_mw"].first().sum()
    if not np.isclose(capacity_check, float(capacity_mw), atol=1e-6):
        raise AssertionError("Spatial virtual capacity proxy does not reconcile to portfolio capacity.")
    return selected.sort_values(["settlement_period", "zone"]).reset_index(drop=True)
