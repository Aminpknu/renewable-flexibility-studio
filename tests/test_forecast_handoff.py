from __future__ import annotations

import pandas as pd
import pytest

from engine.forecast_handoff import assess_forecast_freshness, validate_national_forecast


def _frame(target="2026-09-03") -> pd.DataFrame:
    return pd.DataFrame({
        "forecast_created_utc": ["2026-09-02T10:20:51Z"] * 48,
        "target_date": [target] * 48,
        "settlement_period": range(1, 49),
        "valid_time_utc": pd.date_range(f"{target}T00:00:00Z", periods=48, freq="30min"),
        "wind_pred_cf": [0.4] * 48,
        "wind_forecast_mw": [10000.0] * 48,
        "solar_pred_cf": [0.2] * 48,
        "solar_forecast_mw": [4000.0] * 48,
    })


def test_national_handoff_contract() -> None:
    meta = validate_national_forecast(_frame())
    assert meta["target_date"] == "2026-09-03"
    assert meta["period_count"] == 48


def test_handoff_rejects_incomplete_period_set() -> None:
    with pytest.raises(ValueError, match="46, 48 or 50"):
        validate_national_forecast(_frame().iloc[:-1].copy())

def test_handoff_rejects_duplicate_periods() -> None:
    frame = _frame()
    frame.loc[1, "settlement_period"] = 1
    with pytest.raises(ValueError, match="complete and sequential"):
        validate_national_forecast(frame)


def test_freshness_status_is_explicit() -> None:
    meta = validate_national_forecast(_frame())
    current = assess_forecast_freshness(meta, now_utc=pd.Timestamp("2026-09-03T12:00:00Z"))
    stale = assess_forecast_freshness(meta, now_utc=pd.Timestamp("2026-09-04T12:00:00Z"))
    assert current["status"] == "CURRENT"
    assert stale["status"] == "STALE_TARGET"

def test_bundle_selection_falls_back_on_bad_latest_checksum(tmp_path) -> None:
    import json
    from engine.forecast_handoff import select_forecast_bundle, sha256_file

    latest = tmp_path / "latest.csv"
    fallback = tmp_path / "fallback.csv"
    latest_manifest = tmp_path / "latest.json"
    fallback_manifest = tmp_path / "fallback.json"
    _frame().to_csv(latest, index=False)
    _frame().to_csv(fallback, index=False)
    base = {"target_date": "2026-09-03", "row_count": 48}
    latest_manifest.write_text(json.dumps({**base, "sha256": "bad"}), encoding="utf-8")
    fallback_manifest.write_text(json.dumps({**base, "sha256": sha256_file(fallback)}), encoding="utf-8")
    selected, _, status = select_forecast_bundle(latest, latest_manifest, fallback, fallback_manifest)
    assert selected == fallback
    assert status == "FALLBACK"