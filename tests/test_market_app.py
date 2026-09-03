from __future__ import annotations

import app


def test_market_optimisation_layer_uses_stage_a_design_and_real_market_archives() -> None:
    note, cards, figure = app.run_market_optimisation(
        1, "2026-06-30", "mixed", 100, 50, 90, 90, 2.0
    )
    values = {card.children[0].children: card.children[1].children for card in cards}
    assert values["Installed design"] == "25 MW / 200 MWh"
    assert "APX market VWAP" in values
    assert "Settlement-aware value" in values
    assert "Wholesale arbitrage" in values
    assert "Co-optimised value" in values
    assert "Co-opt error reduction" in values
    assert len(figure.data) == 5
    names = [trace.name for trace in figure.data]
    assert "Elexon System Price" in names
    assert "APX Market Index Price" in names
    assert "Co-optimised residual" in names
    text = str(note)
    assert "perfect-information benchmark" in text
    assert "not an executable day-ahead trading instruction" in text
    assert "share one physical battery power limit" in text
