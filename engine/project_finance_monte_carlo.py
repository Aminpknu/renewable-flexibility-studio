"""Block-resampled downside simulation for the screening project-finance layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .monte_carlo import TriangularMultiplier, contiguous_block_bootstrap_indices
from .project_finance import ProjectFinanceAssumptions, appraise_project_finance
from .tail_risk import summarise_npv_distribution


@dataclass(frozen=True)
class ProjectFinanceMonteCarloConfig:
    simulations: int = 2000
    seed: int = 20260903
    sample_days: int = 365
    block_days: int = 7
    confidence: float = 0.95

    def __post_init__(self) -> None:
        if self.simulations <= 0 or self.sample_days <= 0 or self.block_days <= 0:
            raise ValueError("Project-finance Monte Carlo counts must be positive.")
        if not 0 < self.confidence < 1:
            raise ValueError("Project-finance Monte Carlo confidence must lie in (0, 1).")


@dataclass(frozen=True)
class ProjectFinanceDistributions:
    capex_multiplier: TriangularMultiplier = TriangularMultiplier(0.85, 1.00, 1.20)
    fixed_opex_multiplier: TriangularMultiplier = TriangularMultiplier(0.90, 1.00, 1.15)
    availability_fraction: TriangularMultiplier = TriangularMultiplier(0.90, 0.95, 1.00)
    degradation_multiplier: TriangularMultiplier = TriangularMultiplier(0.75, 1.00, 1.25)
    debt_rate_multiplier: TriangularMultiplier = TriangularMultiplier(0.85, 1.00, 1.25)


def _finite_quantiles(values: np.ndarray) -> tuple[float | None, float | None, float | None]:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return None, None, None
    return tuple(float(np.quantile(finite, q)) for q in (0.10, 0.50, 0.90))


def run_project_finance_monte_carlo(
    daily_market_value: pd.DataFrame,
    value_column: str,
    base: ProjectFinanceAssumptions,
    config: ProjectFinanceMonteCarloConfig | None = None,
    distributions: ProjectFinanceDistributions | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = config or ProjectFinanceMonteCarloConfig()
    dist = distributions or ProjectFinanceDistributions()
    required = {"settlement_date", value_column}
    missing = sorted(required.difference(daily_market_value.columns))
    if missing:
        raise ValueError(f"Project-finance daily evidence is missing columns: {missing}")
    work = daily_market_value.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"], errors="raise").dt.normalize()
    work[value_column] = pd.to_numeric(work[value_column], errors="raise")
    if work.empty or not np.isfinite(work[value_column].to_numpy(float)).all():
        raise ValueError("Project-finance daily market evidence must be finite and non-empty.")
    work = work.groupby("settlement_date", as_index=False)[value_column].sum().sort_values("settlement_date")
    values = work[value_column].to_numpy(float)
    rng = np.random.default_rng(cfg.seed)
    rows: list[dict[str, float | int | bool]] = []
    for simulation in range(cfg.simulations):
        indexes = contiguous_block_bootstrap_indices(len(values), cfg.sample_days, cfg.block_days, rng)
        sampled = values[indexes]
        availability = dist.availability_fraction.sample(rng)
        online = rng.random(cfg.sample_days) < availability
        annual_value = float(sampled[online].sum())
        capex_multiplier = dist.capex_multiplier.sample(rng)
        opex_multiplier = dist.fixed_opex_multiplier.sample(rng)
        degradation_multiplier = dist.degradation_multiplier.sample(rng)
        debt_rate_multiplier = dist.debt_rate_multiplier.sample(rng)
        assumptions = ProjectFinanceAssumptions(
            total_capex_gbp=base.total_capex_gbp * capex_multiplier,
            fixed_opex_gbp_per_year=base.fixed_opex_gbp_per_year * opex_multiplier,
            asset_life_years=base.asset_life_years,
            project_discount_rate=base.project_discount_rate,
            annual_revenue_degradation_fraction=min(base.annual_revenue_degradation_fraction * degradation_multiplier, 0.999999),
            debt_fraction=base.debt_fraction,
            debt_interest_rate=base.debt_interest_rate * debt_rate_multiplier,
            debt_tenor_years=base.debt_tenor_years,
            corporation_tax_rate=base.corporation_tax_rate,
            capital_allowance_year1_fraction=base.capital_allowance_year1_fraction,
            capital_allowance_remaining_years=base.capital_allowance_remaining_years,
            equity_hurdle_rate=base.equity_hurdle_rate,
            dscr_threshold=base.dscr_threshold,
            replacement_year=base.replacement_year,
            replacement_cost_gbp=base.replacement_cost_gbp * capex_multiplier,
        )
        result = appraise_project_finance(annual_value, assumptions)
        equity_irr = result["equity_irr_fraction"]
        project_irr = result["project_irr_fraction"]
        rows.append({
            "simulation": simulation + 1,
            "annual_market_value_gbp": annual_value,
            "availability_fraction": availability,
            "available_days": int(online.sum()),
            "capex_multiplier": capex_multiplier,
            "fixed_opex_multiplier": opex_multiplier,
            "degradation_multiplier": degradation_multiplier,
            "debt_rate_multiplier": debt_rate_multiplier,
            "project_npv_gbp": float(result["project_npv_gbp"]),
            "equity_npv_gbp": float(result["equity_npv_gbp"]),
            "project_irr_fraction": np.nan if project_irr is None else float(project_irr),
            "equity_irr_fraction": np.nan if equity_irr is None else float(equity_irr),
            "minimum_dscr": float(result["minimum_dscr"]),
            "llcr": float(result["llcr"]),
            "dscr_breach": bool(result["dscr_breach_years"] > 0),
            "equity_irr_below_hurdle": bool(equity_irr is None or equity_irr < base.equity_hurdle_rate),
        })
    results = pd.DataFrame(rows)
    project_tail = summarise_npv_distribution(results["project_npv_gbp"].to_numpy(float), confidence=cfg.confidence)
    equity_npv = results["equity_npv_gbp"].to_numpy(float)
    project_irr_q = _finite_quantiles(results["project_irr_fraction"].to_numpy(float))
    equity_irr_q = _finite_quantiles(results["equity_irr_fraction"].to_numpy(float))
    dscr_q = _finite_quantiles(results["minimum_dscr"].to_numpy(float))
    llcr_q = _finite_quantiles(results["llcr"].to_numpy(float))
    annual_q = _finite_quantiles(results["annual_market_value_gbp"].to_numpy(float))
    summary: dict[str, Any] = {
        **project_tail,
        "seed": int(cfg.seed),
        "simulations": int(cfg.simulations),
        "sample_days": int(cfg.sample_days),
        "block_days": int(cfg.block_days),
        "resampling": "contiguous circular blocks of realised forecast-selected daily wholesale value",
        "probability_negative_equity_npv_pct": float(100.0 * np.mean(equity_npv < 0.0)),
        "equity_npv_p10_gbp": float(np.quantile(equity_npv, 0.10)),
        "equity_npv_p50_gbp": float(np.quantile(equity_npv, 0.50)),
        "equity_npv_p90_gbp": float(np.quantile(equity_npv, 0.90)),
        "project_irr_p10_fraction": project_irr_q[0],
        "project_irr_p50_fraction": project_irr_q[1],
        "project_irr_p90_fraction": project_irr_q[2],
        "equity_irr_p10_fraction": equity_irr_q[0],
        "equity_irr_p50_fraction": equity_irr_q[1],
        "equity_irr_p90_fraction": equity_irr_q[2],
        "finite_equity_irr_pct": float(100.0 * results["equity_irr_fraction"].notna().mean()),
        "probability_equity_irr_below_hurdle_pct": float(100.0 * results["equity_irr_below_hurdle"].mean()),
        "minimum_dscr_p10": dscr_q[0],
        "minimum_dscr_p50": dscr_q[1],
        "minimum_dscr_p90": dscr_q[2],
        "probability_dscr_breach_pct": float(100.0 * results["dscr_breach"].mean()),
        "llcr_p10": llcr_q[0],
        "llcr_p50": llcr_q[1],
        "llcr_p90": llcr_q[2],
        "annual_market_value_p10_gbp": annual_q[0],
        "annual_market_value_p50_gbp": annual_q[1],
        "annual_market_value_p90_gbp": annual_q[2],
        "equity_hurdle_rate_pct": float(100.0 * base.equity_hurdle_rate),
        "dscr_threshold": float(base.dscr_threshold),
        "tax_boundary": "screening tax only; no loss carry-forward, VAT, group relief or legal eligibility opinion",
    }
    return results, summary
