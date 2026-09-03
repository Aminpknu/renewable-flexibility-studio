import app


def test_stage10_default_market_backed_view_is_populated() -> None:
    note, cards, figure = app.update_market_backed_investment(
        "mixed", 100, 50, 90, 90,
        25, 0.5, 15, 8, 2, 0, 0,
    )
    labels = [card.children[0].children for card in cards]
    assert "Market-backed NPV" in labels
    assert "Break-even operating value" in labels
    assert "QR upside NPV" in labels
    assert "prior-date APX Market Index forecasts" in str(note)
    assert len(figure.data) == 1


def test_stage10_rejects_unsupported_revenue_scaling() -> None:
    note, cards, figure = app.update_market_backed_investment(
        "mixed", 200, 50, 90, 90,
        25, 0.5, 15, 8, 2, 0, 0,
    )
    assert "frozen for the default 100 MW 50/50" in str(note)
    assert cards == []
    assert len(figure.data) == 0


def test_stage10_market_backed_monte_carlo_callback() -> None:
    note, cards, figure, payload = app.run_market_backed_monte_carlo(
        1, "mixed", 100, 50, 90, 90,
        25, 0.5, 15, 8, 2, 95, 0, 0,
        100, 7, 20260903,
    )
    labels = [card.children[0].children for card in cards]
    assert "P50 NPV" in labels
    assert "95% CVaR loss" in labels
    assert "Quick Reserve is excluded" in str(note)
    assert payload["stage"] == "10_market_backed_investment_monte_carlo"
    assert payload["scope"] == "420-day forecast-selected wholesale evidence; QR excluded"
    assert len(figure.data) == 1
