"""Block-resampled Monte Carlo for Stage 6B BESS investment value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from .battery import BatteryConfig, simulate_reactive_firming
from .tail_risk import summarise_npv_distribution
from .value import ValueAssumptions, appraise_intervention


@dataclass(frozen=True)
class TriangularMultiplier:
    low: float
    mode: float
    high: float

    def __post_init__(self) -> None:
        if not (0 <= self.low <= self.mode <= self.high):
            raise ValueError("Triangular multiplier must satisfy 0 <= low <= mode <= high.")

    def sample(self, rng: np.random.Generator) -> float:
        if self.low == self.high:
            return float(self.low)
        return float(rng.triangular(self.low, self.mode, self.high))


@dataclass(frozen=True)
class MonteCarloConfig:
    simulations: int = 2000
    seed: int = 20260903
    sample_days: int = 365
    block_days: int = 7
    confidence: float = 0.95
    firming_target_pct: float | None = None
    reliability_target_pct: float | None = None

    def __post_init__(self) -> None:
        if self.simulations <= 0 or self.sample_days <= 0 or self.block_days <= 0:
            raise ValueError("Simulation, sample-day and block-day counts must be positive.")
        if not 0 < self.confidence < 1:
            raise ValueError("confidence must lie in (0, 1).")
        targets = (self.firming_target_pct, self.reliability_target_pct)
        if (targets[0] is None) != (targets[1] is None):
            raise ValueError("Firming and reliability targets must be supplied together.")
        if targets[0] is not None and not all(0 <= float(v) <= 100 for v in targets):
            raise ValueError("Firming and reliability targets must lie in [0, 100].")

@dataclass(frozen=True)
class MonteCarloDistributions:
    consequence_multiplier: TriangularMultiplier = TriangularMultiplier(0.70, 1.00, 1.30)
    capex_multiplier: TriangularMultiplier = TriangularMultiplier(0.85, 1.00, 1.20)
    opex_multiplier: TriangularMultiplier = TriangularMultiplier(0.90, 1.00, 1.15)
    availability_fraction: TriangularMultiplier = TriangularMultiplier(0.90, 0.95, 1.00)
    degradation_multiplier: TriangularMultiplier = TriangularMultiplier(0.75, 1.00, 1.25)


def contiguous_block_bootstrap_indices(
    length: int,
    sample_length: int,
    block_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Sample contiguous circular blocks until the requested length is reached."""
    if length <= 0 or sample_length <= 0 or block_length <= 0:
        raise ValueError("Bootstrap lengths must be positive.")
    blocks: list[np.ndarray] = []
    remaining = sample_length
    while remaining > 0:
        start = int(rng.integers(0, length))
        take = min(block_length, remaining)
        blocks.append((start + np.arange(take, dtype=int)) % length)
        remaining -= take
    return np.concatenate(blocks)


def resample_complete_settlement_days(
    frame: pd.DataFrame,
    sample_days: int,
    block_days: int,
    rng: np.random.Generator,
    date_column: str = "settlement_date",
) -> pd.DataFrame:
    """Resample whole chronological settlement days in contiguous circular blocks."""
    if date_column not in frame.columns or frame.empty:
        raise ValueError(f"Frame must contain non-empty {date_column!r} data.")
    work = frame.copy()
    work[date_column] = pd.to_datetime(work[date_column], errors="raise").dt.normalize()
    dates = pd.Index(work[date_column].drop_duplicates()).sort_values()
    indexes = contiguous_block_bootstrap_indices(len(dates), sample_days, block_days, rng)
    parts: list[pd.DataFrame] = []
    for draw_number, date_index in enumerate(indexes):
        day = work.loc[work[date_column].eq(dates[date_index])].copy()
        day["bootstrap_day"] = draw_number + 1
        day["source_settlement_date"] = dates[date_index]
        parts.append(day)
    return pd.concat(parts, ignore_index=True)


def build_daily_value_evidence(
    portfolio: pd.DataFrame,
    battery: BatteryConfig,
) -> pd.DataFrame:
    """Build daily avoided-exposure/throughput evidence with SOC reset each day."""
    required = {"settlement_date", "settlement_period", "valid_time_utc", "actual_mw", "forecast_mw"}
    missing = sorted(required.difference(portfolio.columns))
    if missing:
        raise ValueError(f"Portfolio is missing daily-evidence columns: {missing}")
    if portfolio.empty:
        raise ValueError("Portfolio is empty.")
    work = portfolio.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"], errors="raise").dt.normalize()
    rows: list[dict[str, float | int | str]] = []
    for date, day in work.groupby("settlement_date", sort=True):
        sim = simulate_reactive_firming(day, battery)
        before = float(sim["forecast_error_mw"].abs().sum() * battery.interval_hours)
        after = float(sim["residual_error_mw"].abs().sum() * battery.interval_hours)
        throughput = float((sim["charge_mw"] + sim["discharge_mw"]).sum() * battery.interval_hours)
        absorbed = 100.0 * (1.0 - after / before) if before > 0 else 100.0
        rows.append({
            "settlement_date": pd.Timestamp(date).date().isoformat(),
            "period_count": int(len(day)),
            "baseline_exposure_mwh": before,
            "residual_exposure_mwh": after,
            "avoided_exposure_mwh": max(before - after, 0.0),
            "throughput_mwh": throughput,
            "absorbed_pct": absorbed,
        })
    return pd.DataFrame(rows)

def run_value_monte_carlo(
    daily_evidence: pd.DataFrame,
    base_assumptions: ValueAssumptions,
    config: MonteCarloConfig | None = None,
    distributions: MonteCarloDistributions | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Simulate NPV while preserving day-level temporal dependence by block bootstrap."""
    cfg = config or MonteCarloConfig()
    dist = distributions or MonteCarloDistributions()
    required = {"settlement_date", "avoided_exposure_mwh", "throughput_mwh"}
    if cfg.firming_target_pct is not None:
        required.add("absorbed_pct")
    missing = sorted(required.difference(daily_evidence.columns))
    if missing:
        raise ValueError(f"Daily evidence is missing Monte Carlo columns: {missing}")
    if daily_evidence.empty:
        raise ValueError("Daily evidence is empty.")
    work = daily_evidence.copy()
    work["settlement_date"] = pd.to_datetime(work["settlement_date"], errors="raise").dt.normalize()
    aggregation = {"avoided_exposure_mwh": "sum", "throughput_mwh": "sum"}
    if "absorbed_pct" in work.columns:
        aggregation["absorbed_pct"] = "mean"
    daily = work.groupby("settlement_date", as_index=False).agg(aggregation)
    if (daily[["avoided_exposure_mwh", "throughput_mwh"]] < 0).any().any():
        raise ValueError("Daily avoided exposure and throughput must be non-negative.")

    rng = np.random.default_rng(cfg.seed)
    rows: list[dict[str, float | int]] = []
    for simulation in range(cfg.simulations):
        indexes = contiguous_block_bootstrap_indices(
            len(daily), cfg.sample_days, cfg.block_days, rng
        )
        sample = daily.iloc[indexes]
        availability = dist.availability_fraction.sample(rng)
        available_mask = rng.random(len(sample)) < availability
        annual_avoided = float(sample.loc[available_mask, "avoided_exposure_mwh"].sum())
        annual_throughput = float(sample.loc[available_mask, "throughput_mwh"].sum())
        consequence_multiplier = dist.consequence_multiplier.sample(rng)
        capex_multiplier = dist.capex_multiplier.sample(rng)
        opex_multiplier = dist.opex_multiplier.sample(rng)
        degradation_multiplier = dist.degradation_multiplier.sample(rng)
        assumptions = ValueAssumptions(
            consequence_value_gbp_per_mwh=(
                base_assumptions.consequence_value_gbp_per_mwh * consequence_multiplier
            ),
            total_capex_gbp=base_assumptions.total_capex_gbp * capex_multiplier,
            fixed_opex_gbp_per_year=(
                base_assumptions.fixed_opex_gbp_per_year * opex_multiplier
            ),
            variable_opex_gbp_per_mwh=(
                base_assumptions.variable_opex_gbp_per_mwh * opex_multiplier
            ),
            asset_life_years=base_assumptions.asset_life_years,
            discount_rate=base_assumptions.discount_rate,
            annual_degradation_fraction=min(
                base_assumptions.annual_degradation_fraction * degradation_multiplier,
                0.999999,
            ),
        )
        value = appraise_intervention(annual_avoided, annual_throughput, assumptions)
        days_meeting_target_pct = None
        firming_gate_met = None
        if cfg.firming_target_pct is not None:
            effective_absorbed = sample["absorbed_pct"].to_numpy(float) * available_mask.astype(float)
            days_meeting_target_pct = float(100.0 * np.mean(effective_absorbed >= cfg.firming_target_pct))
            firming_gate_met = bool(days_meeting_target_pct + 1e-12 >= cfg.reliability_target_pct)
        rows.append({
            "simulation": simulation + 1,
            "annual_avoided_exposure_mwh": annual_avoided,
            "annual_throughput_mwh": annual_throughput,
            "availability_fraction": availability,
            "realised_available_days_pct": float(100.0 * available_mask.mean()),
            "consequence_multiplier": consequence_multiplier,
            "capex_multiplier": capex_multiplier,
            "opex_multiplier": opex_multiplier,
            "degradation_multiplier": degradation_multiplier,
            "npv_gbp": float(value["npv_gbp"]),
            "benefit_cost_ratio": float(value["benefit_cost_ratio"]),
            "days_meeting_firming_target_pct": days_meeting_target_pct,
            "firming_gate_met": firming_gate_met,
        })
    results = pd.DataFrame(rows)
    summary = summarise_npv_distribution(results["npv_gbp"].to_numpy(float), cfg.confidence)
    summary.update({
        "seed": cfg.seed,
        "sample_days": cfg.sample_days,
        "block_days": cfg.block_days,
        "resampling": "contiguous circular blocks of complete historical days",
        "distribution_dependence_assumption": "parameter multipliers sampled independently; temporal dependence retained through day blocks; daily outage states sampled independently conditional on availability",
    })
    if cfg.firming_target_pct is not None:
        summary.update({
            "firming_target_pct": float(cfg.firming_target_pct),
            "reliability_target_pct": float(cfg.reliability_target_pct),
            "probability_failing_firming_gate_pct": float(100.0 * (~results["firming_gate_met"].astype(bool)).mean()),
            "p10_days_meeting_firming_target_pct": float(results["days_meeting_firming_target_pct"].quantile(0.10)),
            "p50_days_meeting_firming_target_pct": float(results["days_meeting_firming_target_pct"].quantile(0.50)),
        })
    return results, summary