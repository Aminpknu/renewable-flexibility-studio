import json
from pathlib import Path

import pandas as pd

from engine.regimes import build_daily_forecast_regimes, summarise_regime_range

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "historical_backtest.csv"
DAILY = ROOT / "outputs" / "regimes" / "stage15_daily_regime_evidence.csv"
MANIFEST = ROOT / "outputs" / "regimes" / "stage15_regime_manifest.json"


def test_regime_thresholds_use_development_oof_only() -> None:
    history = pd.read_csv(HISTORY)
    daily, thresholds = build_daily_forecast_regimes(history)
    assert thresholds["calibration_segment"] == "development_oof"
    assert thresholds["calibration_days"] == 360
    assert daily["settlement_date"].nunique() == 450
    assert set(daily["wind_outlook"]) <= {"Low", "Medium", "High"}
    assert set(daily["ramp_stress"]) <= {"Normal", "High-ramp"}

def test_regime_daily_contract_and_range_summary() -> None:
    daily = pd.read_csv(DAILY)
    summary = summarise_regime_range(daily, "wind_outlook", "2025-04-01", "2026-06-30")
    assert int(summary["days"].sum()) == 450
    assert set(summary["group"]) == {"Low", "Medium", "High"}
    assert summary["days_meeting_90_pct"].between(0, 100).all()
    assert summary["mean_firming_pct"].between(0, 100).all()


def test_stage15_manifest_is_explicit_about_regime_boundary() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["days"] == 450
    assert manifest["stage14_locked_days"] == 90
    assert manifest["market_days"] == 420
    assert "not formal meteorological" in manifest["boundary"]
