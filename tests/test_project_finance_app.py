import json

import app


def _default_args():
    return (
        "mixed", 100.0, 50.0, 90.0, 90.0,
        25.0, 0.5, 15, 8.0, 2.0,
        0, 0.0, 60.0, 6.0, 10,
        25.0, 0.0, 10, 12.0, 1.2,
    )


def test_project_finance_ui_uses_stage10_base_and_labels_stage11_upside() -> None:
    note, cards, figure = app.update_project_finance(*_default_args())
    labels = [card.children[0].children for card in cards]
    assert "Wholesale-base project NPV" in labels
    assert "Minimum DSCR" in labels
    assert "Perfect-information upper NPV" in labels
    assert "not contracted debt-service revenue" in str(note)
    assert len(figure.data) == 5


def test_project_finance_monte_carlo_ui_and_download() -> None:
    args = _default_args()
    mc = app.run_project_finance_mc_callback(
        1, *args[:10], 95.0, *args[10:], 40, 7, 20260903,
    )
    note, cards, figure, payload = mc
    assert payload["stage"] == "12_project_finance_monte_carlo"
    assert payload["summary"]["probability_dscr_breach_pct"] >= 0.0
    assert len(cards) == 8
    assert len(figure.data) == 2
    assert "Perfect-information ancillary-service upside is excluded" in str(note)

    download = app.download_project_finance(1, *args, payload)
    body = json.loads(download["content"])
    assert body["stage"] == "12_project_finance_screening"
    assert "Forecast wholesale base" in body["deterministic_scenarios"]
    assert body["monte_carlo"]["stage"] == "12_project_finance_monte_carlo"
    assert any("perfect-information" in text.lower() for text in body["boundaries"])
