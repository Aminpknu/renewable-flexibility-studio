from pathlib import Path

import app


def test_reader_explanations_present() -> None:
    source = Path(app.__file__).read_text(encoding="utf-8")
    assert "def _reader_explanation" in source
    assert source.count("_reader_explanation(") >= 12
    for phrase in ("What this shows", "Why it matters", "How to read it"):
        assert phrase in source


def test_reader_explanation_style_present() -> None:
    css = (Path(app.__file__).parent / "assets" / "styles.css").read_text(encoding="utf-8")
    assert ".reader-explanation" in css
    assert "grid-template-columns" in css
