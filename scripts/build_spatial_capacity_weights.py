"""Build fixed REPD renewable-capacity proxy weights for the 10 V2 spatial zones."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
REPD_PATH = ROOT / "data" / "repd_july_2026.csv"
ZONE_CONFIG = ROOT / "config" / "spatial_zones.json"
OUT_PATH = ROOT / "data" / "spatial_capacity_weights.csv"
MANIFEST_PATH = ROOT / "data" / "spatial_capacity_weights_manifest.json"
REPD_URL = "https://assets.publishing.service.gov.uk/media/6a6cbdc00c36759b5ccaa305/REPD_Publication_Q2_2026.csv"


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0088
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlambda / 2) ** 2
    return 2 * r * np.arctan2(np.sqrt(a), np.sqrt(1 - a))


def main() -> None:
    try:
        from pyproj import Transformer
    except ImportError as error:
        raise SystemExit("Build-only dependency pyproj is required to regenerate spatial weights.") from error

    zones = json.loads(ZONE_CONFIG.read_text(encoding="utf-8"))["zones"]
    frame = pd.read_csv(REPD_PATH, encoding="cp1252", low_memory=False)
    frame["capacity_mw"] = pd.to_numeric(frame["Installed Capacity (MWelec)"], errors="coerce")
    frame["x"] = pd.to_numeric(frame["X-coordinate"], errors="coerce")
    frame["y"] = pd.to_numeric(frame["Y-coordinate"], errors="coerce")
    frame = frame.loc[
        frame["Development Status (short)"].eq("Operational")
        & frame["Country"].isin(["England", "Scotland", "Wales"])
        & frame["Technology Type"].isin(["Wind Onshore", "Wind Offshore", "Solar Photovoltaics"])
        & frame["capacity_mw"].gt(0)
        & frame["x"].notna() & frame["y"].notna()
    ].copy()
    transformer = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(frame["x"].to_numpy(), frame["y"].to_numpy())
    frame["longitude"], frame["latitude"] = lon, lat

    zone_lat = np.array([z["latitude"] for z in zones], dtype=float)
    zone_lon = np.array([z["longitude"] for z in zones], dtype=float)
    assignments = []
    for row in frame.itertuples(index=False):
        distances = haversine_km(row.latitude, row.longitude, zone_lat, zone_lon)
        assignments.append(zones[int(np.argmin(distances))]["name"])
    frame["zone"] = assignments
    frame["technology_group"] = np.where(
        frame["Technology Type"].eq("Solar Photovoltaics"), "solar", "wind"
    )
    grouped = frame.groupby(["technology_group", "zone"], as_index=False).agg(
        proxy_capacity_mw=("capacity_mw", "sum"),
        project_count=("Ref ID", "count"),
    )
    full = pd.MultiIndex.from_product(
        [["wind", "solar"], [z["name"] for z in zones]],
        names=["technology_group", "zone"],
    ).to_frame(index=False)
    grouped = full.merge(grouped, on=["technology_group", "zone"], how="left").fillna(0)
    totals = grouped.groupby("technology_group")["proxy_capacity_mw"].transform("sum")
    grouped["proxy_share"] = grouped["proxy_capacity_mw"] / totals
    grouped.to_csv(OUT_PATH, index=False)

    raw_sha = hashlib.sha256(REPD_PATH.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "1.0",
        "source": "DESNZ Renewable Energy Planning Database (REPD), July 2026",
        "source_url": REPD_URL,
        "source_sha256": raw_sha,
        "licence": "UK Open Government Licence",
        "scope": "Operational wind onshore/offshore and solar PV in England, Scotland and Wales",
        "allocation": "Each REPD project is assigned to the nearest of the ten V2 representative weather locations using OSGB36 easting/northing converted to WGS84.",
        "purpose": "Spatial weighting proxy only; NESO national embedded capacity remains authoritative for total MW.",
        "limitations": [
            "REPD tracks projects above 150 kW and had a 1 MW threshold before 2021.",
            "The weights are not a complete census of embedded renewable capacity.",
            "Nearest-zone assignment is a spatial proxy, not a network connection-zone model."
        ],
        "rows_used": int(len(frame)),
        "proxy_capacity_mw": {
            key: float(value) for key, value in frame.groupby("technology_group")["capacity_mw"].sum().items()
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(grouped.to_string(index=False))
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
