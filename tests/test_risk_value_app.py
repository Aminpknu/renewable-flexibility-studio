from __future__ import annotations

import app


def test_default_risk_value_layer_uses_selected_stage_a_design() -> None:
    note, cards, figure, sensitivity = app.update_risk_value(
        "mixed", 100, 50, 90, 90,
        100, 25, 0.5, 2.0, 15, 8, 2, 95,
    )
    values = {card.children[0].children: card.children[1].children for card in cards}
    assert values["Selected design"] == "25 MW / 200 MWh"
    assert "MWh/yr" in values["Annual avoided exposure"]
    assert "£" in values["NPV"]
    assert "£" in values["Break-even consequence"]
    assert values["Expected availability"] == "95%"
    assert len(figure.data) >= 2
    assert len(sensitivity.data) == 1
    assert any(trace.name == "Selected stable design" for trace in figure.data)
    text = str(note)
    assert "scenario-based screening outputs" in text
    assert "No actual market-revenue claim" in text

def test_downside_risk_layer_reports_probabilistic_npv_and_tail_loss() -> None:
    note, cards, npv_figure, stress_figure, payload = app.run_downside_risk(
        1, "mixed", 100, 50, 90, 90,
        100, 25, 0.5, 2.0, 15, 8, 2, 95,
        30, 3, 12345,
    )
    values = {card.children[0].children: card.children[1].children for card in cards}
    assert "P10 NPV" in values and "P50 NPV" in values and "P90 NPV" in values
    assert "95% CVaR loss" in values
    assert "Fail design gate" in values
    assert len(npv_figure.data) == 1
    assert len(stress_figure.data) == 1
    assert payload["stage"] == "6B_quantitative_downside_risk"
    assert payload["summary"]["loss_convention"] == "investment_loss_gbp = -NPV_gbp"
    assert payload["simulation_settings"]["seed"] == 12345
    assert "contiguous historical blocks" in str(note)

    download = app.download_downside_risk(1, payload)
    assert download["filename"] == "downside_risk_summary.json"
    assert "6B_quantitative_downside_risk" in download["content"]
