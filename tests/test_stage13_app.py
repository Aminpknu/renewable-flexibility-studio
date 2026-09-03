import pytest

import app


def test_stage13_layout_cards_and_chart() -> None:
    layout = str(app.app.layout)
    assert "Issue-time, acceptance-calibrated multi-service strategy (Stage 13)" in layout
    assert "stage13-evidence-chart" in layout
    cards = app._stage13_evidence_cards()
    labels = [card.children[0].children for card in cards]
    assert "Stage 13 non-BM value" in labels
    assert "Acceptance Brier improvement" in labels
    non_bm_card = next(card for card in cards if card.children[0].children == "Stage 13 non-BM value")
    assert "£2.22m/yr" in non_bm_card.children[1].children
    figure = app._stage13_evidence_figure()
    assert len(figure.data) == 4
    assert any(trace.name == "Actual acceptance" for trace in figure.data)


def test_stage13_project_finance_sits_between_base_and_upper_bound() -> None:
    assumptions = app._project_finance_assumptions(
        25.0, 0.5, 15, 8.0, 2.0, 60.0, 6.0, 10,
        25.0, 0.0, 10, 12.0, 1.2, 0, 0.0,
    )
    scenarios = app._project_finance_scenarios(assumptions)
    base = scenarios["Forecast wholesale base"]
    calibrated = scenarios["Stage 13 non-BM calibrated"]
    upper = scenarios["Stage 11 non-BM upside"]
    assert base["project_npv_gbp"] < calibrated["project_npv_gbp"] < upper["project_npv_gbp"]
    assert calibrated["project_npv_gbp"] == pytest.approx(-13_059_723.5182, rel=1e-8)
    assert calibrated["minimum_dscr"] == pytest.approx(0.664182, rel=1e-5)
