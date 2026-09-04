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
    text = str(note)
    if not values:
        assert "target does not match the renewable forecast target" in text
        assert len(figure.data) == 0
        return
    assert values["Installed design"] == "25 MW / 200 MWh"
    assert values["Recommended start SOC"] == "50.0%"
    assert "Reserve-aware signal value" in values
    assert "Reserve opportunity cost" in values
    assert values["Price history"] == "90 days"
    assert len(figure.data) == 6
    names = [trace.name for trace in figure.data]
    assert "Forecast APX MIP" in names and "Reserve-aware schedule" in names and "Reserve SOC floor" in names


def test_quick_reserve_layer_uses_shared_battery_and_availability_only() -> None:
    note, cards, figure = app.run_quick_reserve_stacking(
        1, "2026-06-30", "mixed", 100, 50, 90, 90, 2.0, 2
    )
    values = {card.children[0].children: card.children[1].children for card in cards}
    assert values["Installed design"] == "25 MW / 200 MWh"
    assert "Arbitrage-only value" in values
    assert "QR-only availability" in values
    assert "Firming + arbitrage" in values
    assert "Arbitrage + QR" in values
    assert "Firming + market + QR" in values
    assert "Triple-stack firming" in values
    assert "Triple independent-sum overstatement" in values
    assert "Mean PQR / NQR" in values
    names = [trace.name for trace in figure.data]
    assert "PQR clearing price" in names
    assert "NQR clearing price" in names
    assert "PQR contracted MW" in names
    assert "NQR contracted MW (shown negative)" in names
    assert "Triple-stack residual" in names
    assert "Triple-stack SOC" in names
    text = str(note)
    assert "availability only" in text
    assert "Utilisation revenue" in text
    assert "price taker" in text
    assert "not proof" in text.lower()


def test_quick_reserve_predelivery_layer_reports_signal_not_acceptance_revenue() -> None:
    note, cards, figure = app.update_quick_reserve_predelivery("2026-06-30")
    values = {card.children[0].children: card.children[1].children for card in cards}
    assert values["Forecast allocation capture"] == "93.1%"
    assert values["Naive allocation capture"] == "88.0%"
    assert "Forecast QR value" in values
    assert values["Simple bid-threshold precision"] == "28.9%"
    assert "Selected-day capture" in values
    names = [trace.name for trace in figure.data]
    assert "PQR realised clearing" in names
    assert "PQR prior-date forecast" in names
    assert "Forecast-selected PQR MW" in names
    text = str(note)
    assert "not acceptance-adjusted" in text
    assert "poor execution classifier" in text
