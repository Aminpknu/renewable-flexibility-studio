import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_market_backed_investment_evidence_artifact() -> None:
    summary = json.loads(
        (ROOT / "outputs" / "market_investment" / "market_investment_summary.json")
        .read_text(encoding="utf-8")
    )
    assert summary["stage"] == "10_market_backed_investment"
    assert summary["market_evidence"]["base_days"] == 420
    assert summary["market_evidence"]["locked_days"] == 90
    assert summary["market_evidence"]["throughput_cost_already_embedded_gbp_per_mwh"] == 2.0
    base = summary["scenarios"]["forecast_wholesale_420d"]
    assert base["annual_operating_value_gbp"] > 1_000_000
    assert base["npv_gbp"] < 0
    assert base["benefit_cost_ratio"] < 1.0
    mc = summary["monte_carlo_forecast_wholesale"]
    assert mc["simulation_count"] == 5000
    assert mc["loss_convention"] == "investment_loss_gbp = -NPV_gbp"
    assert mc["probability_negative_npv_pct"] == 100.0
    relative = [
        float(value) for key, value in summary["convergence"].items()
        if "relative_difference_pct" in key
    ]
    assert relative and max(relative) < 1.0
    assert any(
        "QR" in item and "excluded" in item
        for item in summary["limitations"]
    )
