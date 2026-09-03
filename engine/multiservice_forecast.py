"""Issue-time-correct clearing-price forecasts for current NESO EAC products."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class MultiServiceForecastConfig:
    minimum_history_days: int = 21
    lookback_days: int = 180
    ridge_alpha: float = 20.0

    def __post_init__(self) -> None:
        if self.minimum_history_days <= 0:
            raise ValueError("Minimum multi-service forecast history must be positive.")
        if self.lookback_days < self.minimum_history_days:
            raise ValueError("Multi-service lookback must cover minimum history.")
        if not np.isfinite(self.ridge_alpha) or self.ridge_alpha < 0:
            raise ValueError("Multi-service ridge alpha must be finite and non-negative.")

FEATURE_COLUMNS = [
    "time_sin", "time_cos", "dow_sin", "dow_cos", "doy_sin", "doy_cos",
    "price_lag1", "price_lag7", "price_roll7", "price_roll28",
    "volume_lag1", "volume_roll7",
]


def build_multiservice_forecast_features(history: pd.DataFrame) -> pd.DataFrame:
    required = {
        "delivery_start_utc", "product", "family",
        "clearing_price_gbp_per_mw_per_hour", "cleared_volume_mw",
    }
    missing = sorted(required.difference(history.columns))
    if missing:
        raise ValueError(f"Multi-service history is missing forecast columns: {missing}")
    work = history.copy()
    work["delivery_start_utc"] = pd.to_datetime(work["delivery_start_utc"], utc=True)
    local = work["delivery_start_utc"].dt.tz_convert("Europe/London")
    work["service_date"] = pd.to_datetime(local.dt.date)
    work["local_start_minute"] = local.dt.hour * 60 + local.dt.minute
    minute = work["local_start_minute"].astype(float)
    work["time_sin"] = np.sin(2 * np.pi * minute / 1440.0)
    work["time_cos"] = np.cos(2 * np.pi * minute / 1440.0)
    dow = work["service_date"].dt.dayofweek.astype(float)
    doy = work["service_date"].dt.dayofyear.astype(float)
    work["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    work["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    work["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    work["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    price = "clearing_price_gbp_per_mw_per_hour"
    volume = "cleared_volume_mw"
    keys = ["product", "local_start_minute"]
    work = work.sort_values(keys + ["delivery_start_utc"]).reset_index(drop=True)
    grouped = work.groupby(keys, group_keys=False)
    work["price_lag1"] = grouped[price].shift(1)
    work["price_lag7"] = grouped[price].shift(7)
    work["volume_lag1"] = grouped[volume].shift(1)
    work["price_roll7"] = grouped[price].transform(lambda s: s.shift(1).rolling(7, min_periods=3).mean())
    work["price_roll28"] = grouped[price].transform(lambda s: s.shift(1).rolling(28, min_periods=7).mean())
    work["volume_roll7"] = grouped[volume].transform(lambda s: s.shift(1).rolling(7, min_periods=3).mean())
    return work.sort_values(["service_date", "delivery_start_utc", "product"]).reset_index(drop=True)


def _ridge_predict(train: pd.DataFrame, future: pd.DataFrame, alpha: float) -> np.ndarray:
    x_train = train[FEATURE_COLUMNS].to_numpy(float)
    y_train = train["clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    x_future = future[FEATURE_COLUMNS].to_numpy(float)
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale < 1e-9] = 1.0
    design = np.column_stack([np.ones(len(train)), (x_train - mean) / scale])
    future_design = np.column_stack([np.ones(len(future)), (x_future - mean) / scale])
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(design.T @ design + alpha * penalty, design.T @ y_train)
    return future_design @ beta


def forecast_multiservice_day(
    features: pd.DataFrame,
    target_date: str | pd.Timestamp,
    config: MultiServiceForecastConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = config or MultiServiceForecastConfig()
    target = pd.Timestamp(target_date).normalize()
    work = features.copy()
    work["service_date"] = pd.to_datetime(work["service_date"]).dt.normalize()
    outputs: list[pd.DataFrame] = []
    metadata: dict[str, Any] = {"target_date": target.date().isoformat(), "products": {}}
    for product in sorted(work.loc[work["service_date"].eq(target), "product"].unique()):
        product_rows = work.loc[work["product"].eq(product)].copy()
        prior_dates = product_rows.loc[product_rows["service_date"].lt(target), "service_date"].drop_duplicates()
        if len(prior_dates) < cfg.minimum_history_days:
            metadata["products"][str(product)] = {
                "status": "insufficient_history", "prior_days": int(len(prior_dates))
            }
            continue
        cutoff = target - pd.Timedelta(days=cfg.lookback_days)
        train = product_rows.loc[
            product_rows["service_date"].lt(target)
            & product_rows["service_date"].ge(cutoff)
        ].dropna(subset=FEATURE_COLUMNS + ["clearing_price_gbp_per_mw_per_hour"])
        future = product_rows.loc[product_rows["service_date"].eq(target)].copy()
        if future.empty or future[FEATURE_COLUMNS].isna().any().any() or train.empty:
            metadata["products"][str(product)] = {
                "status": "missing_features", "prior_days": int(len(prior_dates))
            }
            continue
        predicted = _ridge_predict(train, future, cfg.ridge_alpha)
        if not future["family"].eq("Dynamic Containment").all() and not future["family"].eq("Dynamic Moderation").all() and not future["family"].eq("Dynamic Regulation").all():
            predicted = np.clip(predicted, 0.0, None)
        output = future[[
            "service_date", "delivery_start_utc", "product", "family", "direction",
            "window_hours", "cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour",
        ]].copy()
        output["forecast_clearing_price_gbp_per_mw_per_hour"] = predicted
        output["prior_same_window_price_gbp_per_mw_per_hour"] = future["price_lag1"].to_numpy(float)
        output["naive_clearing_price_gbp_per_mw_per_hour"] = future["price_lag1"].to_numpy(float)
        outputs.append(output)
        metadata["products"][str(product)] = {
            "status": "forecast", "prior_days": int(len(prior_dates)),
            "training_days": int(train["service_date"].nunique()), "training_rows": int(len(train)),
        }
    if not outputs:
        raise ValueError(f"No multi-service products are forecastable for {target.date()}.")
    result = pd.concat(outputs, ignore_index=True)
    metadata.update({
        "method": "product_specific_ridge_calendar_prior_price_volume_lags",
        "minimum_history_days": int(cfg.minimum_history_days),
        "lookback_days": int(cfg.lookback_days),
        "ridge_alpha": float(cfg.ridge_alpha),
        "uses_target_date_clearing_price": False,
        "issue_rule": "every model feature is derived from earlier service dates only",
    })
    return result.sort_values(["delivery_start_utc", "product"]).reset_index(drop=True), metadata


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    error = predicted - actual
    variance = float(np.sum((actual - actual.mean()) ** 2))
    return {
        "mae": float(np.mean(np.abs(error))),
        "rmse": float(np.sqrt(np.mean(error**2))),
        "bias": float(np.mean(error)),
        "r2": float(1.0 - np.sum(error**2) / variance) if variance > 0 else 0.0,
    }


def backtest_multiservice_price_forecast(
    history: pd.DataFrame,
    start_date: str = "2026-05-01",
    end_date: str = "2026-06-30",
    config: MultiServiceForecastConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = config or MultiServiceForecastConfig()
    features = build_multiservice_forecast_features(history)
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    dates = pd.date_range(start, end, freq="D")
    outputs: list[pd.DataFrame] = []
    for date in dates:
        try:
            day, _ = forecast_multiservice_day(features, date, cfg)
        except ValueError:
            continue
        outputs.append(day)
    if not outputs:
        raise ValueError("No multi-service price-forecast backtest dates were eligible.")
    result = pd.concat(outputs, ignore_index=True)
    actual = result["clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    forecast = result["forecast_clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    naive = result["naive_clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    summary: dict[str, Any] = {
        "method": "prior-date-only product-specific NESO EAC clearing-price forecast",
        "validation_start": start.date().isoformat(),
        "validation_end": end.date().isoformat(),
        "days": int(result["service_date"].nunique()),
        "rows": int(len(result)),
        "forecast": _metrics(actual, forecast),
        "naive_previous_same_product_window": _metrics(actual, naive),
        "issue_rule": "strictly earlier service dates only",
        "by_product": {},
    }
    summary["mae_improvement_vs_naive_pct"] = 100.0 * (
        1.0 - summary["forecast"]["mae"] / summary["naive_previous_same_product_window"]["mae"]
    )
    for product, group in result.groupby("product"):
        a = group["clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
        f = group["forecast_clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
        n = group["naive_clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
        summary["by_product"][str(product)] = {
            "rows": int(len(group)), "days": int(group["service_date"].nunique()),
            "forecast": _metrics(a, f), "naive": _metrics(a, n),
        }
    return result, summary
