"""Load and scale precomputed robust battery-design evidence."""

from __future__ import annotations

from pathlib import Path
import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {
    "wind_share_pct", "power_mw", "duration_hours", "energy_mwh",
    "development_overall_absorbed_pct", "locked_overall_absorbed_pct",
    "development_days80_pct", "development_days90_pct", "development_days95_pct",
    "locked_days80_pct", "locked_days90_pct", "locked_days95_pct",
    "grid_reset_import_mwh", "grid_reset_export_mwh", "design_operating_mode",
}


def load_design_grid(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Design grid is missing columns: {missing}")
    if frame.empty or frame.duplicated(["wind_share_pct", "power_mw", "duration_hours"]).any():
        raise ValueError("Design grid is empty or contains duplicate design cells.")
    shares = sorted(pd.to_numeric(frame["wind_share_pct"], errors="raise").astype(int).unique())
    if shares != list(range(0, 101, 5)):
        raise ValueError("Design grid must contain every 5% wind-share step from 0 to 100.")
    return frame


def _resolve_wind_share(portfolio_type: str, wind_share_pct: float) -> int:
    kind = str(portfolio_type).strip().lower()
    if kind == "wind":
        return 100
    if kind == "solar":
        return 0
    if kind != "mixed":
        raise ValueError("portfolio_type must be wind, solar or mixed.")
    share = float(wind_share_pct)
    if not np.isfinite(share) or not 0 <= share <= 100:
        raise ValueError("wind_share_pct must lie between 0 and 100.")
    rounded = int(round(share / 5.0) * 5)
    if abs(share - rounded) > 1e-9:
        raise ValueError("Mixed design sizing supports 5% wind-share increments.")
    return rounded


def scaled_design_grid(
    grid: pd.DataFrame,
    portfolio_type: str,
    capacity_mw: float,
    wind_share_pct: float,
) -> pd.DataFrame:
    capacity = float(capacity_mw)
    if not np.isfinite(capacity) or capacity <= 0:
        raise ValueError("capacity_mw must be positive and finite.")
    share = _resolve_wind_share(portfolio_type, wind_share_pct)
    selected = grid.loc[grid["wind_share_pct"].eq(share)].copy()
    if selected.empty:
        raise KeyError(f"No precomputed design grid exists for wind share {share}%.")
    scale = capacity / 100.0
    for column in ("power_mw", "energy_mwh", "grid_reset_import_mwh", "grid_reset_export_mwh", "mean_daily_grid_reset_import_mwh"):
        selected[column] = selected[column].astype(float) * scale
    selected["portfolio_capacity_mw"] = capacity
    selected["resolved_wind_share_pct"] = share
    return selected.reset_index(drop=True)
