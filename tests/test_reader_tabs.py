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
