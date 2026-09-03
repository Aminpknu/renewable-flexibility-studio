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
    assert any(trace.name == "Selected Stage A design" for trace in figure.data)
    text = str(note)
    assert "scenario-based screening outputs" in text
    assert "No actual market-revenue claim" in text