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


def test_pre_delivery_strategy_layer_separates_forecast_from_perfect_foresight() -> None:
    note, cards, figure = app.update_pre_delivery_strategy("2026-06-30")
    values = {card.children[0].children: card.children[1].children for card in cards}
    assert values["MAE gain vs naive"] == "11.2%"
    assert values["420-day capture"] == "60.0%"
    assert values["Reserve-aware capture"] == "49.6%"
    assert values["Locked-period capture"] == "63.4%"
    assert len(figure.data) == 3
    assert [trace.name for trace in figure.data][:2] == [
        "Realised APX MIP", "Pre-delivery price forecast"
    ]
    text = str(note)
    assert "trained only on earlier settlement dates" in text
    assert "not a licensed day-ahead auction backtest" in text


def test_pre_delivery_strategy_reports_insufficient_initial_history() -> None:
    note, cards, _figure = app.update_pre_delivery_strategy("2025-04-15")
    assert "starts after 30 prior market days" in str(note)
    assert cards == []


def test_forecast_day_market_schedule_uses_price_forecast_and_stage_b_reserve() -> None:
    note, cards, figure = app.update_forecast_market_schedule(
        "mixed", 100, 50, 90, 90, 50, 2.0
    )
    values = {card.children[0].children: card.children[1].children for card in cards}
    assert values["Installed design"] == "25 MW / 200 MWh"
    assert values["Recommended start SOC"] == "50.0%"
    assert "Reserve-aware signal value" in values
    assert "Reserve opportunity cost" in values
    assert values["Price history"] == "90 days"
    assert len(figure.data) == 6
    names = [trace.name for trace in figure.data]
    assert "Forecast APX MIP" in names
    assert "Reserve-aware schedule" in names
    assert "Reserve SOC floor" in names
    text = str(note)
    assert "as-if pre-delivery reconstruction" in text
    assert "excludes every target-day Market Index observation" in text
