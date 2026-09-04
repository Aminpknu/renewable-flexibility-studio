import app


def test_product_tabs_are_present_and_separate() -> None:
    text = str(app.app.layout)
    assert 'product-tabs' in text
    for label in ['Overview', 'Assets', 'Forecast & Risk', 'Markets', 'Investment', 'Evidence']:
        assert label in text


def test_tab_intros_use_plain_english() -> None:
    assets = str(app.update_tab_intro('assets'))
    forecast = str(app.update_tab_intro('forecast'))
    markets = str(app.update_tab_intro('markets'))
    evidence = str(app.update_tab_intro('evidence'))
    assert 'battery or renewable-plus-storage site' in assets
    assert 'what that means for reserve and state of charge' in forecast
    assert 'what is observed and what is modelled' in markets
    assert 'where a result came from' in evidence


def test_methods_guide_deeplink_opens_evidence_tab() -> None:
    assert app.open_tab_from_hash('#models-data-validation-guide') == 'evidence'
    assert app.open_tab_from_hash(None) is app.no_update


def test_methods_guide_deeplink_scrolls_after_tab_is_visible() -> None:
    source = open(app.__file__, encoding='utf-8').read()
    assert "window.location.hash === '#models-data-validation-guide'" in source
    assert "target.scrollIntoView" in source
