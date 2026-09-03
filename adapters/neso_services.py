from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

import numpy as np
import pandas as pd

EAC_RESULTS_RESOURCE_ID = "596f29ac-0387-4ba4-a6d3-95c243140707"
EAC_SQL_URL = "https://api.neso.energy/api/3/action/datastore_search_sql"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SPEC_PATH = ROOT / "config" / "neso_service_products.json"


def load_service_specs(path: str | Path = DEFAULT_SPEC_PATH) -> pd.DataFrame:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    frame = pd.DataFrame(payload["products"])
    required = {"product", "family", "direction", "minimum_mw", "whole_mw", "bm_required", "energy_guard_hours", "window_hours"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"NESO service specification is missing columns: {missing}")
    if frame["product"].duplicated().any():
        raise ValueError("NESO service product definitions must be unique.")
    if not set(frame["direction"]).issubset({"upward", "downward"}):
        raise ValueError("NESO service direction must be upward or downward.")
    return frame.sort_values(["family", "product"]).reset_index(drop=True)


def fetch_eac_service_results(start_utc: str, end_utc: str, timeout_seconds: int = 60) -> pd.DataFrame:
    specs = load_service_specs()
    products = specs["product"].tolist()
    literals = ",".join(f"'{p}'" for p in products)
    sql = (
        f'SELECT * FROM "{EAC_RESULTS_RESOURCE_ID}" '
        f'WHERE "auctionProduct" IN ({literals}) '
        f'AND "deliveryStart">=\'{start_utc}\' AND "deliveryStart"<\'{end_utc}\' LIMIT 50000'
    )
    with urlopen(f"{EAC_SQL_URL}?sql={quote(sql)}", timeout=timeout_seconds) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not payload.get("success"):
        raise RuntimeError("NESO EAC API did not return a successful response.")
    frame = pd.DataFrame(payload.get("result", {}).get("records", []))
    required = {"auctionID", "auctionProduct", "serviceType", "deliveryStart", "deliveryEnd", "clearedVolume", "clearingPrice"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"NESO EAC response is missing columns: {missing}")
    if frame.empty:
        raise KeyError("No NESO EAC service results were returned.")
    frame["auction_id"] = pd.to_numeric(frame["auctionID"], errors="raise").astype(int)
    frame["product"] = frame["auctionProduct"].astype(str)
    frame["delivery_start_utc"] = pd.to_datetime(frame["deliveryStart"], utc=True, errors="raise")
    frame["delivery_end_utc"] = pd.to_datetime(frame["deliveryEnd"], utc=True, errors="raise")
    frame["cleared_volume_mw"] = pd.to_numeric(frame["clearedVolume"], errors="raise")
    frame["clearing_price_gbp_per_mw_per_hour"] = pd.to_numeric(frame["clearingPrice"], errors="raise")
    frame["window_hours"] = (frame["delivery_end_utc"] - frame["delivery_start_utc"]).dt.total_seconds() / 3600.0
    frame = frame.merge(specs, on="product", how="left", validate="many_to_one", suffixes=("", "_spec"))
    if frame["family"].isna().any():
        raise ValueError("EAC service result contains an undefined product.")
    if not np.isfinite(frame[["cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour", "window_hours"]].to_numpy(float)).all():
        raise ValueError("NESO EAC service results contain non-finite values.")
    if (frame["cleared_volume_mw"] < 0).any():
        raise ValueError("NESO EAC cleared volume cannot be negative.")
    if not np.allclose(frame["window_hours"], frame["window_hours_spec"], atol=1e-9):
        bad = frame.loc[~np.isclose(frame["window_hours"], frame["window_hours_spec"], atol=1e-9), ["product", "window_hours", "window_hours_spec"]]
        raise ValueError(f"NESO EAC delivery-window duration does not match service specification: {bad.head().to_dict('records')}")
    frame["availability_payment_per_mw_gbp"] = frame["clearing_price_gbp_per_mw_per_hour"] * frame["window_hours"]
    keep = [
        "auction_id", "product", "family", "direction", "delivery_start_utc", "delivery_end_utc",
        "window_hours", "cleared_volume_mw", "clearing_price_gbp_per_mw_per_hour",
        "availability_payment_per_mw_gbp", "minimum_mw", "whole_mw", "bm_required",
        "response_seconds", "energy_guard_hours",
    ]
    result = frame[keep].sort_values(["delivery_start_utc", "product"]).reset_index(drop=True)
    if result.duplicated(["delivery_start_utc", "product"]).any():
        raise ValueError("NESO EAC service archive contains duplicate product/windows.")
    return result


def load_eac_service_history(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    for column in ("delivery_start_utc", "delivery_end_utc"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    return frame.sort_values(["delivery_start_utc", "product"]).reset_index(drop=True)
