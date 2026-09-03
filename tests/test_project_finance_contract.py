import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_project_finance_reference_artifacts() -> None:
    summary = json.loads(
        (ROOT / "outputs" / "project_finance" / "project_finance_summary.json").read_text(encoding="utf-8")
    )
    draws = pd.read_csv(
        ROOT / "outputs" / "project_finance" / "project_finance_monte_carlo_2000.csv"
    )
    assert summary["stage"] == "12_project_finance_screening"
    assert summary["base_case_rule"].startswith("forecast-selected Stage 10")
    assert "perfect-information" in summary["stage11_rule"]
    assert len(draws) == 2000
    assert {"project_npv_gbp", "equity_npv_gbp", "minimum_dscr", "llcr"}.issubset(draws.columns)
