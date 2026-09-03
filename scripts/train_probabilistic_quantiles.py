"""Train and validate the Stage 14 V2 conditional-quantile post-processor."""
from __future__ import annotations

from hashlib import sha256
import json
from math import ceil
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_pinball_loss

from engine.probabilistic import (
    PROBABILISTIC_FEATURES,
    build_mix_features,
    expand_training_portfolios,
    repair_quantiles,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "historical_backtest.csv"
MODEL_OUT = ROOT / "models" / "probabilistic_quantiles.joblib"
METADATA_OUT = ROOT / "models" / "probabilistic_quantiles_metadata.json"
OUT = ROOT / "outputs" / "probabilistic"
SHARE_GRID = [round(value / 20.0, 2) for value in range(21)]
TRAIN_SHARES = [0.0, 0.25, 0.50, 0.75, 1.0]
CANDIDATES = [
    {"name": "qA", "max_iter": 180, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 80, "l2_regularization": 1.0},
    {"name": "qB", "max_iter": 220, "learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 80, "l2_regularization": 1.0},
    {"name": "qC", "max_iter": 200, "learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 80, "l2_regularization": 1.0},
    {"name": "qD", "max_iter": 220, "learning_rate": 0.04, "max_leaf_nodes": 15, "min_samples_leaf": 120, "l2_regularization": 2.0},
]


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model(params: dict[str, object], quantile: float) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(
        loss="quantile", quantile=quantile,
        max_iter=int(params["max_iter"]), learning_rate=float(params["learning_rate"]),
        max_leaf_nodes=int(params["max_leaf_nodes"]), min_samples_leaf=int(params["min_samples_leaf"]),
        l2_regularization=float(params["l2_regularization"]), random_state=42,
    )


def _finite_conformal(scores: np.ndarray, coverage: float = 0.80) -> float:
    values = np.asarray(scores, dtype=float)
    rank = min(int(ceil((len(values) + 1) * coverage)), len(values))
    return float(np.partition(values, rank - 1)[rank - 1])
def _fit_three(training: pd.DataFrame, params: dict[str, object]) -> dict[str, HistGradientBoostingRegressor]:
    models = {}
    for label, quantile in (("q10", 0.10), ("q50", 0.50), ("q90", 0.90)):
        estimator = _model(params, quantile)
        estimator.fit(training[PROBABILISTIC_FEATURES], training["residual_cf"])
        models[label] = estimator
    return models


def _raw_predictions(
    source: pd.DataFrame,
    models: dict[str, HistGradientBoostingRegressor],
    wind_share: float,
) -> pd.DataFrame:
    work = build_mix_features(source, wind_share)
    matrix = work[PROBABILISTIC_FEATURES]
    point = work["portfolio_forecast_cf"].to_numpy(float)
    for label in ("q10", "q50", "q90"):
        work[f"raw_{label}"] = np.clip(point + models[label].predict(matrix), 0.0, 1.0)
    return work


def _pinball_score(validation: pd.DataFrame, models: dict[str, Any]) -> dict[str, float]:
    losses: list[float] = []
    by_quantile = {"q10": [], "q50": [], "q90": []}
    for share in TRAIN_SHARES:
        work = _raw_predictions(validation, models, share)
        actual = work["portfolio_actual_cf"].to_numpy(float)
        for label, alpha in (("q10", 0.10), ("q50", 0.50), ("q90", 0.90)):
            loss = float(mean_pinball_loss(actual, work[f"raw_{label}"], alpha=alpha))
            by_quantile[label].append(loss)
            losses.append(loss)
    return {
        "mean_pinball_loss": float(np.mean(losses)),
        **{f"mean_{key}_pinball": float(np.mean(values)) for key, values in by_quantile.items()},
    }
def _evaluate_locked_share(
    scoring: pd.DataFrame,
    models: dict[str, HistGradientBoostingRegressor],
    wind_share: float,
    lookback_days: int = 90,
) -> tuple[pd.DataFrame, dict[str, float]]:
    work = _raw_predictions(scoring, models, wind_share)
    actual = work["portfolio_actual_cf"].to_numpy(float)
    work["nonconformity"] = np.maximum.reduce([
        work["raw_q10"].to_numpy(float) - actual,
        actual - work["raw_q90"].to_numpy(float),
        np.zeros(len(work)),
    ])
    rows: list[pd.DataFrame] = []
    locked_dates = sorted(work.loc[work["evaluation_segment"].eq("locked_test"), "settlement_date"].unique())
    for target in locked_dates:
        start = pd.Timestamp(target) - pd.Timedelta(days=lookback_days)
        prior = work.loc[work["settlement_date"].lt(target) & work["settlement_date"].ge(start)]
        if prior["settlement_date"].nunique() < 30:
            raise ValueError(f"Insufficient rolling calibration history for {target}.")
        correction = _finite_conformal(prior["nonconformity"].to_numpy(float), 0.80)
        day = work.loc[work["settlement_date"].eq(target)].copy()
        q10 = np.clip(day["raw_q10"].to_numpy(float) - correction, 0.0, 1.0)
        q50 = day["raw_q50"].to_numpy(float)
        q90 = np.clip(day["raw_q90"].to_numpy(float) + correction, 0.0, 1.0)
        q10, q50, q90 = repair_quantiles(q10, q50, q90)
        day["p10_cf"], day["p50_cf"], day["p90_cf"] = q10, q50, q90
        day["conformal_correction_cf"] = correction
        rows.append(day)
    result = pd.concat(rows, ignore_index=True)
    actual = result["portfolio_actual_cf"].to_numpy(float)
    q10 = result["p10_cf"].to_numpy(float)
    q50 = result["p50_cf"].to_numpy(float)
    q90 = result["p90_cf"].to_numpy(float)
    point = result["portfolio_forecast_cf"].to_numpy(float)
    inside = (actual >= q10) & (actual <= q90)
    metrics = {
        "wind_share": float(wind_share),
        "periods": int(len(result)),
        "days": int(result["settlement_date"].nunique()),
        "observed_p10_p90_coverage_pct": float(100.0 * inside.mean()),
        "mean_p10_p90_width_cf": float(np.mean(q90 - q10)),
        "p10_pinball": float(mean_pinball_loss(actual, q10, alpha=0.10)),
        "p50_pinball": float(mean_pinball_loss(actual, q50, alpha=0.50)),
        "p90_pinball": float(mean_pinball_loss(actual, q90, alpha=0.90)),
        "p50_mae_cf": float(np.mean(np.abs(actual - q50))),
        "v2_point_mae_cf": float(np.mean(np.abs(actual - point))),
        "median_rolling_correction_cf": float(
            result.groupby("settlement_date")["conformal_correction_cf"].first().median()
        ),
    }
    keep = [
        "settlement_date", "settlement_period", "valid_time_utc", "wind_share",
        "portfolio_actual_cf", "portfolio_forecast_cf", "p10_cf", "p50_cf", "p90_cf",
        "conformal_correction_cf",
    ]
    return result[keep], metrics


def _production_corrections(
    calibration: pd.DataFrame,
    models: dict[str, HistGradientBoostingRegressor],
) -> dict[str, float]:
    corrections: dict[str, float] = {}
    for share in SHARE_GRID:
        work = _raw_predictions(calibration, models, share)
        actual = work["portfolio_actual_cf"].to_numpy(float)
        scores = np.maximum.reduce([
            work["raw_q10"].to_numpy(float) - actual,
            actual - work["raw_q90"].to_numpy(float),
            np.zeros(len(work)),
        ])
        corrections[f"{share:.2f}"] = _finite_conformal(scores, 0.80)
    return corrections


def main() -> None:
    source = pd.read_csv(SOURCE)
    source["settlement_date"] = pd.to_datetime(source["settlement_date"]).dt.normalize()
    source["valid_time_utc"] = pd.to_datetime(source["valid_time_utc"], utc=True)
    development = source.loc[source["evaluation_segment"].eq("development_oof")].copy()
    selection_train = development.loc[development["settlement_date"].lt("2025-10-01")]
    selection_validation = development.loc[
        development["settlement_date"].ge("2025-10-01")
        & development["settlement_date"].le("2025-12-31")
    ]
    train_expanded = expand_training_portfolios(selection_train, TRAIN_SHARES)
    candidates: list[dict[str, object]] = []
    fitted_candidates: dict[str, dict[str, HistGradientBoostingRegressor]] = {}
    for params in CANDIDATES:
        fitted = _fit_three(train_expanded, params)
        score = _pinball_score(selection_validation, fitted)
        candidates.append({**params, **score})
        fitted_candidates[str(params["name"])] = fitted
        print(params["name"], score, flush=True)
    selected = min(candidates, key=lambda item: float(item["mean_pinball_loss"]))
    selected_params = next(item for item in CANDIDATES if item["name"] == selected["name"])
    evaluation_train = development.loc[development["settlement_date"].lt("2026-01-01")]
    evaluation_scoring = source.loc[
        source["settlement_date"].ge("2026-01-01")
        & source["settlement_date"].le("2026-06-30")
    ].copy()
    evaluation_models = _fit_three(
        expand_training_portfolios(evaluation_train, TRAIN_SHARES), selected_params
    )
    locked_parts: list[pd.DataFrame] = []
    locked_metrics: list[dict[str, float]] = []
    for share in SHARE_GRID:
        predictions, metrics = _evaluate_locked_share(
            evaluation_scoring, evaluation_models, share, lookback_days=90
        )
        locked_parts.append(predictions)
        locked_metrics.append(metrics)
    locked_predictions = pd.concat(locked_parts, ignore_index=True)
    locked_summary = pd.DataFrame(locked_metrics)

    production_models = _fit_three(
        expand_training_portfolios(development, TRAIN_SHARES), selected_params
    )
    locked_calibration = source.loc[source["evaluation_segment"].eq("locked_test")].copy()
    production_corrections = _production_corrections(locked_calibration, production_models)

    OUT.mkdir(parents=True, exist_ok=True)
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    locked_predictions.to_csv(OUT / "stage14_locked_predictions.csv", index=False)
    locked_summary.to_csv(OUT / "stage14_locked_summary_by_mix.csv", index=False)
    joblib.dump(production_models, MODEL_OUT, compress=3)
    metadata = {
        "schema_version": "1.0",
        "stage": "14_probabilistic_renewable_quantiles",
        "model_version": "v3-conditional-quantile-2026-09",
        "method": "mix-aware conditional residual quantile regression with conformal calibration",
        "base_forecast": "frozen V2 deterministic out-of-sample wind/solar forecast",
        "features": PROBABILISTIC_FEATURES,
        "quantiles": [0.10, 0.50, 0.90],
        "nominal_central_coverage_pct": 80.0,
        "selection_training_period": "2025-04-01 to 2025-09-30 development OOF only",
        "selection_validation_period": "2025-10-01 to 2025-12-31 development OOF only",
        "locked_evaluation_training_period": "2025-04-01 to 2025-12-31 development OOF only",
        "locked_evaluation_period": "2026-04-01 to 2026-06-30; 90 V2 locked days",
        "locked_evaluation_calibration": "rolling prior 90 calendar days; target day excluded",
        "production_training_period": "2025-04-01 to 2026-03-31 development OOF",
        "production_conformal_calibration_period": "2026-04-01 to 2026-06-30 locked V2 evidence",
        "production_conformal_correction_cf_by_wind_share": production_corrections,
        "supported_wind_share_grid": SHARE_GRID,
        "training_share_grid": TRAIN_SHARES,
        "candidate_results": candidates,
        "selected_candidate": selected,
        "selected_hyperparameters": selected_params,
        "source_sha256": _hash(SOURCE),
        "model_sha256": _hash(MODEL_OUT),
    }
    metadata["boundary"] = [
        "This is a statistical post-processor of V2 point forecasts, not an ECMWF ensemble forecast.",
        "Locked-period metrics use models and rolling corrections based only on earlier dates.",
        "The locked Apr-Jun evidence is used only after evaluation to calibrate the production interval width.",
        "P10/P50/P90 describe the virtual portfolio capacity-factor distribution under historical V2 error behaviour.",
    ]
    METADATA_OUT.write_text(json.dumps(metadata, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    default = locked_summary.loc[np.isclose(locked_summary["wind_share"], 0.50)].iloc[0].to_dict()
    wind = locked_summary.loc[np.isclose(locked_summary["wind_share"], 1.00)].iloc[0].to_dict()
    solar = locked_summary.loc[np.isclose(locked_summary["wind_share"], 0.00)].iloc[0].to_dict()
    summary = {
        "schema_version": "1.0",
        "stage": "14_probabilistic_renewable_quantiles",
        "selected_candidate": selected,
        "locked_reference": {"solar": solar, "mixed_50_50": default, "wind": wind},
        "mix_grid_rows": int(len(locked_summary)),
        "locked_prediction_rows": int(len(locked_predictions)),
        "model_sha256": _hash(MODEL_OUT),
        "metadata_sha256": _hash(METADATA_OUT),
        "source_sha256": _hash(SOURCE),
        "claim_boundary": "conditional quantile/conformal uncertainty around V2; not weather-ensemble probabilities",
    }
    (OUT / "stage14_summary.json").write_text(
        json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, allow_nan=False), flush=True)


if __name__ == "__main__":
    main()
