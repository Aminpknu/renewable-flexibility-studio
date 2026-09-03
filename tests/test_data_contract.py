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


def test_stage6b_default_summary_artifact() -> None:
    summary = json.loads(
        (ROOT / "outputs" / "risk_value" / "stage6b_default_summary.json").read_text(encoding="utf-8")
    )
    assert summary["schema_version"] == "1.0"
    assert summary["stage"] == "6B_quantitative_downside_risk"
    assert summary["selected_design"]["energy_mwh"] == 200.0
    comparison = summary["comparison_2000_simulations"]
    assert set(comparison) == {"25mw_2h", "25mw_4h", "25mw_8h"}
    assert comparison["25mw_8h"]["loss_convention"] == "investment_loss_gbp = -NPV_gbp"
    assert comparison["25mw_2h"]["probability_failing_firming_gate_pct"] == 100.0
    assert 0 <= comparison["25mw_8h"]["probability_failing_firming_gate_pct"] <= 100
    convergence = summary["selected_design_convergence"]
    relative = [float(value) for key, value in convergence.items() if "relative_difference_pct" in key]
    assert relative and max(relative) < 2.0
    stress_names = {row["scenario"] for row in summary["stress_scenarios"]}
    assert {"poor_forecast_accuracy", "derating_availability_loss", "adverse_cost_value", "combined_downside"}.issubset(stress_names)


def test_elexon_market_index_archive_integrity() -> None:
    import hashlib
    import pandas as pd

    csv_path = ROOT / "data" / "elexon_market_index_prices.csv"
    manifest = json.loads(
        (ROOT / "data" / "elexon_market_index_prices_manifest.json").read_text(encoding="utf-8")
    )
    frame = pd.read_csv(csv_path)
    assert manifest["schema_version"] == "1.0"
    assert manifest["data_provider"] == "APXMIDP"
    assert manifest["target_days"] == 450
    assert manifest["rows"] == 21600
    assert "not day-ahead" in manifest["semantic_label"]
    assert len(frame) == 21600
    assert frame["settlement_date"].nunique() == 450
    assert not frame.duplicated(["settlement_date", "settlement_period", "market_index_provider"]).any()
    canonical = csv_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["sha256"]


def test_market_optimisation_evidence_artifact() -> None:
    import pandas as pd

    summary = json.loads(
        (ROOT / "outputs" / "market_optimisation" / "default_mixed_summary.json")
        .read_text(encoding="utf-8")
    )
    daily = pd.read_csv(
        ROOT / "outputs" / "market_optimisation" / "default_mixed_daily.csv"
    )
    assert summary["schema_version"] == "1.0"
    assert summary["stage"] == "9_market_optimisation_packet1"
    assert summary["perfect_information"] is True
    assert summary["observed_days"] == 450
    assert "not day-ahead" in summary["market_reference"]["semantic_label"]
    assert len(daily) == 450
    assert daily["settlement_date"].nunique() == 450
    assert summary["cooptimised_total_net_value_gbp"] >= (
        summary["arbitrage_total_net_margin_gbp"] - 1e-5
    )
    assert summary["mean_daily_error_reduction_pct_reactive"] > (
        summary["mean_daily_error_reduction_pct_market_aware"]
    )


def test_pre_delivery_market_strategy_artifacts() -> None:
    import pandas as pd
    price = pd.read_csv(ROOT / "outputs" / "market_optimisation" / "price_forecast_backtest.csv")
    daily = pd.read_csv(ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_daily.csv")
    summary = json.loads(
        (ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_summary.json").read_text(encoding="utf-8")
    )
    assert price["settlement_date"].nunique() == 420
    assert len(price) == 20160
    assert len(daily) == 420
    assert summary["price_forecast"]["issue_rule"] == "strictly earlier settlement dates only"
    assert 50.0 < summary["forecast_capture_rate_pct"] < 70.0
    assert summary["reserve_corridor_feasible_days_pct"] == 100.0
    assert summary["locked_test"]["days"] == 90


def test_latest_market_price_forecast_is_labelled_by_actual_issue_timing() -> None:
    import pandas as pd
    frame = pd.read_csv(ROOT / "data" / "latest_market_price_forecast.csv")
    manifest = json.loads((ROOT / "data" / "latest_market_price_forecast_manifest.json").read_text(encoding="utf-8"))
    assert len(frame) in {46, 48, 50}
    assert frame["settlement_date"].nunique() == 1
    assert manifest["method"]["uses_target_date_prices"] is False
    assert manifest["method"]["issue_rule"].endswith("strictly earlier than target date")
    assert manifest["operational_status"] in {"pre_delivery_issue", "as_if_reconstruction_after_target_start"}
    assert manifest["semantic_label"].endswith("not day-ahead auction price")


def test_operational_market_forecast_pipeline_artifacts() -> None:
    import hashlib

    csv_path = ROOT / "data" / "latest_market_price_forecast.csv"
    manifest = json.loads(
        (ROOT / "data" / "latest_market_price_forecast_manifest.json").read_text(encoding="utf-8")
    )
    status = json.loads(
        (ROOT / "data" / "market_forecast_pipeline_status.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == "1.1"
    assert manifest["row_count"] in {46, 48, 50}
    canonical = csv_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["sha256"]
    assert status["pipeline_status"] in {
        "PUBLISHED", "RETAINED_PRE_DELIVERY_BUNDLE", "FALLBACK_RETAINED",
        "FALLBACK_RESTORED", "RENEWABLE_TARGET_STALE",
    }
    assert status["bundle_health"]["status"] in {
        "LIVE", "RECONSTRUCTED", "STALE_TARGET", "STALE_TIME",
    }


def test_quick_reserve_archive_integrity() -> None:
    import hashlib
    import pandas as pd

    csv_path = ROOT / "data" / "neso_quick_reserve_prices.csv"
    manifest = json.loads(
        (ROOT / "data" / "neso_quick_reserve_prices_manifest.json").read_text(encoding="utf-8")
    )
    frame = pd.read_csv(csv_path)
    assert manifest["schema_version"] == "1.0"
    assert manifest["service"] == "Quick Reserve"
    assert manifest["products"] == ["PQR", "NQR"]
    assert manifest["rights"] == "NESO Open Data Licence"
    assert manifest["rows"] == 8744
    assert set(frame["product"]) == {"PQR", "NQR"}
    assert frame["window_hours"].eq(0.5).all()
    assert not frame.duplicated(["delivery_start_utc", "product"]).any()
    canonical = csv_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == manifest["sha256"]


def test_quick_reserve_stacking_evidence_artifact() -> None:
    import pandas as pd

    summary = json.loads(
        (ROOT / "outputs" / "quick_reserve" / "quick_reserve_summary.json").read_text(encoding="utf-8")
    )
    daily = pd.read_csv(ROOT / "outputs" / "quick_reserve" / "quick_reserve_daily.csv")
    assert summary["stage"] == "9_quick_reserve_availability_stacking"
    assert summary["payment_scope"] == "availability only; utilisation excluded"
    assert len(daily) == 90
    two = summary["guard_sensitivity"]["2"]
    assert two["days"] == 90
    assert two["stacked_annualised_gbp"] >= two["arbitrage_annualised_gbp"]
    assert two["naive_independent_sum_annualised_gbp"] >= two["stacked_annualised_gbp"]
    assert two["double_count_avoided_annualised_gbp"] > 0
    assert summary["guard_sensitivity"]["4"]["stacked_annualised_gbp"] <= (
        summary["guard_sensitivity"]["1"]["stacked_annualised_gbp"] + 1e-6
    )
