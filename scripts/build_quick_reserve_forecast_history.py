"""Build extended Phase-2 Quick Reserve history for pre-delivery price forecasting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from adapters.quick_reserve import EAC_RESULTS_RESOURCE_ID, fetch_quick_reserve_results

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "neso_quick_reserve_forecast_history.csv"
MANIFEST = ROOT / "data" / "neso_quick_reserve_forecast_history_manifest.json"
START = pd.Timestamp("2025-09-02T00:00:00Z")
END = pd.Timestamp("2026-07-01T00:00:00Z")
CUTOVER = pd.Timestamp("2026-03-31T22:00:00Z")
FY2025_ARCHIVE_RESOURCE_ID = "be55ee51-b79e-47da-b71e-a0f8865d9d66"


def _fetch_segment(start: pd.Timestamp, end: pd.Timestamp, resource_id: str):
    parts = []
    cursor = start
    while cursor < end:
        next_month = min(cursor + pd.offsets.MonthBegin(1), end)
        if next_month <= cursor:
            next_month = min(cursor + pd.Timedelta(days=28), end)
        print(f"fetch {cursor.isoformat()} -> {next_month.isoformat()}", flush=True)
        parts.append(fetch_quick_reserve_results(
            cursor.isoformat(), next_month.isoformat(), resource_id=resource_id
        ))
        cursor = next_month
    return parts


def main() -> None:
    parts = []
    parts.extend(_fetch_segment(START, CUTOVER, FY2025_ARCHIVE_RESOURCE_ID))
    parts.extend(_fetch_segment(CUTOVER, END, EAC_RESULTS_RESOURCE_ID))
    frame = pd.concat(parts, ignore_index=True)
    frame = frame.drop_duplicates(["delivery_start_utc", "product"], keep="last")
    frame = frame.sort_values(["delivery_start_utc", "product"]).reset_index(drop=True)
    text = frame.to_csv(index=False, lineterminator="\n")
    OUTPUT.write_text(text, encoding="utf-8", newline="")
    payload = {
        "schema_version": "1.0",
        "source": "NESO Enduring Auction Capability Results Summary",
        "source_resources": {
            "fy2025_archive": FY2025_ARCHIVE_RESOURCE_ID,
            "current_results": EAC_RESULTS_RESOURCE_ID,
        },
        "rights": "NESO Open Data Licence",
        "service": "Quick Reserve",
        "products": ["PQR", "NQR"],
        "history_scope": "Phase-2-era price-forecast evidence; current-rule investment validation remains Apr-Jun 2026",
        "start_utc": frame["delivery_start_utc"].min().isoformat(),
        "end_utc": frame["delivery_start_utc"].max().isoformat(),
        "rows": int(len(frame)),
        "delivery_windows": int(frame["delivery_start_utc"].nunique()),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "sha256_normalisation": "UTF-8 text with LF line endings",
    }
    MANIFEST.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
