"""Quick Reserve availability stacking with a physically shared BESS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from .battery import BatteryConfig


@dataclass(frozen=True)
class QuickReserveStackingConfig:
    """Screening assumptions for QR availability plus wholesale arbitrage."""

    throughput_cost_gbp_per_mwh: float = 2.0
    crossover_guard_windows: int = 2
    enable_arbitrage: bool = True

    def __post_init__(self) -> None:
        if not np.isfinite(float(self.throughput_cost_gbp_per_mwh)):
            raise ValueError("QR throughput cost must be finite.")
        if self.throughput_cost_gbp_per_mwh < 0:
            raise ValueError("QR throughput cost cannot be negative.")
        if self.crossover_guard_windows <= 0:
            raise ValueError("QR crossover guard must cover at least one window.")


def _pivot_quick_reserve(qr: pd.DataFrame) -> pd.DataFrame:
    required = {
        "delivery_start_utc", "product", "cleared_volume_mw",
        "clearing_price_gbp_per_mw_per_hour", "window_hours",
    }
    missing = sorted(required.difference(qr.columns))
    if missing:
        raise ValueError(f"Quick Reserve frame is missing columns: {missing}")
    work = qr.copy()
    work["delivery_start_utc"] = pd.to_datetime(work["delivery_start_utc"], utc=True)
    if work.duplicated(["delivery_start_utc", "product"]).any():
        raise ValueError("Quick Reserve frame contains duplicate product/windows.")
    price = work.pivot(
        index="delivery_start_utc", columns="product",
        values="clearing_price_gbp_per_mw_per_hour",
    ).rename(columns={"PQR": "pqr_price", "NQR": "nqr_price"})
    volume = work.pivot(
        index="delivery_start_utc", columns="product", values="cleared_volume_mw",
    ).rename(columns={"PQR": "pqr_volume", "NQR": "nqr_volume"})
    window = work.groupby("delivery_start_utc")["window_hours"].first().rename("window_hours")
    result = price.join(volume).join(window).reset_index()
    required_pivot = {"pqr_price", "nqr_price", "pqr_volume", "nqr_volume"}
    if required_pivot.difference(result.columns) or result[list(required_pivot)].isna().any().any():
        raise ValueError("Both PQR and NQR results are required for every modelled window.")
    return result.sort_values("delivery_start_utc").reset_index(drop=True)


def optimise_arbitrage_and_quick_reserve(
    market_prices: pd.DataFrame,
    quick_reserve: pd.DataFrame,
    battery: BatteryConfig,
    config: QuickReserveStackingConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Co-optimise wholesale schedule and QR availability capacity.

    Availability is valued at realised EAC pay-as-clear prices. Utilisation energy
    and utilisation payments are intentionally excluded from this first packet.
    """
    cfg = config or QuickReserveStackingConfig()
    required_market = {"valid_time_utc", "market_index_price_gbp_per_mwh"}
    missing = sorted(required_market.difference(market_prices.columns))
    if missing:
        raise ValueError(f"Market-price frame is missing QR stacking columns: {missing}")
    market = market_prices.copy()
    market["valid_time_utc"] = pd.to_datetime(market["valid_time_utc"], utc=True)
    market = market.sort_values("valid_time_utc").reset_index(drop=True)
    qr = _pivot_quick_reserve(quick_reserve)
    frame = market.merge(
        qr, left_on="valid_time_utc", right_on="delivery_start_utc",
        how="left", validate="one_to_one",
    )
    if frame[["pqr_price", "nqr_price", "pqr_volume", "nqr_volume"]].isna().any().any():
        raise ValueError("Quick Reserve join produced missing auction windows.")
    prices = pd.to_numeric(frame["market_index_price_gbp_per_mwh"], errors="raise").to_numpy(float)
    pqr_price = pd.to_numeric(frame["pqr_price"], errors="raise").to_numpy(float)
    nqr_price = pd.to_numeric(frame["nqr_price"], errors="raise").to_numpy(float)
    pqr_volume = pd.to_numeric(frame["pqr_volume"], errors="raise").to_numpy(float)
    nqr_volume = pd.to_numeric(frame["nqr_volume"], errors="raise").to_numpy(float)
    window_hours = pd.to_numeric(frame["window_hours"], errors="raise").to_numpy(float)
    if not np.allclose(window_hours, battery.interval_hours, atol=1e-9):
        raise ValueError("QR windows must align with the battery interval duration.")
    n = len(frame)
    dt = battery.interval_hours
    eta_c = battery.charge_efficiency
    eta_d = battery.discharge_efficiency
    charge_offset = 0
    discharge_offset = n
    pqr_offset = 2 * n
    nqr_offset = 3 * n
    soc_offset = 4 * n
    mode_offset = 5 * n
    variable_count = 6 * n

    objective = np.zeros(variable_count, dtype=float)
    objective[charge_offset:charge_offset + n] = (
        prices + cfg.throughput_cost_gbp_per_mwh
    ) * dt
    objective[discharge_offset:discharge_offset + n] = (
        -prices + cfg.throughput_cost_gbp_per_mwh
    ) * dt
    objective[pqr_offset:pqr_offset + n] = -pqr_price * dt
    objective[nqr_offset:nqr_offset + n] = -nqr_price * dt
    lower = np.zeros(variable_count, dtype=float)
    upper = np.full(variable_count, np.inf, dtype=float)
    arbitrage_power = battery.power_mw if cfg.enable_arbitrage else 0.0
    upper[charge_offset:charge_offset + n] = arbitrage_power
    upper[discharge_offset:discharge_offset + n] = arbitrage_power
    upper[pqr_offset:pqr_offset + n] = np.minimum(pqr_volume, battery.power_mw)
    upper[nqr_offset:nqr_offset + n] = np.minimum(nqr_volume, battery.power_mw)
    lower[soc_offset:soc_offset + n] = battery.minimum_soc_mwh
    upper[soc_offset:soc_offset + n] = battery.maximum_soc_mwh
    upper[mode_offset:mode_offset + n] = 1.0

    equality = np.zeros((n + 1, variable_count), dtype=float)
    rhs = np.zeros(n + 1, dtype=float)
    for t in range(n):
        equality[t, soc_offset + t] = 1.0
        equality[t, charge_offset + t] = -eta_c * dt
        equality[t, discharge_offset + t] = dt / eta_d
        if t == 0:
            rhs[t] = battery.initial_soc_mwh
        else:
            equality[t, soc_offset + t - 1] = -1.0
    equality[n, soc_offset + n - 1] = 1.0
    rhs[n] = battery.initial_soc_mwh

    rows = []
    row_upper = []
    for t in range(n):
        # Conservative headroom: scheduled charging does not count toward PQR capability,
        # and scheduled discharging does not count toward NQR capability.
        up = np.zeros(variable_count, dtype=float)
        up[discharge_offset + t] = 1.0
        up[pqr_offset + t] = 1.0
        rows.append(up)
        row_upper.append(battery.power_mw)
        down = np.zeros(variable_count, dtype=float)
        down[charge_offset + t] = 1.0
        down[nqr_offset + t] = 1.0
        rows.append(down)
        row_upper.append(battery.power_mw)

        split = np.zeros(variable_count, dtype=float)
        split[pqr_offset + t] = 1.0
        split[nqr_offset + t] = 1.0
        rows.append(split)
        row_upper.append(battery.power_mw)

        charge_mode = np.zeros(variable_count, dtype=float)
        charge_mode[charge_offset + t] = 1.0
        charge_mode[mode_offset + t] = battery.power_mw
        rows.append(charge_mode)
        row_upper.append(battery.power_mw)
        discharge_mode = np.zeros(variable_count, dtype=float)
        discharge_mode[discharge_offset + t] = 1.0
        discharge_mode[mode_offset + t] = -battery.power_mw
        rows.append(discharge_mode)
        row_upper.append(0.0)
    guard = min(cfg.crossover_guard_windows, n)
    for t in range(n):
        end = min(n - 1, t + guard - 1)
        pqr_energy = np.zeros(variable_count, dtype=float)
        for j in range(t, end + 1):
            pqr_energy[pqr_offset + j] = dt / eta_d
        pqr_energy[soc_offset + end] = -1.0
        rows.append(pqr_energy)
        row_upper.append(-battery.minimum_soc_mwh)

        nqr_energy = np.zeros(variable_count, dtype=float)
        for j in range(t, end + 1):
            nqr_energy[nqr_offset + j] = eta_c * dt
        nqr_energy[soc_offset + end] = 1.0
        rows.append(nqr_energy)
        row_upper.append(battery.maximum_soc_mwh)

    inequality = np.vstack(rows)
    constraints = [
        LinearConstraint(equality, rhs, rhs),
        LinearConstraint(
            inequality,
            np.full(len(row_upper), -np.inf),
            np.asarray(row_upper, dtype=float),
        ),
    ]
    integrality = np.zeros(variable_count, dtype=int)
    integrality[pqr_offset:pqr_offset + n] = 1
    integrality[nqr_offset:nqr_offset + n] = 1
    integrality[mode_offset:mode_offset + n] = 1
    solution = milp(
        c=objective,
        integrality=integrality,
        bounds=Bounds(lower, upper),
        constraints=constraints,
        options={"disp": False},
    )
    if not solution.success:
        raise RuntimeError(f"Quick Reserve stacking optimisation failed: {solution.message}")
    x = solution.x
    charge = x[charge_offset:charge_offset + n]
    discharge = x[discharge_offset:discharge_offset + n]
    pqr = np.rint(x[pqr_offset:pqr_offset + n])
    nqr = np.rint(x[nqr_offset:nqr_offset + n])
    soc_end = x[soc_offset:soc_offset + n]
    tolerance = 1e-7
    for values in (charge, discharge, pqr, nqr):
        values[np.abs(values) < tolerance] = 0.0
    if ((charge > tolerance) & (discharge > tolerance)).any():
        raise AssertionError("QR stacking charged and discharged simultaneously.")
    if abs(float(soc_end[-1]) - battery.initial_soc_mwh) > 1e-5:
        raise AssertionError("QR stacking violated terminal SOC equality.")
    if ((pqr > 0) & (pqr < 1 - tolerance)).any() or ((nqr > 0) & (nqr < 1 - tolerance)).any():
        raise AssertionError("QR contract volume fell below the 1 MW minimum.")
    charge_energy = charge * dt
    discharge_energy = discharge * dt
    arbitrage_purchase = float((charge_energy * prices).sum())
    arbitrage_sale = float((discharge_energy * prices).sum())
    throughput_mwh = float(charge_energy.sum() + discharge_energy.sum())
    throughput_cost = throughput_mwh * cfg.throughput_cost_gbp_per_mwh
    arbitrage_margin = arbitrage_sale - arbitrage_purchase - throughput_cost
    pqr_payment = float((pqr * pqr_price * dt).sum())
    nqr_payment = float((nqr * nqr_price * dt).sum())
    availability_payment = pqr_payment + nqr_payment
    net_value = arbitrage_margin + availability_payment

    frame["qr_arbitrage_charge_mw"] = charge
    frame["qr_arbitrage_discharge_mw"] = discharge
    frame["pqr_contracted_mw"] = pqr
    frame["nqr_contracted_mw"] = nqr
    frame["qr_soc_end_mwh"] = soc_end
    frame["qr_availability_payment_gbp"] = (
        pqr * pqr_price * dt + nqr * nqr_price * dt
    )
    frame["qr_arbitrage_cashflow_gbp"] = (
        discharge_energy - charge_energy
    ) * prices
    summary: dict[str, Any] = {
        "method": "price_taker_quick_reserve_availability_plus_wholesale_arbitrage",
        "perfect_information": True,
        "availability_only": True,
        "utilisation_revenue_included": False,
        "period_count": int(n),
        "crossover_guard_windows": int(cfg.crossover_guard_windows),
        "minimum_contract_mw": 1,
        "pqr_contracted_mw_hours": float((pqr * dt).sum()),
        "nqr_contracted_mw_hours": float((nqr * dt).sum()),
        "pqr_availability_payment_gbp": pqr_payment,
        "nqr_availability_payment_gbp": nqr_payment,
        "total_availability_payment_gbp": float(availability_payment),
        "arbitrage_margin_after_throughput_cost_gbp": float(arbitrage_margin),
        "throughput_mwh": throughput_mwh,
        "throughput_cost_gbp": float(throughput_cost),
        "net_stacked_value_gbp": float(net_value),
        "ending_soc_pct": float(100.0 * soc_end[-1] / battery.energy_capacity_mwh),
        "assumption": "asset is a price taker accepted at the observed clearing price; utilisation excluded",
        "solver_status": str(solution.message),
    }
    return frame, summary
