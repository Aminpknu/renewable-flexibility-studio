import app


def _text(component) -> str:
    if component is None:
        return ""
    if isinstance(component, (str, int, float)):
        return str(component)
    if isinstance(component, (list, tuple)):
        return " ".join(_text(item) for item in component)
    children = getattr(component, "children", None)
    return _text(children)


def test_app_uses_full_v2_date_archive() -> None:
    assert len(app.DATE_OPTIONS) == 450
    assert app.DATE_OPTIONS[0] == "2025-04-01"
    assert app.DATE_OPTIONS[-1] == "2026-06-30"
    assert app.DEFAULT_DATE == "2026-06-30"


def test_long_run_benchmark_is_visible() -> None:
    text = _text(app._long_run_benchmark_content())
    assert "33.5%" in text
    assert "50.2%" in text
    assert "44.4%" in text
    assert "Wind: 50 MW / 1800 MWh (36 h)" in text
    assert "Solar: 25 MW / 400 MWh (16 h)" in text
    assert "Mixed: 25 MW / 900 MWh (36 h)" in text


def test_initial_energy_assumption_is_explicit() -> None:
    text = app._initial_energy_explanation(25, 2, 50, 90)
    assert "25.0 MWh is assumed already stored" in text
    assert "20.0 MWh above the 10% reserve" in text
    assert "19.0 MWh deliverable" in text
    assert "earlier periods" in text
    conservative = app._initial_energy_explanation(25, 2, 10, 90)
    assert "no usable prior energy above the reserve" in conservative


def test_selected_day_note_identifies_forecast_quality_prior_energy_and_uncertainty() -> None:
    _g, _b, _cards, note, _stored = app.run_scenario(
        1, "2026-06-30", "wind", 100, 50, 25, 2, 50, 90
    )
    text = _text(note)
    assert "selected-day forecast MAE" in text
    assert "450-day out-of-sample average" in text
    assert "starts with 25.0 MWh stored" in text
    assert "assumed available from prior periods" in text
    assert "Forecast uncertainty: nominal 80% rolling expected range" in text
    assert "Actual output was outside the expected range" in text


def test_generation_chart_contains_uncertainty_band_and_outside_markers() -> None:
    generation, _battery, _cards, _note, _stored = app.run_scenario(
        1, "2026-06-30", "wind", 100, 50, 25, 2, 50, 90
    )
    names = [trace.name for trace in generation.data]
    assert "Nominal 80% expected range" in names
    assert "Forecast" in names
    assert "Actual" in names
    assert "After battery" in names
    assert "Actual outside range" in names


def test_sizing_section_has_clear_initial_placeholder() -> None:
    text = _text(app.app.layout)
    assert "Selected-day battery sizing (exploratory)" in text
    assert "No sizing result yet" in text
    assert "not the long-run battery recommendation" in text


def test_long_run_benchmark_includes_grid_settlement_exposure() -> None:
    text = _text(app._long_run_benchmark_content())
    assert "35.2%" in text
    assert "48.5%" in text
    assert "44.9%" in text
    assert "£4,533" in text
    assert "£2,497" in text
    assert "not battery profit" in text


def test_selected_day_elexon_exposure_is_visible() -> None:
    _g, _b, _cards, _note, stored = app.run_scenario(
        1, "2026-06-30", "wind", 100, 50, 25, 2, 50, 90
    )
    note, cards, figure = app.update_imbalance_settlement(stored, "2026-06-30")
    text = _text([note, cards])
    assert "£13,276" in text
    assert "£10,826" in text
    assert "18.5%" in text
    assert "not profit" in text
    names = [trace.name for trace in figure.data]
    assert "Imbalance before battery" in names
    assert "Residual after battery" in names
    assert "Elexon System Price" in names
