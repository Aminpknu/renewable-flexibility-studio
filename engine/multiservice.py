"""Conservative shared-BESS co-optimisation across current NESO EAC service families."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from .battery import BatteryConfig


DEFAULT_FAMILIES = (
    "Quick Reserve", "Slow Reserve", "Dynamic Containment",
    "Dynamic Moderation", "Dynamic Regulation", "Balancing Reserve",
)


@dataclass(frozen=True)
class MultiServiceConfig:
    throughput_cost_gbp_per_mwh: float = 2.0
    enable_firming: bool = True
    enable_arbitrage: bool = True
    assume_bm_eligible: bool = False
    enabled_families: tuple[str, ...] = DEFAULT_FAMILIES
    complete_service_windows_only: bool = True

    def __post_init__(self) -> None:
        if not np.isfinite(float(self.throughput_cost_gbp_per_mwh)) or self.throughput_cost_gbp_per_mwh < 0:
            raise ValueError("Multi-service throughput cost must be finite and non-negative.")
        unknown = sorted(set(self.enabled_families).difference(DEFAULT_FAMILIES))
        if unknown:
            raise ValueError(f"Unknown NESO service families: {unknown}")


def _prepare_day(
    portfolio: pd.DataFrame,
    system_prices: pd.DataFrame,
    market_prices: pd.DataFrame,
) -> pd.DataFrame:
    required = {"settlement_period", "valid_time_utc", "actual_mw", "forecast_mw"}
    missing = sorted(required.difference(portfolio.columns))
    if missing:
        raise ValueError(f"Portfolio is missing multi-service columns: {missing}")
    frame = portfolio.copy().sort_values("settlement_period").reset_index(drop=True)
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True)
    for source, column, label in (
        (system_prices, "system_price_gbp_per_mwh", "System Price"),
        (market_prices, "market_index_price_gbp_per_mwh", "Market Index"),
    ):
        if {"settlement_period", column}.difference(source.columns):
            raise ValueError(f"{label} frame is missing required columns.")
        extra_columns = []
        if label == "Market Index":
            extra_columns = [
                candidate for candidate in ("soc_floor_mwh", "soc_ceiling_mwh")
                if candidate in source.columns
            ]
        selected = source[["settlement_period", column, *extra_columns]].copy()
        if selected["settlement_period"].duplicated().any():
            raise ValueError(f"{label} frame contains duplicate settlement periods.")
        frame = frame.merge(selected, on="settlement_period", how="left", validate="one_to_one")
    if frame[["system_price_gbp_per_mwh", "market_index_price_gbp_per_mwh"]].isna().any().any():
        raise ValueError("Multi-service price join produced missing values.")
    return frame


def _prepare_services(
    services: pd.DataFrame,
    period_starts: pd.Series,
    dt_hours: float,
    config: MultiServiceConfig,
) -> pd.DataFrame:
    required = {
        "product", "family", "direction", "delivery_start_utc", "delivery_end_utc",
        "cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour", "window_hours",
        "minimum_mw", "whole_mw", "bm_required", "energy_guard_hours",
    }
    missing = sorted(required.difference(services.columns))
    if missing:
        raise ValueError(f"NESO service frame is missing columns: {missing}")
    work = services.copy()
    work["delivery_start_utc"] = pd.to_datetime(work["delivery_start_utc"], utc=True)
    work["delivery_end_utc"] = pd.to_datetime(work["delivery_end_utc"], utc=True)
    start = pd.Timestamp(period_starts.min())
    end = pd.Timestamp(period_starts.max()) + pd.Timedelta(hours=dt_hours)
    overlap = work["delivery_end_utc"].gt(start) & work["delivery_start_utc"].lt(end)
    work = work.loc[overlap].copy()
    if config.complete_service_windows_only:
        work = work.loc[
            work["delivery_start_utc"].ge(start) & work["delivery_end_utc"].le(end)
        ].copy()
    work = work.loc[work["family"].isin(config.enabled_families)].copy()
    if not config.assume_bm_eligible:
        work = work.loc[~work["bm_required"].astype(bool)].copy()
    if work.empty:
        return work.reset_index(drop=True)
    if work.duplicated(["delivery_start_utc", "product"]).any():
        raise ValueError("NESO service day contains duplicate product windows.")
    if not set(work["direction"]).issubset({"upward", "downward"}):
        raise ValueError("NESO service direction must be upward/downward.")
    return work.sort_values(["delivery_start_utc", "product"]).reset_index(drop=True)


def optimise_firming_arbitrage_and_services(
    portfolio: pd.DataFrame,
    system_prices: pd.DataFrame,
    market_prices: pd.DataFrame,
    services: pd.DataFrame,
    battery: BatteryConfig,
    config: MultiServiceConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    cfg = config or MultiServiceConfig()
    frame = _prepare_day(portfolio, system_prices, market_prices)
    svc = _prepare_services(services, frame["valid_time_utc"], battery.interval_hours, cfg)
    n = len(frame)
    m = len(svc)
    dt = battery.interval_hours
    eta_c = battery.charge_efficiency
    eta_d = battery.discharge_efficiency
    actual = frame["actual_mw"].to_numpy(float)
    forecast = frame["forecast_mw"].to_numpy(float)
    error = actual - forecast
    system_price = frame["system_price_gbp_per_mwh"].to_numpy(float)
    market_price = frame["market_index_price_gbp_per_mwh"].to_numpy(float)

    firm_charge_offset = 0
    firm_discharge_offset = n
    arb_charge_offset = 2 * n
    arb_discharge_offset = 3 * n
    soc_offset = 4 * n
    mode_offset = 5 * n
    service_offset = 6 * n
    variable_count = 6 * n + m

    objective = np.zeros(variable_count, dtype=float)
    objective[firm_charge_offset:firm_charge_offset + n] = (
        system_price + cfg.throughput_cost_gbp_per_mwh
    ) * dt
    objective[firm_discharge_offset:firm_discharge_offset + n] = (
        -system_price + cfg.throughput_cost_gbp_per_mwh
    ) * dt
    objective[arb_charge_offset:arb_charge_offset + n] = (
        market_price + cfg.throughput_cost_gbp_per_mwh
    ) * dt
    objective[arb_discharge_offset:arb_discharge_offset + n] = (
        -market_price + cfg.throughput_cost_gbp_per_mwh
    ) * dt
    if m:
        objective[service_offset:] = -(
            svc["clearing_price_gbp_per_mw_per_hour"].to_numpy(float)
            * svc["window_hours"].to_numpy(float)
        )

    lower = np.zeros(variable_count, dtype=float)
    upper = np.full(variable_count, np.inf, dtype=float)
    for t, value in enumerate(error):
        upper[firm_charge_offset + t] = min(max(float(value), 0.0), battery.power_mw) if cfg.enable_firming else 0.0
        upper[firm_discharge_offset + t] = min(max(float(-value), 0.0), battery.power_mw) if cfg.enable_firming else 0.0
    arb_power = battery.power_mw if cfg.enable_arbitrage else 0.0
    upper[arb_charge_offset:arb_charge_offset + n] = arb_power
    upper[arb_discharge_offset:arb_discharge_offset + n] = arb_power
    lower[soc_offset:soc_offset + n] = battery.minimum_soc_mwh
    upper[soc_offset:soc_offset + n] = battery.maximum_soc_mwh
    if {"soc_floor_mwh", "soc_ceiling_mwh"}.issubset(frame.columns):
        corridor_floor = pd.to_numeric(frame["soc_floor_mwh"], errors="raise").to_numpy(float)
        corridor_ceiling = pd.to_numeric(frame["soc_ceiling_mwh"], errors="raise").to_numpy(float)
        if not np.isfinite(np.column_stack([corridor_floor, corridor_ceiling])).all():
            raise ValueError("Multi-service SOC corridor contains non-finite values.")
        corridor_floor = np.maximum(corridor_floor, battery.minimum_soc_mwh)
        corridor_ceiling = np.minimum(corridor_ceiling, battery.maximum_soc_mwh)
        if (corridor_floor > corridor_ceiling + 1e-9).any():
            raise ValueError("Multi-service SOC reserve corridor is infeasible.")
        lower[soc_offset:soc_offset + n] = corridor_floor
        upper[soc_offset:soc_offset + n] = corridor_ceiling
    upper[mode_offset:mode_offset + n] = 1.0
    if m:
        upper[service_offset:] = np.minimum(
            svc["cleared_volume_mw"].to_numpy(float), battery.power_mw
        )

    equality = np.zeros((n + 1, variable_count), dtype=float)
    rhs = np.zeros(n + 1, dtype=float)
    for t in range(n):
        equality[t, soc_offset + t] = 1.0
        equality[t, firm_charge_offset + t] = -eta_c * dt
        equality[t, arb_charge_offset + t] = -eta_c * dt
        equality[t, firm_discharge_offset + t] = dt / eta_d
        equality[t, arb_discharge_offset + t] = dt / eta_d
        if t == 0:
            rhs[t] = battery.initial_soc_mwh
        else:
            equality[t, soc_offset + t - 1] = -1.0
    equality[n, soc_offset + n - 1] = 1.0
    rhs[n] = battery.initial_soc_mwh

    # Current PSR transition rule: identical MW across each linked local-time window.
    link_rows: list[np.ndarray] = []
    if m and (svc["product"] == "PSR").any():
        psr = svc.loc[svc["product"].eq("PSR")].copy()
        local = psr["delivery_start_utc"].dt.tz_convert("Europe/London")
        minutes = local.dt.hour * 60 + local.dt.minute
        psr["local_date"] = local.dt.date
        psr["linked_block"] = np.select(
            [
                (minutes >= 360) & (minutes < 630),
                (minutes >= 630) & (minutes < 900),
                (minutes >= 900) & (minutes < 1260),
            ],
            ["morning", "midday", "evening"],
            default="unlinked",
        )
        for (_date, block), group in psr.loc[psr["linked_block"].ne("unlinked")].groupby(["local_date", "linked_block"]):
            indexes = group.index.tolist()
            if len(indexes) > 1:
                anchor = indexes[0]
                for j in indexes[1:]:
                    row = np.zeros(variable_count, dtype=float)
                    row[service_offset + j] = 1.0
                    row[service_offset + anchor] = -1.0
                    link_rows.append(row)
    if link_rows:
        equality = np.vstack([equality, *link_rows])
        rhs = np.concatenate([rhs, np.zeros(len(link_rows), dtype=float)])

    starts = frame["valid_time_utc"].tolist()
    active_by_period: list[list[int]] = []
    for start_time in starts:
        active: list[int] = []
        for j, row in svc.iterrows():
            if row["delivery_start_utc"] <= start_time < row["delivery_end_utc"]:
                active.append(j)
        active_by_period.append(active)

    rows: list[np.ndarray] = []
    row_upper: list[float] = []
    upward = svc["direction"].eq("upward").to_numpy(bool) if m else np.array([], dtype=bool)
    downward = svc["direction"].eq("downward").to_numpy(bool) if m else np.array([], dtype=bool)
    guards = svc["energy_guard_hours"].to_numpy(float) if m else np.array([], dtype=float)
    for t, active in enumerate(active_by_period):
        up = np.zeros(variable_count, dtype=float)
        up[firm_discharge_offset + t] = 1.0
        up[arb_discharge_offset + t] = 1.0
        for j in active:
            if upward[j]:
                up[service_offset + j] = 1.0
        rows.append(up)
        row_upper.append(battery.power_mw)

        down = np.zeros(variable_count, dtype=float)
        down[firm_charge_offset + t] = 1.0
        down[arb_charge_offset + t] = 1.0
        for j in active:
            if downward[j]:
                down[service_offset + j] = 1.0
        rows.append(down)
        row_upper.append(battery.power_mw)

        nameplate = np.zeros(variable_count, dtype=float)
        for j in active:
            nameplate[service_offset + j] = 1.0
        rows.append(nameplate)
        row_upper.append(battery.power_mw)

        charge_mode = np.zeros(variable_count, dtype=float)
        charge_mode[firm_charge_offset + t] = 1.0
        charge_mode[arb_charge_offset + t] = 1.0
        charge_mode[mode_offset + t] = battery.power_mw
        rows.append(charge_mode)
        row_upper.append(battery.power_mw)

        discharge_mode = np.zeros(variable_count, dtype=float)
        discharge_mode[firm_discharge_offset + t] = 1.0
        discharge_mode[arb_discharge_offset + t] = 1.0
        discharge_mode[mode_offset + t] = -battery.power_mw
        rows.append(discharge_mode)
        row_upper.append(0.0)

        energy_up = np.zeros(variable_count, dtype=float)
        for j in active:
            if upward[j]:
                energy_up[service_offset + j] = guards[j] / eta_d
        if t == 0:
            rows.append(energy_up)
            row_upper.append(battery.initial_soc_mwh - battery.minimum_soc_mwh)
        else:
            energy_up[soc_offset + t - 1] = -1.0
            rows.append(energy_up)
            row_upper.append(-battery.minimum_soc_mwh)

        energy_down = np.zeros(variable_count, dtype=float)
        for j in active:
            if downward[j]:
                energy_down[service_offset + j] = guards[j] * eta_c
        if t == 0:
            rows.append(energy_down)
            row_upper.append(battery.maximum_soc_mwh - battery.initial_soc_mwh)
        else:
            energy_down[soc_offset + t - 1] = 1.0
            rows.append(energy_down)
            row_upper.append(battery.maximum_soc_mwh)

    constraints = [LinearConstraint(equality, rhs, rhs)]
    if rows:
        constraints.append(LinearConstraint(
            np.vstack(rows), np.full(len(row_upper), -np.inf), np.asarray(row_upper, dtype=float)
        ))
    integrality = np.zeros(variable_count, dtype=int)
    integrality[mode_offset:mode_offset + n] = 1
    if m:
        if not svc["whole_mw"].astype(bool).all():
            raise ValueError("The current generic release expects whole-MW NESO products.")
        integrality[service_offset:] = 1

    solution = milp(
        c=objective, integrality=integrality,
        bounds=Bounds(lower, upper), constraints=constraints,
        options={"disp": False},
    )
    if not solution.success:
        raise RuntimeError(f"Multi-service optimisation failed: {solution.message}")
    x = solution.x
    firm_charge = x[firm_charge_offset:firm_charge_offset + n]
    firm_discharge = x[firm_discharge_offset:firm_discharge_offset + n]
    arb_charge = x[arb_charge_offset:arb_charge_offset + n]
    arb_discharge = x[arb_discharge_offset:arb_discharge_offset + n]
    soc_end = x[soc_offset:soc_offset + n]
    service_q = np.rint(x[service_offset:]) if m else np.array([], dtype=float)
    tolerance = 1e-7
    for series in (firm_charge, firm_discharge, arb_charge, arb_discharge, service_q):
        series[np.abs(series) < tolerance] = 0.0
    total_charge = firm_charge + arb_charge
    total_discharge = firm_discharge + arb_discharge
    if ((total_charge > tolerance) & (total_discharge > tolerance)).any():
        raise AssertionError("Multi-service optimiser charged and discharged simultaneously.")
    if abs(float(soc_end[-1]) - battery.initial_soc_mwh) > 1e-5:
        raise AssertionError("Multi-service optimiser violated terminal SOC equality.")

    residual = error - firm_charge + firm_discharge
    if (np.abs(residual) > np.abs(error) + tolerance).any():
        raise AssertionError("Multi-service firming amplified renewable forecast error.")
    firming_value = float(((firm_discharge - firm_charge) * system_price * dt).sum())
    arbitrage_value = float(((arb_discharge - arb_charge) * market_price * dt).sum())
    throughput_mwh = float((total_charge + total_discharge).sum() * dt)
    throughput_cost = throughput_mwh * cfg.throughput_cost_gbp_per_mwh

    service_payment = 0.0
    family_payment: dict[str, float] = {}
    family_mwh: dict[str, float] = {}
    if m:
        svc = svc.copy()
        svc["contracted_mw"] = service_q
        svc["availability_payment_gbp"] = (
            svc["contracted_mw"] * svc["clearing_price_gbp_per_mw_per_hour"] * svc["window_hours"]
        )
        service_payment = float(svc["availability_payment_gbp"].sum())
        family_payment = svc.groupby("family")["availability_payment_gbp"].sum().astype(float).to_dict()
        family_mwh = (
            svc.assign(mw_hours=svc["contracted_mw"] * svc["window_hours"])
            .groupby("family")["mw_hours"].sum().astype(float).to_dict()
        )
    net_value = firming_value + arbitrage_value + service_payment - throughput_cost
    before = float(np.abs(error).sum() * dt)
    after = float(np.abs(residual).sum() * dt)

    frame["multiservice_firm_charge_mw"] = firm_charge
    frame["multiservice_firm_discharge_mw"] = firm_discharge
    frame["multiservice_arbitrage_charge_mw"] = arb_charge
    frame["multiservice_arbitrage_discharge_mw"] = arb_discharge
    frame["multiservice_soc_end_mwh"] = soc_end
    frame["multiservice_residual_error_mw"] = residual
    if m:
        for family in sorted(svc["family"].unique()):
            active_capacity = np.zeros(n, dtype=float)
            selected_family = svc.loc[svc["family"].eq(family)]
            for _, row in selected_family.iterrows():
                mask = (
                    frame["valid_time_utc"].ge(row["delivery_start_utc"])
                    & frame["valid_time_utc"].lt(row["delivery_end_utc"])
                )
                active_capacity[mask.to_numpy()] += float(row["contracted_mw"])
            slug = family.lower().replace(" ", "_")
            frame[f"{slug}_contracted_mw"] = active_capacity

    summary: dict[str, Any] = {
        "method": "ex_post_shared_bess_firming_arbitrage_neso_multiservice_availability",
        "perfect_information": True,
        "availability_only": True,
        "utilisation_revenue_included": False,
        "performance_penalties_included": False,
        "assume_bm_eligible": bool(cfg.assume_bm_eligible),
        "enabled_families": list(cfg.enabled_families),
        "complete_service_windows_only": bool(cfg.complete_service_windows_only),
        "conservative_no_double_selling": True,
        "service_contract_rows": int(m),
        "firming_settlement_value_gbp": float(firming_value),
        "wholesale_arbitrage_value_gbp": float(arbitrage_value),
        "ancillary_availability_payment_gbp": float(service_payment),
        "family_availability_payment_gbp": family_payment,
        "family_contracted_mw_hours": family_mwh,
        "throughput_mwh": throughput_mwh,
        "throughput_cost_gbp": float(throughput_cost),
        "net_stacked_value_gbp": float(net_value),
        "absolute_error_before_mwh": before,
        "absolute_error_after_mwh": after,
        "error_reduction_pct": 100.0 * (1.0 - after / before) if before > 0 else 0.0,
        "ending_soc_pct": float(100.0 * soc_end[-1] / battery.energy_capacity_mwh),
        "assumption": "price-taker acceptance at observed EAC clearing prices; realised prices/error; conservative no-double-selling across simultaneous services",
        "solver_status": str(solution.message),
        "service_contracts": (
            [
                {
                    "product": str(row.product),
                    "family": str(row.family),
                    "direction": str(row.direction),
                    "delivery_start_utc": row.delivery_start_utc.isoformat(),
                    "delivery_end_utc": row.delivery_end_utc.isoformat(),
                    "window_hours": float(row.window_hours),
                    "contracted_mw": float(row.contracted_mw),
                    "clearing_price_gbp_per_mw_per_hour": float(row.clearing_price_gbp_per_mw_per_hour),
                    "energy_guard_hours": float(row.energy_guard_hours),
                    "bm_required": bool(row.bm_required),
                }
                for row in svc.loc[svc["contracted_mw"].gt(1e-7)].itertuples(index=False)
            ] if m else []
        ),
    }
    return frame, summary
