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


def test_reserve_planning_validation_artifact() -> None:
    import pandas as pd

    summary = json.loads(
        (ROOT / "outputs" / "reserve_planning_validation.json").read_text(encoding="utf-8")
    )
    daily = pd.read_csv(ROOT / "outputs" / "reserve_planning_daily.csv")
    assert summary["schema_version"] == "1.0"
    assert summary["method"] == "minimum_adjustment_to_directional_reserve_safe_soc_band"
    assert summary["current_soc_baseline_pct"] == 50.0
    assert set(summary["summaries"]) == {"solar", "mixed", "wind"}
    assert len(daily) == 1260
    assert daily.groupby("portfolio_type")["settlement_date"].nunique().to_dict() == {
        "mixed": 420, "solar": 420, "wind": 420
    }
    mixed = summary["summaries"]["mixed"]
    assert mixed["selected_design"]["energy_mwh"] == 200.0
    assert mixed["all_eligible"]["adjustment_days"] == 0
    assert mixed["locked_test"]["mean_directional_interval_coverage_pct"] > 80.0
    wind = summary["summaries"]["wind"]
    assert wind["all_eligible"]["infeasible_safe_band_days"] > 0
