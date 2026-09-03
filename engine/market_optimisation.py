"""Market-linked BESS benchmarks for GB renewable forecast-error firming."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from .battery import BatteryConfig


@dataclass(frozen=True)
class SettlementOptimisationConfig:
    """Assumptions for an ex-post settlement-value firming benchmark."""

    restoration_price_gbp_per_mwh: float
    throughput_cost_gbp_per_mwh: float = 0.0

    def __post_init__(self) -> None:
        values = [self.restoration_price_gbp_per_mwh, self.throughput_cost_gbp_per_mwh]
        if not all(np.isfinite(float(value)) for value in values):
            raise ValueError("Market-optimisation cost assumptions must be finite.")
        if self.throughput_cost_gbp_per_mwh < 0:
            raise ValueError("Throughput cost cannot be negative.")


def _join_system_prices(portfolio: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    required_portfolio = {"settlement_period", "actual_mw", "forecast_mw", "valid_time_utc"}
    required_prices = {"settlement_period", "system_price_gbp_per_mwh"}
    missing_portfolio = sorted(required_portfolio.difference(portfolio.columns))
    missing_prices = sorted(required_prices.difference(prices.columns))
    if missing_portfolio or missing_prices:
        raise ValueError(
            f"Market optimisation columns missing: portfolio={missing_portfolio}, prices={missing_prices}"
        )
    left = portfolio.copy()
    right = prices.copy()
    keys = ["settlement_period"]
    if "settlement_date" in left.columns and "settlement_date" in right.columns:
        left["settlement_date"] = pd.to_datetime(left["settlement_date"], errors="raise").dt.normalize()
        right["settlement_date"] = pd.to_datetime(right["settlement_date"], errors="raise").dt.normalize()
        keys = ["settlement_date", "settlement_period"]
    if right.duplicated(keys).any():
        raise ValueError("System-price frame contains duplicate settlement keys.")
    frame = left.merge(
        right[keys + ["system_price_gbp_per_mwh"]],
        on=keys,
        how="left",
        validate="one_to_one",
    )
    if frame["system_price_gbp_per_mwh"].isna().any():
        raise ValueError("System-price join produced missing prices.")
    return frame.sort_values("settlement_period").reset_index(drop=True)


def optimise_settlement_aware_firming(
    portfolio: pd.DataFrame,
    system_prices: pd.DataFrame,
    battery: BatteryConfig,
    config: SettlementOptimisationConfig,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Optimise which deviations to firm using realised System Price.

    This is an ex-post perfect-information benchmark. Dispatch is restricted to
    reducing the observed renewable deviation; it cannot reverse or amplify it.
    End-of-day SOC restoration is explicitly priced at the market-reference input.
    """
    if portfolio.empty:
        raise ValueError("Portfolio frame is empty.")
    frame = _join_system_prices(portfolio, system_prices)
    if frame[["actual_mw", "forecast_mw", "system_price_gbp_per_mwh"]].isna().any().any():
        raise ValueError("Market optimisation input contains missing numeric values.")
    actual = frame["actual_mw"].to_numpy(float)
    forecast = frame["forecast_mw"].to_numpy(float)
    prices = frame["system_price_gbp_per_mwh"].to_numpy(float)
    if not np.isfinite(np.column_stack([actual, forecast, prices])).all():
        raise ValueError("Market optimisation input contains non-finite values.")

    error = actual - forecast
    n = len(frame)
    dt = battery.interval_hours
    eta_c = battery.charge_efficiency
    eta_d = battery.discharge_efficiency
    charge_offset = 0
    discharge_offset = n
    soc_offset = 2 * n
    restore_import_index = 3 * n
    restore_export_index = 3 * n + 1
    restore_mode_index = 3 * n + 2
    variable_count = 3 * n + 3

    objective = np.zeros(variable_count, dtype=float)
    objective[charge_offset:charge_offset + n] = (
        prices + config.throughput_cost_gbp_per_mwh
    ) * dt
    objective[discharge_offset:discharge_offset + n] = (
        -prices + config.throughput_cost_gbp_per_mwh
    ) * dt
    objective[restore_import_index] = config.restoration_price_gbp_per_mwh
    objective[restore_export_index] = -config.restoration_price_gbp_per_mwh
    objective[restore_mode_index] = 0.0

    bounds: list[tuple[float, float | None]] = []
    for value in error:
        upper = min(max(float(value), 0.0), battery.power_mw)
        bounds.append((0.0, upper))
    for value in error:
        upper = min(max(float(-value), 0.0), battery.power_mw)
        bounds.append((0.0, upper))
    bounds.extend([
        (battery.minimum_soc_mwh, battery.maximum_soc_mwh)
        for _ in range(n)
    ])
    restore_limit = battery.energy_capacity_mwh / min(eta_c, eta_d)
    bounds.extend([(0.0, restore_limit), (0.0, restore_limit), (0.0, 1.0)])

    a_eq = np.zeros((n + 1, variable_count), dtype=float)
    b_eq = np.zeros(n + 1, dtype=float)
    for t in range(n):
        a_eq[t, soc_offset + t] = 1.0
        a_eq[t, charge_offset + t] = -eta_c * dt
        a_eq[t, discharge_offset + t] = dt / eta_d
        if t == 0:
            b_eq[t] = battery.initial_soc_mwh
        else:
            a_eq[t, soc_offset + t - 1] = -1.0
    a_eq[n, soc_offset + n - 1] = 1.0
    a_eq[n, restore_import_index] = eta_c
    a_eq[n, restore_export_index] = -1.0 / eta_d
    b_eq[n] = battery.initial_soc_mwh

    a_mode = np.zeros((2, variable_count), dtype=float)
    a_mode[0, restore_import_index] = 1.0
    a_mode[0, restore_mode_index] = -restore_limit
    a_mode[1, restore_export_index] = 1.0
    a_mode[1, restore_mode_index] = restore_limit
    constraints = [
        LinearConstraint(a_eq, b_eq, b_eq),
        LinearConstraint(
            a_mode,
            np.array([-np.inf, -np.inf]),
            np.array([0.0, restore_limit]),
        ),
    ]
    lower = np.array([value[0] for value in bounds], dtype=float)
    upper = np.array([
        np.inf if value[1] is None else value[1] for value in bounds
    ], dtype=float)
    integrality = np.zeros(variable_count, dtype=int)
    integrality[restore_mode_index] = 1
    solution = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"disp": False},
    )
    if not solution.success:
        raise RuntimeError(f"Settlement-aware optimisation failed: {solution.message}")
    x = solution.x
    charge = x[charge_offset:charge_offset + n]
    discharge = x[discharge_offset:discharge_offset + n]
    soc_end = x[soc_offset:soc_offset + n]
    tolerance = 1e-8
    charge[np.abs(charge) < tolerance] = 0.0
    discharge[np.abs(discharge) < tolerance] = 0.0
    soc_start = np.concatenate([[battery.initial_soc_mwh], soc_end[:-1]])
    residual = error - charge + discharge
    settlement_before = -error * prices * dt
    settlement_after = -residual * prices * dt
    throughput_mwh = float((charge + discharge).sum() * dt)
    throughput_cost = throughput_mwh * config.throughput_cost_gbp_per_mwh
    restore_import = float(x[restore_import_index])
    restore_export = float(x[restore_export_index])
    restoration_net_cost = (
        restore_import - restore_export
    ) * config.restoration_price_gbp_per_mwh

    frame["forecast_error_mw"] = error
    frame["market_optimised_charge_mw"] = charge
    frame["market_optimised_discharge_mw"] = discharge
    frame["market_optimised_soc_start_mwh"] = soc_start
    frame["market_optimised_soc_end_mwh"] = soc_end
    frame["market_optimised_residual_error_mw"] = residual
    frame["settlement_payment_before_gbp"] = settlement_before
    frame["settlement_payment_after_gbp"] = settlement_after
    frame["settlement_value_improvement_gbp"] = settlement_before - settlement_after

    if ((charge > tolerance) & (discharge > tolerance)).any():
        raise AssertionError("Market optimiser charged and discharged simultaneously.")
    if (np.abs(residual) > np.abs(error) + tolerance).any():
        raise AssertionError("Market optimiser amplified or reversed a forecast deviation.")
    if not pd.Series(soc_end).between(
        battery.minimum_soc_mwh - tolerance,
        battery.maximum_soc_mwh + tolerance,
    ).all():
        raise AssertionError("Market optimiser violated SOC bounds.")

    absolute_before = float(np.abs(error).sum() * dt)
    absolute_after = float(np.abs(residual).sum() * dt)
    settlement_improvement = float((settlement_before - settlement_after).sum())
    net_value = settlement_improvement - throughput_cost - restoration_net_cost
    summary: dict[str, Any] = {
        "method": "ex_post_system_price_settlement_aware_directional_firming",
        "perfect_information": True,
        "period_count": int(n),
        "absolute_error_before_mwh": absolute_before,
        "absolute_error_after_mwh": absolute_after,
        "error_reduction_pct": (
            100.0 * (1.0 - absolute_after / absolute_before)
            if absolute_before > 0 else 0.0
        ),
        "settlement_payment_before_gbp": float(settlement_before.sum()),
        "settlement_payment_after_gbp": float(settlement_after.sum()),
        "settlement_value_improvement_before_costs_gbp": settlement_improvement,
        "throughput_mwh": throughput_mwh,
        "throughput_cost_gbp": float(throughput_cost),
        "ending_soc_pct_before_restoration": float(
            100.0 * soc_end[-1] / battery.energy_capacity_mwh
        ),
        "grid_restoration_import_mwh": restore_import,
        "grid_restoration_export_mwh": restore_export,
        "restoration_price_gbp_per_mwh": float(config.restoration_price_gbp_per_mwh),
        "restoration_net_cost_gbp": float(restoration_net_cost),
        "net_settlement_value_improvement_gbp": float(net_value),
        "solver_status": str(solution.message),
    }
    return frame, summary


@dataclass(frozen=True)
class WholesaleArbitrageConfig:
    """Assumptions for an ex-post wholesale-price arbitrage benchmark."""

    throughput_cost_gbp_per_mwh: float = 0.0

    def __post_init__(self) -> None:
        if not np.isfinite(float(self.throughput_cost_gbp_per_mwh)):
            raise ValueError("Arbitrage throughput cost must be finite.")
        if self.throughput_cost_gbp_per_mwh < 0:
            raise ValueError("Arbitrage throughput cost cannot be negative.")


def optimise_wholesale_arbitrage(
    market_prices: pd.DataFrame,
    battery: BatteryConfig,
    config: WholesaleArbitrageConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Maximise ex-post wholesale arbitrage value with terminal SOC equality.

    The entire realised price path is known to this benchmark, so results are an
    upper bound and must not be described as deployable trading revenue.
    """
    cfg = config or WholesaleArbitrageConfig()
    required = {"settlement_period", "market_index_price_gbp_per_mwh"}
    missing = sorted(required.difference(market_prices.columns))
    if missing:
        raise ValueError(f"Market-price frame is missing arbitrage columns: {missing}")
    if market_prices.empty:
        raise ValueError("Market-price frame is empty.")
    frame = market_prices.copy().sort_values("settlement_period").reset_index(drop=True)
    prices = pd.to_numeric(
        frame["market_index_price_gbp_per_mwh"], errors="raise"
    ).to_numpy(float)
    if not np.isfinite(prices).all():
        raise ValueError("Market-price frame contains non-finite prices.")
    n = len(frame)
    dt = battery.interval_hours
    eta_c = battery.charge_efficiency
    eta_d = battery.discharge_efficiency
    charge_offset = 0
    discharge_offset = n
    soc_offset = 2 * n
    mode_offset = 3 * n
    variable_count = 4 * n

    objective = np.zeros(variable_count, dtype=float)
    objective[charge_offset:charge_offset + n] = (
        prices + cfg.throughput_cost_gbp_per_mwh
    ) * dt
    objective[discharge_offset:discharge_offset + n] = (
        -prices + cfg.throughput_cost_gbp_per_mwh
    ) * dt

    lower = np.zeros(variable_count, dtype=float)
    upper = np.full(variable_count, np.inf, dtype=float)
    upper[charge_offset:charge_offset + n] = battery.power_mw
    upper[discharge_offset:discharge_offset + n] = battery.power_mw
    lower[soc_offset:soc_offset + n] = battery.minimum_soc_mwh
    upper[soc_offset:soc_offset + n] = battery.maximum_soc_mwh
    corridor_columns = {"soc_floor_mwh", "soc_ceiling_mwh"}
    if corridor_columns.issubset(frame.columns):
        corridor_floor = pd.to_numeric(frame["soc_floor_mwh"], errors="raise").to_numpy(float)
        corridor_ceiling = pd.to_numeric(frame["soc_ceiling_mwh"], errors="raise").to_numpy(float)
        if not np.isfinite(np.column_stack([corridor_floor, corridor_ceiling])).all():
            raise ValueError("SOC corridor contains non-finite values.")
        corridor_floor = np.maximum(corridor_floor, battery.minimum_soc_mwh)
        corridor_ceiling = np.minimum(corridor_ceiling, battery.maximum_soc_mwh)
        if (corridor_floor > corridor_ceiling + 1e-9).any():
            raise ValueError("SOC reserve corridor is infeasible for at least one period.")
        lower[soc_offset:soc_offset + n] = corridor_floor
        upper[soc_offset:soc_offset + n] = corridor_ceiling
    upper[mode_offset:mode_offset + n] = 1.0

    a_eq = np.zeros((n + 1, variable_count), dtype=float)
    b_eq = np.zeros(n + 1, dtype=float)
    for t in range(n):
        a_eq[t, soc_offset + t] = 1.0
        a_eq[t, charge_offset + t] = -eta_c * dt
        a_eq[t, discharge_offset + t] = dt / eta_d
        if t == 0:
            b_eq[t] = battery.initial_soc_mwh
        else:
            a_eq[t, soc_offset + t - 1] = -1.0
    a_eq[n, soc_offset + n - 1] = 1.0
    b_eq[n] = battery.initial_soc_mwh

    a_mode = np.zeros((2 * n, variable_count), dtype=float)
    mode_upper = np.zeros(2 * n, dtype=float)
    for t in range(n):
        a_mode[2 * t, charge_offset + t] = 1.0
        a_mode[2 * t, mode_offset + t] = battery.power_mw
        mode_upper[2 * t] = battery.power_mw
        a_mode[2 * t + 1, discharge_offset + t] = 1.0
        a_mode[2 * t + 1, mode_offset + t] = -battery.power_mw
        mode_upper[2 * t + 1] = 0.0
    constraints = [
        LinearConstraint(a_eq, b_eq, b_eq),
        LinearConstraint(a_mode, np.full(2 * n, -np.inf), mode_upper),
    ]
    integrality = np.zeros(variable_count, dtype=int)
    integrality[mode_offset:mode_offset + n] = 1
    solution = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"disp": False},
    )
    if not solution.success:
        raise RuntimeError(f"Wholesale arbitrage optimisation failed: {solution.message}")
    x = solution.x
    charge = x[charge_offset:charge_offset + n]
    discharge = x[discharge_offset:discharge_offset + n]
    soc_end = x[soc_offset:soc_offset + n]
    tolerance = 1e-8
    charge[np.abs(charge) < tolerance] = 0.0
    discharge[np.abs(discharge) < tolerance] = 0.0
    if ((charge > tolerance) & (discharge > tolerance)).any():
        raise AssertionError("Wholesale arbitrage charged and discharged simultaneously.")
    if abs(float(soc_end[-1]) - battery.initial_soc_mwh) > 1e-6:
        raise AssertionError("Wholesale arbitrage violated terminal SOC equality.")

    charge_energy = charge * dt
    discharge_energy = discharge * dt
    purchase_cost = float((charge_energy * prices).sum())
    sale_revenue = float((discharge_energy * prices).sum())
    throughput_mwh = float(charge_energy.sum() + discharge_energy.sum())
    throughput_cost = throughput_mwh * cfg.throughput_cost_gbp_per_mwh
    gross_margin = sale_revenue - purchase_cost
    net_margin = gross_margin - throughput_cost
    frame["arbitrage_charge_mw"] = charge
    frame["arbitrage_discharge_mw"] = discharge
    frame["arbitrage_soc_end_mwh"] = soc_end
    frame["arbitrage_net_export_mw"] = discharge - charge
    frame["arbitrage_market_cashflow_gbp"] = (
        discharge_energy - charge_energy
    ) * prices
    summary: dict[str, Any] = {
        "method": "ex_post_market_index_perfect_foresight_arbitrage",
        "perfect_information": True,
        "period_count": int(n),
        "purchase_cost_gbp": purchase_cost,
        "sale_revenue_gbp": sale_revenue,
        "gross_arbitrage_margin_gbp": float(gross_margin),
        "throughput_mwh": throughput_mwh,
        "throughput_cost_gbp": float(throughput_cost),
        "net_arbitrage_margin_gbp": float(net_margin),
        "charge_energy_mwh": float(charge_energy.sum()),
        "discharge_energy_mwh": float(discharge_energy.sum()),
        "ending_soc_pct": float(100.0 * soc_end[-1] / battery.energy_capacity_mwh),
        "min_market_price_gbp_per_mwh": float(prices.min()),
        "max_market_price_gbp_per_mwh": float(prices.max()),
        "solver_status": str(solution.message),
    }
    return frame, summary


def optimise_firming_and_arbitrage(
    portfolio: pd.DataFrame,
    system_prices: pd.DataFrame,
    market_prices: pd.DataFrame,
    battery: BatteryConfig,
    throughput_cost_gbp_per_mwh: float = 0.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Co-optimise ex-post imbalance firming and wholesale arbitrage.

    Firming dispatch changes the renewable imbalance settled at System Price.
    Arbitrage dispatch is treated as a separately nominated wholesale transaction
    at Market Index Price. Both uses share the same battery MW, SOC and throughput.
    """
    if not np.isfinite(float(throughput_cost_gbp_per_mwh)) or throughput_cost_gbp_per_mwh < 0:
        raise ValueError("Co-optimisation throughput cost must be finite and non-negative.")
    frame = _join_system_prices(portfolio, system_prices)
    market_required = {"settlement_period", "market_index_price_gbp_per_mwh"}
    missing = sorted(market_required.difference(market_prices.columns))
    if missing:
        raise ValueError(f"Market-price frame is missing co-optimisation columns: {missing}")
    market = market_prices[["settlement_period", "market_index_price_gbp_per_mwh"]].copy()
    if market["settlement_period"].duplicated().any():
        raise ValueError("Market-price frame contains duplicate settlement periods.")
    frame = frame.merge(market, on="settlement_period", how="left", validate="one_to_one")
    if frame["market_index_price_gbp_per_mwh"].isna().any():
        raise ValueError("Market-price join produced missing prices.")
    actual = frame["actual_mw"].to_numpy(float)
    forecast = frame["forecast_mw"].to_numpy(float)
    error = actual - forecast
    system = frame["system_price_gbp_per_mwh"].to_numpy(float)
    market_price = frame["market_index_price_gbp_per_mwh"].to_numpy(float)
    if not np.isfinite(np.column_stack([actual, forecast, system, market_price])).all():
        raise ValueError("Co-optimisation inputs contain non-finite values.")
    n = len(frame)
    dt = battery.interval_hours
    eta_c = battery.charge_efficiency
    eta_d = battery.discharge_efficiency
    firm_charge_offset = 0
    firm_discharge_offset = n
    arb_charge_offset = 2 * n
    arb_discharge_offset = 3 * n
    soc_offset = 4 * n
    mode_offset = 5 * n
    variable_count = 6 * n

    objective = np.zeros(variable_count, dtype=float)
    objective[firm_charge_offset:firm_charge_offset + n] = (
        system + throughput_cost_gbp_per_mwh
    ) * dt
    objective[firm_discharge_offset:firm_discharge_offset + n] = (
        -system + throughput_cost_gbp_per_mwh
    ) * dt
    objective[arb_charge_offset:arb_charge_offset + n] = (
        market_price + throughput_cost_gbp_per_mwh
    ) * dt
    objective[arb_discharge_offset:arb_discharge_offset + n] = (
        -market_price + throughput_cost_gbp_per_mwh
    ) * dt

    lower = np.zeros(variable_count, dtype=float)
    upper = np.full(variable_count, np.inf, dtype=float)
    for t, value in enumerate(error):
        upper[firm_charge_offset + t] = min(max(float(value), 0.0), battery.power_mw)
        upper[firm_discharge_offset + t] = min(max(float(-value), 0.0), battery.power_mw)
    upper[arb_charge_offset:arb_charge_offset + n] = battery.power_mw
    upper[arb_discharge_offset:arb_discharge_offset + n] = battery.power_mw
    lower[soc_offset:soc_offset + n] = battery.minimum_soc_mwh
    upper[soc_offset:soc_offset + n] = battery.maximum_soc_mwh
    upper[mode_offset:mode_offset + n] = 1.0

    a_eq = np.zeros((n + 1, variable_count), dtype=float)
    b_eq = np.zeros(n + 1, dtype=float)
    for t in range(n):
        a_eq[t, soc_offset + t] = 1.0
        a_eq[t, firm_charge_offset + t] = -eta_c * dt
        a_eq[t, arb_charge_offset + t] = -eta_c * dt
        a_eq[t, firm_discharge_offset + t] = dt / eta_d
        a_eq[t, arb_discharge_offset + t] = dt / eta_d
        if t == 0:
            b_eq[t] = battery.initial_soc_mwh
        else:
            a_eq[t, soc_offset + t - 1] = -1.0
    a_eq[n, soc_offset + n - 1] = 1.0
    b_eq[n] = battery.initial_soc_mwh
    a_mode = np.zeros((2 * n, variable_count), dtype=float)
    mode_upper = np.zeros(2 * n, dtype=float)
    for t in range(n):
        a_mode[2 * t, firm_charge_offset + t] = 1.0
        a_mode[2 * t, arb_charge_offset + t] = 1.0
        a_mode[2 * t, mode_offset + t] = battery.power_mw
        mode_upper[2 * t] = battery.power_mw
        a_mode[2 * t + 1, firm_discharge_offset + t] = 1.0
        a_mode[2 * t + 1, arb_discharge_offset + t] = 1.0
        a_mode[2 * t + 1, mode_offset + t] = -battery.power_mw
        mode_upper[2 * t + 1] = 0.0
    constraints = [
        LinearConstraint(a_eq, b_eq, b_eq),
        LinearConstraint(a_mode, np.full(2 * n, -np.inf), mode_upper),
    ]
    integrality = np.zeros(variable_count, dtype=int)
    integrality[mode_offset:mode_offset + n] = 1
    solution = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"disp": False},
    )
    if not solution.success:
        raise RuntimeError(f"Firming/arbitrage co-optimisation failed: {solution.message}")
    x = solution.x
    firm_charge = x[firm_charge_offset:firm_charge_offset + n]
    firm_discharge = x[firm_discharge_offset:firm_discharge_offset + n]
    arb_charge = x[arb_charge_offset:arb_charge_offset + n]
    arb_discharge = x[arb_discharge_offset:arb_discharge_offset + n]
    soc_end = x[soc_offset:soc_offset + n]
    tolerance = 1e-8
    for values in (firm_charge, firm_discharge, arb_charge, arb_discharge):
        values[np.abs(values) < tolerance] = 0.0
    total_charge = firm_charge + arb_charge
    total_discharge = firm_discharge + arb_discharge
    if ((total_charge > tolerance) & (total_discharge > tolerance)).any():
        raise AssertionError("Co-optimiser charged and discharged simultaneously.")
    if (total_charge > battery.power_mw + tolerance).any() or (
        total_discharge > battery.power_mw + tolerance
    ).any():
        raise AssertionError("Co-optimiser exceeded battery power.")
    if abs(float(soc_end[-1]) - battery.initial_soc_mwh) > 1e-6:
        raise AssertionError("Co-optimiser violated terminal SOC equality.")

    residual = error - firm_charge + firm_discharge
    if (np.abs(residual) > np.abs(error) + tolerance).any():
        raise AssertionError("Co-optimiser amplified the renewable forecast deviation.")
    firming_value = float(
        ((firm_discharge - firm_charge) * system * dt).sum()
    )
    arbitrage_value = float(
        ((arb_discharge - arb_charge) * market_price * dt).sum()
    )
    throughput_mwh = float((total_charge + total_discharge).sum() * dt)
    throughput_cost = throughput_mwh * throughput_cost_gbp_per_mwh
    net_value = firming_value + arbitrage_value - throughput_cost
    absolute_before = float(np.abs(error).sum() * dt)
    absolute_after = float(np.abs(residual).sum() * dt)

    frame["coopt_firm_charge_mw"] = firm_charge
    frame["coopt_firm_discharge_mw"] = firm_discharge
    frame["coopt_arbitrage_charge_mw"] = arb_charge
    frame["coopt_arbitrage_discharge_mw"] = arb_discharge
    frame["coopt_total_charge_mw"] = total_charge
    frame["coopt_total_discharge_mw"] = total_discharge
    frame["coopt_soc_end_mwh"] = soc_end
    frame["coopt_residual_error_mw"] = residual
    summary: dict[str, Any] = {
        "method": "ex_post_cooptimised_system_price_firming_and_market_index_arbitrage",
        "perfect_information": True,
        "period_count": int(n),
        "firming_settlement_value_gbp": firming_value,
        "wholesale_arbitrage_value_gbp": arbitrage_value,
        "throughput_mwh": throughput_mwh,
        "throughput_cost_gbp": float(throughput_cost),
        "net_cooptimised_value_gbp": float(net_value),
        "absolute_error_before_mwh": absolute_before,
        "absolute_error_after_mwh": absolute_after,
        "error_reduction_pct": (
            100.0 * (1.0 - absolute_after / absolute_before)
            if absolute_before > 0 else 0.0
        ),
        "ending_soc_pct": float(100.0 * soc_end[-1] / battery.energy_capacity_mwh),
        "solver_status": str(solution.message),
    }
    return frame, summary


def evaluate_arbitrage_schedule(
    schedule: pd.DataFrame,
    realised_market_prices: pd.DataFrame,
    throughput_cost_gbp_per_mwh: float = 0.0,
) -> dict[str, Any]:
    """Evaluate a pre-computed arbitrage schedule against realised Market Index prices."""
    if throughput_cost_gbp_per_mwh < 0 or not np.isfinite(throughput_cost_gbp_per_mwh):
        raise ValueError("Throughput cost must be finite and non-negative.")
    required_schedule = {
        "settlement_period", "arbitrage_charge_mw", "arbitrage_discharge_mw"
    }
    missing = sorted(required_schedule.difference(schedule.columns))
    if missing:
        raise ValueError(f"Arbitrage schedule is missing columns: {missing}")
    required_price = {"settlement_period", "market_index_price_gbp_per_mwh"}
    missing = sorted(required_price.difference(realised_market_prices.columns))
    if missing:
        raise ValueError(f"Realised market prices are missing columns: {missing}")
    prices = realised_market_prices[list(required_price)].copy()
    if prices["settlement_period"].duplicated().any():
        raise ValueError("Realised market prices contain duplicate settlement periods.")
    frame = schedule[[
        "settlement_period", "arbitrage_charge_mw", "arbitrage_discharge_mw"
    ]].merge(prices, on="settlement_period", how="left", validate="one_to_one")
    if frame["market_index_price_gbp_per_mwh"].isna().any():
        raise ValueError("Realised market-price join produced missing values.")
    dt = 0.5
    charge_mwh = frame["arbitrage_charge_mw"].to_numpy(float) * dt
    discharge_mwh = frame["arbitrage_discharge_mw"].to_numpy(float) * dt
    price = frame["market_index_price_gbp_per_mwh"].to_numpy(float)
    purchase_cost = float((charge_mwh * price).sum())
    sale_revenue = float((discharge_mwh * price).sum())
    throughput = float(charge_mwh.sum() + discharge_mwh.sum())
    throughput_cost = throughput * float(throughput_cost_gbp_per_mwh)
    gross = sale_revenue - purchase_cost
    return {
        "realised_purchase_cost_gbp": purchase_cost,
        "realised_sale_revenue_gbp": sale_revenue,
        "realised_gross_arbitrage_margin_gbp": float(gross),
        "throughput_mwh": throughput,
        "throughput_cost_gbp": float(throughput_cost),
        "realised_net_arbitrage_margin_gbp": float(gross - throughput_cost),
    }
