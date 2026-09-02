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


def test_elexon_system_price_archive_integrity() -> None:
    import hashlib
    import pandas as pd

    csv_path = ROOT / "data" / "elexon_system_prices.csv"
    manifest = json.loads(
        (ROOT / "data" / "elexon_system_prices_manifest.json").read_text(encoding="utf-8")
    )
    frame = pd.read_csv(csv_path)
    assert manifest["requested_target_days"] == 450
    assert manifest["retrieved_target_days"] == 450
    assert manifest["rows"] == 21600
    assert manifest["failures"] == {}
    assert len(frame) == 21600
    assert frame["settlement_date"].nunique() == 450
    assert not frame.duplicated(["settlement_date", "settlement_period"]).any()
    canonical = csv_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert manifest["sha256_normalisation"] == "UTF-8 text with LF line endings"
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["sha256"]
