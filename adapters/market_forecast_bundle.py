"""Validation and freshness status for forecast-day market-price bundles."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_COLUMNS = {
    "forecast_created_utc", "settlement_date", "settlement_period",
    "valid_time_utc", "forecast_market_index_price_gbp_per_mwh",
    "naive_market_index_price_gbp_per_mwh",
}


def canonical_csv_sha256(path: str | Path) -> str:
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_market_forecast_bundle(
    csv_path: str | Path,
    manifest_path: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    frame = pd.read_csv(csv_path)
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_COLUMNS.difference(frame.columns))
    if missing:
        raise ValueError(f"Market forecast bundle is missing columns: {missing}")
    if frame.empty:
        raise ValueError("Market forecast bundle is empty.")
    frame["settlement_date"] = pd.to_datetime(frame["settlement_date"], errors="raise").dt.normalize()
    frame["settlement_period"] = pd.to_numeric(frame["settlement_period"], errors="raise").astype(int)
    frame["valid_time_utc"] = pd.to_datetime(frame["valid_time_utc"], utc=True, errors="raise")
    frame["forecast_created_utc"] = pd.to_datetime(frame["forecast_created_utc"], utc=True, errors="raise")
    target_dates = frame["settlement_date"].drop_duplicates()
    if len(target_dates) != 1:
        raise ValueError("Market forecast bundle must contain exactly one settlement date.")
    if frame["settlement_period"].duplicated().any():
        raise ValueError("Market forecast bundle contains duplicate settlement periods.")
    count = int(frame["settlement_period"].nunique())
    if count not in {46, 48, 50}:
        raise ValueError(f"Market forecast bundle has {count} periods, expected 46/48/50.")
    numeric = frame[[
        "forecast_market_index_price_gbp_per_mwh",
        "naive_market_index_price_gbp_per_mwh",
    ]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise ValueError("Market forecast bundle contains non-finite prices.")
    target_text = target_dates.iloc[0].date().isoformat()
    if str(manifest.get("target_date")) != target_text:
        raise ValueError("Market forecast manifest target does not match CSV target.")
    if int(manifest.get("period_count", -1)) != count:
        raise ValueError("Market forecast manifest period count does not match CSV.")
    expected_sha = manifest.get("sha256")
    if expected_sha and canonical_csv_sha256(csv_path) != expected_sha:
        raise ValueError("Market forecast CSV checksum does not match manifest.")
    return frame.sort_values("settlement_period").reset_index(drop=True), manifest


def assess_market_forecast_bundle(
    manifest: dict[str, Any],
    *,
    expected_target_date: str,
    now_utc: pd.Timestamp | None = None,
) -> dict[str, Any]:
    now = pd.Timestamp.now(tz="UTC") if now_utc is None else pd.Timestamp(now_utc)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    target = str(manifest.get("target_date", ""))
    target_start = pd.Timestamp(manifest["target_start_utc"])
    if target_start.tzinfo is None:
        target_start = target_start.tz_localize("UTC")
    created = pd.Timestamp(manifest["forecast_created_utc"])
    if created.tzinfo is None:
        created = created.tz_localize("UTC")
    issued_before = bool(manifest.get("issued_before_target_start", created <= target_start))
    if target != str(expected_target_date):
        status = "STALE_TARGET"
    elif now > target_start + pd.Timedelta(hours=26):
        status = "STALE_TIME"
    elif not issued_before:
        status = "RECONSTRUCTED"
    else:
        status = "LIVE"
    return {
        "status": status,
        "target_date": target,
        "expected_target_date": str(expected_target_date),
        "forecast_created_utc": created.isoformat(),
        "target_start_utc": target_start.isoformat(),
        "issued_before_target_start": issued_before,
        "age_hours_at_target_start": float((target_start - created).total_seconds() / 3600.0),
    }
