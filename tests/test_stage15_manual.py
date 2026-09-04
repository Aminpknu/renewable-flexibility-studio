import app


def test_stage15_regime_callback_and_layout() -> None:
    note, cards, figure = app.update_regime_comparison(
        "2025-04-01", "2026-06-30", "wind_outlook"
    )
    labels = [card.children[0].children for card in cards]
    assert "Evidence days" in labels
    assert "Days meeting 90%" in labels
    assert len(figure.data) >= 4
    assert "forecast quantities only" in str(note)
    layout = str(app.app.layout)
    assert "Seasonal & forecast-defined regime comparison" in layout
    assert "regime-date-range" in layout


def test_models_data_validation_guide_is_visible_and_complete() -> None:
    layout = str(app.app.layout)
    required = [
        "Models, Data & Validation Guide",
        "Forecast evidence and probabilistic percentiles (P10/P50/P90)",
        "Battery physics, firming and state of charge (SOC)",
        "Wholesale, imbalance and National Energy System Operator (NESO) service optimisation",
        "Project-finance screening",
        "Data sources and references",
        "Assumption register",
        "Practical manual: how to use the Studio",
        "Validation and reproducibility",
    ]
    for label in required:
        assert label in layout
