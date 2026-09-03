import math

import pytest

from engine.project_finance import ProjectFinanceAssumptions, appraise_project_finance


def test_debt_schedule_amortises_and_tax_shield_is_nonnegative() -> None:
    assumptions = ProjectFinanceAssumptions(
        total_capex_gbp=1_000.0,
        fixed_opex_gbp_per_year=50.0,
        asset_life_years=5,
        project_discount_rate=0.08,
        annual_revenue_degradation_fraction=0.0,
        debt_fraction=0.60,
        debt_interest_rate=0.06,
        debt_tenor_years=3,
        corporation_tax_rate=0.25,
        capital_allowance_year1_fraction=0.0,
        capital_allowance_remaining_years=3,
        equity_hurdle_rate=0.12,
        dscr_threshold=1.2,
    )
    result = appraise_project_finance(500.0, assumptions)
    assert result["debt_amount_gbp"] == pytest.approx(600.0)
    assert result["initial_equity_gbp"] == pytest.approx(400.0)
    assert result["yearly_schedule"][2]["debt_closing_gbp"] == pytest.approx(0.0, abs=1e-8)
    assert all(row["cash_tax_after_interest_gbp"] <= row["unlevered_tax_gbp"] + 1e-9 for row in result["yearly_schedule"])
    assert result["minimum_dscr"] > 0
    assert result["llcr"] > 0


def test_zero_tax_unlevered_cashflow_matches_simple_case() -> None:
    assumptions = ProjectFinanceAssumptions(
        total_capex_gbp=200.0, fixed_opex_gbp_per_year=10.0,
        asset_life_years=3, project_discount_rate=0.0,
        annual_revenue_degradation_fraction=0.0,
        debt_fraction=0.0, debt_interest_rate=0.0, debt_tenor_years=1,
        corporation_tax_rate=0.0, capital_allowance_year1_fraction=1.0,
        capital_allowance_remaining_years=0, equity_hurdle_rate=0.0,
    )
    result = appraise_project_finance(100.0, assumptions)
    assert result["project_npv_gbp"] == pytest.approx(70.0)
    assert result["equity_npv_gbp"] == pytest.approx(70.0)
    assert math.isinf(result["llcr"])
