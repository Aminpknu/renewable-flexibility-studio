"""NESO EAC Quick Reserve availability-clearing data."""

from __future__ import annotations

import json
from urllib.parse import quote
from urllib.request import urlopen

import numpy as np
import pandas as pd

EAC_RESULTS_RESOURCE_ID = "596f29ac-0387-4ba4-a6d3-95c243140707"
EAC_SQL_URL = "https://api.neso.energy/api/3/action/datastore_search_sql"


def fetch_quick_reserve_results(
    start_utc: str,
    end_utc: str,
    timeout_seconds: int = 45,
    resource_id: str = EAC_RESULTS_RESOURCE_ID,
) -> pd.DataFrame:
    """Fetch PQR/NQR clearing results from the NESO EAC open-data resource."""
    sql = (
        f'SELECT * FROM "{resource_id}" '
        f'WHERE "serviceType"=\'Quick Reserve\' '
        f'AND "deliveryStart">=\'{start_utc}\' '
        f'AND "deliveryStart"<\'{end_utc}\' LIMIT 20000'
    )
    with urlopen(f"{EAC_SQL_URL}?sql={quote(sql)}", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("success"):
        raise RuntimeError("NESO EAC API did not return a successful response.")
    frame = pd.DataFrame(payload.get("result", {}).get("records", []))
    required = {
        "auctionID", "auctionProduct", "serviceType", "deliveryStart",
        "deliveryEnd", "clearedVolume", "clearingPrice",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"EAC Quick Reserve response is missing columns: {missing}")
    if frame.empty:
        raise KeyError("No Quick Reserve clearing results were returned.")
    frame = frame.loc[frame["auctionProduct"].isin(["PQR", "NQR"])].copy()
    frame["auction_id"] = pd.to_numeric(frame["auctionID"], errors="raise").astype(int)
    frame["delivery_start_utc"] = pd.to_datetime(frame["deliveryStart"], utc=True, errors="raise")
    frame["delivery_end_utc"] = pd.to_datetime(frame["deliveryEnd"], utc=True, errors="raise")
    frame["cleared_volume_mw"] = pd.to_numeric(frame["clearedVolume"], errors="raise")
    frame["clearing_price_gbp_per_mw_per_hour"] = pd.to_numeric(frame["clearingPrice"], errors="raise")
    frame["window_hours"] = (
        frame["delivery_end_utc"] - frame["delivery_start_utc"]
    ).dt.total_seconds() / 3600.0
    if not np.isfinite(frame[[
        "cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour", "window_hours"
    ]].to_numpy(float)).all():
        raise ValueError("Quick Reserve clearing data contains non-finite values.")
    if (frame["cleared_volume_mw"] < 0).any():
        raise ValueError("Quick Reserve cleared volume cannot be negative.")
    if not np.allclose(frame["window_hours"].to_numpy(float), 0.5, atol=1e-9):
        raise ValueError("This Quick Reserve release expects 30-minute EAC windows.")
    frame["product"] = frame["auctionProduct"]
    frame["direction"] = frame["auctionProduct"].map({"PQR": "positive", "NQR": "negative"})
    frame["availability_payment_per_mw_gbp"] = (
        frame["clearing_price_gbp_per_mw_per_hour"] * frame["window_hours"]
    )
    keep = [
        "auction_id", "product", "direction", "delivery_start_utc",
        "delivery_end_utc", "window_hours", "cleared_volume_mw",
        "clearing_price_gbp_per_mw_per_hour", "availability_payment_per_mw_gbp",
    ]
    result = frame[keep].sort_values(["delivery_start_utc", "product"]).reset_index(drop=True)
    if result.duplicated(["delivery_start_utc", "product"]).any():
        raise ValueError("Quick Reserve data contains duplicate product/windows.")
    return result


def load_quick_reserve_history(path: str) -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame["delivery_start_utc"] = pd.to_datetime(frame["delivery_start_utc"], utc=True, errors="raise")
    frame["delivery_end_utc"] = pd.to_datetime(frame["delivery_end_utc"], utc=True, errors="raise")
    return frame.sort_values(["delivery_start_utc", "product"]).reset_index(drop=True)
