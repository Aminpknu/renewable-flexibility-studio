from __future__ import annotations

import numpy as np
import pandas as pd

from engine.market_investment import MarketInvestmentAssumptions
from engine.market_investment_monte_carlo import (
    MarketInvestmentMonteCarloConfig,
    run_market_investment_monte_carlo,
)


def _daily(days: int = 30) -> pd.DataFrame:
    return pd.DataFrame({
        "settlement_date": pd.date_range("2026-01-01", periods=days, freq="D"),
        "market_value_gbp": np.linspace(-100.0, 500.0, days),
    })


def test_market_investment_monte_carlo_is_seed_reproducible() -> None:
    assumptions = MarketInvestmentAssumptions(
        total_capex_gbp=1_000_000.0,
        fixed_opex_gbp_per_year=20_000.0,
        asset_life_years=10,
        discount_rate=0.05,
        annual_revenue_degradation_fraction=0.01,
    )
    config = MarketInvestmentMonteCarloConfig(
        simulations=40, seed=123, sample_days=30, block_days=3
    )
    first, first_summary = run_market_investment_monte_carlo(
        _daily(), "market_value_gbp", assumptions, config
    )
    second, second_summary = run_market_investment_monte_carlo(
        _daily(), "market_value_gbp", assumptions, config
    )
    pd.testing.assert_frame_equal(first, second)
    assert first_summary == second_summary


def test_market_monte_carlo_reports_value_and_tail_metrics() -> None:
    assumptions = MarketInvestmentAssumptions(
        total_capex_gbp=100_000.0,
        fixed_opex_gbp_per_year=5_000.0,
        asset_life_years=5,
        discount_rate=0.05,
        annual_revenue_degradation_fraction=0.01,
    )
    results, summary = run_market_investment_monte_carlo(
        _daily(), "market_value_gbp", assumptions,
        MarketInvestmentMonteCarloConfig(
            simulations=30, seed=9, sample_days=30, block_days=2
        ),
    )
    assert len(results) == 30
    assert "npv_p10_gbp" in summary
    assert "cvar_expected_shortfall_gbp" in summary
    assert "annual_market_value_p50_gbp" in summary
    assert summary["loss_convention"] == "investment_loss_gbp = -NPV_gbp"
    assert results["realised_available_days"].between(0, 30).all()
