"""Atomic operational pipeline for the forecast-day market-price bundle."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from adapters.latest_forecast import latest_target_date, load_latest_forecast
from adapters.market_forecast_bundle import (
    assess_market_forecast_bundle,
    validate_market_forecast_bundle,
)
from scripts.build_latest_market_price_forecast import build_forecast_bundle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
RENEWABLE = DATA / "latest_forecast.csv"
LATEST_CSV = DATA / "latest_market_price_forecast.csv"
LATEST_MANIFEST = DATA / "latest_market_price_forecast_manifest.json"
LAST_VALID_CSV = DATA / "last_valid_market_price_forecast.csv"
LAST_VALID_MANIFEST = DATA / "last_valid_market_price_forecast_manifest.json"
STATUS_PATH = DATA / "market_forecast_pipeline_status.json"


def _load_if_valid(csv_path: Path, manifest_path: Path):
    if not csv_path.exists() or not manifest_path.exists():
        return None
    try:
        return validate_market_forecast_bundle(csv_path, manifest_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def _write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _archive_current() -> None:
    current = _load_if_valid(LATEST_CSV, LATEST_MANIFEST)
    if current is None:
        return
    shutil.copy2(LATEST_CSV, LAST_VALID_CSV)
    shutil.copy2(LATEST_MANIFEST, LAST_VALID_MANIFEST)


def _replace_with_retry(source: Path, destination: Path, attempts: int = 6) -> str:
    """Prefer atomic replacement, with a validated copy fallback for OneDrive."""
    pending = destination.with_name(f".{destination.name}.pending")
    pending.unlink(missing_ok=True)
    shutil.copy2(source, pending)
    try:
        for attempt in range(attempts):
            try:
                os.replace(pending, destination)
                return "ATOMIC_REPLACE"
            except PermissionError:
                if attempt + 1 < attempts:
                    time.sleep(0.25 * (attempt + 1))
        # Some Windows Files-On-Demand paths reject replace-over-existing even
        # when normal overwrite is permitted. Manifest-last publication plus
        # immediate contract validation keeps this fallback bounded and visible.
        shutil.copy2(pending, destination)
        return "VALIDATED_COPY_FALLBACK"
    finally:
        pending.unlink(missing_ok=True)


def _publish(candidate_csv: Path, candidate_manifest: Path) -> dict[str, str]:
    _archive_current()
    modes = {
        "csv": _replace_with_retry(candidate_csv, LATEST_CSV),
        "manifest": _replace_with_retry(candidate_manifest, LATEST_MANIFEST),
    }
    validate_market_forecast_bundle(LATEST_CSV, LATEST_MANIFEST)
    return modes


def run_pipeline(
    builder: Callable[..., dict[str, Any]] = build_forecast_bundle,
) -> dict[str, Any]:
    renewable = load_latest_forecast(RENEWABLE)
    expected_target = latest_target_date(renewable)
    current = _load_if_valid(LATEST_CSV, LATEST_MANIFEST)
    if current is not None:
        current_health = assess_market_forecast_bundle(
            current[1], expected_target_date=expected_target
        )
        if current_health["status"] == "LIVE":
            result = {
                "pipeline_status": "RETAINED_LIVE_BUNDLE",
                "bundle_health": current_health,
                "expected_target_date": expected_target,
            }
            _write_status(result)
            return result
    with tempfile.TemporaryDirectory(dir=DATA) as temp_dir:
        temp = Path(temp_dir)
        candidate_csv = temp / "candidate.csv"
        candidate_manifest = temp / "candidate.json"
        try:
            builder(candidate_csv, candidate_manifest, target_date=expected_target)
            _frame, manifest = validate_market_forecast_bundle(
                candidate_csv, candidate_manifest
            )
            candidate_health = assess_market_forecast_bundle(
                manifest, expected_target_date=expected_target
            )
            current_health = None
            if current is not None:
                current_health = assess_market_forecast_bundle(
                    current[1], expected_target_date=expected_target
                )
            if candidate_health["status"] == "STALE_TIME":
                result = {
                    "pipeline_status": "RENEWABLE_TARGET_STALE",
                    "bundle_health": current_health or candidate_health,
                    "candidate_health": candidate_health,
                    "expected_target_date": expected_target,
                }
                _write_status(result)
                return result
            if (
                candidate_health["status"] == "RECONSTRUCTED"
                and current_health is not None
                and current_health["status"] == "LIVE"
            ):
                result = {
                    "pipeline_status": "RETAINED_PRE_DELIVERY_BUNDLE",
                    "bundle_health": current_health,
                    "candidate_health": candidate_health,
                    "expected_target_date": expected_target,
                }
                _write_status(result)
                return result
            publication_mode = _publish(candidate_csv, candidate_manifest)
            result = {
                "pipeline_status": "PUBLISHED",
                "publication_mode": publication_mode,
                "bundle_health": candidate_health,
                "expected_target_date": expected_target,
            }
            _write_status(result)
            return result
        except Exception as error:
            retained = _load_if_valid(LATEST_CSV, LATEST_MANIFEST)
            if retained is not None:
                health = assess_market_forecast_bundle(
                    retained[1], expected_target_date=expected_target
                )
                result = {
                    "pipeline_status": "FALLBACK_RETAINED",
                    "bundle_health": health,
                    "expected_target_date": expected_target,
                    "refresh_error": f"{type(error).__name__}: {error}",
                }
                _write_status(result)
                return result
            fallback = _load_if_valid(LAST_VALID_CSV, LAST_VALID_MANIFEST)
            if fallback is not None:
                shutil.copy2(LAST_VALID_CSV, LATEST_CSV)
                shutil.copy2(LAST_VALID_MANIFEST, LATEST_MANIFEST)
                health = assess_market_forecast_bundle(
                    fallback[1], expected_target_date=expected_target
                )
                result = {
                    "pipeline_status": "FALLBACK_RESTORED",
                    "bundle_health": health,
                    "expected_target_date": expected_target,
                    "refresh_error": f"{type(error).__name__}: {error}",
                }
                _write_status(result)
                return result
            result = {
                "pipeline_status": "FAILED_NO_FALLBACK",
                "expected_target_date": expected_target,
                "refresh_error": f"{type(error).__name__}: {error}",
            }
            _write_status(result)
            raise


def main() -> None:
    print(json.dumps(run_pipeline(), indent=2))


if __name__ == "__main__":
    main()
