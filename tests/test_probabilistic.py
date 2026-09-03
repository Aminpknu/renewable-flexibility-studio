import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from engine.probabilistic import (
    PROBABILISTIC_FEATURES,
    load_probabilistic_bundle,
    predict_portfolio_quantiles,
    repair_quantiles,
)

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "models" / "probabilistic_quantiles.joblib"
METADATA = ROOT / "models" / "probabilistic_quantiles_metadata.json"
LATEST = ROOT / "data" / "latest_forecast.csv"
SUMMARY = ROOT / "outputs" / "probabilistic" / "stage14_summary.json"
COMPARISON = ROOT / "outputs" / "probabilistic" / "stage14_uncertainty_comparison_summary.json"
def _latest() -> pd.DataFrame:
    frame = pd.read_csv(LATEST)
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    return frame


def test_probabilistic_bundle_contract_and_monotone_quantiles() -> None:
    models, metadata = load_probabilistic_bundle(MODEL, METADATA)
    assert metadata["features"] == PROBABILISTIC_FEATURES
    frame, info = predict_portfolio_quantiles(_latest(), models, metadata, 0.50, 100.0)
    assert info["available"] is True
    assert np.all(frame["p10_cf"] <= frame["p50_cf"] + 1e-12)
    assert np.all(frame["p50_cf"] <= frame["p90_cf"] + 1e-12)
    assert frame[["p10_cf", "p50_cf", "p90_cf"]].ge(0).all().all()
    assert frame[["p10_cf", "p50_cf", "p90_cf"]].le(1).all().all()
    expected = 0.5 * frame["wind_pred_cf"] + 0.5 * frame["solar_pred_cf"]
    assert np.allclose(frame["forecast_mw"], expected * 100.0)


def test_probabilistic_predictions_do_not_use_realised_target_values() -> None:
    models, metadata = load_probabilistic_bundle(MODEL, METADATA)
    base = _latest()
    augmented = base.copy()
    augmented["wind_cf"] = np.linspace(0, 1, len(augmented))
    augmented["solar_cf"] = np.linspace(1, 0, len(augmented))
    first, _ = predict_portfolio_quantiles(base, models, metadata, 0.75, 100.0)
    second, _ = predict_portfolio_quantiles(augmented, models, metadata, 0.75, 100.0)
    assert np.allclose(first[["p10_cf", "p50_cf", "p90_cf"]], second[["p10_cf", "p50_cf", "p90_cf"]])
def test_probabilistic_share_grid_is_explicit() -> None:
    models, metadata = load_probabilistic_bundle(MODEL, METADATA)
    predict_portfolio_quantiles(_latest(), models, metadata, 0.55, 100.0)
    with pytest.raises(KeyError):
        predict_portfolio_quantiles(_latest(), models, metadata, 0.53, 100.0)


def test_stage14_locked_evidence_is_calibrated_and_auditable() -> None:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    assert summary["selected_candidate"]["name"] == "qD"
    assert summary["mix_grid_rows"] == 21
    mixed = summary["locked_reference"]["mixed_50_50"]
    assert 78.0 <= mixed["observed_p10_p90_coverage_pct"] <= 88.0
    assert mixed["mean_p10_p90_width_cf"] > 0
    comparison = json.loads(COMPARISON.read_text(encoding="utf-8"))
    assert comparison["old_method"].startswith("rolling 180-day")
    assert comparison["by_wind_share"]["0.50"]["days"] == 90


def test_repair_quantiles_is_target_independent() -> None:
    low, median, high = repair_quantiles(
        np.array([0.7, 0.1]), np.array([0.5, 0.4]), np.array([0.3, 0.9])
    )
    assert np.all(low <= median)
    assert np.all(median <= high)
