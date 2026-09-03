"""Open GB wholesale-market reference data and licensed day-ahead contract adapters."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import numpy as np
import pandas as pd

ELEXON_MARKET_INDEX_URL = (
    "https://data.elexon.co.uk/bmrs/api/v1/balancing/pricing/market-index"
)


def _validate_period_count(frame: pd.DataFrame, target: str, label: str) -> None:
    count = frame["settlement_period"].nunique()
    if count not in {46, 48, 50}:
        raise ValueError(f"{label} {target} has {count} periods, expected 46/48/50.")
    if frame["settlement_period"].duplicated().any():
        raise ValueError(f"{label} {target} contains duplicate settlement periods.")


def fetch_market_index_prices(
    target_date: str,
    data_provider: str = "APXMIDP",
    timeout_seconds: int = 30,
) -> pd.DataFrame:
    """Fetch one complete settlement date of Elexon Market Index Data."""
    target = pd.Timestamp(target_date).strftime("%Y-%m-%d")
    query = urlencode({
        "from": target,
        "to": target,
        "settlementPeriodFrom": 1,
        "settlementPeriodTo": 50,
        "format": "json",
    })
    with urlopen(f"{ELEXON_MARKET_INDEX_URL}?{query}", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    frame = pd.DataFrame(payload.get("data", []))
    required = {
        "startTime", "dataProvider", "settlementDate", "settlementPeriod",
        "price", "volume",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Elexon market-index response is missing columns: {missing}")
    frame = frame.loc[
        frame["settlementDate"].eq(target)
        & frame["dataProvider"].eq(data_provider)
    ].copy()
    if frame.empty:
        raise KeyError(f"No {data_provider} Market Index Data available for {target}.")
    frame["settlement_period"] = pd.to_numeric(frame["settlementPeriod"], errors="raise").astype(int)
    frame["valid_time_utc"] = pd.to_datetime(frame["startTime"], utc=True, errors="raise")
    frame["market_index_price_gbp_per_mwh"] = pd.to_numeric(frame["price"], errors="raise")
    frame["market_index_volume_mwh"] = pd.to_numeric(frame["volume"], errors="raise")
    frame["market_index_provider"] = data_provider
    if not np.isfinite(frame[[
        "market_index_price_gbp_per_mwh", "market_index_volume_mwh"
    ]].to_numpy(float)).all():
        raise ValueError("Market Index Data contains non-finite values.")
    frame = frame.sort_values("settlement_period").reset_index(drop=True)
    _validate_period_count(frame, target, "Elexon Market Index Data")
    return frame[[
        "settlement_period", "valid_time_utc", "market_index_provider",
        "market_index_price_gbp_per_mwh", "market_index_volume_mwh",
    ]]


def load_market_index_history(path: str | Path) -> pd.DataFrame:
    """Load a versioned Elexon Market Index archive."""
    frame = pd.read_csv(path)
    required = {
        "settlement_date", "settlement_period", "market_index_provider",
        "market_index_price_gbp_per_mwh", "market_index_volume_mwh",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Market-index history is missing columns: {missing}")
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"], errors="raise").dt.normalize()
    frame["settlement_period"] = pd.to_numeric(frame["settlement_period"], errors="raise").astype(int)
    numeric = ["market_index_price_gbp_per_mwh", "market_index_volume_mwh"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(frame[numeric].to_numpy(float)).all():
        raise ValueError("Market-index history contains non-finite values.")
    keys = ["settlement_date", "settlement_period", "market_index_provider"]
    if frame.duplicated(keys).any():
        raise ValueError("Market-index history contains duplicate provider/period rows.")
    return frame.sort_values(keys).reset_index(drop=True)


def select_market_index_prices(
    frame: pd.DataFrame,
    target_date: str,
    data_provider: str = "APXMIDP",
) -> pd.DataFrame:
    """Select one complete provider/day from a versioned market-index archive."""
    target = pd.Timestamp(target_date).normalize()
    selected = frame.loc[
        frame["settlement_date"].eq(target)
        & frame["market_index_provider"].eq(data_provider)
    ].copy()
    if selected.empty:
        raise KeyError(f"No {data_provider} market-index prices available for {target.date()}.")
    selected = selected.sort_values("settlement_period").reset_index(drop=True)
    _validate_period_count(selected, target.date().isoformat(), "Market-index archive")
    return selected


def load_licensed_day_ahead_prices(
    path: str | Path,
    issue_cutoff_utc: str | pd.Timestamp | None = None,
) -> pd.DataFrame:
    """Validate a user-supplied licensed GB day-ahead price file.

    The public repository does not bundle licensed NEMO auction data. This adapter
    provides the stable contract for a future authorised feed or local file.
    """
    frame = pd.read_csv(path)
    required = {
        "settlement_date", "settlement_period", "valid_time_utc",
        "publication_time_utc", "day_ahead_price_gbp_per_mwh", "source",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Licensed day-ahead file is missing columns: {missing}")
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"], errors="raise").dt.normalize()
    frame["settlement_period"] = pd.to_numeric(frame["settlement_period"], errors="raise").astype(int)
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True, errors="raise")
    frame["publication_time_utc"] = pd.to_datetime(frame["publication_time_utc"], utc=True, errors="raise")
    frame["day_ahead_price_gbp_per_mwh"] = pd.to_numeric(
        frame["day_ahead_price_gbp_per_mwh"], errors="raise"
    )
    if not np.isfinite(frame["day_ahead_price_gbp_per_mwh"].to_numpy(float)).all():
        raise ValueError("Licensed day-ahead prices contain non-finite values.")
    if frame.duplicated(["settlement_date", "settlement_period"]).any():
        raise ValueError("Licensed day-ahead prices contain duplicate settlement periods.")
    if issue_cutoff_utc is not None:
        cutoff = pd.Timestamp(issue_cutoff_utc)
        cutoff = cutoff.tz_localize("UTC") if cutoff.tzinfo is None else cutoff.tz_convert("UTC")
        if frame["publication_time_utc"].gt(cutoff).any():
            raise ValueError("Licensed day-ahead file contains prices published after the issue cutoff.")
    counts = frame.groupby("settlement_date")["settlement_period"].nunique()
    if not counts.isin({46, 48, 50}).all():
        bad = counts.loc[~counts.isin({46, 48, 50})]
        raise ValueError(f"Licensed day-ahead file contains incomplete GB days: {bad.to_dict()}")
    return frame.sort_values(["settlement_date", "settlement_period"]).reset_index(drop=True)
