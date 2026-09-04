from pathlib import Path
import app


def test_product_navigation_and_share_state_present():
    source = Path(app.__file__).read_text(encoding='utf-8')
    for token in ('product-tabs', 'id="overview"', 'id="assets"', 'id="forecast-risk"', 'id="markets"', 'id="investment"', 'id="evidence"', 'scenario-share-link', 'scenario-compare-store'):
        assert token in source


def test_competitive_release_sections_present():
    source = Path(app.__file__).read_text(encoding='utf-8')
    for token in ('SITE & CONNECTION', 'BALANCING MECHANISM EVIDENCE', 'PORTFOLIO', 'site-envelope-summary', 'portfolio-benchmark-summary', 'BM_BATTERY_EVIDENCE'):
        assert token in source
