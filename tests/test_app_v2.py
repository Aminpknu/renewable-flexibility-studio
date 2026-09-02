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


def test_selected_day_note_identifies_forecast_quality_and_prior_energy() -> None:
    _g, _b, _cards, note, _stored = app.run_scenario(1, "2026-06-30", "wind", 100, 50, 25, 2, 50, 90)
    assert "selected-day forecast MAE" in note
    assert "450-day out-of-sample average" in note
    assert "starts with 25.0 MWh stored" in note
    assert "assumed available from prior periods" in note
