from pathlib import Path

import app


def test_stage17_decision_path_is_present():
    layout_text = str(app.app.layout)
    for label in ("01 Forecast", "02 Uncertainty", "03 Reserve", "04 Market", "05 Value", "06 Evidence"):
        assert label in layout_text
    assert "Validated analytical release" in layout_text


def test_stage17_avoids_generic_gradient_card_language():
    css = (Path(__file__).resolve().parents[1] / "assets" / "styles.css").read_text(encoding="utf-8")
    assert "linear-gradient" not in css
    assert ".decision-path" in css
    assert "border-radius: 999px" not in css
