from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import app
from adapters.spatial_forecast import build_spatial_virtual_forecast, load_latest_spatial_forecast

ROOT = Path(__file__).resolve().parents[1]


def test_latest_spatial_bundle_is_complete_and_reconciled() -> None:
    spatial = load_latest_spatial_forecast(ROOT / "data" / "latest_spatial_forecast.csv")
    assert spatial["zone"].nunique() == 10
    assert spatial["settlement_period"].nunique() == 48
    counts = spatial.groupby("settlement_period")["zone"].nunique()
    assert counts.eq(10).all()
    wind = spatial.groupby("settlement_period")["wind_share"].sum()
    solar = spatial.groupby("settlement_period")["solar_share"].sum()
    assert np.allclose(wind.to_numpy(), 1.0, atol=1e-9)
    assert np.allclose(solar.to_numpy(), 1.0, atol=1e-9)


def test_spatial_virtual_portfolio_reconciles_to_national() -> None:
    live_target = pd.to_datetime(app.LATEST_FORECAST["target_date"]).dt.normalize().iloc[0]
    spatial_target = pd.to_datetime(app.LATEST_SPATIAL_FORECAST["target_date"]).dt.normalize().iloc[0]
    if live_target != spatial_target:
        with pytest.raises(ValueError, match="target does not match"):
            build_spatial_virtual_forecast(app.LATEST_SPATIAL_FORECAST, app.LATEST_FORECAST, "mixed", 100.0, 0.5)
        return
    spatial = build_spatial_virtual_forecast(
        app.LATEST_SPATIAL_FORECAST, app.LATEST_FORECAST,
        "mixed", 100.0, 0.5,
    )
    assert spatial["zone"].nunique() == 10
    assert abs(spatial.groupby("zone")["zone_virtual_capacity_proxy_mw"].first().sum() - 100.0) < 1e-6


def test_spatial_zone_view_labels_proxy_boundary() -> None:
    note, cards, figure, system_figure = app._spatial_zone_view(
        "London", "mixed", 100.0, 50.0, 90.0, 90.0,
    )
    if "STALE" in str(cards):
        assert "not reused as current" in str(note)
        return
    text = str(note)
    assert "not an independently trained or observed city-generation forecast" in text
    assert "not an independently sized local battery recommendation" in text
    labels = [card.children[0].children for card in cards]
    assert "Indicative BESS share" in labels
    assert "Allocated wind forecast" in [trace.name for trace in figure.data]
    assert "Allocated solar forecast" in [trace.name for trace in figure.data]
    assert "Zone total" in [trace.name for trace in figure.data]

