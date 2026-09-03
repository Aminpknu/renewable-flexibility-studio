"""Issue-time acceptance calibration for simple standalone EAC sell orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

MARGIN_EDGES = [-np.inf, -10, -5, -2, -1, -0.5, 0, 0.5, 1, 2, 5, np.inf]
MARGIN_LABELS = ["<-10", "-10:-5", "-5:-2", "-2:-1", "-1:-0.5", "-0.5:0", "0:0.5", "0.5:1", "1:2", "2:5", ">5"]
QUANTITY_EDGES = [0, 1, 5, 10, 25, np.inf]
QUANTITY_LABELS = ["0:1", "1:5", "5:10", "10:25", ">25"]


@dataclass(frozen=True)
class AcceptanceLookupConfig:
    minimum_cell_orders: int = 100
    minimum_margin_orders: int = 200
    smoothing_strength: float = 50.0

    def __post_init__(self) -> None:
        if self.minimum_cell_orders <= 0 or self.minimum_margin_orders <= 0:
            raise ValueError("Acceptance calibration minimum counts must be positive.")
        if self.smoothing_strength < 0 or not np.isfinite(self.smoothing_strength):
            raise ValueError("Acceptance smoothing strength must be finite and non-negative.")


def add_acceptance_bins(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    required = {"product", "price_limit", "quantity_mw", "prior_same_window_price", "acceptance_ratio"}
    missing = sorted(required.difference(work.columns))
    if missing:
        raise ValueError(f"Acceptance frame is missing columns: {missing}")
    work["margin_to_prior_price"] = (
        pd.to_numeric(work["price_limit"], errors="raise")
        - pd.to_numeric(work["prior_same_window_price"], errors="raise")
    )
    work["quantity_mw"] = pd.to_numeric(work["quantity_mw"], errors="raise")
    work["acceptance_ratio"] = pd.to_numeric(work["acceptance_ratio"], errors="raise").clip(0.0, 1.0)
    work["margin_bin"] = pd.cut(
        work["margin_to_prior_price"], MARGIN_EDGES, labels=MARGIN_LABELS,
        include_lowest=True, right=True,
    ).astype(str)
    work["quantity_bin"] = pd.cut(
        work["quantity_mw"], QUANTITY_EDGES, labels=QUANTITY_LABELS,
        include_lowest=True, right=True,
    ).astype(str)
    return work


def aggregate_acceptance_orders(frame: pd.DataFrame, sample_class: str) -> pd.DataFrame:
    work = add_acceptance_bins(frame)
    grouped = work.groupby(["product", "margin_bin", "quantity_bin"], observed=True, as_index=False).agg(
        orders=("acceptance_ratio", "size"), accepted_fraction_sum=("acceptance_ratio", "sum")
    )
    grouped["sample_class"] = str(sample_class)
    return grouped


def _product_prior(calibration: pd.DataFrame, product: str, sample_class: str) -> tuple[float, int]:
    selected = calibration.loc[
        calibration["product"].eq(product) & calibration["sample_class"].eq(sample_class)
    ]
    n = int(selected["orders"].sum())
    if n <= 0:
        return 0.0, 0
    return float(selected["accepted_fraction_sum"].sum() / n), n


def _smoothed_ratio(accepted: float, orders: int, prior: float, strength: float) -> float:
    if orders <= 0:
        return float(prior)
    return float((accepted + strength * prior) / (orders + strength))


def predict_acceptance_ratio(
    calibration: pd.DataFrame,
    product: str,
    bid_price: float,
    quantity_mw: float,
    prior_same_window_price: float,
    config: AcceptanceLookupConfig | None = None,
) -> tuple[float, dict[str, Any]]:
    cfg = config or AcceptanceLookupConfig()
    probe = add_acceptance_bins(pd.DataFrame([{
        "product": product, "price_limit": bid_price, "quantity_mw": quantity_mw,
        "prior_same_window_price": prior_same_window_price, "acceptance_ratio": 0.0,
    }])).iloc[0]
    margin_bin = str(probe["margin_bin"])
    quantity_bin = str(probe["quantity_bin"])
    for sample_class in ("standalone_parent", "nonlooped_parent"):
        prior, prior_n = _product_prior(calibration, product, sample_class)
        if prior_n <= 0:
            continue
        cell = calibration.loc[
            calibration["product"].eq(product)
            & calibration["sample_class"].eq(sample_class)
            & calibration["margin_bin"].eq(margin_bin)
            & calibration["quantity_bin"].eq(quantity_bin)
        ]
        cell_n = int(cell["orders"].sum())
        if cell_n >= cfg.minimum_cell_orders:
            accepted = float(cell["accepted_fraction_sum"].sum())
            return _smoothed_ratio(accepted, cell_n, prior, cfg.smoothing_strength), {
                "level": f"{sample_class}:product_margin_quantity", "orders": cell_n,
                "margin_bin": margin_bin, "quantity_bin": quantity_bin,
            }
        margin = calibration.loc[
            calibration["product"].eq(product)
            & calibration["sample_class"].eq(sample_class)
            & calibration["margin_bin"].eq(margin_bin)
        ]
        margin_n = int(margin["orders"].sum())
        if margin_n >= cfg.minimum_margin_orders:
            accepted = float(margin["accepted_fraction_sum"].sum())
            return _smoothed_ratio(accepted, margin_n, prior, cfg.smoothing_strength), {
                "level": f"{sample_class}:product_margin", "orders": margin_n,
                "margin_bin": margin_bin, "quantity_bin": quantity_bin,
            }
        if sample_class == "standalone_parent" and prior_n >= cfg.minimum_margin_orders:
            return float(prior), {
                "level": "standalone_parent:product", "orders": prior_n,
                "margin_bin": margin_bin, "quantity_bin": quantity_bin,
            }
    broad_prior, broad_n = _product_prior(calibration, product, "nonlooped_parent")
    if broad_n > 0:
        return float(broad_prior), {
            "level": "nonlooped_parent:product", "orders": broad_n,
            "margin_bin": margin_bin, "quantity_bin": quantity_bin,
        }
    return 0.0, {"level": "no_calibration", "orders": 0, "margin_bin": margin_bin, "quantity_bin": quantity_bin}
