"""Conditional quantile post-processing for V2 renewable forecasts."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import warnings
import joblib
import numpy as np
import pandas as pd

PROBABILISTIC_FEATURES = [
    "wind_pred_cf", "solar_pred_cf", "portfolio_forecast_cf",
    "portfolio_forecast_sq", "wind_share", "wind_share_x_wind",
    "solar_share_x_solar", "wind_ramp", "solar_ramp",
    "wind_day_mean", "solar_day_mean", "sp_sin", "sp_cos",
    "doy_sin", "doy_cos",
]


def _prepare_base_features(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    if "settlement_date" not in work.columns and "target_date" in work.columns:
        work["settlement_date"] = pd.to_datetime(work["target_date"]).dt.normalize()
    required = {"settlement_date", "settlement_period", "valid_time_utc", "wind_pred_cf", "solar_pred_cf"}
    missing = sorted(required.difference(work.columns))
    if missing:
        raise ValueError(f"Probabilistic input is missing columns: {missing}")
    work = work.sort_values(["settlement_date", "settlement_period"]).reset_index(drop=True)
    work["settlement_date"] = pd.to_datetime(work["settlement_date"]).dt.normalize()
    work["valid_time_utc"] = pd.to_datetime(work["valid_time_utc"], utc=True)
    local = work["valid_time_utc"].dt.tz_convert("Europe/London")
    sp = work["settlement_period"].astype(float)
    doy = local.dt.dayofyear.astype(float)
    work["sp_sin"] = np.sin(2 * np.pi * sp / 48.0)
    work["sp_cos"] = np.cos(2 * np.pi * sp / 48.0)
    work["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    work["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    work["wind_ramp"] = work.groupby("settlement_date")["wind_pred_cf"].diff().fillna(0.0)
    work["solar_ramp"] = work.groupby("settlement_date")["solar_pred_cf"].diff().fillna(0.0)
    work["wind_day_mean"] = work.groupby("settlement_date")["wind_pred_cf"].transform("mean")
    work["solar_day_mean"] = work.groupby("settlement_date")["solar_pred_cf"].transform("mean")
    return work


def build_mix_features(frame: pd.DataFrame, wind_share: float) -> pd.DataFrame:
    """Build issue-time features for one virtual wind/solar portfolio mix."""
    share = float(wind_share)
    if not np.isfinite(share) or not 0.0 <= share <= 1.0:
        raise ValueError("wind_share must be between 0 and 1.")
    work = _prepare_base_features(frame)
    work["wind_share"] = share
    work["portfolio_forecast_cf"] = (
        share * work["wind_pred_cf"] + (1.0 - share) * work["solar_pred_cf"]
    ).clip(0.0, 1.0)
    work["portfolio_forecast_sq"] = work["portfolio_forecast_cf"] ** 2
    work["wind_share_x_wind"] = share * work["wind_pred_cf"]
    work["solar_share_x_solar"] = (1.0 - share) * work["solar_pred_cf"]
    if {"wind_cf", "solar_cf"}.issubset(work.columns):
        work["portfolio_actual_cf"] = (
            share * work["wind_cf"] + (1.0 - share) * work["solar_cf"]
        )
        work["residual_cf"] = work["portfolio_actual_cf"] - work["portfolio_forecast_cf"]
    if work[PROBABILISTIC_FEATURES].isna().any().any():
        raise ValueError("Probabilistic feature matrix contains missing values.")
    return work


def expand_training_portfolios(
    frame: pd.DataFrame,
    wind_shares: list[float] | tuple[float, ...],
) -> pd.DataFrame:
    """Expand historical V2 evidence across transparent virtual portfolio mixes."""
    if not {"wind_cf", "solar_cf"}.issubset(frame.columns):
        raise ValueError("Training evidence requires observed wind_cf and solar_cf.")
    parts = [build_mix_features(frame, float(share)) for share in wind_shares]
    return pd.concat(parts, ignore_index=True)


def repair_quantiles(
    q10: np.ndarray, q50: np.ndarray, q90: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Enforce monotone quantiles without looking at realised target values."""
    low = np.asarray(q10, dtype=float)
    med = np.asarray(q50, dtype=float)
    high = np.asarray(q90, dtype=float)
    if not (low.shape == med.shape == high.shape):
        raise ValueError("Quantile arrays must have the same shape.")
    low = np.minimum(low, med)
    high = np.maximum(high, med)
    return low, med, high


def load_probabilistic_bundle(
    model_path: str | Path,
    metadata_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load fitted q10/q50/q90 regressors and validate their feature contract."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Setting the shape on a NumPy array has been deprecated.*", category=DeprecationWarning)
        models = joblib.load(Path(model_path))
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if sorted(models) != ["q10", "q50", "q90"]:
        raise ValueError("Probabilistic model bundle must contain q10, q50 and q90.")
    if metadata.get("features") != PROBABILISTIC_FEATURES:
        raise ValueError("Probabilistic metadata feature contract does not match code.")
    for name, model in models.items():
        count = getattr(model, "n_features_in_", len(PROBABILISTIC_FEATURES))
        if int(count) != len(PROBABILISTIC_FEATURES):
            raise ValueError(f"{name} feature count does not match probabilistic metadata.")
    return models, metadata


def correction_for_wind_share(metadata: dict[str, Any], wind_share: float) -> float:
    """Return the production conformal correction for an exact 5%-step mix."""
    share = float(wind_share)
    key = f"{share:.2f}"
    corrections = metadata.get("production_conformal_correction_cf_by_wind_share", {})
    if key not in corrections:
        raise KeyError(
            f"No production conformal correction is available for wind share {share:.2f}. "
            "The current contract supports the 0.05 share grid."
        )
    return float(corrections[key])


def predict_portfolio_quantiles(
    frame: pd.DataFrame,
    models: dict[str, Any],
    metadata: dict[str, Any],
    wind_share: float,
    capacity_mw: float,
    correction_cf: float | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Predict P10/P50/P90 and a reserve envelope around the deterministic V2 schedule."""
    if not np.isfinite(capacity_mw) or float(capacity_mw) <= 0:
        raise ValueError("capacity_mw must be positive and finite.")
    features = build_mix_features(frame, wind_share)
    matrix = features[PROBABILISTIC_FEATURES]
    correction = (
        correction_for_wind_share(metadata, wind_share)
        if correction_cf is None else float(correction_cf)
    )
    if correction < 0 or not np.isfinite(correction):
        raise ValueError("Conformal correction must be finite and non-negative.")
    point = features["portfolio_forecast_cf"].to_numpy(float)
    q10_raw = np.clip(point + models["q10"].predict(matrix) - correction, 0.0, 1.0)
    q50_raw = np.clip(point + models["q50"].predict(matrix), 0.0, 1.0)
    q90_raw = np.clip(point + models["q90"].predict(matrix) + correction, 0.0, 1.0)
    q10, q50, q90 = repair_quantiles(q10_raw, q50_raw, q90_raw)
    result = features.copy()
    result["p10_cf"] = q10
    result["p50_cf"] = q50
    result["p90_cf"] = q90
    result["p10_mw"] = q10 * float(capacity_mw)
    result["p50_mw"] = q50 * float(capacity_mw)
    result["p90_mw"] = q90 * float(capacity_mw)
    result["forecast_mw"] = point * float(capacity_mw)
    result["prediction_interval_lower_cf"] = np.minimum(q10, point)
    result["prediction_interval_upper_cf"] = np.maximum(q90, point)
    result["prediction_interval_lower_mw"] = result["prediction_interval_lower_cf"] * float(capacity_mw)
    result["prediction_interval_upper_mw"] = result["prediction_interval_upper_cf"] * float(capacity_mw)
    width = result["p90_mw"] - result["p10_mw"]
    return result, {
        "available": True,
        "method": metadata.get("method", "conditional_quantile_residual_postprocessor"),
        "nominal_central_coverage_pct": 80.0,
        "wind_share": float(wind_share),
        "conformal_correction_cf": correction,
        "mean_p10_p90_width_mw": float(width.mean()),
        "point_forecast_role": "V2 deterministic schedule; quantiles are uncertainty evidence",
    }
