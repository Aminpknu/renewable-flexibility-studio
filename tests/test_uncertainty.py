from pathlib import Path

from adapters.forecast_data import load_historical_predictions
from engine.portfolio import build_virtual_portfolio
from engine.uncertainty import build_rolling_prediction_interval

ROOT = Path(__file__).resolve().parents[1]
DATA = load_historical_predictions(ROOT / "data" / "historical_backtest.csv")


def test_interval_uses_only_prior_dates_and_marks_outliers() -> None:
    portfolio = build_virtual_portfolio(DATA, "wind", 100.0)
    interval, meta = build_rolling_prediction_interval(portfolio, "2026-06-30")
    assert meta["available"] is True
    assert meta["nominal_coverage_pct"] == 80.0
    assert meta["calibration_end"] == "2026-06-29"
    assert int(meta["history_days"]) > 0
    assert len(interval) == 48
    assert interval["prediction_interval_lower_mw"].le(
        interval["prediction_interval_upper_mw"]
    ).all()
    assert interval["actual_inside_prediction_interval"].dtype == bool
    assert int(meta["outside_periods"]) > 0


def test_interval_refuses_to_use_future_data_when_history_is_short() -> None:
    portfolio = build_virtual_portfolio(DATA, "wind", 100.0)
    interval, meta = build_rolling_prediction_interval(portfolio, "2025-04-01")
    assert meta["available"] is False
    assert meta["reason"] == "insufficient_prior_history"
    assert meta["history_days"] == 0
    assert "prediction_interval_lower_mw" not in interval.columns


def test_directional_future_interval_uses_signed_residual_quantiles() -> None:
    from adapters.latest_forecast import load_latest_forecast
    from engine.portfolio import build_virtual_forecast
    from engine.uncertainty import (
        PredictionIntervalConfig,
        build_forecast_only_directional_interval,
    )

    latest = load_latest_forecast(ROOT / "data" / "latest_forecast.csv")
    history = build_virtual_portfolio(DATA, "mixed", 100.0, wind_share=0.5)
    future = build_virtual_forecast(latest, "mixed", 100.0, wind_share=0.5)
    interval, meta = build_forecast_only_directional_interval(
        history, future, "2026-09-03",
        PredictionIntervalConfig(lookback_days=180, minimum_history_days=30),
    )
    assert meta["available"] is True
    assert meta["calibration_end"] == "2026-06-30"
    assert meta["lower_quantile_pct"] == 10.0
    assert meta["upper_quantile_pct"] == 90.0
    assert len(interval) == 48
    assert interval["prediction_interval_lower_mw"].le(
        interval["prediction_interval_upper_mw"]
    ).all()
