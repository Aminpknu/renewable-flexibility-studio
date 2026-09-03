from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "multiservice"
FILES = [
    ROOT / "data" / "neso_multiservice_forecast_history_manifest.json",
    ROOT / "data" / "neso_multiservice_acceptance_calibration_manifest.json",
    OUT / "stage13_price_forecast_summary.json",
    OUT / "stage13_price_forecast_backtest.csv",
    OUT / "stage13_acceptance_summary.json",
    OUT / "stage13_acceptance_validation.csv",
    OUT / "stage13_issue_time_multiservice_summary.json",
    OUT / "stage13_issue_time_multiservice_daily.csv",
    OUT / "stage13_issue_time_multiservice_offers.csv",
]


def sha256(path: Path) -> str:
    # Evidence files are CSV/JSON text. Canonicalise line endings so the
    # manifest is stable across Windows development and Linux CI/deploys.
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
def main() -> None:
    missing = [str(path) for path in FILES if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Stage 13 manifest inputs are missing: {missing}")
    strategy = json.loads((OUT / "stage13_issue_time_multiservice_summary.json").read_text(encoding="utf-8"))
    price = json.loads((OUT / "stage13_price_forecast_summary.json").read_text(encoding="utf-8"))
    acceptance = json.loads((OUT / "stage13_acceptance_summary.json").read_text(encoding="utf-8"))
    payload = {
        "schema_version": "1.0",
        "stage": "13_issue_time_multiservice_acceptance_calibrated",
        "evidence_files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
            for path in FILES
        },
        "headline": {
            "eligible_days": int(strategy["eligible_days"]),
            "excluded_calendar_dates": strategy["excluded_calendar_dates"],
            "non_bm_annualised_value_gbp": strategy["scenarios"]["non_bm"]["annualised_acceptance_calibrated_total_gbp"],
            "non_bm_capture_vs_stage11_pct": strategy["scenarios"]["non_bm"]["capture_vs_stage11_perfect_information_pct"],
            "price_forecast_mae": price["forecast"]["mae"],
            "price_forecast_mae_improvement_pct": price["mae_improvement_vs_naive_pct"],
            "acceptance_validation_orders": acceptance["validation"]["orders"],
            "acceptance_brier_improvement_pct": acceptance["validation"]["brier_improvement_vs_product_baseline_pct"],
        },
        "identity_fields_retained": False,
        "raw_sell_order_archives_committed": False,
    }
    (OUT / "stage13_manifest.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
