"""Build transparent virtual wind, solar and mixed renewable portfolios."""

from __future__ import annotations

from typing import Literal

import numpy as np
import pandas as pd

PortfolioType = Literal["wind", "solar", "mixed"]

REQUIRED_COLUMNS = {
    "settlement_date",
    "settlement_period",
    "valid_time_utc",
    "wind_cf",
    "solar_cf",
    "wind_pred_cf",
    "solar_pred_cf",
}


def _validate_source_frame(frame: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Historical forecast data is missing columns: {missing}")
    if frame.empty:
        raise ValueError("Historical forecast data is empty.")
    if frame.duplicated(["settlement_date", "settlement_period"]).any():
        raise ValueError("Duplicate settlement-date/period rows were detected.")
    numeric = ["wind_cf", "solar_cf", "wind_pred_cf", "solar_pred_cf"]
    if frame[numeric].isna().any().any():
        raise ValueError("Capacity-factor columns contain missing values.")
    if not np.isfinite(frame[numeric].to_numpy(dtype=float)).all():
        raise ValueError("Capacity-factor columns contain non-finite values.")


def build_virtual_portfolio(
    frame: pd.DataFrame,
    portfolio_type: PortfolioType,
    capacity_mw: float,
    wind_share: float = 0.5,
) -> pd.DataFrame:
    """Scale national capacity-factor evidence to a virtual portfolio.

    Parameters
    ----------
    frame:
        One or more complete historical settlement days containing actual and
        predicted national wind/solar capacity factors.
    portfolio_type:
        ``wind``, ``solar`` or ``mixed``.
    capacity_mw:
        Total virtual portfolio nameplate capacity.
    wind_share:
        Wind capacity share for a mixed portfolio, expressed from 0 to 1.

    Notes
    -----
    This is a transparent portfolio-level benchmark. National forecast errors
    are not claimed to reproduce the behaviour of any individual wind or solar
    site.
    """

    _validate_source_frame(frame)
    kind = str(portfolio_type).strip().lower()
    if kind not in {"wind", "solar", "mixed"}:
        raise ValueError("portfolio_type must be 'wind', 'solar' or 'mixed'.")
    if not np.isfinite(capacity_mw) or capacity_mw <= 0:
        raise ValueError("capacity_mw must be a positive finite number.")
    if not np.isfinite(wind_share) or not 0 <= wind_share <= 1:
        raise ValueError("wind_share must be between 0 and 1.")

    result = frame.copy().sort_values(
        ["settlement_date", "settlement_period"]
    ).reset_index(drop=True)
    result["valid_time_utc"] = pd.to_datetime(result["valid_time_utc"], utc=True)

    if kind == "wind":
        actual_cf = result["wind_cf"].to_numpy(dtype=float)
        forecast_cf = result["wind_pred_cf"].to_numpy(dtype=float)
        effective_wind_share = 1.0
    elif kind == "solar":
        actual_cf = result["solar_cf"].to_numpy(dtype=float)
        forecast_cf = result["solar_pred_cf"].to_numpy(dtype=float)
        effective_wind_share = 0.0
    else:
        actual_cf = (
            wind_share * result["wind_cf"].to_numpy(dtype=float)
            + (1 - wind_share) * result["solar_cf"].to_numpy(dtype=float)
        )
        forecast_cf = (
            wind_share * result["wind_pred_cf"].to_numpy(dtype=float)
            + (1 - wind_share) * result["solar_pred_cf"].to_numpy(dtype=float)
        )
        effective_wind_share = float(wind_share)

    # Predictions are bounded for physical portfolio presentation. Historical
    # observations remain unchanged so suspicious source values are visible.
    forecast_cf = np.clip(forecast_cf, 0.0, 1.0)

    result["portfolio_type"] = kind
    result["portfolio_capacity_mw"] = float(capacity_mw)
    result["wind_share"] = effective_wind_share
    result["actual_cf"] = actual_cf
    result["forecast_cf"] = forecast_cf
    result["actual_mw"] = actual_cf * float(capacity_mw)
    result["forecast_mw"] = forecast_cf * float(capacity_mw)
    result["forecast_error_mw"] = result["actual_mw"] - result["forecast_mw"]
    return result


def build_virtual_forecast(
    frame: pd.DataFrame,
    portfolio_type: PortfolioType,
    capacity_mw: float,
    wind_share: float = 0.5,
) -> pd.DataFrame:
    """Scale a forecast-only wind/solar bundle to a virtual portfolio."""
    required = {"target_date", "settlement_period", "valid_time_utc", "wind_pred_cf", "solar_pred_cf"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Latest forecast data is missing columns: {missing}")
    kind = str(portfolio_type).strip().lower()
    if kind not in {"wind", "solar", "mixed"}:
        raise ValueError("portfolio_type must be 'wind', 'solar' or 'mixed'.")
    if not np.isfinite(capacity_mw) or capacity_mw <= 0:
        raise ValueError("capacity_mw must be a positive finite number.")
    if not np.isfinite(wind_share) or not 0 <= wind_share <= 1:
        raise ValueError("wind_share must be between 0 and 1.")
    result = frame.copy().sort_values("settlement_period").reset_index(drop=True)
    result["valid_time_utc"] = pd.to_datetime(result["valid_time_utc"], utc=True)
    result["settlement_date"] = pd.to_datetime(result["target_date"]).dt.normalize()
    if kind == "wind":
        forecast_cf = result["wind_pred_cf"].to_numpy(dtype=float)
        effective_wind_share = 1.0
    elif kind == "solar":
        forecast_cf = result["solar_pred_cf"].to_numpy(dtype=float)
        effective_wind_share = 0.0
    else:
        forecast_cf = (
            wind_share * result["wind_pred_cf"].to_numpy(dtype=float)
            + (1 - wind_share) * result["solar_pred_cf"].to_numpy(dtype=float)
        )
        effective_wind_share = float(wind_share)
    forecast_cf = np.clip(forecast_cf, 0.0, 1.0)
    result["portfolio_type"] = kind
    result["portfolio_capacity_mw"] = float(capacity_mw)
    result["wind_share"] = effective_wind_share
    result["forecast_cf"] = forecast_cf
    result["forecast_mw"] = forecast_cf * float(capacity_mw)
    return result
