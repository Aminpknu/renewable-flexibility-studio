from pathlib import Path

import app
from engine.quality_assurance import assure_market_investment

ROOT = Path(app.__file__).resolve().parent


def test_default_negative_npv_is_independently_reconciled() -> None:
    assumptions = app._market_investment_assumptions(25, 0.5, 15, 8, 2, 0, 0)
    scenarios = app._market_investment_scenarios(assumptions)
    case = scenarios["Forecast wholesale · 420d"]
    assurance = assure_market_investment(
        case["annual_operating_value_gbp"],
        assumptions,
        reported=case,
        daily_evidence=app.PREDELIVERY_DAILY,
    )
    assert assurance["npv_gbp"] < 0
    assert assurance["calculation_status"] == "PASS"
    assert assurance["checks_passed"] == assurance["checks_total"]
    assert assurance["minimum_annual_market_value_for_zero_npv_gbp"] > case["annual_operating_value_gbp"]


def test_investment_panel_separates_calculation_from_economic_outcome() -> None:
    note, _cards, _figure = app.update_market_backed_investment(
        "mixed", 100, 50, 90, 90, 25, 0.5, 15, 8, 2, 0, 0
    )
    text = str(note)
    assert "Calculation integrity" in text
    assert "CHECKED" in text
    assert "BELOW BREAK-EVEN" in text
    assert "Arithmetic assurance does not make this a bankable revenue forecast" in text


def test_public_metadata_and_accessibility_polish_are_present() -> None:
    assert app.app.title == "Renewable Flexibility Studio"
    assert 'name="description"' in app.app.index_string
    assert 'rel="canonical"' in app.app.index_string
    assert 'property="og:title"' in app.app.index_string

    css = (ROOT / "assets" / "styles.css").read_text(encoding="utf-8")
    assert ":focus-visible" in css
    assert "prefers-reduced-motion" in css
    assert ".model-assurance-panel" in css


def test_documentation_avoids_stale_daily_claims_and_has_unique_guide_numbers() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manual = (ROOT / "manual.py").read_text(encoding="utf-8")

    assert "current 3 September forecast" not in readme
    for number in range(1, 20):
        assert manual.count(f'_details("{number}.') == 1
    assert "Terminology and abbreviations" in manual
    assert "Battery and forecasting terminology" in manual


def test_principal_headings_are_product_facing() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")
    for old_heading in (
        "Market-backed investment case (Stage 10)",
        "Project-finance screening (Stage 12)",
        "Quantitative downside risk (Stage 6B)",
        "NESO multi-service stacking (Stage 11)",
    ):
        assert old_heading not in source
