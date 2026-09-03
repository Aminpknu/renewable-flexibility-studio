"""Leakage-safe pre-delivery forecasting for the public GB Market Index reference."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

PRICE_COLUMN = "market_index_price_gbp_per_mwh"
FEATURE_COLUMNS = [
    "tod_sin", "tod_cos", "tod2_sin", "tod2_cos",
    "dow_sin", "dow_cos", "doy_sin", "doy_cos",
    "lag_day_mean", "mean7", "mean28", "lag_sp", "sp7", "sp28",
]


@dataclass(frozen=True)
class MarketPriceForecastConfig:
    minimum_history_days: int = 30
    ridge_alpha: float = 20.0

    def __post_init__(self) -> None:
        if self.minimum_history_days < 7:
            raise ValueError("minimum_history_days must be at least 7.")
        if not np.isfinite(self.ridge_alpha) or self.ridge_alpha < 0:
            raise ValueError("ridge_alpha must be finite and non-negative.")
def build_market_price_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Build lag/calendar features using only prices from earlier settlement dates."""
    required = {"settlement_date", "settlement_period", "valid_time_utc", PRICE_COLUMN}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Market-price frame is missing forecast columns: {missing}")
    if frame.empty:
        raise ValueError("Market-price frame is empty.")
    work = frame.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"], errors="raise").dt.normalize()
    work["settlement_period"] = pd.to_numeric(work["settlement_period"], errors="raise").astype(int)
    work["valid_time_utc"] = pd.to_datetime(work["valid_time_utc"], utc=True, errors="raise")
    work[PRICE_COLUMN] = pd.to_numeric(work[PRICE_COLUMN], errors="coerce")
    work = work.sort_values(["settlement_date", "settlement_period"]).reset_index(drop=True)
    if work.duplicated(["settlement_date", "settlement_period"]).any():
        raise ValueError("Market-price frame contains duplicate settlement keys.")

    daily = work.groupby("settlement_date")[PRICE_COLUMN].mean()
    daily_features = pd.DataFrame(index=daily.index)
    daily_features["lag_day_mean"] = daily.shift(1)
    daily_features["mean7"] = daily.shift(1).rolling(7, min_periods=3).mean()
    daily_features["mean28"] = daily.shift(1).rolling(28, min_periods=7).mean()
    for column in daily_features.columns:
        work[column] = work["settlement_date"].map(daily_features[column])
    work["lag_sp"] = work.groupby("settlement_period")[PRICE_COLUMN].shift(1)
    work["sp7"] = work.groupby("settlement_period")[PRICE_COLUMN].transform(
        lambda s: s.shift(1).rolling(7, min_periods=3).mean()
    )
    work["sp28"] = work.groupby("settlement_period")[PRICE_COLUMN].transform(
        lambda s: s.shift(1).rolling(28, min_periods=7).mean()
    )
    local = work["valid_time_utc"].dt.tz_convert("Europe/London")
    minute = local.dt.hour * 60 + local.dt.minute
    work["tod_sin"] = np.sin(2 * np.pi * minute / 1440.0)
    work["tod_cos"] = np.cos(2 * np.pi * minute / 1440.0)
    work["tod2_sin"] = np.sin(4 * np.pi * minute / 1440.0)
    work["tod2_cos"] = np.cos(4 * np.pi * minute / 1440.0)
    dow = work["settlement_date"].dt.dayofweek
    work["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    work["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    doy = work["settlement_date"].dt.dayofyear
    work["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    work["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    for column in ("lag_sp", "sp7", "sp28"):
        work[column] = work[column].fillna(work["mean7"]).fillna(work["mean28"])
    return work
def forecast_market_price_day(
    feature_frame: pd.DataFrame,
    target_date: str | pd.Timestamp,
    config: MarketPriceForecastConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fit on earlier dates only and forecast one complete target settlement day."""
    cfg = config or MarketPriceForecastConfig()
    target = pd.Timestamp(target_date).normalize()
    work = feature_frame.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"]).dt.normalize()
    train = work.loc[work["settlement_date"].lt(target)].dropna(
        subset=FEATURE_COLUMNS + [PRICE_COLUMN]
    )
    future = work.loc[work["settlement_date"].eq(target)].copy()
    history_days = int(work.loc[work["settlement_date"].lt(target), "settlement_date"].nunique())
    training_days = int(train["settlement_date"].nunique())
    if history_days < cfg.minimum_history_days:
        raise ValueError(
            f"Only {history_days} prior price days are available; "
            f"{cfg.minimum_history_days} are required."
        )
    if future.empty:
        raise KeyError(f"Target date {target.date()} is not present in the price frame.")
    if len(future) not in {46, 48, 50}:
        raise ValueError("Target price day must contain 46, 48 or 50 settlement periods.")
    if future[FEATURE_COLUMNS].isna().any().any():
        raise ValueError("Target price features contain missing prior-history values.")
    x_train = train[FEATURE_COLUMNS].to_numpy(float)
    y_train = train[PRICE_COLUMN].to_numpy(float)
    x_future = future[FEATURE_COLUMNS].to_numpy(float)
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale < 1e-9] = 1.0
    x_train = (x_train - mean) / scale
    x_future = (x_future - mean) / scale
    design = np.column_stack([np.ones(len(x_train)), x_train])
    future_design = np.column_stack([np.ones(len(x_future)), x_future])
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(
        design.T @ design + cfg.ridge_alpha * penalty,
        design.T @ y_train,
    )
    predicted = future_design @ beta
    future["forecast_market_index_price_gbp_per_mwh"] = predicted
    future["naive_market_index_price_gbp_per_mwh"] = future["lag_sp"].astype(float)
    metadata = {
        "method": "expanding_ridge_calendar_and_prior_price_lags",
        "target_date": target.date().isoformat(),
        "history_days": history_days,
        "training_rows": int(len(train)),
        "training_days_with_complete_features": training_days,
        "ridge_alpha": float(cfg.ridge_alpha),
        "feature_count": len(FEATURE_COLUMNS),
        "uses_target_date_prices": False,
        "issue_rule": "target-day forecast uses settlement dates strictly earlier than target date",
    }
    return future.reset_index(drop=True), metadata
def backtest_market_price_forecast(
    market_history: pd.DataFrame,
    config: MarketPriceForecastConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Generate expanding-window price forecasts after the minimum history period."""
    cfg = config or MarketPriceForecastConfig()
    features = build_market_price_features(market_history)
    dates = pd.Index(features["settlement_date"].drop_duplicates()).sort_values()
    parts: list[pd.DataFrame] = []
    for target in dates:
        prior_days = int((dates < target).sum())
        if prior_days < cfg.minimum_history_days:
            continue
        forecast, _meta = forecast_market_price_day(features, target, cfg)
        keep = forecast[[
            "settlement_date", "settlement_period", "valid_time_utc", PRICE_COLUMN,
            "forecast_market_index_price_gbp_per_mwh",
            "naive_market_index_price_gbp_per_mwh",
        ]].copy()
        parts.append(keep)
    if not parts:
        raise ValueError("No price-forecast dates were eligible for backtesting.")
    result = pd.concat(parts, ignore_index=True)
    actual = result[PRICE_COLUMN].to_numpy(float)
    pred = result["forecast_market_index_price_gbp_per_mwh"].to_numpy(float)
    naive = result["naive_market_index_price_gbp_per_mwh"].to_numpy(float)
    def _metrics(values: np.ndarray) -> dict[str, float]:
        error = values - actual
        denominator = float(((actual - actual.mean()) ** 2).sum())
        return {
            "mae_gbp_per_mwh": float(np.mean(np.abs(error))),
            "rmse_gbp_per_mwh": float(np.sqrt(np.mean(error**2))),
            "bias_gbp_per_mwh": float(np.mean(error)),
            "r2": float(1.0 - (error**2).sum() / denominator) if denominator > 0 else 0.0,
        }
    forecast_metrics = _metrics(pred)
    naive_metrics = _metrics(naive)
    summary: dict[str, Any] = {
        "method": "expanding_ridge_calendar_and_prior_price_lags",
        "eligible_days": int(result["settlement_date"].nunique()),
        "period_count": int(len(result)),
        "minimum_history_days": int(cfg.minimum_history_days),
        "ridge_alpha": float(cfg.ridge_alpha),
        "forecast": forecast_metrics,
        "naive_previous_observed_same_period": naive_metrics,
        "mae_improvement_vs_naive_pct": float(
            100.0 * (1.0 - forecast_metrics["mae_gbp_per_mwh"] / naive_metrics["mae_gbp_per_mwh"])
        ),
        "issue_rule": "strictly earlier settlement dates only",
    }
    return result, summary

