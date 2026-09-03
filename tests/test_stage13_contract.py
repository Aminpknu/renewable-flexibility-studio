import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "multiservice"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_stage13_manifest_hashes_and_boundaries() -> None:
    manifest = json.loads((OUT / "stage13_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stage"] == "13_issue_time_multiservice_acceptance_calibrated"
    assert manifest["identity_fields_retained"] is False
    assert manifest["raw_sell_order_archives_committed"] is False
    for relative, expected in manifest["evidence_files"].items():
        assert _sha256(ROOT / relative) == expected
def test_stage13_strategy_reference_values() -> None:
    summary = json.loads((OUT / "stage13_issue_time_multiservice_summary.json").read_text(encoding="utf-8"))
    assert summary["calendar_days"] == 61
    assert summary["eligible_days"] == 60
    assert summary["excluded_calendar_dates"] == ["2026-06-24"]
    non_bm = summary["scenarios"]["non_bm"]
    assert non_bm["annualised_acceptance_calibrated_total_gbp"] == pytest.approx(2_223_233.3563, rel=1e-8)
    assert non_bm["capture_vs_stage11_perfect_information_pct"] == pytest.approx(47.9239, rel=1e-5)
    assert non_bm["incremental_value_vs_reserve_aware_wholesale_gbp_per_year"] > 1_000_000
    assert summary["realised_information_used_only_for_scoring"] == [
        "APX Market Index price", "EAC system clearing price and system cleared volume"
    ]


def test_stage13_price_and_acceptance_evidence() -> None:
    price = json.loads((OUT / "stage13_price_forecast_summary.json").read_text(encoding="utf-8"))
    acceptance = json.loads((OUT / "stage13_acceptance_summary.json").read_text(encoding="utf-8"))
    assert price["days"] == 61
    assert price["mae_improvement_vs_naive_pct"] > 10.0
    assert acceptance["identity_fields_retained"] is False
    assert acceptance["validation"]["orders"] == 514_583
    assert acceptance["validation"]["brier_improvement_vs_product_baseline_pct"] > 20.0
    offers = pd.read_csv(OUT / "stage13_issue_time_multiservice_offers.csv")
    assert offers["predicted_acceptance_ratio_at_bid_time"].between(0.0, 1.0).all()
    assert (offers["acceptance_calibrated_expected_accepted_mw"] <= offers["contracted_mw"] + 1e-9).all()
    assert not {"auctionUnit", "registeredAuctionParticipant"}.intersection(offers.columns)
