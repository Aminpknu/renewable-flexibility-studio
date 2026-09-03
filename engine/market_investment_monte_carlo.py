"""Block-resampled market-backed BESS investment Monte Carlo."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .market_investment import MarketInvestmentAssumptions, appraise_market_operating_value
from .monte_carlo import TriangularMultiplier, contiguous_block_bootstrap_indices
from .tail_risk import summarise_npv_distribution


@dataclass(frozen=True)
class MarketInvestmentMonteCarloConfig:
    simulations: int = 2000
    seed: int = 20260903
    sample_days: int = 365
    block_days: int = 7
    confidence: float = 0.95

    def __post_init__(self) -> None:
        if self.simulations <= 0 or self.sample_days <= 0 or self.block_days <= 0:
            raise ValueError("Market Monte Carlo counts must be positive.")
        if not 0 < self.confidence < 1:
            raise ValueError("Market Monte Carlo confidence must lie in (0, 1).")


@dataclass(frozen=True)
class MarketInvestmentDistributions:
    capex_multiplier: TriangularMultiplier = TriangularMultiplier(0.85, 1.00, 1.20)
    fixed_opex_multiplier: TriangularMultiplier = TriangularMultiplier(0.90, 1.00, 1.15)
    availability_fraction: TriangularMultiplier = TriangularMultiplier(0.90, 0.95, 1.00)
    degradation_multiplier: TriangularMultiplier = TriangularMultiplier(0.75, 1.00, 1.25)


def run_market_investment_monte_carlo(
    daily_market_value: pd.DataFrame,
    value_column: str,
    base_assumptions: MarketInvestmentAssumptions,
    config: MarketInvestmentMonteCarloConfig | None = None,
    distributions: MarketInvestmentDistributions | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Resample contiguous historical day blocks and propagate investment assumptions."""
    cfg = config or MarketInvestmentMonteCarloConfig()
    dist = distributions or MarketInvestmentDistributions()
    required = {"settlement_date", value_column}
    missing = sorted(required.difference(daily_market_value.columns))
    if missing:
        raise ValueError(f"Daily market evidence is missing columns: {missing}")
    if daily_market_value.empty:
        raise ValueError("Daily market evidence is empty.")
    work = daily_market_value.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"], errors="raise").dt.normalize()
    work[value_column] = pd.to_numeric(work[value_column], errors="raise")
    if not np.isfinite(work[value_column].to_numpy(float)).all():
        raise ValueError("Daily market values must be finite.")
    work = work.groupby("settlement_date", as_index=False)[value_column].sum().sort_values("settlement_date")
    rng = np.random.default_rng(cfg.seed)
    rows: list[dict[str, float | int]] = []
    values = work[value_column].to_numpy(float)
    for simulation in range(cfg.simulations):
        indexes = contiguous_block_bootstrap_indices(
            len(values), cfg.sample_days, cfg.block_days, rng
        )
        sampled = values[indexes]
        availability = dist.availability_fraction.sample(rng)
        online = rng.random(cfg.sample_days) < availability
        annual_value = float(sampled[online].sum())
        capex_multiplier = dist.capex_multiplier.sample(rng)
        fixed_opex_multiplier = dist.fixed_opex_multiplier.sample(rng)
        degradation_multiplier = dist.degradation_multiplier.sample(rng)
        assumptions = MarketInvestmentAssumptions(
            total_capex_gbp=base_assumptions.total_capex_gbp * capex_multiplier,
            fixed_opex_gbp_per_year=(
                base_assumptions.fixed_opex_gbp_per_year * fixed_opex_multiplier
            ),
            asset_life_years=base_assumptions.asset_life_years,
            discount_rate=base_assumptions.discount_rate,
            annual_revenue_degradation_fraction=min(
                base_assumptions.annual_revenue_degradation_fraction
                * degradation_multiplier,
                0.999999,
            ),
            replacement_year=base_assumptions.replacement_year,
            replacement_cost_gbp=(
                base_assumptions.replacement_cost_gbp * capex_multiplier
            ),
        )
        appraisal = appraise_market_operating_value(annual_value, assumptions)
        rows.append({
            "simulation": simulation + 1,
            "annual_market_value_gbp": annual_value,
            "availability_fraction": availability,
            "realised_available_days": int(online.sum()),
            "capex_multiplier": capex_multiplier,
            "fixed_opex_multiplier": fixed_opex_multiplier,
            "degradation_multiplier": degradation_multiplier,
            "npv_gbp": float(appraisal["npv_gbp"]),
            "benefit_cost_ratio": float(appraisal["benefit_cost_ratio"]),
        })
    results = pd.DataFrame(rows)
    summary = summarise_npv_distribution(
        results["npv_gbp"].to_numpy(float), confidence=cfg.confidence
    )
    annual_values = results["annual_market_value_gbp"].to_numpy(float)
    summary.update({
        "seed": int(cfg.seed),
        "sample_days": int(cfg.sample_days),
        "block_days": int(cfg.block_days),
        "resampling": "contiguous circular blocks of realised forecast-selected daily market value",
        "availability_model": "simulation-level availability rate with independent daily online draws",
        "annual_market_value_p10_gbp": float(np.quantile(annual_values, 0.10)),
        "annual_market_value_p50_gbp": float(np.quantile(annual_values, 0.50)),
        "annual_market_value_p90_gbp": float(np.quantile(annual_values, 0.90)),
        "mean_annual_market_value_gbp": float(annual_values.mean()),
        "probability_negative_annual_market_value_pct": float(
            100.0 * np.mean(annual_values < 0.0)
        ),
    })
    return results, summary
