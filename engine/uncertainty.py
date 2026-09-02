"""Leakage-safe rolling prediction intervals for historical forecast review."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PredictionIntervalConfig:
    """Configuration for a rolling local residual prediction interval."""

    nominal_coverage: float = 0.80
    lookback_days: int = 90
    minimum_history_days: int = 30
    neighbour_count: int = 600

    def __post_init__(self) -> None:
        if not 0 < self.nominal_coverage < 1:
            raise ValueError("nominal_coverage must be between 0 and 1.")
        if self.lookback_days <= 0 or self.minimum_history_days <= 0:
            raise ValueError("History windows must be positive.")
        if self.neighbour_count <= 0:
            raise ValueError("neighbour_count must be positive.")

def _finite_sample_quantile(scores: np.ndarray, coverage: float) -> float:
    """Return the conservative finite-sample absolute-residual quantile."""

    values = np.asarray(scores, dtype=float)
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("Calibration scores must be finite and non-empty.")
    rank = min(int(ceil((values.size + 1) * coverage)), values.size)
    return float(np.partition(values, rank - 1)[rank - 1])


def build_rolling_prediction_interval(
    portfolio: pd.DataFrame,
    target_date: str | pd.Timestamp,
    config: PredictionIntervalConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, float | int | str | bool]]:
    """Build an interval for one date using only earlier out-of-sample errors.

    The calibration window is restricted to target dates strictly earlier than
    the selected date. For each settlement period, the interval half-width is
    calibrated from the nearest prior forecasts by forecast capacity factor.
    """

    cfg = config or PredictionIntervalConfig()
    required = {
        "settlement_date", "settlement_period", "valid_time_utc",
        "actual_cf", "forecast_cf", "portfolio_capacity_mw",
    }
    missing = sorted(required.difference(portfolio.columns))
    if missing:
        raise ValueError(f"Portfolio frame is missing uncertainty columns: {missing}")
    frame = portfolio.copy()
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"]).dt.normalize()
    target = pd.Timestamp(target_date).normalize()
    selected = frame.loc[frame["settlement_date"].eq(target)].copy()
    if selected.empty:
        raise KeyError(f"No portfolio evidence is available for {target.date()}.")

    window_start = target - pd.Timedelta(days=cfg.lookback_days)
    calibration = frame.loc[
        frame["settlement_date"].lt(target)
        & frame["settlement_date"].ge(window_start)
    ].copy()
    history_days = int(calibration["settlement_date"].nunique())
    if history_days < cfg.minimum_history_days:
        metadata = {
            "available": False,
            "reason": "insufficient_prior_history",
            "history_days": history_days,
            "minimum_history_days": cfg.minimum_history_days,
            "nominal_coverage_pct": cfg.nominal_coverage * 100,
        }
        return selected, metadata

    calibration["abs_residual_cf"] = (
        calibration["actual_cf"].to_numpy(float)
        - calibration["forecast_cf"].to_numpy(float)
    )
    calibration["abs_residual_cf"] = calibration["abs_residual_cf"].abs()
    cal_forecast = calibration["forecast_cf"].to_numpy(float)
    cal_scores = calibration["abs_residual_cf"].to_numpy(float)
    neighbours = min(cfg.neighbour_count, len(calibration))
    lower_cf: list[float] = []
    upper_cf: list[float] = []
    half_width_cf: list[float] = []
    for prediction in selected["forecast_cf"].to_numpy(float):
        distance = np.abs(cal_forecast - prediction)
        if neighbours == len(calibration):
            local_scores = cal_scores
        else:
            indexes = np.argpartition(distance, neighbours - 1)[:neighbours]
            local_scores = cal_scores[indexes]
        q = _finite_sample_quantile(local_scores, cfg.nominal_coverage)
        half_width_cf.append(q)
        lower_cf.append(max(0.0, prediction - q))
        upper_cf.append(min(1.0, prediction + q))

    selected["prediction_interval_lower_cf"] = lower_cf
    selected["prediction_interval_upper_cf"] = upper_cf
    selected["prediction_interval_half_width_cf"] = half_width_cf
    capacity = selected["portfolio_capacity_mw"].to_numpy(float)
    selected["prediction_interval_lower_mw"] = np.asarray(lower_cf) * capacity
    selected["prediction_interval_upper_mw"] = np.asarray(upper_cf) * capacity
    inside = selected["actual_mw"].between(
        selected["prediction_interval_lower_mw"],
        selected["prediction_interval_upper_mw"],
        inclusive="both",
    )
    selected["actual_inside_prediction_interval"] = inside

    width = (
        selected["prediction_interval_upper_mw"]
        - selected["prediction_interval_lower_mw"]
    )
    metadata = {
        "available": True,
        "method": "rolling_local_absolute_residual_interval",
        "nominal_coverage_pct": cfg.nominal_coverage * 100,
        "lookback_days": cfg.lookback_days,
        "history_days": history_days,
        "calibration_start": calibration["settlement_date"].min().date().isoformat(),
        "calibration_end": calibration["settlement_date"].max().date().isoformat(),
        "neighbour_count": neighbours,
        "mean_interval_width_mw": float(width.mean()),
        "observed_day_coverage_pct": float(inside.mean() * 100),
        "outside_periods": int((~inside).sum()),
        "period_count": int(len(selected)),
    }
    return selected, metadata
