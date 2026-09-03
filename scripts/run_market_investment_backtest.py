"""Generate market-backed BESS investment and downside-risk evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from engine.market_investment import (
    MarketInvestmentAssumptions,
    appraise_market_operating_value,
    maximum_capex_for_market_zero_npv_gbp,
    minimum_annual_market_value_for_zero_npv_gbp,
)
from engine.market_investment_monte_carlo import (
    MarketInvestmentMonteCarloConfig,
    run_market_investment_monte_carlo,
)

ROOT = Path(__file__).resolve().parents[1]
MARKET_DAILY = pd.read_csv(
    ROOT / "outputs" / "market_optimisation" / "pre_delivery_strategy_daily.csv"
)
QR_DAILY = pd.read_csv(
    ROOT / "outputs" / "quick_reserve" / "quick_reserve_predelivery_daily.csv"
)
OUTPUT_DIR = ROOT / "outputs" / "market_investment"
ASSUMPTIONS = MarketInvestmentAssumptions(
    total_capex_gbp=25_000_000.0,
    fixed_opex_gbp_per_year=500_000.0,
    asset_life_years=15,
    discount_rate=0.08,
    annual_revenue_degradation_fraction=0.02,
)


def _annualise(series: pd.Series) -> float:
    return float(series.sum() * 365.25 / len(series))


def _scenario(name: str, annual_value: float) -> dict:
    appraisal = appraise_market_operating_value(annual_value, ASSUMPTIONS)
    return {
        "scenario": name,
        "annual_operating_value_gbp": annual_value,
        "npv_gbp": appraisal["npv_gbp"],
        "benefit_cost_ratio": appraisal["benefit_cost_ratio"],
        "simple_payback_years": appraisal["simple_payback_years"],
        "pv_market_value_gbp": appraisal["pv_market_value_gbp"],
        "pv_total_cost_gbp": appraisal["pv_total_cost_gbp"],
        "maximum_capex_for_zero_npv_gbp": maximum_capex_for_market_zero_npv_gbp(
            annual_value, ASSUMPTIONS
        ),
        "minimum_annual_market_value_for_zero_npv_gbp": (
            minimum_annual_market_value_for_zero_npv_gbp(ASSUMPTIONS)
        ),
    }


def main() -> None:
    market = MARKET_DAILY.copy()
    market["settlement_date"] = pd.to_datetime(market["settlement_date"])
    qr = QR_DAILY.copy()
    qr["settlement_date"] = pd.to_datetime(qr["settlement_date"])
    locked = market.loc[market["evaluation_segment"].eq("locked_test")].copy()
    base_annual = _annualise(market["forecast_strategy_margin_gbp"])
    reserve_annual = _annualise(market["reserve_aware_forecast_margin_gbp"])
    locked_market_annual = _annualise(locked["forecast_strategy_margin_gbp"])
    locked_reserve_annual = _annualise(locked["reserve_aware_forecast_margin_gbp"])
    qr_annual = _annualise(qr["forecast_selected_qr_availability_gbp"])
    aligned_market_qr_annual = locked_market_annual + qr_annual
    aligned_reserve_qr_annual = locked_reserve_annual + qr_annual
    scenarios = {
        "forecast_wholesale_420d": _scenario("Forecast-selected wholesale · 420-day evidence", base_annual),
        "reserve_aware_wholesale_420d": _scenario("Reserve-aware wholesale · 420-day evidence", reserve_annual),
        "locked_forecast_wholesale_90d": _scenario("Forecast-selected wholesale · Apr-Jun regime", locked_market_annual),
        "aligned_wholesale_plus_qr_90d": _scenario("Wholesale + QR price-taker upside · Apr-Jun aligned", aligned_market_qr_annual),
        "aligned_reserve_plus_qr_90d": _scenario("Reserve-aware wholesale + QR price-taker upside · Apr-Jun aligned", aligned_reserve_qr_annual),
    }
    mc_input = market[["settlement_date", "forecast_strategy_margin_gbp"]].rename(
        columns={"forecast_strategy_margin_gbp": "market_value_gbp"}
    )
    reserve_mc_input = market[["settlement_date", "reserve_aware_forecast_margin_gbp"]].rename(
        columns={"reserve_aware_forecast_margin_gbp": "market_value_gbp"}
    )
    convergence = {}
    draws_5000 = None
    for simulations in (1000, 5000):
        draws, summary = run_market_investment_monte_carlo(
            mc_input,
            "market_value_gbp",
            ASSUMPTIONS,
            MarketInvestmentMonteCarloConfig(
                simulations=simulations,
                seed=20260903,
                sample_days=365,
                block_days=7,
                confidence=0.95,
            ),
        )
        convergence[str(simulations)] = summary
        if simulations == 5000:
            draws_5000 = draws
    _reserve_draws, reserve_summary = run_market_investment_monte_carlo(
        reserve_mc_input,
        "market_value_gbp",
        ASSUMPTIONS,
        MarketInvestmentMonteCarloConfig(
            simulations=2000, seed=20260903, sample_days=365, block_days=7
        ),
    )
    conv_metrics = {}
    for key in (
        "npv_p10_gbp", "npv_p50_gbp", "npv_p90_gbp",
        "cvar_expected_shortfall_gbp", "annual_market_value_p50_gbp",
    ):
        a = float(convergence["1000"][key])
        b = float(convergence["5000"][key])
        denom = max(abs(b), 1.0)
        conv_metrics[f"{key}_relative_difference_pct_1000_vs_5000"] = float(
            100.0 * abs(a - b) / denom
        )
    payload = {
        "schema_version": "1.0",
        "stage": "10_market_backed_investment",
        "battery": {"power_mw": 25.0, "energy_mwh": 200.0, "duration_hours": 8.0},
        "market_evidence": {
            "base_days": int(len(market)),
            "locked_days": int(len(locked)),
            "throughput_cost_already_embedded_gbp_per_mwh": 2.0,
            "base_source": "realised value of forecast-selected APX Market Index schedule",
            "reserve_source": "realised value of reserve-aware forecast-selected APX schedule",
            "qr_source": "forecast-selected QR capacity under system-volume-capped price-taker scoring",
        },
        "assumptions": {
            "total_capex_gbp": ASSUMPTIONS.total_capex_gbp,
            "fixed_opex_gbp_per_year": ASSUMPTIONS.fixed_opex_gbp_per_year,
            "asset_life_years": ASSUMPTIONS.asset_life_years,
            "discount_rate_pct": 100.0 * ASSUMPTIONS.discount_rate,
            "annual_revenue_degradation_pct": 100.0 * ASSUMPTIONS.annual_revenue_degradation_fraction,
            "replacement_year": ASSUMPTIONS.replacement_year,
            "replacement_cost_gbp": ASSUMPTIONS.replacement_cost_gbp,
        },
        "scenarios": scenarios,
        "monte_carlo_forecast_wholesale": convergence["5000"],
        "monte_carlo_reserve_aware_wholesale": reserve_summary,
        "convergence": conv_metrics,
        "limitations": [
            "market operating value is a forecast-selected APX Market Index benchmark, not licensed day-ahead auction revenue",
            "daily market evidence already includes the frozen £2/MWh throughput-cost assumption",
            "QR is shown only in deterministic Apr-Jun aligned price-taker upside scenarios and is excluded from the base Monte Carlo",
            "QR asset-specific auction acceptance remains unidentified",
            "CAPEX, fixed OPEX, lifetime, discount rate and degradation are transparent screening assumptions",
            "tax, financing, transaction costs, grid-connection charges and site-specific constraints are excluded",
        ],
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "market_investment_summary.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )
    if draws_5000 is not None:
        draws_5000.to_csv(
            OUTPUT_DIR / "market_investment_monte_carlo_5000.csv", index=False
        )
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
