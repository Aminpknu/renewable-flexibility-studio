"""BSC-style imbalance settlement exposure for a virtual renewable portfolio."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def apply_imbalance_settlement(
    simulation: pd.DataFrame,
    system_prices: pd.DataFrame,
    interval_hours: float = 0.5,
) -> pd.DataFrame:
    """Join Elexon System Price/NIV and calculate illustrative imbalance cashflows.

    The virtual portfolio forecast is treated as an illustrative contracted/scheduled
    export. Positive imbalance means actual delivery exceeded schedule (long); negative
    means actual delivery was below schedule (short). Elexon cashflow sign convention is
    preserved: positive cashflow is a payment by the portfolio, negative is a receipt.
    """
    if interval_hours <= 0:
        raise ValueError("interval_hours must be positive.")
    required_sim = {"settlement_period", "forecast_error_mw", "residual_error_mw"}
    missing = sorted(required_sim.difference(simulation.columns))
    if missing:
        raise ValueError(f"Simulation is missing imbalance columns: {missing}")
    required_prices = {
        "settlement_period", "system_price_gbp_per_mwh",
        "net_imbalance_volume_mwh", "system_direction",
    }
    missing = sorted(required_prices.difference(system_prices.columns))
    if missing:
        raise ValueError(f"System-price data is missing columns: {missing}")

    simulation_frame = simulation.copy()
    price_frame = system_prices.copy()
    join_keys = ["settlement_period"]
    if "settlement_date" in simulation_frame.columns and "settlement_date" in price_frame.columns:
        simulation_frame["settlement_date"] = pd.to_datetime(
            simulation_frame["settlement_date"], errors="raise"
        ).dt.normalize()
        price_frame["settlement_date"] = pd.to_datetime(
            price_frame["settlement_date"], errors="raise"
        ).dt.normalize()
        join_keys = ["settlement_date", "settlement_period"]
        required_prices.add("settlement_date")
    if price_frame.duplicated(join_keys).any():
        raise ValueError("System-price data contains duplicate settlement keys.")
    frame = simulation_frame.merge(
        price_frame[list(required_prices)],
        on=join_keys,
        how="left",
        validate="many_to_one",
    )
    numeric_required = [
        "system_price_gbp_per_mwh", "net_imbalance_volume_mwh"
    ]
    if frame[numeric_required].isna().any().any() or frame["system_direction"].isna().any():
        raise ValueError("System-price join produced missing settlement data.")
    frame["imbalance_before_mwh"] = frame["forecast_error_mw"].astype(float) * interval_hours
    frame["imbalance_after_mwh"] = frame["residual_error_mw"].astype(float) * interval_hours
    price = frame["system_price_gbp_per_mwh"].astype(float)
    frame["settlement_cashflow_before_gbp"] = -frame["imbalance_before_mwh"] * price
    frame["settlement_cashflow_after_gbp"] = -frame["imbalance_after_mwh"] * price
    frame["gross_cashout_exposure_before_gbp"] = frame["settlement_cashflow_before_gbp"].abs()
    frame["gross_cashout_exposure_after_gbp"] = frame["settlement_cashflow_after_gbp"].abs()
    frame["gross_cashout_exposure_reduction_gbp"] = (
        frame["gross_cashout_exposure_before_gbp"]
        - frame["gross_cashout_exposure_after_gbp"]
    )
    frame["portfolio_direction_before"] = np.select(
        [frame["imbalance_before_mwh"].gt(0), frame["imbalance_before_mwh"].lt(0)],
        ["long", "short"], default="balanced"
    )
    frame["portfolio_direction_after"] = np.select(
        [frame["imbalance_after_mwh"].gt(0), frame["imbalance_after_mwh"].lt(0)],
        ["long", "short"], default="balanced"
    )
    sign_before = np.sign(frame["imbalance_before_mwh"].to_numpy(float))
    sign_after = np.sign(frame["imbalance_after_mwh"].to_numpy(float))
    sign_niv = np.sign(frame["net_imbalance_volume_mwh"].to_numpy(float))
    frame["direction_helpful_before"] = (sign_before == sign_niv) & (sign_before != 0)
    frame["direction_helpful_after"] = (sign_after == sign_niv) & (sign_after != 0)
    return frame


def summarise_imbalance_settlement(frame: pd.DataFrame) -> dict[str, Any]:
    """Summarise signed cashflow and gross cash-out exposure."""
    required = {
        "settlement_cashflow_before_gbp", "settlement_cashflow_after_gbp",
        "gross_cashout_exposure_before_gbp", "gross_cashout_exposure_after_gbp",
        "imbalance_before_mwh", "imbalance_after_mwh", "system_price_gbp_per_mwh",
        "net_imbalance_volume_mwh", "direction_helpful_before", "direction_helpful_after",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Settlement frame is missing summary columns: {missing}")
    gross_before = float(frame["gross_cashout_exposure_before_gbp"].sum())
    gross_after = float(frame["gross_cashout_exposure_after_gbp"].sum())
    reduction = 100.0 * (1.0 - gross_after / gross_before) if gross_before > 0 else 0.0
    return {
        "signed_cashflow_before_gbp": float(frame["settlement_cashflow_before_gbp"].sum()),
        "signed_cashflow_after_gbp": float(frame["settlement_cashflow_after_gbp"].sum()),
        "gross_exposure_before_gbp": gross_before,
        "gross_exposure_after_gbp": gross_after,
        "gross_exposure_reduction_gbp": gross_before - gross_after,
        "gross_exposure_reduction_pct": float(reduction),
        "absolute_imbalance_before_mwh": float(frame["imbalance_before_mwh"].abs().sum()),
        "absolute_imbalance_after_mwh": float(frame["imbalance_after_mwh"].abs().sum()),
        "mean_system_price_gbp_per_mwh": float(frame["system_price_gbp_per_mwh"].mean()),
        "max_system_price_gbp_per_mwh": float(frame["system_price_gbp_per_mwh"].max()),
        "min_system_price_gbp_per_mwh": float(frame["system_price_gbp_per_mwh"].min()),
        "negative_price_periods": int(frame["system_price_gbp_per_mwh"].lt(0).sum()),
        "system_short_periods": int(frame["net_imbalance_volume_mwh"].gt(0).sum()),
        "system_long_periods": int(frame["net_imbalance_volume_mwh"].lt(0).sum()),
        "direction_helpful_before_periods": int(frame["direction_helpful_before"].sum()),
        "direction_helpful_after_periods": int(frame["direction_helpful_after"].sum()),
        "period_count": int(len(frame)),
    }
