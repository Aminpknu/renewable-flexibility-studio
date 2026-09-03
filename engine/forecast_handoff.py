"""Validation and health rules for cross-repository forecast bundle handoff."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def sha256_file(path: str | Path) -> str:
    source = Path(path)
    if source.suffix.lower() in {".csv", ".json", ".txt"}:
        text = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    digest = hashlib.sha256()
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _one_target(frame: pd.DataFrame, column: str, label: str) -> pd.Timestamp:
    if column not in frame.columns:
        raise ValueError(f"{label} is missing {column}.")
    values = pd.to_datetime(frame[column], errors="raise").dt.normalize().drop_duplicates()
    if len(values) != 1:
        raise ValueError(f"{label} must contain exactly one target date.")
    return pd.Timestamp(values.iloc[0])


def validate_national_forecast(frame: pd.DataFrame) -> dict[str, Any]:
    required = {
        "forecast_created_utc", "target_date", "settlement_period", "valid_time_utc",
        "wind_pred_cf", "wind_forecast_mw", "solar_pred_cf", "solar_forecast_mw",
    }
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"National forecast is missing columns: {missing}")
    work = frame.copy()
    target = _one_target(work, "target_date", "National forecast")
    work["settlement_period"] = pd.to_numeric(work["settlement_period"], errors="raise").astype(int)
    work["valid_time_utc"] = pd.to_datetime(work["valid_time_utc"], utc=True, errors="raise")
    created = pd.to_datetime(work["forecast_created_utc"], utc=True, errors="raise")
    if created.nunique() != 1:
        raise ValueError("National forecast must contain one forecast_created_utc value.")
    count = len(work)
    if count not in {46, 48, 50}:
        raise ValueError(f"National forecast must contain 46, 48 or 50 periods; found {count}.")
    if sorted(work["settlement_period"].tolist()) != list(range(1, count + 1)):
        raise ValueError("National forecast settlement periods are not complete and sequential.")
    if work["settlement_period"].duplicated().any() or work["valid_time_utc"].duplicated().any():
        raise ValueError("National forecast contains duplicate period or UTC valid-time keys.")
    numeric = work[["wind_pred_cf", "wind_forecast_mw", "solar_pred_cf", "solar_forecast_mw"]].apply(pd.to_numeric, errors="raise")
    if not np.isfinite(numeric.to_numpy(float)).all():
        raise ValueError("National forecast contains non-finite forecast values.")
    if not numeric["wind_pred_cf"].between(0, 1).all() or not numeric["solar_pred_cf"].between(0, 1).all():
        raise ValueError("National forecast capacity factors must lie between zero and one.")
    if numeric[["wind_forecast_mw", "solar_forecast_mw"]].lt(0).any().any():
        raise ValueError("National forecast MW values cannot be negative.")
    return {
        "target_date": target.date().isoformat(),
        "period_count": int(count),
        "forecast_created_utc": pd.Timestamp(created.iloc[0]).isoformat(),
        "valid_time_start_utc": work["valid_time_utc"].min().isoformat(),
        "valid_time_end_utc": work["valid_time_utc"].max().isoformat(),
    }


def assess_forecast_freshness(
    metadata: dict[str, Any],
    *,
    now_utc: pd.Timestamp | None = None,
    max_issue_age_hours: float = 48.0,
) -> dict[str, Any]:
    now = pd.Timestamp.now(tz="UTC") if now_utc is None else pd.Timestamp(now_utc)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    created = pd.Timestamp(metadata["forecast_created_utc"])
    if created.tzinfo is None:
        created = created.tz_localize("UTC")
    else:
        created = created.tz_convert("UTC")
    target = pd.Timestamp(metadata["target_date"], tz="UTC")
    issue_age = float((now - created).total_seconds() / 3600.0)
    target_lag_days = int((now.normalize() - target.normalize()).days)
    if target_lag_days > 0:
        status = "STALE_TARGET"
    elif issue_age > max_issue_age_hours:
        status = "STALE_ISSUE"
    else:
        status = "CURRENT"
    return {
        "status": status,
        "issue_age_hours": issue_age,
        "target_lag_days": target_lag_days,
    }


def validate_forecast_bundle_files(
    csv_path: str | Path,
    manifest_path: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    csv_path = Path(csv_path)
    manifest_path = Path(manifest_path)
    if not csv_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Forecast bundle CSV/manifest pair is incomplete.")
    frame = pd.read_csv(csv_path)
    metadata = validate_national_forecast(frame)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_hash = manifest.get("sha256")
    if expected_hash and sha256_file(csv_path) != expected_hash:
        raise ValueError("Forecast bundle checksum does not match its manifest.")
    if str(manifest.get("target_date")) != metadata["target_date"]:
        raise ValueError("Forecast manifest target date does not match the CSV.")
    if int(manifest.get("row_count", -1)) != metadata["period_count"]:
        raise ValueError("Forecast manifest row count does not match the CSV.")
    return metadata, manifest


def select_forecast_bundle(
    latest_csv: str | Path,
    latest_manifest: str | Path,
    fallback_csv: str | Path,
    fallback_manifest: str | Path,
) -> tuple[Path, dict[str, Any], str]:
    try:
        _metadata, manifest = validate_forecast_bundle_files(latest_csv, latest_manifest)
        return Path(latest_csv), manifest, "LATEST"
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        _metadata, manifest = validate_forecast_bundle_files(fallback_csv, fallback_manifest)
        return Path(fallback_csv), manifest, "FALLBACK"
