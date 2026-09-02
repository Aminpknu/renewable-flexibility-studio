import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_data_manifest_identifies_v2_out_of_sample_source() -> None:
    manifest = json.loads((ROOT / "data" / "data_manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "2.0"
    assert manifest["bundle_type"] == "out_of_sample_historical_backtest"
    assert manifest["row_count"] == 21600
    assert manifest["target_days"] == 450
    assert manifest["target_date_start"] == "2025-04-01"
    assert manifest["target_date_end"] == "2026-06-30"
    assert manifest["evaluation_segments"]["development_oof"]["days"] == 360
    assert manifest["evaluation_segments"]["locked_test"]["days"] == 90
    assert len(manifest["sha256"]) == 64
