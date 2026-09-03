"""Validate and atomically publish the latest V2 forecast bundle into the Studio."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from engine.forecast_handoff import assess_forecast_freshness, sha256_file, validate_national_forecast

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
LATEST = DATA / "latest_forecast.csv"
LATEST_SUMMARY = DATA / "latest_forecast_summary.json"
MANIFEST = DATA / "latest_forecast_manifest.json"
LAST_VALID = DATA / "last_valid_forecast.csv"
LAST_VALID_SUMMARY = DATA / "last_valid_forecast_summary.json"
LAST_VALID_MANIFEST = DATA / "last_valid_forecast_manifest.json"


def _source_revision(source_csv: Path) -> str | None:
    for parent in source_csv.resolve().parents:
        if (parent / ".git").exists():
            try:
                return subprocess.check_output(
                    ["git", "-C", str(parent), "rev-parse", "HEAD"], text=True
                ).strip()
            except (OSError, subprocess.CalledProcessError):
                return None
    return None


def _archive_current() -> None:
    if LATEST.exists() and MANIFEST.exists():
        shutil.copy2(LATEST, LAST_VALID)
        shutil.copy2(MANIFEST, LAST_VALID_MANIFEST)
        if LATEST_SUMMARY.exists():
            shutil.copy2(LATEST_SUMMARY, LAST_VALID_SUMMARY)

def publish(source_csv: Path, source_summary: Path | None = None) -> dict[str, object]:
    candidate = pd.read_csv(source_csv)
    metadata = validate_national_forecast(candidate)
    health = assess_forecast_freshness(metadata)
    if health["status"] != "CURRENT":
        raise ValueError(f"Forecast candidate is not current: {health['status']}")
    with tempfile.TemporaryDirectory(dir=DATA) as temp_dir:
        temp = Path(temp_dir)
        staged_csv = temp / "latest_forecast.csv"
        staged_manifest = temp / "latest_forecast_manifest.json"
        shutil.copy2(source_csv, staged_csv)
        manifest = {
            "schema_version": "2.0",
            "bundle_type": "latest_day_ahead_forecast",
            "source_repository": "https://github.com/Aminpknu/gb-renewable-forecast",
            "source_file": source_csv.name,
            "source_revision": _source_revision(source_csv),
            "target_date": metadata["target_date"],
            "forecast_created_utc": metadata["forecast_created_utc"],
            "row_count": metadata["period_count"],
            "sha256": sha256_file(staged_csv),
            "health_at_publication": health,
        }
        staged_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        _archive_current()
        os.replace(staged_csv, LATEST)
        os.replace(staged_manifest, MANIFEST)
        if source_summary and source_summary.is_file():
            shutil.copy2(source_summary, LATEST_SUMMARY)
            manifest["source_summary_file"] = source_summary.name
            MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--source-summary", type=Path, default=None)
    args = parser.parse_args()
    print(json.dumps(publish(args.source_csv, args.source_summary), indent=2))


if __name__ == "__main__":
    main()