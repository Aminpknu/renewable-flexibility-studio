"""Build ten-zone demand weights, GSP load shapes and latest spatial demand forecast."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import zipfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "build_sources" / "spatial_demand"
ZONES_PATH = ROOT / "config" / "spatial_zones.json"
LATEST_RENEWABLE_PATH = ROOT / "data" / "latest_forecast.csv"
WEIGHTS_PATH = ROOT / "data" / "spatial_demand_zone_weights.csv"
ZONE_GSP_PATH = ROOT / "data" / "spatial_demand_zone_gsp_mix.csv"
PROFILE_PATH = ROOT / "data" / "gsp_group_demand_profiles.csv"
LATEST_PATH = ROOT / "data" / "latest_spatial_demand_forecast.csv"
MANIFEST_PATH = ROOT / "data" / "spatial_demand_manifest.json"
GSP_ZIPS = [SOURCE / "AGV_2025.zip", SOURCE / "AGV_2026.zip"]
GSP_REGIONS_ZIP = SOURCE / "gsp_regions_20260209.zip"
LA_CONSUMPTION_PATH = SOURCE / "elec_LA_stacked_2005-2024.csv"
LAD_CENTROIDS_PATH = SOURCE / "lad24_centroids.json"
GSP_GEOJSON_MEMBER = "Proj_4326/GSP_regions_4326_20260209.geojson"
HISTORY_START = pd.Timestamp("2025-01-01")
HISTORY_END = pd.Timestamp("2026-08-31")
VALIDATION_TRAIN_END = pd.Timestamp("2026-03-31")
VALIDATION_START = pd.Timestamp("2026-04-01")
VALIDATION_END = pd.Timestamp("2026-06-30")
ELEXON_HISTORY_URL = "https://data.elexon.co.uk/bmrs/api/v1/forecast/demand/day-ahead/history"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def _point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        crosses = ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi
        )
        if crosses:
            inside = not inside
        j = i
    return inside


def _point_in_geometry(lon: float, lat: float, geometry: dict) -> bool:
    polygons = geometry["coordinates"] if geometry["type"] == "MultiPolygon" else [geometry["coordinates"]]
    for polygon in polygons:
        if not polygon or not _point_in_ring(lon, lat, polygon[0]):
            continue
        if any(_point_in_ring(lon, lat, hole) for hole in polygon[1:]):
            continue
        return True
    return False


def _load_zones() -> pd.DataFrame:
    payload = json.loads(ZONES_PATH.read_text(encoding="utf-8"))
    frame = pd.DataFrame(payload["zones"])
    if len(frame) != 10 or frame["name"].nunique() != 10:
        raise ValueError("Spatial demand requires the ten authoritative V2 zones.")
    return frame.rename(columns={"name": "zone"})


def _load_gsp_boundaries() -> list[dict]:
    with zipfile.ZipFile(GSP_REGIONS_ZIP) as archive:
        payload = json.loads(archive.read(GSP_GEOJSON_MEMBER))
    features = []
    for feature in payload["features"]:
        group = feature.get("properties", {}).get("GSPGroup")
        geometry = feature.get("geometry")
        if group and geometry:
            features.append({"group": group, "geometry": geometry})
    if not features:
        raise ValueError("NESO GSP region archive contains no usable GSPGroup polygons.")
    return features


def _gsp_group_for_point(lon: float, lat: float, features: list[dict]) -> str | None:
    for feature in features:
        if _point_in_geometry(lon, lat, feature["geometry"]):
            return str(feature["group"])
    return None


def _load_lad_centroids() -> pd.DataFrame:
    payload = json.loads(LAD_CENTROIDS_PATH.read_text(encoding="utf-8"))
    rows = [item["attributes"] for item in payload.get("features", [])]
    result = pd.DataFrame(rows).rename(
        columns={"LAD24CD": "LA_Code", "LAD24NM": "LA", "LONG": "longitude", "LAT": "latitude"}
    )
    return result[["LA_Code", "LA", "longitude", "latitude"]].dropna()


def _nearest_zone(lon: float, lat: float, zones: pd.DataFrame) -> str:
    distance = zones.apply(
        lambda row: _haversine_km(lon, lat, float(row["longitude"]), float(row["latitude"])), axis=1
    )
    return str(zones.loc[distance.idxmin(), "zone"])


def build_zone_weights(zones: pd.DataFrame, gsp_features: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    consumption = pd.read_csv(LA_CONSUMPTION_PATH, encoding="cp1252", low_memory=False)
    consumption = consumption.loc[consumption["Year"].eq(2024)].copy()
    for column in ("Domestic_consumption_GWh", "Non_domestic_consumption_GWh", "All_consumption_GWh"):
        consumption[column] = pd.to_numeric(consumption[column], errors="raise")
    centroids = _load_lad_centroids()
    merged = consumption.merge(centroids, on="LA_Code", how="left", suffixes=("", "_ons"))
    missing = merged["longitude"].isna()
    if missing.any():
        by_name = centroids.drop_duplicates("LA").set_index("LA")
        for idx in merged.index[missing]:
            name = merged.at[idx, "LA"]
            if name in by_name.index:
                merged.at[idx, "longitude"] = by_name.at[name, "longitude"]
                merged.at[idx, "latitude"] = by_name.at[name, "latitude"]
    if merged[["longitude", "latitude"]].isna().any().any():
        names = merged.loc[merged["longitude"].isna(), "LA"].tolist()
        raise ValueError(f"Missing ONS centroids for DESNZ local authorities: {names}")
    merged["zone"] = [
        _nearest_zone(float(lon), float(lat), zones)
        for lon, lat in zip(merged["longitude"], merged["latitude"], strict=True)
    ]
    zone_anchor_group = {}
    for row in zones.itertuples(index=False):
        group = _gsp_group_for_point(float(row.longitude), float(row.latitude), gsp_features)
        if group is None:
            raise ValueError(f"Zone anchor {row.zone} does not fall inside a NESO GSP boundary.")
        zone_anchor_group[str(row.zone)] = group
    groups = []
    fallback_count = 0
    for row in merged.itertuples(index=False):
        group = _gsp_group_for_point(float(row.longitude), float(row.latitude), gsp_features)
        if group is None:
            group = zone_anchor_group[str(row.zone)]
            fallback_count += 1
        groups.append(group)
    merged["gsp_group"] = groups

    zone_weights = merged.groupby("zone", as_index=False).agg(
        domestic_consumption_gwh=("Domestic_consumption_GWh", "sum"),
        non_domestic_consumption_gwh=("Non_domestic_consumption_GWh", "sum"),
        annual_consumption_gwh=("All_consumption_GWh", "sum"),
        local_authority_count=("LA_Code", "nunique"),
    )
    zone_weights["annual_consumption_share"] = (
        zone_weights["annual_consumption_gwh"] / zone_weights["annual_consumption_gwh"].sum()
    )
    zone_weights = zones[["zone", "latitude", "longitude"]].merge(zone_weights, on="zone", validate="one_to_one")
    if not np.isclose(zone_weights["annual_consumption_share"].sum(), 1.0, atol=1e-10):
        raise AssertionError("Zone annual electricity-consumption shares do not sum to one.")
    mix = merged.groupby(["zone", "gsp_group"], as_index=False).agg(
        annual_consumption_gwh=("All_consumption_GWh", "sum"),
        local_authority_count=("LA_Code", "nunique"),
    )
    mix["zone_gsp_weight"] = mix["annual_consumption_gwh"] / mix.groupby("zone")["annual_consumption_gwh"].transform("sum")
    if not np.allclose(mix.groupby("zone")["zone_gsp_weight"].sum().to_numpy(), 1.0, atol=1e-10):
        raise AssertionError("Zone GSP composition weights do not sum to one.")
    meta = {
        "desnz_year": 2024,
        "local_authorities": int(merged["LA_Code"].nunique()),
        "ons_centroid_name_fallbacks": int(missing.sum()),
        "gsp_polygon_fallback_local_authorities": int(fallback_count),
        "zone_anchor_gsp_groups": zone_anchor_group,
    }
    return zone_weights.sort_values("zone"), mix.sort_values(["zone", "gsp_group"]), meta


def _load_agv_history() -> pd.DataFrame:
    usecols = [
        "Flow Run Date", "GSP Group Id", "Settlement Date", "Settlement Run Type",
        "CDCA Run Number", "Date of Aggregation", "Settlement Period",
        "Import/Export Indicator", "GSP Group Take Volume",
    ]
    pieces = []
    for archive_path in GSP_ZIPS:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                if member.lower().endswith(".csv"):
                    pieces.append(pd.read_csv(archive.open(member), usecols=usecols))
    frame = pd.concat(pieces, ignore_index=True)
    frame["settlement_date"] = pd.to_datetime(frame["Settlement Date"].astype(str), format="%Y%m%d", errors="raise").dt.normalize()
    frame["flow_run_date"] = pd.to_datetime(frame["Flow Run Date"].astype(str), format="%Y%m%d", errors="coerce")
    frame["aggregation_date"] = pd.to_datetime(frame["Date of Aggregation"].astype(str), format="%Y%m%d", errors="coerce")
    frame["settlement_period"] = pd.to_numeric(frame["Settlement Period"], errors="raise").astype(int)
    frame["cdca_run_number"] = pd.to_numeric(frame["CDCA Run Number"], errors="coerce").fillna(-1).astype(int)
    frame["take_mwh"] = pd.to_numeric(frame["GSP Group Take Volume"], errors="raise")
    frame["gsp_group"] = frame["GSP Group Id"].astype(str)
    frame = frame.loc[frame["settlement_date"].between(HISTORY_START, HISTORY_END)].copy()
    frame["signed_take_mwh"] = np.where(frame["Import/Export Indicator"].eq("E"), -frame["take_mwh"], frame["take_mwh"])
    frame = frame.sort_values(
        ["settlement_date", "settlement_period", "gsp_group", "flow_run_date", "aggregation_date", "cdca_run_number"]
    )
    latest = frame.groupby(["settlement_date", "settlement_period", "gsp_group"], as_index=False).tail(1).copy()
    if latest.duplicated(["settlement_date", "settlement_period", "gsp_group"]).any():
        raise AssertionError("Consolidated AGV history still contains duplicate settlement keys.")
    latest["shape_take_mwh"] = latest["signed_take_mwh"].clip(lower=0.0)
    latest["month"] = latest["settlement_date"].dt.month
    dow = latest["settlement_date"].dt.dayofweek
    latest["day_class"] = np.where(dow.lt(5), "weekday", np.where(dow.eq(5), "saturday", "sunday"))
    daily_total = latest.groupby(["settlement_date", "gsp_group"])["shape_take_mwh"].transform("sum")
    latest = latest.loc[daily_total.gt(0)].copy()
    latest["daily_energy_share"] = latest["shape_take_mwh"] / daily_total[daily_total.gt(0)]
    return latest


def _profile_table(history: pd.DataFrame) -> pd.DataFrame:
    profile = history.groupby(
        ["gsp_group", "month", "day_class", "settlement_period"], as_index=False
    ).agg(
        mean_daily_energy_share=("daily_energy_share", "mean"),
        observations=("settlement_date", "nunique"),
    )
    profile["mean_daily_energy_share"] /= profile.groupby(
        ["gsp_group", "month", "day_class"]
    )["mean_daily_energy_share"].transform("sum")
    return profile


def _target_group_profiles(
    profile: pd.DataFrame, target_date: pd.Timestamp, periods: list[int], groups: list[str]
) -> pd.DataFrame:
    month = int(target_date.month)
    day_class = "weekday" if target_date.dayofweek < 5 else ("saturday" if target_date.dayofweek == 5 else "sunday")
    rows = []
    for group in groups:
        selected = profile.loc[
            profile["gsp_group"].eq(group)
            & profile["month"].eq(month)
            & profile["day_class"].eq(day_class)
            & profile["settlement_period"].isin(periods)
        ].copy()
        if len(selected) != len(periods):
            selected = profile.loc[
                profile["gsp_group"].eq(group)
                & profile["day_class"].eq(day_class)
                & profile["settlement_period"].isin(periods)
            ].groupby(["gsp_group", "settlement_period"], as_index=False).agg(
                mean_daily_energy_share=("mean_daily_energy_share", "mean"), observations=("observations", "sum")
            )
        if len(selected) != len(periods):
            raise ValueError(f"No complete historical GSP demand shape for {group} and target periods.")
        selected = selected.sort_values("settlement_period")
        selected["profile_share"] = (
            selected["mean_daily_energy_share"] / selected["mean_daily_energy_share"].sum()
        )
        selected["gsp_group"] = group
        rows.append(selected[["gsp_group", "settlement_period", "profile_share", "observations"]])
    result = pd.concat(rows, ignore_index=True)
    return result


def validate_profile_shape(history: pd.DataFrame) -> dict:
    train = history.loc[history["settlement_date"].le(VALIDATION_TRAIN_END)].copy()
    test = history.loc[history["settlement_date"].between(VALIDATION_START, VALIDATION_END)].copy()
    profile = _profile_table(train)
    merged = test.merge(
        profile[["gsp_group", "month", "day_class", "settlement_period", "mean_daily_energy_share"]],
        on=["gsp_group", "month", "day_class", "settlement_period"], how="left", validate="many_to_one",
    )
    if merged["mean_daily_energy_share"].isna().any():
        raise ValueError("Locked profile validation encountered missing historical shape cells.")
    predicted = merged["mean_daily_energy_share"].to_numpy(float)
    actual = merged["daily_energy_share"].to_numpy(float)
    profile_mae_pp = float(np.mean(np.abs(predicted - actual)) * 100.0)
    flat = merged.groupby(["settlement_date", "gsp_group"])["settlement_period"].transform("count")
    flat_pred = 1.0 / flat.to_numpy(float)
    flat_mae_pp = float(np.mean(np.abs(flat_pred - actual)) * 100.0)
    return {
        "validation_start": VALIDATION_START.date().isoformat(),
        "validation_end": VALIDATION_END.date().isoformat(),
        "gsp_days": int(merged.groupby(["settlement_date", "gsp_group"]).ngroups),
        "profile_mae_percentage_points_of_daily_energy": profile_mae_pp,
        "flat_profile_mae_percentage_points_of_daily_energy": flat_mae_pp,
        "improvement_vs_flat_pct": float(100.0 * (1.0 - profile_mae_pp / flat_mae_pp)),
    }


def _fetch_ndf_as_of(publish_time: pd.Timestamp) -> pd.DataFrame:
    query = urlencode({"publishTime": publish_time.strftime("%Y-%m-%dT%H:%M:%SZ")})
    with urlopen(f"{ELEXON_HISTORY_URL}?{query}", timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))
    frame = pd.DataFrame(payload.get("data", []))
    if frame.empty:
        return frame
    frame = frame.loc[frame["boundary"].eq("N")].copy()
    frame["settlement_period"] = pd.to_numeric(frame["settlementPeriod"], errors="raise").astype(int)
    frame["valid_time_utc"] = pd.to_datetime(frame["startTime"], utc=True)
    frame["publish_time_utc"] = pd.to_datetime(frame["publishTime"], utc=True)
    frame["national_demand_mw"] = pd.to_numeric(frame["nationalDemand"], errors="raise")
    frame["target_date"] = pd.to_datetime(frame["settlementDate"]).dt.normalize()
    return frame


def _find_complete_predelivery_ndf(target_date: pd.Timestamp, expected_periods: int) -> pd.DataFrame:
    previous = target_date - pd.Timedelta(days=1)
    candidate_hours = list(range(12, 24)) + [10, 11]
    for hour in candidate_hours:
        as_of = pd.Timestamp(previous.date(), tz="UTC") + pd.Timedelta(hours=hour)
        frame = _fetch_ndf_as_of(as_of)
        selected = frame.loc[frame["target_date"].eq(target_date)].copy()
        if selected.empty:
            continue
        selected = selected.sort_values(["settlement_period", "publish_time_utc"]).drop_duplicates(
            "settlement_period", keep="last"
        )
        periods = selected["settlement_period"].tolist()
        if len(selected) == expected_periods and periods == list(range(1, expected_periods + 1)):
            return selected[[
                "target_date", "settlement_period", "valid_time_utc", "publish_time_utc", "national_demand_mw"
            ]].reset_index(drop=True)
    raise ValueError(f"No complete pre-delivery National Demand Forecast found for {target_date.date()}.")


def build_latest_zone_demand(
    zone_weights: pd.DataFrame,
    zone_gsp_mix: pd.DataFrame,
    profile: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    renewable = pd.read_csv(LATEST_RENEWABLE_PATH)
    renewable["target_date"] = pd.to_datetime(renewable["target_date"]).dt.normalize()
    target_values = renewable["target_date"].drop_duplicates().tolist()
    if len(target_values) != 1:
        raise ValueError("Latest renewable forecast must contain exactly one target date.")
    target = pd.Timestamp(target_values[0])
    periods = sorted(pd.to_numeric(renewable["settlement_period"], errors="raise").astype(int).unique().tolist())
    ndf = _find_complete_predelivery_ndf(target, len(periods))
    embedded = renewable[["settlement_period", "wind_forecast_mw", "solar_forecast_mw"]].copy()
    embedded["national_embedded_wind_solar_mw"] = (
        pd.to_numeric(embedded["wind_forecast_mw"], errors="raise")
        + pd.to_numeric(embedded["solar_forecast_mw"], errors="raise")
    )
    ndf = ndf.merge(
        embedded[["settlement_period", "national_embedded_wind_solar_mw"]],
        on="settlement_period", validate="one_to_one",
    )
    ndf["national_underlying_demand_proxy_mw"] = (
        ndf["national_demand_mw"] + ndf["national_embedded_wind_solar_mw"]
    )
    groups = sorted(zone_gsp_mix["gsp_group"].unique().tolist())
    group_profile = _target_group_profiles(profile, target, periods, groups)
    zone_shape = zone_gsp_mix.merge(group_profile, on="gsp_group", how="left", validate="many_to_many")
    if zone_shape["profile_share"].isna().any():
        raise ValueError("Zone demand shape could not map all GSP groups to historical profiles.")
    zone_shape["weighted_profile_share"] = zone_shape["zone_gsp_weight"] * zone_shape["profile_share"]
    zone_shape = zone_shape.groupby(["zone", "settlement_period"], as_index=False).agg(
        zone_daily_profile_share=("weighted_profile_share", "sum"),
        profile_observations=("observations", "sum"),
    )
    zone_shape["zone_daily_profile_share"] /= zone_shape.groupby("zone")["zone_daily_profile_share"].transform("sum")
    zone_shape = zone_shape.merge(
        zone_weights[["zone", "annual_consumption_share", "annual_consumption_gwh"]],
        on="zone", validate="many_to_one",
    )
    zone_shape["raw_period_weight"] = zone_shape["annual_consumption_share"] * zone_shape["zone_daily_profile_share"]
    zone_shape["zone_demand_share"] = zone_shape["raw_period_weight"] / zone_shape.groupby(
        "settlement_period"
    )["raw_period_weight"].transform("sum")
    result = zone_shape.merge(
        ndf[[
            "settlement_period", "valid_time_utc", "publish_time_utc", "national_demand_mw",
            "national_embedded_wind_solar_mw", "national_underlying_demand_proxy_mw",
        ]],
        on="settlement_period", how="left", validate="many_to_one",
    )
    result["target_date"] = target
    result["zone_underlying_demand_mw"] = (
        result["zone_demand_share"] * result["national_underlying_demand_proxy_mw"]
    )
    check = result.groupby("settlement_period", as_index=False).agg(
        allocated_underlying_mw=("zone_underlying_demand_mw", "sum"),
        national_underlying_mw=("national_underlying_demand_proxy_mw", "first"),
    )
    if not np.allclose(check["allocated_underlying_mw"], check["national_underlying_mw"], atol=1e-6):
        raise AssertionError("Spatial underlying-demand proxy does not reconcile to the national proxy.")
    result = result[[
        "target_date", "settlement_period", "valid_time_utc", "zone",
        "zone_underlying_demand_mw", "zone_demand_share", "national_demand_mw",
        "national_embedded_wind_solar_mw", "national_underlying_demand_proxy_mw",
        "annual_consumption_gwh", "annual_consumption_share", "zone_daily_profile_share",
        "profile_observations", "publish_time_utc",
    ]].sort_values(["settlement_period", "zone"]).reset_index(drop=True)
    meta = {
        "target_date": target.date().isoformat(),
        "settlement_periods": int(len(periods)),
        "demand_publish_time_utc": result["publish_time_utc"].max().isoformat(),
        "national_demand_peak_mw": float(result.groupby("settlement_period")["national_demand_mw"].first().max()),
        "national_underlying_demand_proxy_peak_mw": float(
            result.groupby("settlement_period")["national_underlying_demand_proxy_mw"].first().max()
        ),
    }
    return result, meta


def main() -> None:
    required = [*GSP_ZIPS, GSP_REGIONS_ZIP, LA_CONSUMPTION_PATH, LAD_CENTROIDS_PATH, LATEST_RENEWABLE_PATH]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Spatial demand build sources are missing: {missing}")
    zones = _load_zones()
    gsp_features = _load_gsp_boundaries()
    zone_weights, zone_gsp_mix, spatial_meta = build_zone_weights(zones, gsp_features)
    history = _load_agv_history()
    profile = _profile_table(history)
    validation = validate_profile_shape(history)
    latest, target_meta = build_latest_zone_demand(zone_weights, zone_gsp_mix, profile)

    zone_weights.to_csv(WEIGHTS_PATH, index=False)
    zone_gsp_mix.to_csv(ZONE_GSP_PATH, index=False)
    profile.to_csv(PROFILE_PATH, index=False)
    latest.to_csv(LATEST_PATH, index=False, date_format="%Y-%m-%dT%H:%M:%S%z")

    manifest = {
        "schema_version": "1.0",
        "stage": "spatial_demand_allocation",
        "method": (
            "DESNZ 2024 local-authority annual electricity weights + Elexon CDCA-I029 GSP Group Take "
            "within-day shapes; underlying demand reconciled to NDF + V2 embedded wind/solar, with net load reconciling to NDF"
        ),
        "zones": int(zone_weights["zone"].nunique()),
        "spatial_weighting": spatial_meta,
        "gsp_history": {
            "start": history["settlement_date"].min().date().isoformat(),
            "end": history["settlement_date"].max().date().isoformat(),
            "rows": int(len(history)),
            "groups": int(history["gsp_group"].nunique()),
            "export_or_negative_shape_rows_clipped_to_zero": int(history["signed_take_mwh"].lt(0).sum()),
        },
        "profile_validation": validation,
        "latest_forecast": target_meta,
        "sources": {
            "elexon_gsp_take": {
                "description": "Aggregated GSP Group Take Volumes (CDCA-I029), 2025 and 2026 open settlement archives",
                "page": "https://www.elexon.co.uk/bsc/data/open-settlement-data/",
                "files": ["https://www.elexon.co.uk/open-data/AGV_2025.zip", "https://www.elexon.co.uk/open-data/AGV_2026.zip"],
                "sha256": {path.name: _sha256(path) for path in GSP_ZIPS},
            },
            "desnz_subnational_electricity": {
                "description": "Electricity consumption by Local Authority, 2005 to 2024; latest 2024 rows used",
                "url": "https://assets.publishing.service.gov.uk/media/694295bd9273c48f554cf4ef/elec_LA_stacked_2005-2024.csv",
                "sha256": _sha256(LA_CONSUMPTION_PATH),
            },
            "neso_gsp_boundaries": {
                "description": "GSP Regions 20260209, WGS84 boundaries with Elexon GSPGroup identifiers",
                "url": "https://api.neso.energy/dataset/2810092e-d4b2-472f-b955-d8bea01f9ec0/resource/5dfab3dd-f192-40ab-b97f-b365a594293c/download/gsp_regions_20260209.zip",
                "sha256": _sha256(GSP_REGIONS_ZIP),
            },
            "ons_lad_centroids": {
                "description": "Local Authority Districts December 2024 BGC attributes LONG/LAT",
                "service": "ONS Open Geography ArcGIS FeatureServer",
                "sha256": _sha256(LAD_CENTROIDS_PATH),
            },
            "neso_ndf": {
                "description": "Elexon Insights archive of NESO National Demand Forecast",
                "endpoint": ELEXON_HISTORY_URL,
            },
        },
        "semantic_boundary": [
            "zone underlying-demand proxy is a modelled spatial allocation, not measured city demand",
            "GSP Group Take is used for within-day shape only because it is net regional grid take, not gross customer consumption",
            "DESNZ annual local-authority consumption sets spatial level weights",
            "national underlying demand proxy equals NESO National Demand Forecast plus the V2 embedded wind and solar forecast because embedded generation suppresses National Demand",
            "subtracting the identical spatial embedded-renewable forecast makes ten-zone net load reconcile to NESO National Demand Forecast",
            "the spatial underlying-demand and net-load series are system-context proxies and must not be confused with the user-scaled virtual renewable portfolio",
        ],
        "outputs": {
            "zone_weights": WEIGHTS_PATH.name,
            "zone_gsp_mix": ZONE_GSP_PATH.name,
            "gsp_profiles": PROFILE_PATH.name,
            "latest_spatial_demand": LATEST_PATH.name,
        },
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(zone_weights.to_string(index=False))
    print(json.dumps({"validation": validation, "latest": target_meta}, indent=2))


if __name__ == "__main__":
    main()
