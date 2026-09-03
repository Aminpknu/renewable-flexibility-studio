"""Pre-delivery shared-BESS ancillary offers with opportunity-cost bid floors."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from adapters.neso_services import load_service_specs
from .battery import BatteryConfig
from .market_optimisation import (
    WholesaleArbitrageConfig,
    evaluate_arbitrage_schedule,
    optimise_wholesale_arbitrage,
)
from .multiservice import MultiServiceConfig, optimise_firming_arbitrage_and_services
from .multiservice_acceptance import AcceptanceLookupConfig, predict_acceptance_ratio


def _service_frame(
    forecast: pd.DataFrame,
    battery: BatteryConfig,
    acceptance_product_prior: dict[str, float] | None = None,
) -> pd.DataFrame:
    specs = load_service_specs()
    required = {
        "delivery_start_utc", "product", "family", "direction", "window_hours",
        "forecast_clearing_price_gbp_per_mw_per_hour",
        "prior_same_window_price_gbp_per_mw_per_hour",
    }
    missing = sorted(required.difference(forecast.columns))
    if missing:
        raise ValueError(f"Multi-service forecast is missing pre-delivery columns: {missing}")
    work = forecast.copy()
    work["delivery_start_utc"] = pd.to_datetime(work["delivery_start_utc"], utc=True)
    work["delivery_end_utc"] = work["delivery_start_utc"] + pd.to_timedelta(work["window_hours"], unit="h")
    work = work.merge(
        specs.drop(columns=["family", "direction", "window_hours"]),
        on="product", how="left", validate="many_to_one",
    )
    work["cleared_volume_mw"] = float(battery.power_mw)
    work["raw_forecast_price_gbp_per_mw_per_hour"] = work["forecast_clearing_price_gbp_per_mw_per_hour"]
    if acceptance_product_prior is None:
        adjustment = np.ones(len(work), dtype=float)
    else:
        adjustment = work["product"].map(acceptance_product_prior).fillna(0.0).to_numpy(float)
    work["capacity_selection_acceptance_prior"] = adjustment
    work["clearing_price_gbp_per_mw_per_hour"] = (
        work["forecast_clearing_price_gbp_per_mw_per_hour"].to_numpy(float) * adjustment
    )
    return work


def acceptance_product_priors(calibration: pd.DataFrame) -> dict[str, float]:
    selected = calibration.loc[calibration["sample_class"].eq("standalone_parent")]
    grouped = selected.groupby("product").agg(
        orders=("orders", "sum"), accepted=("accepted_fraction_sum", "sum")
    )
    priors = {
        str(product): float(row.accepted / row.orders)
        for product, row in grouped.iterrows() if float(row.orders) > 0
    }
    broad = calibration.loc[calibration["sample_class"].eq("nonlooped_parent")].groupby("product").agg(
        orders=("orders", "sum"), accepted=("accepted_fraction_sum", "sum")
    )
    for product, row in broad.iterrows():
        if str(product) not in priors and float(row.orders) > 0:
            priors[str(product)] = float(row.accepted / row.orders)
    return priors


def build_issue_time_multiservice_schedule(
    market_signal: pd.DataFrame,
    service_forecast: pd.DataFrame,
    battery: BatteryConfig,
    calibration: pd.DataFrame,
    throughput_cost_gbp_per_mwh: float = 2.0,
    assume_bm_eligible: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    required_market = {"settlement_period", "valid_time_utc", "market_index_price_gbp_per_mwh"}
    missing = sorted(required_market.difference(market_signal.columns))
    if missing:
        raise ValueError(f"Market signal is missing pre-delivery multi-service columns: {missing}")
    market = market_signal.copy().sort_values("settlement_period").reset_index(drop=True)
    market["valid_time_utc"] = pd.to_datetime(market["valid_time_utc"], utc=True)
    portfolio = pd.DataFrame({
        "settlement_period": market["settlement_period"],
        "valid_time_utc": market["valid_time_utc"],
        "actual_mw": np.zeros(len(market)),
        "forecast_mw": np.zeros(len(market)),
    })
    system = pd.DataFrame({
        "settlement_period": market["settlement_period"],
        "system_price_gbp_per_mwh": np.zeros(len(market)),
    })
    priors = acceptance_product_priors(calibration)
    services = _service_frame(service_forecast, battery, priors)
    frame, summary = optimise_firming_arbitrage_and_services(
        portfolio, system, market, services, battery,
        MultiServiceConfig(
            throughput_cost_gbp_per_mwh=float(throughput_cost_gbp_per_mwh),
            enable_firming=False, enable_arbitrage=True,
            assume_bm_eligible=bool(assume_bm_eligible),
        ),
    )
    contracts = pd.DataFrame(summary["service_contracts"])
    if not contracts.empty:
        lookup = services[[
            "product", "delivery_start_utc", "raw_forecast_price_gbp_per_mw_per_hour",
            "prior_same_window_price_gbp_per_mw_per_hour", "capacity_selection_acceptance_prior",
        ]]
        contracts["delivery_start_utc"] = pd.to_datetime(contracts["delivery_start_utc"], utc=True)
        contracts = contracts.merge(lookup, on=["product", "delivery_start_utc"], how="left", validate="many_to_one")
    summary = dict(summary)
    summary.update({
        "method": "issue_time_forecast_wholesale_plus_acceptance_prior_multiservice_capacity_allocation",
        "perfect_information": False,
        "uses_realised_service_clearing_price_for_selection": False,
        "uses_realised_forecast_error_for_selection": False,
        "acceptance_prior_source": "earlier EAC standalone-parent orders with nonlooped-parent fallback",
        "ancillary_price_source": "prior-date product-specific clearing-price forecast",
    })
    return frame, contracts, summary


def _contract_constrained_market_signal(
    market_signal: pd.DataFrame,
    contract: pd.Series | dict[str, Any],
    battery: BatteryConfig,
) -> pd.DataFrame:
    work = market_signal.copy().sort_values("settlement_period").reset_index(drop=True)
    work["valid_time_utc"] = pd.to_datetime(work["valid_time_utc"], utc=True)
    start = pd.Timestamp(contract["delivery_start_utc"])
    end = pd.Timestamp(contract["delivery_end_utc"])
    if start.tzinfo is None:
        start = start.tz_localize("UTC")
    else:
        start = start.tz_convert("UTC")
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    else:
        end = end.tz_convert("UTC")
    quantity = float(contract["contracted_mw"])
    guard = float(contract["energy_guard_hours"])
    if quantity <= 0:
        return work
    active = work["valid_time_utc"].ge(start) & work["valid_time_utc"].lt(end)
    work["max_charge_mw"] = float(battery.power_mw)
    work["max_discharge_mw"] = float(battery.power_mw)
    if "soc_floor_mwh" not in work.columns:
        work["soc_floor_mwh"] = float(battery.minimum_soc_mwh)
    if "soc_ceiling_mwh" not in work.columns:
        work["soc_ceiling_mwh"] = float(battery.maximum_soc_mwh)
    direction = str(contract["direction"])
    if direction == "upward":
        work.loc[active, "max_discharge_mw"] = np.maximum(battery.power_mw - quantity, 0.0)
        required_floor = battery.minimum_soc_mwh + quantity * guard / battery.discharge_efficiency
        active_positions = np.flatnonzero(active.to_numpy())
        for position in active_positions:
            if position == 0:
                if battery.initial_soc_mwh + 1e-9 < required_floor:
                    raise ValueError("Contract is infeasible at initial SOC.")
            else:
                work.loc[position - 1, "soc_floor_mwh"] = max(
                    float(work.loc[position - 1, "soc_floor_mwh"]), required_floor
                )
    elif direction == "downward":
        work.loc[active, "max_charge_mw"] = np.maximum(battery.power_mw - quantity, 0.0)
        required_ceiling = battery.maximum_soc_mwh - quantity * guard * battery.charge_efficiency
        active_positions = np.flatnonzero(active.to_numpy())
        for position in active_positions:
            if position == 0:
                if battery.initial_soc_mwh - 1e-9 > required_ceiling:
                    raise ValueError("Contract is infeasible at initial SOC.")
            else:
                work.loc[position - 1, "soc_ceiling_mwh"] = min(
                    float(work.loc[position - 1, "soc_ceiling_mwh"]), required_ceiling
                )
    else:
        raise ValueError("Contract direction must be upward or downward.")
    return work


def attach_opportunity_cost_bids(
    contracts: pd.DataFrame,
    market_signal: pd.DataFrame,
    battery: BatteryConfig,
    calibration: pd.DataFrame,
    throughput_cost_gbp_per_mwh: float = 2.0,
    acceptance_config: AcceptanceLookupConfig | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if contracts.empty:
        return contracts.copy(), {"baseline_forecast_wholesale_value_gbp": 0.0, "contracts": 0}
    base_schedule, base_summary = optimise_wholesale_arbitrage(
        market_signal, battery, WholesaleArbitrageConfig(float(throughput_cost_gbp_per_mwh))
    )
    base_value = float(base_summary["net_arbitrage_margin_gbp"])
    rows: list[dict[str, Any]] = []
    for contract in contracts.to_dict(orient="records"):
        quantity = float(contract["contracted_mw"])
        hours = float(contract["window_hours"])
        if quantity <= 0 or hours <= 0:
            continue
        try:
            constrained_signal = _contract_constrained_market_signal(market_signal, contract, battery)
            _schedule, constrained = optimise_wholesale_arbitrage(
                constrained_signal, battery, WholesaleArbitrageConfig(float(throughput_cost_gbp_per_mwh))
            )
            opportunity_cost = max(base_value - float(constrained["net_arbitrage_margin_gbp"]), 0.0)
            bid_price = opportunity_cost / (quantity * hours)
            feasible = True
        except (ValueError, RuntimeError):
            opportunity_cost = float("inf")
            bid_price = float("inf")
            feasible = False
        prior_price = float(contract["prior_same_window_price_gbp_per_mw_per_hour"])
        if feasible:
            acceptance, lookup = predict_acceptance_ratio(
                calibration, str(contract["product"]), bid_price, quantity, prior_price,
                acceptance_config,
            )
        else:
            acceptance, lookup = 0.0, {"level": "infeasible", "orders": 0}
        record = dict(contract)
        record.update({
            "standalone_wholesale_opportunity_cost_gbp": float(opportunity_cost),
            "opportunity_cost_bid_gbp_per_mw_per_hour": float(bid_price),
            "predicted_acceptance_ratio_at_bid_time": float(acceptance),
            "acceptance_lookup_level": str(lookup["level"]),
            "acceptance_lookup_orders": int(lookup["orders"]),
            "opportunity_cost_bid_feasible": bool(feasible),
        })
        rows.append(record)
    result = pd.DataFrame(rows)
    return result, {
        "baseline_forecast_wholesale_value_gbp": base_value,
        "contracts": int(len(result)),
        "bid_rule": "standalone forecast-wholesale opportunity cost divided by contracted MW-hours",
        "bid_floor_uses_realised_price": False,
        "acceptance_prediction_uses_realised_clearing_price": False,
    }


def score_issue_time_multiservice_schedule(
    schedule: pd.DataFrame,
    bids: pd.DataFrame,
    realised_market: pd.DataFrame,
    realised_services: pd.DataFrame,
    throughput_cost_gbp_per_mwh: float = 2.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    wholesale = schedule.rename(columns={
        "multiservice_arbitrage_charge_mw": "arbitrage_charge_mw",
        "multiservice_arbitrage_discharge_mw": "arbitrage_discharge_mw",
        "multiservice_soc_end_mwh": "arbitrage_soc_end_mwh",
    })
    wholesale_summary = evaluate_arbitrage_schedule(
        wholesale, realised_market, float(throughput_cost_gbp_per_mwh)
    )
    if bids.empty:
        scored = bids.copy()
        ancillary = 0.0
    else:
        scored = bids.copy()
        scored["delivery_start_utc"] = pd.to_datetime(scored["delivery_start_utc"], utc=True)
        actual = realised_services.copy()
        actual["delivery_start_utc"] = pd.to_datetime(actual["delivery_start_utc"], utc=True)
        actual = actual[[
            "product", "delivery_start_utc", "clearing_price_gbp_per_mw_per_hour",
            "cleared_volume_mw",
        ]].rename(columns={
            "clearing_price_gbp_per_mw_per_hour": "realised_clearing_price_gbp_per_mw_per_hour",
            "cleared_volume_mw": "realised_system_cleared_volume_mw",
        })
        scored = scored.merge(actual, on=["product", "delivery_start_utc"], how="left", validate="many_to_one")
        scored["price_eligible_after_auction"] = (
            scored["opportunity_cost_bid_gbp_per_mw_per_hour"]
            <= scored["realised_clearing_price_gbp_per_mw_per_hour"] + 1e-9
        )
        offered = scored["contracted_mw"].to_numpy(float)
        acceptance = scored["predicted_acceptance_ratio_at_bid_time"].to_numpy(float)
        volume = scored["realised_system_cleared_volume_mw"].fillna(0.0).to_numpy(float)
        eligible = scored["price_eligible_after_auction"].fillna(False).to_numpy(bool)
        expected_accepted = np.minimum(offered, volume) * acceptance * eligible.astype(float)
        scored["acceptance_calibrated_expected_accepted_mw"] = expected_accepted
        scored["acceptance_calibrated_availability_payment_gbp"] = (
            expected_accepted
            * scored["realised_clearing_price_gbp_per_mw_per_hour"].fillna(0.0).to_numpy(float)
            * scored["window_hours"].to_numpy(float)
        )
        ancillary = float(scored["acceptance_calibrated_availability_payment_gbp"].sum())
    wholesale_value = float(wholesale_summary["realised_net_arbitrage_margin_gbp"])
    return scored, {
        "method": "frozen_issue_time_schedule_acceptance_calibrated_ex_post_score",
        "realised_wholesale_margin_gbp": wholesale_value,
        "acceptance_calibrated_ancillary_availability_gbp": ancillary,
        "total_acceptance_calibrated_value_gbp": wholesale_value + ancillary,
        "reoptimise_wholesale_after_rejected_offer": False,
        "counterfactual_acceptance_is_exact": False,
        "acceptance_boundary": (
            "expected accepted MW uses an issue-time empirical acceptance ratio; bids above the realised "
            "clearing price receive zero; the exact counterfactual auction result for a non-participating asset is unknowable"
        ),
    }
