"""Official GB day-ahead grid-demand context from Elexon Insights."""

from __future__ import annotations

import json
from urllib.parse import urlencode
from urllib.request import urlopen
import pandas as pd

ELEXON_DAY_AHEAD_URL = "https://data.elexon.co.uk/bmrs/api/v1/forecast/demand/day-ahead"


def fetch_day_ahead_demand(target_date: str, timeout_seconds: int = 20) -> pd.DataFrame:
    """Fetch half-hourly NDF/TSDF and filter explicitly to one GB settlement date."""
    target = pd.Timestamp(target_date).strftime("%Y-%m-%d")
    query = urlencode({"from": target, "to": target})
    with urlopen(f"{ELEXON_DAY_AHEAD_URL}?{query}", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    rows = payload.get("data", [])
    frame = pd.DataFrame(rows)
    required = {"settlementDate", "settlementPeriod", "startTime", "publishTime", "nationalDemand", "transmissionSystemDemand"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Elexon demand response is missing columns: {missing}")
    frame = frame.loc[frame["settlementDate"].eq(target)].copy()
    if frame.empty:
        raise KeyError(f"Elexon returned no day-ahead demand for {target}.")
    frame["settlement_period"] = pd.to_numeric(frame["settlementPeriod"], errors="raise").astype(int)
    frame["valid_time_utc"] = pd.to_datetime(frame["startTime"], utc=True)
    frame["publish_time_utc"] = pd.to_datetime(frame["publishTime"], utc=True)
    frame["national_demand_mw"] = pd.to_numeric(frame["nationalDemand"], errors="raise")
    frame["transmission_system_demand_mw"] = pd.to_numeric(frame["transmissionSystemDemand"], errors="raise")
    frame = frame.sort_values(["settlement_period", "publish_time_utc"]).drop_duplicates("settlement_period", keep="last")
    count = frame["settlement_period"].nunique()
    if count not in {46, 48, 50}:
        raise ValueError(f"Elexon target date {target} has {count} settlement periods, expected 46/48/50.")
    return frame[[
        "settlement_period", "valid_time_utc", "publish_time_utc",
        "national_demand_mw", "transmission_system_demand_mw",
    ]].reset_index(drop=True)
