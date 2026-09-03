"""Generate compact Stage 6B downside-risk evidence for the default mixed portfolio."""

from __future__ import annotations

import json
from pathlib import Path

from adapters.forecast_data import load_historical_predictions
from engine.battery import BatteryConfig
from engine.monte_carlo import (
    MonteCarloConfig,
    build_daily_value_evidence,
    run_value_monte_carlo,
)
from engine.portfolio import build_virtual_portfolio
from engine.stress import run_value_stress_scenarios
from engine.value import ValueAssumptions

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "outputs" / "risk_value" / "stage6b_default_summary.json"


def _assumptions(scale: float = 1.0) -> ValueAssumptions:
    return ValueAssumptions(
        consequence_value_gbp_per_mwh=100.0,
        total_capex_gbp=25_000_000.0 * scale,
        fixed_opex_gbp_per_year=500_000.0 * scale,
        variable_opex_gbp_per_mwh=2.0,
        asset_life_years=15,
        discount_rate=0.08,
        annual_degradation_fraction=0.02,
    )


def _mc_config(simulations: int) -> MonteCarloConfig:
    return MonteCarloConfig(
        simulations=simulations,
        seed=20260903,
        sample_days=365,
        block_days=7,
        confidence=0.95,
        firming_target_pct=90.0,
        reliability_target_pct=90.0,
    )


def main() -> None:
    history = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")
    portfolio = build_virtual_portfolio(
        history, portfolio_type="mixed", capacity_mw=100.0, wind_share=0.5
    )
    comparison = {}
    selected_evidence = None
    for duration in (2.0, 4.0, 8.0):
        battery = BatteryConfig(power_mw=25.0, duration_hours=duration, initial_soc_fraction=0.50)
        evidence = build_daily_value_evidence(portfolio, battery)
        scale = battery.energy_capacity_mwh / 200.0
        _draws, summary = run_value_monte_carlo(
            evidence, _assumptions(scale), _mc_config(2000)
        )
        comparison[f"25mw_{int(duration)}h"] = summary
        if duration == 8.0:
            selected_evidence = evidence

    assert selected_evidence is not None
    _draws_1000, summary_1000 = run_value_monte_carlo(
        selected_evidence, _assumptions(), _mc_config(1000)
    )
    _draws_5000, summary_5000 = run_value_monte_carlo(
        selected_evidence, _assumptions(), _mc_config(5000)
    )
    convergence = {}
    for key in ("npv_p10_gbp", "npv_p50_gbp", "npv_p90_gbp", "cvar_expected_shortfall_gbp"):
        base = float(summary_5000[key])
        convergence[f"{key}_relative_difference_pct_1000_vs_5000"] = (
            100.0 * abs(float(summary_1000[key]) - base) / max(abs(base), 1.0)
        )

    annualisation = 365.25 / len(selected_evidence)
    expected_availability = 0.95
    annual_avoided = float(selected_evidence["avoided_exposure_mwh"].sum()) * annualisation * expected_availability
    annual_throughput = float(selected_evidence["throughput_mwh"].sum()) * annualisation * expected_availability
    stress = run_value_stress_scenarios(annual_avoided, annual_throughput, _assumptions())

    payload = {
        "schema_version": "1.0",
        "stage": "6B_quantitative_downside_risk",
        "portfolio": {"type": "mixed", "capacity_mw": 100.0, "wind_share_pct": 50.0},
        "selected_design": {"power_mw": 25.0, "duration_hours": 8.0, "energy_mwh": 200.0},
        "resampling": "7-day contiguous circular blocks of complete historical settlement days",
        "distribution_dependence_assumption": "financial/technical multipliers sampled independently; chronological dependence retained within resampled day blocks",
        "comparison_2000_simulations": comparison,
        "selected_design_convergence": {"1000": summary_1000, "5000": summary_5000, **convergence},
        "stress_scenarios": stress.to_dict(orient="records"),
        "limitations": [
            "scenario distributions are transparent assumptions, not calibrated market distributions",
            "Monte Carlo is a pre-feasibility uncertainty analysis, not a bankable valuation",
            "parameter correlations are not yet modelled; only forecast-error temporal dependence is preserved through blocks",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    print("saved", OUTPUT)


if __name__ == "__main__":
    main()
