"""Stage 20 stochastic wholesale + Balancing Mechanism screening optimiser.

The optimiser uses a finite scenario set. Wholesale schedules and BM reserve offers
are chosen before the realised scenario is known; scenario-specific SOC then reflects
accepted BM activation. BM prices/probabilities in the generic UI are user scenarios,
not claims about actual BOA acceptance or settlement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from .battery import BatteryConfig


@dataclass(frozen=True)
class StochasticBiddingConfig:
    throughput_cost_gbp_per_mwh: float = 0.0
    terminal_restoration_price_gbp_per_mwh: float = 100.0
    cvar_alpha: float = 0.90
    risk_aversion: float = 0.20

    def __post_init__(self) -> None:
        values = [
            self.throughput_cost_gbp_per_mwh,
            self.terminal_restoration_price_gbp_per_mwh,
            self.cvar_alpha,
            self.risk_aversion,
        ]
        if not all(np.isfinite(float(v)) for v in values):
            raise ValueError("Stochastic bidding assumptions must be finite.")
        if self.throughput_cost_gbp_per_mwh < 0:
            raise ValueError("Throughput cost cannot be negative.")
        if self.terminal_restoration_price_gbp_per_mwh < 0:
            raise ValueError("Restoration price cannot be negative.")
        if not 0 < self.cvar_alpha < 1:
            raise ValueError("CVaR alpha must lie in (0, 1).")
        if self.risk_aversion < 0:
            raise ValueError("Risk aversion cannot be negative.")


def build_stochastic_market_scenarios(
    base_prices: pd.DataFrame,
    *,
    scenario_count: int = 7,
    wholesale_sigma_gbp_per_mwh: float = 20.0,
    bm_up_probability: float = 0.15,
    bm_down_probability: float = 0.15,
    bm_up_value_gbp_per_mwh: float = 140.0,
    bm_down_value_gbp_per_mwh: float = 80.0,
    seed: int = 42,
) -> pd.DataFrame:
    required = {"settlement_period", "forecast_market_index_price_gbp_per_mwh"}
    missing = sorted(required.difference(base_prices.columns))
    if missing:
        raise ValueError(f"Base market forecast is missing columns: {missing}")
    if scenario_count < 3:
        raise ValueError("At least three scenarios are required.")
    if wholesale_sigma_gbp_per_mwh < 0 or not np.isfinite(wholesale_sigma_gbp_per_mwh):
        raise ValueError("Wholesale sigma must be finite and non-negative.")
    for p in (bm_up_probability, bm_down_probability):
        if not 0 <= p <= 1:
            raise ValueError("BM activation probabilities must lie in [0, 1].")
    if bm_up_probability + bm_down_probability > 1:
        raise ValueError("Up/down BM activation probabilities cannot sum above one.")
    frame = base_prices.sort_values("settlement_period").reset_index(drop=True)
    base = pd.to_numeric(frame["forecast_market_index_price_gbp_per_mwh"], errors="raise").to_numpy(float)
    if not np.isfinite(base).all():
        raise ValueError("Base market forecast contains non-finite prices.")
    rng = np.random.default_rng(seed)
    records: list[pd.DataFrame] = []
    for scenario in range(scenario_count):
        shocks = rng.normal(0.0, wholesale_sigma_gbp_per_mwh, len(frame))
        for t in range(1, len(shocks)):
            shocks[t] = 0.65 * shocks[t-1] + np.sqrt(1-0.65**2) * shocks[t]
        draw = rng.random(len(frame))
        up = draw < bm_up_probability
        down = (draw >= bm_up_probability) & (draw < bm_up_probability + bm_down_probability)
        block = pd.DataFrame({
            "scenario_id": scenario,
            "scenario_probability": 1.0 / scenario_count,
            "settlement_period": frame["settlement_period"].to_numpy(int),
            "wholesale_price_gbp_per_mwh": base + shocks,
            "bm_up_accepted": up.astype(int),
            "bm_down_accepted": down.astype(int),
            "bm_up_value_gbp_per_mwh": float(bm_up_value_gbp_per_mwh),
            "bm_down_value_gbp_per_mwh": float(bm_down_value_gbp_per_mwh),
        })
        records.append(block)
    return pd.concat(records, ignore_index=True)


def optimise_stochastic_wholesale_bm(
    scenarios: pd.DataFrame,
    battery: BatteryConfig,
    config: StochasticBiddingConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Choose one pre-delivery wholesale schedule and BM reserve offer across scenarios."""
    cfg = config or StochasticBiddingConfig()
    required = {
        "scenario_id", "scenario_probability", "settlement_period",
        "wholesale_price_gbp_per_mwh", "bm_up_accepted", "bm_down_accepted",
        "bm_up_value_gbp_per_mwh", "bm_down_value_gbp_per_mwh",
    }
    missing = sorted(required.difference(scenarios.columns))
    if missing:
        raise ValueError(f"Stochastic scenario frame is missing columns: {missing}")
    if scenarios.empty:
        raise ValueError("Stochastic scenario frame is empty.")
    frame = scenarios.copy()
    ids = list(pd.unique(frame["scenario_id"]))
    ids = sorted(ids, key=str)
    periods = sorted(pd.unique(frame["settlement_period"]).astype(int).tolist())
    n, m = len(periods), len(ids)
    if n == 0 or m < 2:
        raise ValueError("Stochastic optimisation needs periods and at least two scenarios.")
    period_index = {sp: i for i, sp in enumerate(periods)}
    scenario_index = {sid: i for i, sid in enumerate(ids)}
    probs = np.zeros(m, dtype=float)
    price = np.zeros((m, n), dtype=float)
    up_acc = np.zeros((m, n), dtype=float)
    down_acc = np.zeros((m, n), dtype=float)
    up_value = np.zeros((m, n), dtype=float)
    down_value = np.zeros((m, n), dtype=float)
    for sid in ids:
        block = frame.loc[frame["scenario_id"] == sid].copy()
        if set(block["settlement_period"].astype(int)) != set(periods):
            raise ValueError("Every scenario must contain the same settlement periods.")
        block = block.sort_values("settlement_period")
        s = scenario_index[sid]
        pvals = pd.unique(block["scenario_probability"])
        if len(pvals) != 1:
            raise ValueError("Scenario probability must be constant within a scenario.")
        probs[s] = float(pvals[0])
        price[s, :] = pd.to_numeric(block["wholesale_price_gbp_per_mwh"], errors="raise").to_numpy(float)
        up_acc[s, :] = pd.to_numeric(block["bm_up_accepted"], errors="raise").to_numpy(float)
        down_acc[s, :] = pd.to_numeric(block["bm_down_accepted"], errors="raise").to_numpy(float)
        up_value[s, :] = pd.to_numeric(block["bm_up_value_gbp_per_mwh"], errors="raise").to_numpy(float)
        down_value[s, :] = pd.to_numeric(block["bm_down_value_gbp_per_mwh"], errors="raise").to_numpy(float)
    if not np.isfinite(np.column_stack([price.ravel(), up_acc.ravel(), down_acc.ravel(), up_value.ravel(), down_value.ravel()])).all():
        raise ValueError("Stochastic scenario frame contains non-finite values.")
    if (probs < 0).any() or not np.isclose(probs.sum(), 1.0, atol=1e-8):
        raise ValueError("Scenario probabilities must be non-negative and sum to one.")
    if ((up_acc < 0) | (up_acc > 1) | (down_acc < 0) | (down_acc > 1)).any():
        raise ValueError("BM activation indicators must lie in [0, 1].")

    dt = battery.interval_hours
    eta_c, eta_d = battery.charge_efficiency, battery.discharge_efficiency
    charge_o = 0
    discharge_o = n
    up_o = 2*n
    down_o = 3*n
    mode_o = 4*n
    soc_o = 5*n
    term_pos_o = soc_o + m*n
    term_neg_o = term_pos_o + m
    eta_idx = term_neg_o + m
    z_o = eta_idx + 1
    variable_count = z_o + m
    cost_vectors = np.zeros((m, variable_count), dtype=float)
    for s in range(m):
        cost_vectors[s, charge_o:charge_o+n] = (price[s] + cfg.throughput_cost_gbp_per_mwh) * dt
        cost_vectors[s, discharge_o:discharge_o+n] = (-price[s] + cfg.throughput_cost_gbp_per_mwh) * dt
        cost_vectors[s, up_o:up_o+n] = up_acc[s] * (cfg.throughput_cost_gbp_per_mwh - up_value[s]) * dt
        cost_vectors[s, down_o:down_o+n] = down_acc[s] * (cfg.throughput_cost_gbp_per_mwh - down_value[s]) * dt
        cost_vectors[s, term_pos_o+s] = cfg.terminal_restoration_price_gbp_per_mwh
        cost_vectors[s, term_neg_o+s] = cfg.terminal_restoration_price_gbp_per_mwh

    objective = np.sum(probs[:, None] * cost_vectors, axis=0)
    objective[eta_idx] += cfg.risk_aversion
    objective[z_o:z_o+m] += cfg.risk_aversion * probs / (1.0 - cfg.cvar_alpha)

    lower = np.zeros(variable_count, dtype=float)
    upper = np.full(variable_count, np.inf, dtype=float)
    for offset in (charge_o, discharge_o, up_o, down_o):
        upper[offset:offset+n] = battery.power_mw
    upper[mode_o:mode_o+n] = 1.0
    for s in range(m):
        start = soc_o + s*n
        lower[start:start+n] = battery.minimum_soc_mwh
        upper[start:start+n] = battery.maximum_soc_mwh
    terminal_cap = battery.energy_capacity_mwh
    upper[term_pos_o:term_pos_o+m] = terminal_cap
    upper[term_neg_o:term_neg_o+m] = terminal_cap
    lower[eta_idx] = -1e9
    upper[eta_idx] = 1e9
    upper[z_o:z_o+m] = 1e9

    integrality = np.zeros(variable_count, dtype=int)
    integrality[mode_o:mode_o+n] = 1
    eq_rows: list[np.ndarray] = []
    eq_rhs: list[float] = []
    for s in range(m):
        for t in range(n):
            row = np.zeros(variable_count, dtype=float)
            row[soc_o + s*n + t] = 1.0
            if t > 0:
                row[soc_o + s*n + t - 1] = -1.0
                rhs = 0.0
            else:
                rhs = battery.initial_soc_mwh
            row[charge_o+t] = -eta_c * dt
            row[down_o+t] = -eta_c * dt * down_acc[s, t]
            row[discharge_o+t] = dt / eta_d
            row[up_o+t] = dt / eta_d * up_acc[s, t]
            eq_rows.append(row)
            eq_rhs.append(rhs)
        terminal = np.zeros(variable_count, dtype=float)
        terminal[soc_o + s*n + n - 1] = 1.0
        terminal[term_pos_o+s] = -1.0
        terminal[term_neg_o+s] = 1.0
        eq_rows.append(terminal)
        eq_rhs.append(battery.initial_soc_mwh)

    ub_rows: list[np.ndarray] = []
    ub_rhs: list[float] = []
    for t in range(n):
        charge_side = np.zeros(variable_count, dtype=float)
        charge_side[charge_o+t] = 1.0
        charge_side[down_o+t] = 1.0
        charge_side[mode_o+t] = battery.power_mw
        ub_rows.append(charge_side)
        ub_rhs.append(battery.power_mw)
        discharge_side = np.zeros(variable_count, dtype=float)
        discharge_side[discharge_o+t] = 1.0
        discharge_side[up_o+t] = 1.0
        discharge_side[mode_o+t] = -battery.power_mw
        ub_rows.append(discharge_side)
        ub_rhs.append(0.0)
    for s in range(m):
        row = cost_vectors[s].copy()
        row[eta_idx] -= 1.0
        row[z_o+s] -= 1.0
        ub_rows.append(row)
        ub_rhs.append(0.0)

    constraints = [
        LinearConstraint(np.vstack(eq_rows), np.asarray(eq_rhs), np.asarray(eq_rhs)),
        LinearConstraint(np.vstack(ub_rows), np.full(len(ub_rows), -np.inf), np.asarray(ub_rhs)),
    ]
    solution = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"disp": False},
    )
    if not solution.success:
        raise RuntimeError(f"Stochastic wholesale/BM optimisation failed: {solution.message}")
    x = solution.x
    charge = x[charge_o:charge_o+n]
    discharge = x[discharge_o:discharge_o+n]
    up_offer = x[up_o:up_o+n]
    down_offer = x[down_o:down_o+n]
    tolerance = 1e-7
    for values in (charge, discharge, up_offer, down_offer):
        values[np.abs(values) < tolerance] = 0.0
    if ((charge + down_offer > battery.power_mw + tolerance) |
        (discharge + up_offer > battery.power_mw + tolerance)).any():
        raise AssertionError("Stochastic optimiser exceeded reserved battery power.")
    if ((charge > tolerance) & (discharge > tolerance)).any():
        raise AssertionError("Stochastic optimiser scheduled simultaneous base charge/discharge.")

    scenario_costs = cost_vectors @ x
    scenario_values = -scenario_costs
    expected_value = float(np.dot(probs, scenario_values))
    eta_value = float(x[eta_idx])
    cvar_loss = float(eta_value + np.dot(probs, np.maximum(scenario_costs - eta_value, 0.0)) / (1.0-cfg.cvar_alpha))
    order = np.argsort(scenario_values)
    sorted_values = scenario_values[order]
    sorted_probs = probs[order]
    cumulative = np.cumsum(sorted_probs)
    def weighted_q(q: float) -> float:
        return float(sorted_values[min(int(np.searchsorted(cumulative, q, side="left")), m-1)])

    expected_up_accept = probs @ up_acc
    expected_down_accept = probs @ down_acc
    soc_matrix = np.vstack([
        x[soc_o+s*n:soc_o+(s+1)*n] for s in range(m)
    ])
    schedule = pd.DataFrame({
        "settlement_period": periods,
        "wholesale_charge_mw": charge,
        "wholesale_discharge_mw": discharge,
        "bm_up_offer_mw": up_offer,
        "bm_down_offer_mw": down_offer,
        "expected_bm_up_accepted_mw": up_offer * expected_up_accept,
        "expected_bm_down_accepted_mw": down_offer * expected_down_accept,
        "expected_soc_mwh": probs @ soc_matrix,
    })
    summary: dict[str, Any] = {
        "method": "finite_scenario_pre_delivery_wholesale_plus_bm_screen",
        "perfect_information": False,
        "scenario_count": int(m),
        "period_count": int(n),
        "expected_net_value_gbp": expected_value,
        "p10_net_value_gbp": weighted_q(0.10),
        "p50_net_value_gbp": weighted_q(0.50),
        "p90_net_value_gbp": weighted_q(0.90),
        "cvar_alpha": float(cfg.cvar_alpha),
        "cvar_loss_gbp": cvar_loss,
        "risk_aversion": float(cfg.risk_aversion),
        "risk_adjusted_objective_gbp": float(-solution.fun),
        "throughput_cost_gbp_per_mwh": float(cfg.throughput_cost_gbp_per_mwh),
        "average_bm_up_offer_mw": float(up_offer.mean()),
        "average_bm_down_offer_mw": float(down_offer.mean()),
        "expected_bm_up_activation_mwh": float((up_offer * expected_up_accept).sum() * dt),
        "expected_bm_down_activation_mwh": float((down_offer * expected_down_accept).sum() * dt),
        "scenario_net_values_gbp": [float(v) for v in scenario_values],
        "solver_status": str(solution.message),
        "bm_boundary": "user_scenario_activation_values_and_probabilities_not_actual_boa_forecast_or_settlement",
    }
    return schedule, summary
