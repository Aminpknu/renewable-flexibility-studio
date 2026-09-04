import app


def test_stage11_layout_and_non_bm_callback() -> None:
    layout = str(app.app.layout)
    assert "NESO multi-service stacking" in layout
    assert "multiservice-bm-input" in layout
    note, cards, figure = app.run_multiservice_stacking(
        1, "2026-04-01", "mixed", 100.0, 50.0, 90.0, 90.0, 2.0, []
    )
    labels = [card.children[0].children for card in cards]
    assert "Full multi-service stack" in labels
    assert "Dynamic Regulation" in labels
    assert "price-taker upper-bound" in str(note)
    assert any(trace.name == "Dynamic Regulation" for trace in figure.data)
    assert any(trace.name == "90-day annualised availability" for trace in figure.data)


def test_stage11_bm_toggle_changes_reference_case() -> None:
    _note, cards, figure = app.run_multiservice_stacking(
        1, "2026-04-01", "mixed", 100.0, 50.0, 90.0, 90.0, 2.0, ["bm"]
    )
    card = next(card for card in cards if card.children[0].children == "Full multi-service stack")
    assert "£4.82m/yr" in card.children[1].children
    assert any("Balancing Reserve" in str(value) for value in figure.data[-1].x)
