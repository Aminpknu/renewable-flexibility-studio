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
    periods = frame["settlement_period"].astype(int).tolist()
    count = len(periods)
    if count in {46, 48, 50} and periods == list(range(1, count + 1)):
        context_status = "complete_day"
    else:
        first_period = min(periods)
        last_period = max(periods)
        contiguous = periods == list(range(first_period, last_period + 1))
        if not contiguous or last_period not in {46, 48, 50} or first_period <= 1:
            raise ValueError(
                f"Elexon target date {target} has an incomplete/non-contiguous demand series "
                f"({count} periods, SP{first_period}-SP{last_period})."
            )
        context_status = "partial_remaining_day"
    frame["grid_context_status"] = context_status
    frame["grid_context_period_count"] = count
    return frame[[
        "settlement_period", "valid_time_utc", "publish_time_utc",
        "national_demand_mw", "transmission_system_demand_mw",
        "grid_context_status", "grid_context_period_count",
    ]].reset_index(drop=True)
