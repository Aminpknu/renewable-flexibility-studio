"""Official GB imbalance-settlement price context from Elexon Insights."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

ELEXON_SYSTEM_PRICES_URL = (
    "https://data.elexon.co.uk/bmrs/api/v1/balancing/settlement/system-prices"
)


def fetch_system_prices(target_date: str, timeout_seconds: int = 30) -> pd.DataFrame:
    """Fetch latest SAA system prices and NIV for one settlement date."""
    target = pd.Timestamp(target_date).strftime("%Y-%m-%d")
    query = urlencode({"format": "json"})
    with urlopen(
        f"{ELEXON_SYSTEM_PRICES_URL}/{target}?{query}", timeout=timeout_seconds
    ) as response:
        payload = json.loads(response.read().decode("utf-8"))
    frame = pd.DataFrame(payload.get("data", []))
    required = {
        "settlementDate", "settlementPeriod", "startTime", "createdDateTime",
        "systemSellPrice", "systemBuyPrice", "netImbalanceVolume",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Elexon system-price response is missing columns: {missing}")
    frame = frame.loc[frame["settlementDate"].eq(target)].copy()
    if frame.empty:
        raise KeyError(f"Elexon returned no settlement prices for {target}.")
    frame["settlement_period"] = pd.to_numeric(frame["settlementPeriod"], errors="raise").astype(int)
    frame["valid_time_utc"] = pd.to_datetime(frame["startTime"], utc=True)
    frame["created_time_utc"] = pd.to_datetime(frame["createdDateTime"], utc=True)
    frame["system_sell_price_gbp_per_mwh"] = pd.to_numeric(frame["systemSellPrice"], errors="raise")
    frame["system_buy_price_gbp_per_mwh"] = pd.to_numeric(frame["systemBuyPrice"], errors="raise")
    frame["net_imbalance_volume_mwh"] = pd.to_numeric(frame["netImbalanceVolume"], errors="raise")
    price_gap = (
        frame["system_sell_price_gbp_per_mwh"]
        - frame["system_buy_price_gbp_per_mwh"]
    ).abs()
    if not np.allclose(price_gap.to_numpy(float), 0.0, atol=1e-9):
        raise ValueError("System Buy and Sell Prices differ; single-price assumption is not valid.")
    frame["system_price_gbp_per_mwh"] = frame["system_sell_price_gbp_per_mwh"]
    frame["system_direction"] = np.select(
        [frame["net_imbalance_volume_mwh"].gt(0), frame["net_imbalance_volume_mwh"].lt(0)],
        ["short", "long"],
        default="balanced",
    )
    frame = frame.sort_values(["settlement_period", "created_time_utc"]).drop_duplicates(
        "settlement_period", keep="last"
    )
    count = frame["settlement_period"].nunique()
    if count not in {46, 48, 50}:
        raise ValueError(f"Elexon target date {target} has {count} prices, expected 46/48/50.")
    return frame[[
        "settlement_period", "valid_time_utc", "created_time_utc",
        "system_price_gbp_per_mwh", "system_buy_price_gbp_per_mwh",
        "system_sell_price_gbp_per_mwh", "net_imbalance_volume_mwh",
        "system_direction",
    ]].reset_index(drop=True)


def load_system_price_history(path: str | Path) -> pd.DataFrame:
    """Load the versioned local Elexon price/NIV archive."""
    frame = pd.read_csv(path)
    required = {
        "settlement_date", "settlement_period", "system_price_gbp_per_mwh",
        "net_imbalance_volume_mwh", "system_direction",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Local system-price history is missing columns: {missing}")
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"], errors="raise").dt.normalize()
    frame["settlement_period"] = pd.to_numeric(frame["settlement_period"], errors="raise").astype(int)
    if frame.duplicated(["settlement_date", "settlement_period"]).any():
        raise ValueError("Local system-price history contains duplicate settlement periods.")
    return frame.sort_values(["settlement_date", "settlement_period"]).reset_index(drop=True)


def select_system_prices(frame: pd.DataFrame, target_date: str) -> pd.DataFrame:
    target = pd.Timestamp(target_date).normalize()
    selected = frame.loc[frame["settlement_date"].eq(target)].copy()
    if selected.empty:
        raise KeyError(f"No Elexon settlement prices are available for {target.date()}.")
    return selected.sort_values("settlement_period").reset_index(drop=True)
