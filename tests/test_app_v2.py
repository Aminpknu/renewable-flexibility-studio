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
