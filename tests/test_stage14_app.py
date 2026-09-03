import numpy as np

import app


def test_stage14_forecast_day_helper_uses_probabilistic_quantiles() -> None:
    frame, battery, planning = app._tomorrow_planning_data(
        "mixed", 100.0, 50.0, 25.0, 8.0, 50.0, 90.0
    )
    assert planning["uncertainty"]["method"].startswith("mix-aware conditional")
    assert {"p10_mw", "p50_mw", "p90_mw"}.issubset(frame.columns)
    assert np.all(frame["prediction_interval_lower_mw"] <= frame["forecast_mw"] + 1e-9)
    assert np.all(frame["prediction_interval_upper_mw"] >= frame["forecast_mw"] - 1e-9)
    assert planning["reserve"]["overall_reserve_coverage_pct"] >= 0.0
    assert battery.power_mw == 25.0


def test_stage14_chart_and_layout_are_explicit_about_quantiles() -> None:
    frame, _, _ = app._tomorrow_planning_data(
        "mixed", 100.0, 75.0, 25.0, 8.0, 50.0, 90.0
    )
    figure = app._tomorrow_forecast_figure(frame)
    names = [trace.name for trace in figure.data if trace.name]
    assert "P10\u2013P90 central range" in names
    assert "P50 statistical median" in names
    assert "Scheduled renewable export" in names
    layout = str(app.app.layout)
    assert "Stage 14" in layout
    assert "P10/P50/P90" in layout

