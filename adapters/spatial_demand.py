"""Validated ten-zone underlying-demand allocation derived from official GB/regional evidence."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {
    "target_date", "settlement_period", "valid_time_utc", "zone",
    "zone_underlying_demand_mw", "zone_demand_share", "national_demand_mw",
    "national_embedded_wind_solar_mw", "national_underlying_demand_proxy_mw",
    "annual_consumption_share", "publish_time_utc",
}


def load_latest_spatial_demand(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Spatial demand bundle is missing columns: {missing}")
    frame["target_date"] = pd.to_datetime(frame["target_date"]).dt.normalize()
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    frame["publish_time_utc"] = pd.to_datetime(frame["publish_time_utc"], utc=True)
    frame["settlement_period"] = pd.to_numeric(frame["settlement_period"], errors="raise").astype(int)
    if frame.duplicated(["target_date", "settlement_period", "zone"]).any():
        raise ValueError("Spatial demand contains duplicate target/period/zone rows.")
    zone_counts = frame.groupby(["target_date", "settlement_period"])["zone"].nunique()
    if not zone_counts.eq(10).all():
        raise ValueError("Every spatial-demand period must contain exactly ten zones.")
    if (frame["zone_underlying_demand_mw"] < 0).any() or (frame["zone_demand_share"] < 0).any():
        raise ValueError("Spatial underlying-demand MW and shares must be non-negative.")
    share_sum = frame.groupby(["target_date", "settlement_period"])["zone_demand_share"].sum()
    if not np.allclose(share_sum.to_numpy(float), 1.0, atol=1e-9):
        raise ValueError("Spatial demand shares do not sum to one by settlement period.")
    reconciliation = frame.groupby(["target_date", "settlement_period"], as_index=False).agg(
        allocated_mw=("zone_underlying_demand_mw", "sum"),
        national_mw=("national_underlying_demand_proxy_mw", "first"),
    )
    if not np.allclose(reconciliation["allocated_mw"], reconciliation["national_mw"], atol=1e-6):
        raise ValueError("Spatial underlying demand does not reconcile to the national underlying-demand proxy.")
    national_identity = frame.groupby(["target_date", "settlement_period"], as_index=False).first()
    if not np.allclose(
        national_identity["national_underlying_demand_proxy_mw"],
        national_identity["national_demand_mw"] + national_identity["national_embedded_wind_solar_mw"],
        atol=1e-6,
    ):
        raise ValueError("National underlying-demand identity is inconsistent.")
    return frame.sort_values(["target_date", "settlement_period", "zone"]).reset_index(drop=True)


def select_zone_demand(frame: pd.DataFrame, zone: str) -> pd.DataFrame:
    selected = frame.loc[frame["zone"].eq(str(zone))].copy()
    if selected.empty:
        raise KeyError(f"No spatial demand exists for zone {zone!r}.")
    return selected.sort_values("settlement_period").reset_index(drop=True)
