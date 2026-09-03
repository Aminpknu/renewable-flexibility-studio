from __future__ import annotations

import hashlib
import json
from pathlib import Path

from adapters.neso_services import EAC_RESULTS_RESOURCE_ID, fetch_eac_service_results

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "neso_multiservice_prices.csv"
MANIFEST = ROOT / "data" / "neso_multiservice_prices_manifest.json"
START_UTC = "2026-03-31T22:00:00"
END_UTC = "2026-07-01T00:00:00"


def main() -> None:
    frame = fetch_eac_service_results(START_UTC, END_UTC)
    text = frame.to_csv(index=False, lineterminator="\n")
    OUTPUT.write_text(text, encoding="utf-8", newline="")
    payload = {
        "schema_version": "1.0",
        "source": "NESO Enduring Auction Capability Results Summary",
        "resource_id": EAC_RESULTS_RESOURCE_ID,
        "rights": "NESO Open Data Licence",
        "query_start_utc": START_UTC,
        "query_end_utc": END_UTC,
        "rows": int(len(frame)),
        "families": sorted(frame["family"].unique().tolist()),
        "products": sorted(frame["product"].unique().tolist()),
        "delivery_start_min_utc": frame["delivery_start_utc"].min().isoformat(),
        "delivery_start_max_utc": frame["delivery_start_utc"].max().isoformat(),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "sha256_normalisation": "UTF-8 text with LF line endings",
        "scope_note": "availability clearing-price evidence only; utilisation instructions/payments and performance penalties excluded",
    }
    MANIFEST.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
