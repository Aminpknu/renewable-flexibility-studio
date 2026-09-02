"""Copy a compact latest-forecast bundle into the standalone Studio."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_csv", type=Path)
    parser.add_argument("--source-summary", type=Path, default=None)
    args = parser.parse_args()
    destination = ROOT / "data" / "latest_forecast.csv"
    shutil.copy2(args.source_csv, destination)
    frame = pd.read_csv(destination)
    sha = hashlib.sha256(destination.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "bundle_type": "latest_day_ahead_forecast",
        "source_path": str(args.source_csv),
        "target_date": str(frame["target_date"].iloc[0]),
        "forecast_created_utc": str(frame["forecast_created_utc"].iloc[0]),
        "row_count": int(len(frame)),
        "sha256": sha,
    }
    if args.source_summary and args.source_summary.is_file():
        summary_destination = ROOT / "data" / "latest_forecast_summary.json"
        shutil.copy2(args.source_summary, summary_destination)
        manifest["source_summary"] = str(args.source_summary)
    (ROOT / "data" / "latest_forecast_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
