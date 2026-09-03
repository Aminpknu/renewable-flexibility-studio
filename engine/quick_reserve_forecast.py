"""Issue-time-correct Quick Reserve clearing-price forecasting."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class QuickReserveForecastConfig:
    minimum_history_days: int = 60
    lookback_days: int = 180
    ridge_alpha: float = 20.0

    def __post_init__(self) -> None:
        if self.minimum_history_days <= 0 or self.lookback_days < self.minimum_history_days:
            raise ValueError("QR forecast history settings are invalid.")
        if not np.isfinite(self.ridge_alpha) or self.ridge_alpha < 0:
            raise ValueError("QR ridge alpha must be finite and non-negative.")


FEATURE_COLUMNS = [
    "product_pqr", "sp_sin", "sp_cos", "dow_sin", "dow_cos",
    "doy_sin", "doy_cos", "price_lag1", "price_lag7",
    "price_roll7", "price_roll28", "volume_lag1", "volume_roll7",
]


def build_quick_reserve_features(history: pd.DataFrame) -> pd.DataFrame:
    required = {
        "delivery_start_utc", "product", "clearing_price_gbp_per_mw_per_hour",
        "cleared_volume_mw",
    }
    missing = sorted(required.difference(history.columns))
    if missing:
        raise ValueError(f"QR history is missing forecast columns: {missing}")
    work = history.copy()
    work["delivery_start_utc"] = pd.to_datetime(work["delivery_start_utc"], utc=True)
    local = work["delivery_start_utc"].dt.tz_convert("Europe/London")
    work["settlement_date"] = pd.to_datetime(local.dt.date)
    work = work.sort_values(["settlement_date", "product", "delivery_start_utc"]).reset_index(drop=True)
    work["settlement_period"] = work.groupby(["settlement_date", "product"]).cumcount() + 1
    counts = work.groupby(["settlement_date", "product"])["settlement_period"].max()
    valid_dates = counts.unstack("product").dropna()
    valid_dates = valid_dates.loc[
        valid_dates.apply(lambda row: row.nunique() == 1 and int(row.iloc[0]) in {46, 48, 50}, axis=1)
    ].index
    work = work.loc[work["settlement_date"].isin(valid_dates)].copy()
    work["product_pqr"] = work["product"].eq("PQR").astype(float)
    sp = work["settlement_period"].astype(float)
    work["sp_sin"] = np.sin(2 * np.pi * sp / 48.0)
    work["sp_cos"] = np.cos(2 * np.pi * sp / 48.0)
    dow = work["settlement_date"].dt.dayofweek.astype(float)
    doy = work["settlement_date"].dt.dayofyear.astype(float)
    work["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    work["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    work["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    work["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    price = "clearing_price_gbp_per_mw_per_hour"
    volume = "cleared_volume_mw"
    group_keys = ["product", "settlement_period"]
    grouped = work.groupby(group_keys, group_keys=False)
    work["price_lag1"] = grouped[price].shift(1)
    work["price_lag7"] = grouped[price].shift(7)
    work["volume_lag1"] = grouped[volume].shift(1)
    work["price_roll7"] = grouped[price].transform(
        lambda s: s.shift(1).rolling(7, min_periods=3).mean()
    )
    work["price_roll28"] = grouped[price].transform(
        lambda s: s.shift(1).rolling(28, min_periods=7).mean()
    )
    work["volume_roll7"] = grouped[volume].transform(
        lambda s: s.shift(1).rolling(7, min_periods=3).mean()
    )
    return work.sort_values(
        ["settlement_date", "settlement_period", "product"]
    ).reset_index(drop=True)


def forecast_quick_reserve_day(
    features: pd.DataFrame,
    target_date: str | pd.Timestamp,
    config: QuickReserveForecastConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = config or QuickReserveForecastConfig()
    target = pd.Timestamp(target_date).normalize()
    work = features.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"]).dt.normalize()
    history_dates = work.loc[work["settlement_date"].lt(target), "settlement_date"].drop_duplicates()
    if len(history_dates) < cfg.minimum_history_days:
        raise ValueError(
            f"Only {len(history_dates)} prior QR days are available; "
            f"{cfg.minimum_history_days} are required."
        )
    cutoff = target - pd.Timedelta(days=cfg.lookback_days)
    train = work.loc[
        work["settlement_date"].lt(target)
        & work["settlement_date"].ge(cutoff)
    ].dropna(subset=FEATURE_COLUMNS + ["clearing_price_gbp_per_mw_per_hour"])
    future = work.loc[work["settlement_date"].eq(target)].copy()
    if future.empty:
        raise KeyError(f"QR target date {target.date()} is unavailable.")
    if future[FEATURE_COLUMNS].isna().any().any():
        raise ValueError("QR target-day features contain missing prior-history values.")
    x_train = train[FEATURE_COLUMNS].to_numpy(float)
    y_train = train["clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    x_future = future[FEATURE_COLUMNS].to_numpy(float)
    if len(train) == 0:
        raise ValueError("QR forecast training frame is empty after lag filtering.")
    mean = x_train.mean(axis=0)
    scale = x_train.std(axis=0)
    scale[scale < 1e-9] = 1.0
    x_train_scaled = (x_train - mean) / scale
    x_future_scaled = (x_future - mean) / scale
    design = np.column_stack([np.ones(len(x_train_scaled)), x_train_scaled])
    future_design = np.column_stack([np.ones(len(x_future_scaled)), x_future_scaled])
    penalty = np.eye(design.shape[1])
    penalty[0, 0] = 0.0
    beta = np.linalg.solve(
        design.T @ design + cfg.ridge_alpha * penalty,
        design.T @ y_train,
    )
    predicted = np.clip(future_design @ beta, 0.0, None)
    naive = future["price_lag1"].to_numpy(float)
    output = future[[
        "settlement_date", "settlement_period", "delivery_start_utc",
        "product", "cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour",
    ]].copy()
    output["forecast_qr_clearing_price_gbp_per_mw_per_hour"] = predicted
    output["naive_qr_clearing_price_gbp_per_mw_per_hour"] = naive
    metadata: dict[str, Any] = {
        "method": "expanding_ridge_calendar_prior_qr_lags",
        "target_date": target.date().isoformat(),
        "history_days_available": int(len(history_dates)),
        "lookback_days": int(cfg.lookback_days),
        "training_days": int(train["settlement_date"].nunique()),
        "training_rows": int(len(train)),
        "ridge_alpha": float(cfg.ridge_alpha),
        "feature_count": int(len(FEATURE_COLUMNS)),
        "uses_target_date_clearing_price": False,
        "issue_rule": "target-day features use QR clearing results from earlier settlement dates only",
    }
    return output.sort_values(["settlement_period", "product"]).reset_index(drop=True), metadata


def _distribution_metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    error = predicted - actual
    variance = float(np.sum((actual - actual.mean()) ** 2))
    return {
        "mae_gbp_per_mw_per_hour": float(np.mean(np.abs(error))),
        "rmse_gbp_per_mw_per_hour": float(np.sqrt(np.mean(error**2))),
        "bias_gbp_per_mw_per_hour": float(np.mean(error)),
        "r2": float(1.0 - np.sum(error**2) / variance) if variance > 0 else 0.0,
    }


def backtest_quick_reserve_price_forecast(
    history: pd.DataFrame,
    config: QuickReserveForecastConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = config or QuickReserveForecastConfig()
    features = build_quick_reserve_features(history)
    dates = sorted(pd.to_datetime(features["settlement_date"]).dt.normalize().unique())
    outputs = []
    for target in dates:
        prior_days = int(
            features.loc[features["settlement_date"].lt(target), "settlement_date"].nunique()
        )
        if prior_days < cfg.minimum_history_days:
            continue
        try:
            day, _metadata = forecast_quick_reserve_day(features, target, cfg)
        except (ValueError, KeyError):
            continue
        outputs.append(day)
    if not outputs:
        raise ValueError("No QR forecast backtest dates are eligible.")
    result = pd.concat(outputs, ignore_index=True)
    actual = result["clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    forecast = result["forecast_qr_clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    naive = result["naive_qr_clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
    summary: dict[str, Any] = {
        "method": "prior-date-only Quick Reserve clearing-price ridge forecast",
        "eligible_days": int(result["settlement_date"].nunique()),
        "period_product_rows": int(len(result)),
        "minimum_history_days": int(cfg.minimum_history_days),
        "lookback_days": int(cfg.lookback_days),
        "ridge_alpha": float(cfg.ridge_alpha),
        "forecast": _distribution_metrics(actual, forecast),
        "naive_previous_same_product_period": _distribution_metrics(actual, naive),
        "issue_rule": "strictly earlier settlement dates only",
    }
    summary["mae_improvement_vs_naive_pct"] = float(
        100.0 * (
            1.0
            - summary["forecast"]["mae_gbp_per_mw_per_hour"]
            / summary["naive_previous_same_product_period"]["mae_gbp_per_mw_per_hour"]
        )
    )
    by_product: dict[str, Any] = {}
    for product, group in result.groupby("product"):
        by_product[str(product)] = {
            "rows": int(len(group)),
            "forecast": _distribution_metrics(
                group["clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
                group["forecast_qr_clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
            ),
            "naive": _distribution_metrics(
                group["clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
                group["naive_qr_clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
            ),
        }
    summary["by_product"] = by_product
    locked = result.loc[
        pd.to_datetime(result["settlement_date"]).between(
            pd.Timestamp("2026-04-01"), pd.Timestamp("2026-06-30")
        )
    ]
    if not locked.empty:
        summary["apr_jun_2026"] = {
            "days": int(locked["settlement_date"].nunique()),
            "forecast": _distribution_metrics(
                locked["clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
                locked["forecast_qr_clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
            ),
            "naive": _distribution_metrics(
                locked["clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
                locked["naive_qr_clearing_price_gbp_per_mw_per_hour"].to_numpy(float),
            ),
        }
    return result, summary
