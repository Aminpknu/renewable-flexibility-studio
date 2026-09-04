from __future__ import annotations

import pandas as pd
import pytest

from engine.market_investment import MarketInvestmentAssumptions, appraise_market_operating_value
from engine.project_finance import ProjectFinanceAssumptions, appraise_project_finance
from engine.quality_assurance import (
    annualise_unique_daily_values,
    assure_market_investment,
    assure_project_finance,
)


def test_market_assurance_reconciles_default_style_case() -> None:
    daily = pd.DataFrame({
        "settlement_date": pd.date_range("2026-01-01", periods=4, freq="D"),
        "value": [90.0, 100.0, 110.0, 100.0],
    })
    annual = annualise_unique_daily_values(daily, "value")
    assumptions = MarketInvestmentAssumptions(
        total_capex_gbp=25_000.0,
        fixed_opex_gbp_per_year=500.0,
        asset_life_years=15,
        discount_rate=0.08,
        annual_revenue_degradation_fraction=0.02,
    )
    reported = appraise_market_operating_value(annual, assumptions)
    assurance = assure_market_investment(
        annual, assumptions, reported=reported, daily_evidence=daily, value_column="value"
    )
    assert assurance["calculation_status"] == "PASS"
    assert assurance["checks_passed"] == assurance["checks_total"]


def test_market_assurance_flags_a_wrong_reported_npv() -> None:
    assumptions = MarketInvestmentAssumptions(
        total_capex_gbp=200.0,
        fixed_opex_gbp_per_year=10.0,
        asset_life_years=3,
        discount_rate=0.0,
        annual_revenue_degradation_fraction=0.0,
    )
    reported = appraise_market_operating_value(100.0, assumptions)
    reported["npv_gbp"] += 5.0
    assurance = assure_market_investment(100.0, assumptions, reported=reported, tolerance_gbp=0.01)
    assert assurance["calculation_status"] == "FAIL"
    assert any(
        item["name"] == "Reported NPV reconciliation" and not item["passed"]
        for item in assurance["checks"]
    )


def test_daily_annualisation_rejects_duplicate_dates() -> None:
    frame = pd.DataFrame({"settlement_date": ["2026-01-01", "2026-01-01"], "value": [1.0, 2.0]})
    with pytest.raises(ValueError, match="duplicate dates"):
        annualise_unique_daily_values(frame, "value")


def test_project_finance_assurance_reconciles_cashflows_and_debt() -> None:
    assumptions = ProjectFinanceAssumptions(
        total_capex_gbp=1_000_000.0,
        fixed_opex_gbp_per_year=20_000.0,
        asset_life_years=10,
        project_discount_rate=0.08,
        annual_revenue_degradation_fraction=0.01,
        debt_fraction=0.60,
        debt_interest_rate=0.06,
        debt_tenor_years=5,
        corporation_tax_rate=0.25,
        capital_allowance_year1_fraction=0.0,
        capital_allowance_remaining_years=5,
        equity_hurdle_rate=0.12,
        dscr_threshold=1.2,
    )
    result = appraise_project_finance(250_000.0, assumptions)
    assurance = assure_project_finance(result, assumptions)
    assert assurance["calculation_status"] == "PASS"
    assert assurance["checks_passed"] == assurance["checks_total"]
    assert assurance["independent_project_npv_gbp"] == pytest.approx(result["project_npv_gbp"])
