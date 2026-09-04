import json
from pathlib import Path

import numpy as np
import pandas as pd

import app
from adapters.spatial_demand import load_latest_spatial_demand, select_zone_demand

ROOT = Path(__file__).resolve().parents[1]


def test_spatial_underlying_demand_reconciles_to_national_proxy() -> None:
    frame = load_latest_spatial_demand(ROOT / "data" / "latest_spatial_demand_forecast.csv")
    assert len(frame) == 480
    assert frame["zone"].nunique() == 10
    assert frame["settlement_period"].nunique() == 48
    allocated = frame.groupby("settlement_period")["zone_underlying_demand_mw"].sum()
    national = frame.groupby("settlement_period")["national_underlying_demand_proxy_mw"].first()
    assert np.allclose(allocated, national, atol=1e-6)
    assert np.allclose(frame.groupby("settlement_period")["zone_demand_share"].sum(), 1.0)


def test_underlying_minus_embedded_reconciles_to_neso_national_demand() -> None:
    demand = load_latest_spatial_demand(ROOT / "data" / "latest_spatial_demand_forecast.csv")
    renewable = pd.read_csv(ROOT / "data" / "latest_spatial_forecast.csv")
    merged = demand.merge(
        renewable[["settlement_period", "zone", "zone_total_forecast_mw"]],
        on=["settlement_period", "zone"], validate="one_to_one",
    )
    merged["net_load_mw"] = merged["zone_underlying_demand_mw"] - merged["zone_total_forecast_mw"]
    net = merged.groupby("settlement_period")["net_load_mw"].sum()
    ndf = merged.groupby("settlement_period")["national_demand_mw"].first()
    assert np.allclose(net, ndf, atol=1e-6)


def test_spatial_demand_target_is_not_silently_relabelled() -> None:
    demand = load_latest_spatial_demand(ROOT / "data" / "latest_spatial_demand_forecast.csv")
    renewable = pd.read_csv(ROOT / "data" / "latest_forecast.csv")
    demand_target = demand["target_date"].dt.strftime("%Y-%m-%d").unique().tolist()[0]
    renewable_target = renewable["target_date"].unique().tolist()[0]
    if demand_target != renewable_target:
        note, cards, _, _ = app._spatial_zone_view("London", "mixed", 100.0, 50.0, 90.0, 90.0)
        assert "STALE" in str(cards) and "not reused as current" in str(note)
    assert len(select_zone_demand(demand, "London")) == 48


def test_spatial_demand_manifest_preserves_proxy_boundary() -> None:
    manifest = json.loads((ROOT / "data" / "spatial_demand_manifest.json").read_text(encoding="utf-8"))
    assert manifest["stage"] == "spatial_demand_allocation"
    assert manifest["zones"] == 10
    assert manifest["spatial_weighting"]["local_authorities"] == 350
    assert manifest["spatial_weighting"]["gsp_polygon_fallback_local_authorities"] == 0
    assert manifest["profile_validation"]["improvement_vs_flat_pct"] > 0
    assert manifest["latest_forecast"]["demand_publish_time_utc"].startswith("2026-09-02T11:48")
    boundary = " ".join(manifest["semantic_boundary"])
    assert "not measured city demand" in boundary
    assert "National Demand" in boundary


def test_spatial_zone_view_includes_underlying_demand_and_net_load() -> None:
    note, cards, virtual_figure, system_figure = app._spatial_zone_view(
        "London", "mixed", 100.0, 50.0, 90.0, 90.0
    )
    if "STALE" in str(cards):
        assert "awaiting a target-matched refresh" in str(virtual_figure.layout.annotations[0].text)
        return
    labels = [card.children[0].children for card in cards]
    assert "Underlying demand proxy" in labels
    assert "Embedded wind + solar" in labels
    assert "Peak net load" in labels
    assert "Underlying demand proxy" in [trace.name for trace in system_figure.data]
    assert "Net load after embedded wind + solar" in [trace.name for trace in system_figure.data]
    assert len(virtual_figure.data) == 3
    assert "not measured municipal demand" in str(note)
