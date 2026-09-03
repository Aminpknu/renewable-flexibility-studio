"""Build the issue-time multi-service clearing-price history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from adapters.neso_services import load_eac_service_history, load_service_specs

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "build_sources" / "stage13" / "summary_fy2025.csv"
CURRENT = ROOT / "data" / "neso_multiservice_prices.csv"
OUTPUT = ROOT / "data" / "neso_multiservice_forecast_history.csv"
MANIFEST = ROOT / "data" / "neso_multiservice_forecast_history_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalise_fy2025() -> pd.DataFrame:
    frame = pd.read_csv(RAW)
    specs = load_service_specs()
    keep_products = set(specs["product"])
    frame = frame.loc[frame["auctionProduct"].astype(str).isin(keep_products)].copy()
    frame["auction_id"] = pd.to_numeric(frame["auctionID"], errors="raise").astype(int)
    frame["product"] = frame["auctionProduct"].astype(str)
    frame["delivery_start_utc"] = pd.to_datetime(frame["deliveryStart"], utc=True, errors="raise")
    frame["delivery_end_utc"] = pd.to_datetime(frame["deliveryEnd"], utc=True, errors="raise")
    frame["cleared_volume_mw"] = pd.to_numeric(frame["clearedVolume"], errors="raise")
    frame["clearing_price_gbp_per_mw_per_hour"] = pd.to_numeric(frame["clearingPrice"], errors="raise")
    frame["window_hours"] = (
        frame["delivery_end_utc"] - frame["delivery_start_utc"]
    ).dt.total_seconds() / 3600.0
    # Historical Response EFA blocks are 3/5 h on DST transition dates; retain actual duration.
    spec_columns = [column for column in specs.columns if column != "window_hours"]
    frame = frame.merge(specs[spec_columns], on="product", how="left", validate="many_to_one")
    return frame[[
        "auction_id", "product", "family", "direction",
        "delivery_start_utc", "delivery_end_utc", "window_hours",
        "cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour",
        "minimum_mw", "whole_mw", "bm_required", "response_seconds",
        "energy_guard_hours",
    ]]


def main() -> None:
    old = _normalise_fy2025()
    current = load_eac_service_history(CURRENT)
    columns = old.columns.tolist()
    current = current[columns].copy()
    frame = pd.concat([old, current], ignore_index=True)
    frame = frame.sort_values(["delivery_start_utc", "product", "auction_id"])
    frame = frame.drop_duplicates(["delivery_start_utc", "product"], keep="last")
    frame = frame.reset_index(drop=True)
    text = frame.to_csv(index=False, lineterminator="\n")
    OUTPUT.write_text(text, encoding="utf-8", newline="")
    coverage = {}
    for product, group in frame.groupby("product"):
        local = group["delivery_start_utc"].dt.tz_convert("Europe/London")
        coverage[str(product)] = {
            "rows": int(len(group)),
            "first_delivery_date": str(local.dt.date.min()),
            "last_delivery_date": str(local.dt.date.max()),
        }
    payload = {
        "schema_version": "1.0",
        "stage": "13_multiservice_issue_time_history",
        "source": "NESO EAC Results Summary FY2025 archive + Stage 11 current-results archive",
        "rights": "NESO Open Data Licence",
        "rows": int(len(frame)),
        "products": sorted(frame["product"].unique().tolist()),
        "coverage": coverage,
        "fy2025_source_sha256": _sha256(RAW),
        "stage11_source_sha256": _sha256(CURRENT),
        "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "boundary": "system clearing results only; no participant or sell-order identity fields",
    }
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
