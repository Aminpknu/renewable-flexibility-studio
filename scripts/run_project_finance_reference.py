from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from engine.project_finance import ProjectFinanceAssumptions, appraise_project_finance
from engine.project_finance_monte_carlo import (
    ProjectFinanceMonteCarloConfig,
    run_project_finance_monte_carlo,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "project_finance"
OUT.mkdir(parents=True, exist_ok=True)
STAGE10 = json.loads((ROOT / "outputs" / "market_investment" / "market_investment_summary.json").read_text(encoding="utf-8"))
STAGE11 = json.loads((ROOT / "outputs" / "multiservice" / "multiservice_summary.json").read_text(encoding="utf-8"))
DAILY = pd.read_csv(ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_daily.csv")

DEFAULT = ProjectFinanceAssumptions(
    total_capex_gbp=25_000_000.0,
    fixed_opex_gbp_per_year=500_000.0,
    asset_life_years=15,
    project_discount_rate=0.08,
    annual_revenue_degradation_fraction=0.02,
    debt_fraction=0.60,
    debt_interest_rate=0.06,
    debt_tenor_years=10,
    corporation_tax_rate=0.25,
    capital_allowance_year1_fraction=0.0,
    capital_allowance_remaining_years=10,
    equity_hurdle_rate=0.12,
    dscr_threshold=1.20,
)

VALUES = {
    "forecast_wholesale_base": STAGE10["scenarios"]["forecast_wholesale_420d"]["annual_operating_value_gbp"],
    "reserve_aware_wholesale": STAGE10["scenarios"]["reserve_aware_wholesale_420d"]["annual_operating_value_gbp"],
    "stage11_non_bm_upside": STAGE11["scenarios"]["non_bm_multiservice"]["annualised_net_value_gbp"],
    "stage11_bm_upside": STAGE11["scenarios"]["bm_multiservice"]["annualised_net_value_gbp"],
}


def compact(result: dict) -> dict:
    return {
        "annual_operating_value_gbp": result["annual_operating_value_gbp_year1"],
        "project_npv_gbp": result["project_npv_gbp"],
        "project_irr_fraction": result["project_irr_fraction"],
        "equity_npv_gbp": result["equity_npv_gbp"],
        "equity_irr_fraction": result["equity_irr_fraction"],
        "debt_amount_gbp": result["debt_amount_gbp"],
        "annual_debt_service_gbp": result["annual_debt_service_gbp"],
        "minimum_dscr": result["minimum_dscr"],
        "llcr": result["llcr"],
        "dscr_breach_years": result["dscr_breach_years"],
        "total_interest_gbp": result["total_interest_gbp"],
        "total_cash_tax_gbp": result["total_cash_tax_gbp"],
    }


def main() -> None:
    scenarios = {name: compact(appraise_project_finance(value, DEFAULT)) for name, value in VALUES.items()}
    evidence = DAILY[["settlement_date", "forecast_strategy_margin_gbp"]].rename(
        columns={"forecast_strategy_margin_gbp": "market_value_gbp"}
    )
    draws, mc = run_project_finance_monte_carlo(
        evidence,
        "market_value_gbp",
        DEFAULT,
        ProjectFinanceMonteCarloConfig(simulations=2000, seed=20260903, sample_days=365, block_days=7),
    )
    draws.to_csv(OUT / "project_finance_monte_carlo_2000.csv", index=False)
    payload = {
        "schema_version": "1.0",
        "stage": "12_project_finance_screening",
        "default_assumptions": DEFAULT.__dict__,
        "scenarios": scenarios,
        "monte_carlo_forecast_wholesale": mc,
        "base_case_rule": "forecast-selected Stage 10 wholesale operating value is the finance base",
        "stage11_rule": "Stage 11 multi-service cases are perfect-information price-taker upside screens, not finance-base revenue",
        "tax_boundary": "simplified screening tax and user-defined allowance schedule; no tax advice or legal eligibility opinion",
        "excluded": [
            "tax-loss carry-forward and group relief",
            "VAT and transaction taxes",
            "refinancing, hedging and sculpted debt",
            "working capital and reserve accounts",
            "asset-specific ancillary-service bid acceptance",
        ],
    }
    (OUT / "project_finance_summary.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"scenarios": scenarios, "mc": mc}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
