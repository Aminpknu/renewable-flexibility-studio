import pandas as pd

from engine.project_finance import ProjectFinanceAssumptions
from engine.project_finance_monte_carlo import (
    ProjectFinanceMonteCarloConfig,
    run_project_finance_monte_carlo,
)


def test_project_finance_monte_carlo_is_reproducible_and_reports_lender_risk() -> None:
    daily = pd.DataFrame({
        "settlement_date": pd.date_range("2026-01-01", periods=30, freq="D"),
        "market_value_gbp": [2_000.0 + 100.0 * (i % 5) for i in range(30)],
    })
    assumptions = ProjectFinanceAssumptions(
        total_capex_gbp=1_000_000.0, fixed_opex_gbp_per_year=100_000.0,
        asset_life_years=10, debt_fraction=0.6, debt_interest_rate=0.06,
        debt_tenor_years=7, corporation_tax_rate=0.25,
        capital_allowance_remaining_years=7,
    )
    cfg = ProjectFinanceMonteCarloConfig(simulations=20, seed=7, sample_days=30, block_days=3)
    first, first_summary = run_project_finance_monte_carlo(daily, "market_value_gbp", assumptions, cfg)
    second, second_summary = run_project_finance_monte_carlo(daily, "market_value_gbp", assumptions, cfg)
    assert first.equals(second)
    assert first_summary == second_summary
    assert 0 <= first_summary["probability_dscr_breach_pct"] <= 100
    assert 0 <= first_summary["probability_equity_irr_below_hurdle_pct"] <= 100
    assert first_summary["npv_p10_gbp"] <= first_summary["npv_p50_gbp"] <= first_summary["npv_p90_gbp"]
