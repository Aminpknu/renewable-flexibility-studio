from __future__ import annotations

import hashlib
import json

import pandas as pd
import pytest

from adapters.market_forecast_bundle import (
    assess_market_forecast_bundle,
    validate_market_forecast_bundle,
)


def _write_bundle(tmp_path, target="2026-09-04", created="2026-09-03T18:00:00Z"):
    frame = pd.DataFrame({
        "forecast_created_utc": [created] * 48,
        "settlement_date": [target] * 48,
        "settlement_period": range(1, 49),
        "valid_time_utc": pd.date_range("2026-09-03T23:00Z", periods=48, freq="30min"),
        "forecast_market_index_price_gbp_per_mwh": [80.0] * 48,
        "naive_market_index_price_gbp_per_mwh": [75.0] * 48,
    })
    csv_path = tmp_path / "bundle.csv"
    manifest_path = tmp_path / "bundle.json"
    text = frame.to_csv(index=False, lineterminator="\n")
    csv_path.write_text(text, encoding="utf-8", newline="")
    manifest = {
        "schema_version": "1.1",
        "target_date": target,
        "forecast_created_utc": created,
        "period_count": 48,
        "target_start_utc": "2026-09-03T23:00:00+00:00",
        "issued_before_target_start": True,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return csv_path, manifest_path


def test_market_bundle_validation_and_live_status(tmp_path) -> None:
    csv_path, manifest_path = _write_bundle(tmp_path)
    frame, manifest = validate_market_forecast_bundle(csv_path, manifest_path)
    assert len(frame) == 48
    health = assess_market_forecast_bundle(
        manifest,
        expected_target_date="2026-09-04",
        now_utc=pd.Timestamp("2026-09-03T20:00Z"),
    )
    assert health["status"] == "LIVE"
    assert health["issued_before_target_start"] is True


def test_market_bundle_reports_stale_target(tmp_path) -> None:
    csv_path, manifest_path = _write_bundle(tmp_path)
    _frame, manifest = validate_market_forecast_bundle(csv_path, manifest_path)
    health = assess_market_forecast_bundle(
        manifest,
        expected_target_date="2026-09-05",
        now_utc=pd.Timestamp("2026-09-03T20:00Z"),
    )
    assert health["status"] == "STALE_TARGET"


def test_market_bundle_rejects_checksum_mismatch(tmp_path) -> None:
    csv_path, manifest_path = _write_bundle(tmp_path)
    csv_path.write_text(csv_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum"):
        validate_market_forecast_bundle(csv_path, manifest_path)


def test_market_bundle_reports_reconstruction(tmp_path) -> None:
    csv_path, manifest_path = _write_bundle(
        tmp_path, created="2026-09-04T08:00:00Z"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["issued_before_target_start"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _frame, manifest = validate_market_forecast_bundle(csv_path, manifest_path)
    health = assess_market_forecast_bundle(
        manifest,
        expected_target_date="2026-09-04",
        now_utc=pd.Timestamp("2026-09-04T09:00Z"),
    )
    assert health["status"] == "RECONSTRUCTED"
