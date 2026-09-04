from __future__ import annotations

from pathlib import Path

import app
import manual

ROOT = Path(app.__file__).resolve().parent


def test_glossary_expands_core_abbreviations() -> None:
    core = dict(manual.CORE_TERMS)
    market = dict(manual.MARKET_TERMS)
    finance = dict(manual.FINANCE_TERMS)
    data = dict(manual.DATA_TERMS)

    assert core["BESS"].startswith("Battery Energy Storage System")
    assert core["SOC"].startswith("State of charge")
    assert core["SOH"].startswith("State of health")
    assert core["POC"].startswith("Point of Connection")
    assert market["BM"].startswith("Balancing Mechanism")
    assert market["BOD"].startswith("Bid-Offer Data")
    assert market["BOALF"].startswith("Bid-Offer Acceptance Level Flagged")
    assert finance["NPV"].startswith("Net present value")
    assert finance["DSCR"].startswith("Debt service coverage ratio")
    assert data["REPD"].startswith("Renewable Energy Planning Database")


def test_models_guide_uses_companion_definition_list_pattern() -> None:
    guide = manual.build_models_data_validation_guide(
        app.PROBABILISTIC_SUMMARY,
        app.PROBABILISTIC_COMPARISON,
        app.STAGE13_SUMMARY,
    )
    text = str(guide)
    assert "Terminology and abbreviations" in text
    assert "Battery and forecasting terminology" in text
    assert "GB market and system terminology" in text
    assert "Investment and finance terminology" in text
    assert "Data, spatial and deployment terminology" in text
    assert "guide-definition-grid" in text
    assert "National Energy System Operator" in text
    assert "Conditional value at risk" in text


def test_important_first_mentions_show_full_words() -> None:
    layout = str(app.app.layout)
    assert "Great Britain (GB)" in layout
    assert "battery energy storage system (BESS)" in layout
    assert "point of connection (POC)" in layout
    assert "Balancing Mechanism (BM) decision screen" in layout
    assert "Bid-Offer Data (BOD)" in layout
    assert "Bid-Offer Acceptance Level Flagged (BOALF)" in layout
    assert "Capital expenditure (CAPEX" in layout
    assert "Debt service coverage ratio (DSCR)" in layout


def test_tab_intros_expand_terms_before_using_short_forms() -> None:
    assets = str(app.update_tab_intro("assets"))
    forecast = str(app.update_tab_intro("forecast"))
    markets = str(app.update_tab_intro("markets"))
    investment = str(app.update_tab_intro("investment"))

    assert "battery energy storage system (BESS)" in assets
    assert "state of health (SOH)" in assets
    assert "state of charge (SOC)" in forecast
    assert "P10/P50/P90" in forecast
    assert "Balancing Mechanism (BM)" in markets
    assert "net present value (NPV)" in investment
    assert "internal rate of return (IRR)" in investment


def test_terminology_deep_link_opens_evidence_tab() -> None:
    assert app.open_tab_from_hash("#terminology-abbreviations") == "evidence"
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "#terminology-abbreviations" in source
    assert "terminology-abbreviations" in source


def test_terminology_grid_is_responsive() -> None:
    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    assert ".guide-definition-grid" in css
    assert "grid-template-columns" in css
    assert "@media (max-width: 620px)" in css
