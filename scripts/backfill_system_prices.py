"""Build a versioned Elexon System Price/NIV history matching the V2 archive."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import time

import pandas as pd

from adapters.forecast_data import load_historical_predictions
from adapters.imbalance_settlement import fetch_system_prices

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "historical_backtest.csv"
OUTPUT = ROOT / "data" / "elexon_system_prices.csv"
MANIFEST = ROOT / "data" / "elexon_system_prices_manifest.json"


def _write(frame: pd.DataFrame) -> None:
    """Write through a validated temporary file, then replace the archive atomically."""
    ordered = frame.sort_values(["settlement_date", "settlement_period"]).reset_index(drop=True)
    temp = OUTPUT.with_name(OUTPUT.stem + ".tmp.csv")
    ordered.to_csv(temp, index=False)
    check = pd.read_csv(temp)
    if len(check) != len(ordered) or list(check.columns) != list(ordered.columns):
        temp.unlink(missing_ok=True)
        raise ValueError("Temporary Elexon archive failed row/column validation.")
    temp.replace(OUTPUT)


def main() -> None:
    history = load_historical_predictions(HISTORY)
    target_dates = [d.strftime("%Y-%m-%d") for d in sorted(history["settlement_date"].unique())]
    if OUTPUT.exists():
        existing = pd.read_csv(OUTPUT)
        existing["settlement_date"] = existing["settlement_date"].astype(str)
    else:
        existing = pd.DataFrame()
    done = set(existing["settlement_date"].unique()) if not existing.empty else set()
    parts = [existing] if not existing.empty else []
    failures: dict[str, str] = {}
    for index, target in enumerate(target_dates, start=1):
        if target in done:
            continue
        last_error = None
        for attempt in range(5):
            try:
                day = fetch_system_prices(target, timeout_seconds=45)
                day.insert(0, "settlement_date", target)
                parts.append(day)
                last_error = None
                break
            except Exception as error:
                last_error = error
                time.sleep(min(1.0 * (attempt + 1), 5.0))
        if last_error is not None:
            failures[target] = repr(last_error)
        if index % 25 == 0:
            combined = pd.concat(parts, ignore_index=True)
            _write(combined)
            print(index, "/", len(target_dates), "days processed; failures", len(failures), flush=True)
        time.sleep(0.08)
    combined = pd.concat(parts, ignore_index=True)
    _write(combined)
    payload = OUTPUT.read_bytes()
    manifest = {
        "schema_version": "1.0",
        "source": "Elexon Insights DISEBSP system-prices endpoint",
        "source_endpoint": "https://data.elexon.co.uk/bmrs/api/v1/balancing/settlement/system-prices/{settlementDate}",
        "date_start": min(target_dates),
        "date_end": max(target_dates),
        "requested_target_days": len(target_dates),
        "retrieved_target_days": int(combined["settlement_date"].nunique()),
        "rows": len(combined),
        "failures": failures,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
