from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pandas as pd

import app
from adapters.grid_context import fetch_day_ahead_demand
from adapters.latest_forecast import load_latest_forecast
from engine.portfolio import build_virtual_forecast, build_virtual_portfolio
from engine.uncertainty import PredictionIntervalConfig, build_forecast_only_prediction_interval

ROOT = Path(__file__).resolve().parents[1]


def test_latest_forecast_bundle_is_complete() -> None:
    frame = load_latest_forecast(ROOT / "data" / "latest_forecast.csv")
    assert len(frame) == 48
    assert frame["target_date"].dt.strftime("%Y-%m-%d").unique().tolist() == ["2026-09-03"]
    assert frame["forecast_created_utc"].notna().all()


def test_future_interval_uses_history_only() -> None:
    latest = load_latest_forecast(ROOT / "data" / "latest_forecast.csv")
    history = build_virtual_portfolio(app.HISTORICAL_DATA, "mixed", 100.0, 0.5)
    future = build_virtual_forecast(latest, "mixed", 100.0, 0.5)
    interval, meta = build_forecast_only_prediction_interval(
        history, future, "2026-09-03",
        PredictionIntervalConfig(lookback_days=180, minimum_history_days=30),
    )
    assert meta["available"] is True
    assert meta["calibration_end"] < "2026-09-03"
    assert {"prediction_interval_lower_mw", "prediction_interval_upper_mw"}.issubset(interval.columns)
    assert (interval["prediction_interval_lower_mw"] <= interval["forecast_mw"]).all()
    assert (interval["prediction_interval_upper_mw"] >= interval["forecast_mw"]).all()


def test_grid_adapter_filters_target_date(monkeypatch) -> None:
    rows = []
    for date, count in (("2026-09-02", 2), ("2026-09-03", 48), ("2026-09-04", 2)):
        for period in range(1, count + 1):
            rows.append({
                "settlementDate": date, "settlementPeriod": period,
                "startTime": f"2026-09-03T{(period-1)//2:02d}:{'30' if period % 2 == 0 else '00'}:00Z",
                "publishTime": "2026-09-02T12:47:00Z",
                "nationalDemand": 20000 + period,
                "transmissionSystemDemand": 22000 + period,
            })
    payload = json.dumps({"data": rows}).encode()
    class FakeResponse:
        def __enter__(self): return BytesIO(payload)
        def __exit__(self, *_args): return False
    monkeypatch.setattr("adapters.grid_context.urlopen", lambda *_args, **_kwargs: FakeResponse())
    frame = fetch_day_ahead_demand("2026-09-03")
    assert len(frame) == 48
    assert frame["settlement_period"].tolist() == list(range(1, 49))
    assert frame["national_demand_mw"].iloc[0] == 20001


def test_tomorrow_planning_does_not_simulate_future_dispatch(monkeypatch) -> None:
    grid = pd.DataFrame({
        "settlement_period": range(1, 49),
        "valid_time_utc": pd.date_range("2026-09-02T23:00:00Z", periods=48, freq="30min"),
        "publish_time_utc": pd.Timestamp("2026-09-02T12:47:00Z"),
        "national_demand_mw": 25000.0,
        "transmission_system_demand_mw": 27000.0,
    })
    monkeypatch.setattr(app, "fetch_day_ahead_demand", lambda _date: grid)
    note, cards, forecast_fig, reserve_fig, grid_fig = app.run_tomorrow_planning(
        1, "mixed", 100, 50, 90, 90, 50
    )
    text = str(note)
    assert "no actual future generation or dispatch path is assumed" in text
    assert "25 MW / 200 MWh" in text
    assert "Operational recommendation" in text
    assert "Scheduled renewable export" in [trace.name for trace in forecast_fig.data]
    assert "Downward reserve need" in [trace.name for trace in reserve_fig.data]
    assert "Upward charge headroom need" in [trace.name for trace in reserve_fig.data]
    assert "NESO National Demand Forecast" in [trace.name for trace in grid_fig.data]
    assert any(card.children[0].children == "Installed design" and "25 MW / 200 MWh" in card.children[1].children for card in cards)
    assert any(card.children[0].children == "Current SOC" and card.children[1].children == "50%" for card in cards)
    assert any(card.children[0].children == "Recommended start SOC" for card in cards)
    assert any(card.children[0].children == "Safe SOC band" for card in cards)
