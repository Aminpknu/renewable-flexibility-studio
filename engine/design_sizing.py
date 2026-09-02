"""Leakage-safe long-horizon battery sizing for future portfolio design."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd

from engine.battery import BatteryConfig, simulate_reactive_firming

DEFAULT_POWER_FRACTIONS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60, 0.75, 1.00)
DEFAULT_DURATIONS_HOURS = (1, 2, 4, 6, 8, 12, 16, 24, 36, 48, 72)


@dataclass(frozen=True)
class DesignSizingConfig:
    target_absorbed_pct: float = 90.0
    reliability_pct: float = 90.0
    round_trip_efficiency: float = 0.90
    initial_soc_fraction: float = 0.10
    minimum_soc_fraction: float = 0.10
    maximum_soc_fraction: float = 0.90
    interval_hours: float = 0.50

    def __post_init__(self) -> None:
        if not 0 < self.target_absorbed_pct <= 100:
            raise ValueError("target_absorbed_pct must be in (0, 100].")
        if not 0 < self.reliability_pct <= 100:
            raise ValueError("reliability_pct must be in (0, 100].")


def _daily_codes(frame: pd.DataFrame) -> tuple[np.ndarray, pd.Index]:
    if "settlement_date" not in frame.columns:
        raise ValueError("Design sizing requires settlement_date.")
    dates = pd.to_datetime(frame["settlement_date"], errors="raise").dt.normalize()
    unique_dates = pd.Index(dates.drop_duplicates().sort_values())
    mapping = {value: index for index, value in enumerate(unique_dates)}
    codes = dates.map(mapping).to_numpy(dtype=int)
    return codes, unique_dates


def _fast_metrics(
    portfolio: pd.DataFrame,
    config: BatteryConfig,
    daily_soc_target_fraction: float | None = None,
) -> dict[str, Any]:
    required = {"actual_mw", "forecast_mw", "settlement_date", "settlement_period"}
    missing = sorted(required.difference(portfolio.columns))
    if missing:
        raise ValueError(f"Portfolio frame is missing design columns: {missing}")
    frame = portfolio.sort_values(["settlement_date", "settlement_period"]).reset_index(drop=True)
    errors = frame["actual_mw"].to_numpy(float) - frame["forecast_mw"].to_numpy(float)
    day_codes, unique_dates = _daily_codes(frame)
    daily_before = np.zeros(len(unique_dates), dtype=float)
    daily_after = np.zeros(len(unique_dates), dtype=float)
    daily_power_limited = np.zeros(len(unique_dates), dtype=int)
    daily_energy_limited = np.zeros(len(unique_dates), dtype=int)
    dt = config.interval_hours
    eta_c = config.charge_efficiency
    eta_d = config.discharge_efficiency
    soc = config.initial_soc_mwh
    charge_energy = discharge_energy = losses = 0.0
    grid_reset_import_mwh = grid_reset_export_mwh = 0.0
    if daily_soc_target_fraction is not None:
        if not config.minimum_soc_fraction <= daily_soc_target_fraction <= config.maximum_soc_fraction:
            raise ValueError("daily_soc_target_fraction must lie within SOC bounds.")
        daily_target_mwh = daily_soc_target_fraction * config.energy_capacity_mwh
    else:
        daily_target_mwh = None
    previous_day = -1
    min_soc = max_soc = soc
    tolerance = 1e-10

    for idx, error in enumerate(errors):
        day = day_codes[idx]
        if day != previous_day and daily_target_mwh is not None:
            if soc < daily_target_mwh:
                delta = daily_target_mwh - soc
                grid_reset_import_mwh += delta / eta_c
            elif soc > daily_target_mwh:
                delta = soc - daily_target_mwh
                grid_reset_export_mwh += delta * eta_d
            soc = float(daily_target_mwh)
            previous_day = day
        requested = abs(error)
        residual = error
        charge = discharge = 0.0
        power_limited = energy_limited = False
        if error > tolerance:
            power_cap = min(requested, config.power_mw)
            energy_cap = max(config.maximum_soc_mwh - soc, 0.0) / (eta_c * dt)
            charge = min(power_cap, energy_cap)
            power_limited = requested > config.power_mw + tolerance
            energy_limited = power_cap > energy_cap + tolerance
            soc += charge * eta_c * dt
            residual = error - charge
        elif error < -tolerance:
            power_cap = min(requested, config.power_mw)
            energy_cap = max(soc - config.minimum_soc_mwh, 0.0) * eta_d / dt
            discharge = min(power_cap, energy_cap)
            power_limited = requested > config.power_mw + tolerance
            energy_limited = power_cap > energy_cap + tolerance
            soc -= discharge / eta_d * dt
            residual = error + discharge
        soc = float(np.clip(soc, config.minimum_soc_mwh, config.maximum_soc_mwh))
        daily_before[day] += abs(error) * dt
        daily_after[day] += abs(residual) * dt
        daily_power_limited[day] += int(power_limited)
        daily_energy_limited[day] += int(energy_limited)
        charge_energy += charge * dt
        discharge_energy += discharge * dt
        losses += charge * dt * (1.0 - eta_c) + discharge * dt * (1.0 / eta_d - 1.0)
        min_soc = min(min_soc, soc)
        max_soc = max(max_soc, soc)

    valid_days = daily_before > tolerance
    daily_reduction = np.full(len(unique_dates), np.nan, dtype=float)
    daily_reduction[valid_days] = 100.0 * (1.0 - daily_after[valid_days] / daily_before[valid_days])
    before = float(daily_before.sum())
    after = float(daily_after.sum())
    overall = 100.0 * (1.0 - after / before) if before > tolerance else 100.0
    usable = max(config.usable_energy_mwh, tolerance)
    efc = (charge_energy + discharge_energy) / (2.0 * usable)
    return {
        "overall_absorbed_pct": overall,
        "daily_reduction_pct": daily_reduction,
        "daily_before_mwh": daily_before,
        "daily_after_mwh": daily_after,
        "daily_dates": unique_dates.to_numpy(),
        "day_count": int(valid_days.sum()),
        "power_limited_periods": int(daily_power_limited.sum()),
        "energy_limited_periods": int(daily_energy_limited.sum()),
        "equivalent_full_cycles": float(efc),
        "conversion_losses_mwh": float(losses),
        "grid_reset_import_mwh": float(grid_reset_import_mwh),
        "grid_reset_export_mwh": float(grid_reset_export_mwh),
        "ending_soc_pct": float(100.0 * soc / config.energy_capacity_mwh),
        "minimum_soc_pct": float(100.0 * min_soc / config.energy_capacity_mwh),
        "maximum_soc_pct": float(100.0 * max_soc / config.energy_capacity_mwh),
    }


def evaluate_design_candidate(
    portfolio: pd.DataFrame,
    power_mw: float,
    duration_hours: float,
    sizing: DesignSizingConfig,
) -> dict[str, Any]:
    config = BatteryConfig(
        power_mw=float(power_mw),
        duration_hours=float(duration_hours),
        round_trip_efficiency=sizing.round_trip_efficiency,
        initial_soc_fraction=sizing.initial_soc_fraction,
        minimum_soc_fraction=sizing.minimum_soc_fraction,
        maximum_soc_fraction=sizing.maximum_soc_fraction,
        interval_hours=sizing.interval_hours,
    )
    metrics = _fast_metrics(portfolio, config)
    daily = np.asarray(metrics.pop("daily_reduction_pct"), dtype=float)
    metrics.pop("daily_before_mwh", None)
    metrics.pop("daily_after_mwh", None)
    metrics.pop("daily_dates", None)
    valid = np.isfinite(daily)
    reliability = 100.0 * float((daily[valid] >= sizing.target_absorbed_pct).mean()) if valid.any() else 100.0
    result = {
        "power_mw": float(power_mw),
        "duration_hours": float(duration_hours),
        "energy_mwh": float(config.energy_capacity_mwh),
        "overall_absorbed_pct": float(metrics["overall_absorbed_pct"]),
        "days_meeting_target_pct": reliability,
        "median_daily_absorbed_pct": float(np.nanmedian(daily)),
        "p05_daily_absorbed_pct": float(np.nanquantile(daily, 0.05)),
    }
    result.update(metrics)
    result["meets_design_gate"] = bool(
        result["overall_absorbed_pct"] >= sizing.target_absorbed_pct
        and result["days_meeting_target_pct"] >= sizing.reliability_pct
    )
    return result


def run_design_grid(
    development_portfolio: pd.DataFrame,
    sizing: DesignSizingConfig,
    power_candidates_mw: Iterable[float],
    duration_candidates_hours: Iterable[float] = DEFAULT_DURATIONS_HOURS,
) -> tuple[dict[str, Any] | None, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for power in power_candidates_mw:
        for duration in duration_candidates_hours:
            rows.append(evaluate_design_candidate(
                development_portfolio, float(power), float(duration), sizing
            ))
    comparison = pd.DataFrame(rows).sort_values(
        ["energy_mwh", "power_mw", "duration_hours"]
    ).reset_index(drop=True)
    feasible = comparison.loc[comparison["meets_design_gate"]]
    selected = None if feasible.empty else feasible.iloc[0].to_dict()
    return selected, comparison


def default_power_candidates(capacity_mw: float) -> tuple[float, ...]:
    capacity = float(capacity_mw)
    if not np.isfinite(capacity) or capacity <= 0:
        raise ValueError("capacity_mw must be positive and finite.")
    return tuple(round(capacity * fraction, 6) for fraction in DEFAULT_POWER_FRACTIONS)


def classify_duration(duration_hours: float) -> str:
    duration = float(duration_hours)
    if duration <= 4:
        return "short-duration BESS"
    if duration <= 12:
        return "extended-duration BESS"
    return "long-duration storage territory"


def _segment_summary(simulation: pd.DataFrame, target_pct: float) -> dict[str, Any]:
    before = simulation["forecast_error_mw"].abs() * 0.5
    after = simulation["residual_error_mw"].abs() * 0.5
    total_before = float(before.sum())
    total_after = float(after.sum())
    overall = 100.0 * (1.0 - total_after / total_before) if total_before > 0 else 100.0
    daily = pd.DataFrame({
        "settlement_date": pd.to_datetime(simulation["settlement_date"]).dt.normalize(),
        "before": before.to_numpy(float),
        "after": after.to_numpy(float),
    }).groupby("settlement_date", as_index=False)[["before", "after"]].sum()
    daily["absorbed_pct"] = np.where(
        daily["before"].gt(0), 100.0 * (1.0 - daily["after"] / daily["before"]), 100.0
    )
    daily["residual_mwh"] = daily["after"]
    return {
        "overall_absorbed_pct": float(overall),
        "days_meeting_target_pct": float(100.0 * (daily["absorbed_pct"] >= target_pct).mean()),
        "median_daily_absorbed_pct": float(daily["absorbed_pct"].median()),
        "p05_daily_absorbed_pct": float(daily["absorbed_pct"].quantile(0.05)),
        "p95_daily_residual_mwh": float(daily["residual_mwh"].quantile(0.95)),
        "max_daily_residual_mwh": float(daily["residual_mwh"].max()),
        "target_days": int(len(daily)),
    }


def validate_selected_design(
    full_portfolio: pd.DataFrame,
    selected: dict[str, Any],
    sizing: DesignSizingConfig,
) -> dict[str, Any]:
    if "evaluation_segment" not in full_portfolio.columns:
        raise ValueError("Locked validation requires evaluation_segment labels.")
    config = BatteryConfig(
        power_mw=float(selected["power_mw"]),
        duration_hours=float(selected["duration_hours"]),
        round_trip_efficiency=sizing.round_trip_efficiency,
        initial_soc_fraction=sizing.initial_soc_fraction,
        minimum_soc_fraction=sizing.minimum_soc_fraction,
        maximum_soc_fraction=sizing.maximum_soc_fraction,
        interval_hours=sizing.interval_hours,
    )
    simulation = simulate_reactive_firming(full_portfolio, config)
    development = simulation.loc[simulation["evaluation_segment"].eq("development_oof")].copy()
    locked = simulation.loc[simulation["evaluation_segment"].eq("locked_test")].copy()
    if development.empty or locked.empty:
        raise ValueError("Both development_oof and locked_test rows are required.")
    dev_summary = _segment_summary(development, sizing.target_absorbed_pct)
    locked_summary = _segment_summary(locked, sizing.target_absorbed_pct)
    locked_pass = bool(
        locked_summary["overall_absorbed_pct"] >= sizing.target_absorbed_pct
        and locked_summary["days_meeting_target_pct"] >= sizing.reliability_pct
    )
    return {
        "development": dev_summary,
        "locked_test": locked_summary,
        "locked_validation_passed": locked_pass,
        "classification": classify_duration(float(selected["duration_hours"])),
        "ending_soc_pct": float(
            100.0 * simulation["soc_end_mwh"].iloc[-1] / config.energy_capacity_mwh
        ),
        "power_limited_periods_full": int(simulation["power_limited"].sum()),
        "energy_limited_periods_full": int(simulation["energy_limited"].sum()),
        "equivalent_full_cycles_full": float(
            (simulation["charge_mw"].sum() + simulation["discharge_mw"].sum())
            * sizing.interval_hours / (2.0 * config.usable_energy_mwh)
        ),
    }


def evaluate_stability_candidate(
    full_portfolio: pd.DataFrame,
    power_mw: float,
    duration_hours: float,
    target_pct: float,
    round_trip_efficiency: float = 0.90,
    initial_soc_fraction: float = 0.10,
    daily_soc_target_fraction: float | None = None,
) -> dict[str, Any]:
    """Evaluate one design continuously across all 450 days and both time regimes."""
    config = BatteryConfig(
        power_mw=float(power_mw), duration_hours=float(duration_hours),
        round_trip_efficiency=float(round_trip_efficiency),
        initial_soc_fraction=float(initial_soc_fraction),
    )
    metrics = _fast_metrics(
        full_portfolio, config, daily_soc_target_fraction=daily_soc_target_fraction
    )
    daily_before = np.asarray(metrics.pop("daily_before_mwh"), dtype=float)
    daily_after = np.asarray(metrics.pop("daily_after_mwh"), dtype=float)
    daily_dates = pd.to_datetime(metrics.pop("daily_dates")).normalize()
    daily_reduction = np.asarray(metrics.pop("daily_reduction_pct"), dtype=float)
    segment_by_date = (
        full_portfolio.assign(settlement_date=pd.to_datetime(full_portfolio["settlement_date"]).dt.normalize())
        .groupby("settlement_date")["evaluation_segment"].first()
    )
    segments = pd.Series(daily_dates).map(segment_by_date).to_numpy()
    row: dict[str, Any] = {
        "power_mw": float(power_mw),
        "duration_hours": float(duration_hours),
        "energy_mwh": float(config.energy_capacity_mwh),
        "classification": classify_duration(duration_hours),
    }
    for segment, prefix in (("development_oof", "development"), ("locked_test", "locked")):
        mask = segments == segment
        before = float(daily_before[mask].sum())
        after = float(daily_after[mask].sum())
        overall = 100.0 * (1.0 - after / before) if before > 0 else 100.0
        valid = np.isfinite(daily_reduction[mask])
        reductions = daily_reduction[mask][valid]
        row[f"{prefix}_overall_absorbed_pct"] = overall
        row[f"{prefix}_days_meeting_target_pct"] = float(
            100.0 * (reductions >= target_pct).mean()
        ) if len(reductions) else 100.0
        for threshold in (80, 90, 95):
            row[f"{prefix}_days{threshold}_pct"] = float(
                100.0 * (reductions >= threshold).mean()
            ) if len(reductions) else 100.0
        row[f"{prefix}_p05_daily_absorbed_pct"] = float(np.quantile(reductions, 0.05)) if len(reductions) else 100.0
        row[f"{prefix}_median_daily_absorbed_pct"] = float(np.median(reductions)) if len(reductions) else 100.0
    row["full_overall_absorbed_pct"] = float(metrics["overall_absorbed_pct"])
    valid_full = daily_reduction[np.isfinite(daily_reduction)]
    row["full_days_meeting_target_pct"] = float(100.0 * (valid_full >= target_pct).mean())
    for threshold in (80, 90, 95):
        row[f"full_days{threshold}_pct"] = float(100.0 * (valid_full >= threshold).mean())
    row.update({
        "power_limited_periods": metrics["power_limited_periods"],
        "energy_limited_periods": metrics["energy_limited_periods"],
        "equivalent_full_cycles": metrics["equivalent_full_cycles"],
        "grid_reset_import_mwh": metrics["grid_reset_import_mwh"],
        "grid_reset_export_mwh": metrics["grid_reset_export_mwh"],
        "mean_daily_grid_reset_import_mwh": metrics["grid_reset_import_mwh"] / max(metrics["day_count"], 1),
        "ending_soc_pct": metrics["ending_soc_pct"],
    })
    return row


def select_stable_design(
    comparison: pd.DataFrame,
    target_pct: float,
    reliability_pct: float,
) -> dict[str, Any] | None:
    target = int(round(float(target_pct)))
    if target not in {80, 90, 95}:
        raise ValueError("Stable design target must be 80, 90 or 95%.")
    reliability = float(reliability_pct)
    required = [
        "development_overall_absorbed_pct", "locked_overall_absorbed_pct",
        f"development_days{target}_pct", f"locked_days{target}_pct",
    ]
    missing = sorted(set(required).difference(comparison.columns))
    if missing:
        raise ValueError(f"Design grid is missing stability columns: {missing}")
    feasible = comparison.loc[
        comparison["development_overall_absorbed_pct"].ge(target)
        & comparison["locked_overall_absorbed_pct"].ge(target)
        & comparison[f"development_days{target}_pct"].ge(reliability)
        & comparison[f"locked_days{target}_pct"].ge(reliability)
    ].sort_values(["energy_mwh", "power_mw", "duration_hours"])
    return None if feasible.empty else feasible.iloc[0].to_dict()
